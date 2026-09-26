"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const UPLOAD_OPTION = "__upload__";
// Empty string, not a sentinel token — matches the backend's OutlineRequest
// default (""), which means "pick a template from the brief's topic" (see
// server/main.py's `_choose_template`).
const AUTO_TEMPLATE_OPTION = "";


const THINKING_PHRASES = [
  "Разбираю шаблон и паттерны слайдов…",
  "Прикидываю структуру презентации…",
  "Пишу outline по брифу…",
  "Раскладываю контент по слайдам…",
  "Подбираю формулировки для заголовков…",
  "Проверяю плотность буллетов…",
  "Почти готово…",
];

const PIPELINE_STAGES: { key: string; label: string; disabled?: boolean }[] = [
  { key: "parse", label: "Разбор шаблона" },
  { key: "digest", label: "Разбор материалов" },
  { key: "outline", label: "Генерация outline" },
  { key: "content", label: "Слайды + текст выступления" },
  { key: "layout", label: "Сборка вёрстки" },
  { key: "audit", label: "Аудит" },
];

// The generation budget from the task statement: everything after the
// context is prepared must finish within five minutes.
const GENERATION_BUDGET_SECONDS = 300;

const DURATIONS: { value: number; label: string }[] = [
  { value: 0, label: "—" },
  ...[3, 5, 7, 10, 15, 20].map((m) => ({ value: m, label: `${m} мин` })),
];

const NO_PACK_OPTION = "";
const UPLOAD_PACK_OPTION = "__upload_pack__";

// Mirrors packages/ir_schema/src/ir_schema/models.py — the pipeline's IR.
type Color = { kind: "rgb" | "theme"; rgb: string | null; theme_color: string | null };
type TextRun = {
  text: string;
  font_name: string | null;
  font_size_pt: number | null;
  bold: boolean | null;
  italic: boolean | null;
  underline: boolean | null;
  color: Color | null;
};
type Paragraph = { runs: TextRun[]; alignment: string | null; level: number };
type ShapeBase = {
  shape_id: number;
  name: string;
  z_order: number;
  left: number;
  top: number;
  width: number;
  height: number;
  rotation: number;
  is_placeholder: boolean;
  placeholder_type: string | null;
  placeholder_idx: number | null;
};
type TextBoxShape = ShapeBase & { kind: "text_box"; paragraphs: Paragraph[] };
type AutoShape = ShapeBase & { kind: "autoshape"; autoshape_type: string | null; fill_color: Color | null; paragraphs: Paragraph[] };
type PictureShape = ShapeBase & {
  kind: "picture";
  image_bytes_b64: string | null;
  content_type: string | null;
  crop_left: number;
  crop_top: number;
  crop_right: number;
  crop_bottom: number;
  attribution_text: string | null;
  attribution_url: string | null;
};
type TableCell = { paragraphs: Paragraph[] };
type TableShape = ShapeBase & { kind: "table"; rows: TableCell[][]; column_widths: number[]; row_heights: number[] };
type PassthroughShape = ShapeBase & { kind: "passthrough"; original_shape_type: string | null };
type Shape = TextBoxShape | AutoShape | PictureShape | TableShape | PassthroughShape;
type Slide = { index: number; layout_name: string; shapes: Shape[]; background: Color | null; notes: string | null };
type Deck = { slide_width: number; slide_height: number; slides: Slide[]; theme_colors: Record<string, string> };
type Finding = { check: string; kind: "deterministic"; slide_index: number; shape_id: number | null; message: string };
type VariantResult = { deck: Deck; findings: Finding[] };
type FactSheet = { project_name: string; one_liner: string } & Record<string, unknown>;
type DeckAudit = {
  compact: VariantResult;
  standard: VariantResult;
  detailed: VariantResult;
  slide_seconds: number[];
  spoken_seconds: number[];
  fact_sheet: FactSheet | null;
  timings: Record<string, number>;
};

type Density = "compact" | "standard" | "detailed";

type SlotInfo = {
  has_title: boolean;
  body_slots: number;
  card_slots: number;
  has_table: boolean;
  has_picture: boolean;
  title_font_size_pt: number | null;
  body_lines: number | null;
  body_chars_per_line: number | null;
};
type InspectedSlide = { index: number; layout_name: string; roles: Record<string, string>; slots: SlotInfo };
type InspectedTemplate = { deck: Deck; slides: InspectedSlide[] };

// role -> [outline color, Russian label, what generation does with it]
const ROLE_STYLE: Record<string, [string, string, string]> = {
  title: ["#ff5c8a", "Заголовок", "сюда пишется заголовок слайда"],
  body: ["#4da3ff", "Текст", "сюда идут пункты или абзац"],
  card: ["#3ddc97", "Карточка", "повторяющийся слот: по одному пункту в каждый"],
  table: ["#ffb020", "Таблица", "сюда встаёт таблица с данными"],
  picture: ["#b48cff", "Картинка", "фото по теме слайда (Unsplash)"],
  chrome: ["#8a8a8a", "QR / лого / ссылка", "служебный элемент — не трогаем"],
  display_accent: ["#8a8a8a", "Акцент-надпись", "крупная декоративная надпись — не трогаем"],
  data_placeholder: ["#8a8a8a", "«ХХ%» на графике", "метка данных графика — не трогаем"],
  text: ["#e0e0e0", "Прочий текст", "используется только в крайнем случае"],
};

type BrandPack = { id: string; name: string; status: "building" | "ready" | "error"; error: string | null; templates: string[] };

// What goes with a brief besides its text — see "Материалы" in the composer.
type TaskMaterials = { files: File[]; story: string };
const EMPTY_MATERIALS: TaskMaterials = { files: [], story: "" };

function hasMaterials(m: TaskMaterials): boolean {
  return m.files.length > 0 || m.story.trim() !== "";
}

function formatSeconds(total: number): string {
  const m = Math.floor(total / 60);
  const s = Math.round(total % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s} с`;
}

const VARIANTS: { key: Density; label: string }[] = [
  { key: "compact", label: "Сжато" },
  { key: "standard", label: "Стандарт" },
  { key: "detailed", label: "Подробно" },
];

// Mirrors generator.outline.MODES — see "Content modes" in
// skills/outline-generation/SKILL.md for what each one does to the writing.
const MODES: { key: string; label: string }[] = [
  { key: "", label: "Авто (по брифу)" },
  { key: "briefing", label: "Статус-отчёт" },
  { key: "narrative", label: "История / питч" },
  { key: "pyramid", label: "Выводы вперёд" },
  { key: "showcase", label: "Витрина / анонс" },
  { key: "instructional", label: "Обучение" },
];

// Best-effort keyword read of the brief's own wording — no LLM call, just
// scans for words a person would naturally use to ask for more/less detail.
// Returns null when the brief doesn't say either way, so the caller can ask
// instead of silently guessing.
function detectDensity(brief: string): Density | null {
  const text = brief.toLowerCase();
  if (/сжат|кратк|коротк|минимал/.test(text)) return "compact";
  if (/подробн|детальн|развёрнут|развернут|максимал/.test(text)) return "detailed";
  if (/стандарт|обычн|средн/.test(text)) return "standard";
  return null;
}

type Message =
  | { id: string; kind: "user"; text: string }
  | { id: string; kind: "audit"; audit: DeckAudit; density: Density }
  | { id: string; kind: "error"; text: string }
  | {
      id: string;
      kind: "density-question";
      brief: string;
      answered: Density | null;
      materials: TaskMaterials;
    };

type StageStatus = "idle" | "active" | "done" | "error";

function uid() {
  return Math.random().toString(36).slice(2);
}

type TemplateInfo = { id: string; label: string };

type ChatSession = {
  id: string;
  title: string;
  messages: Message[];
  busy: boolean;
  stages: Record<string, StageStatus>;
  // Wall-clock start of the running generation (ms), for the budget timer.
  startedAt: number | null;
};

function sessionTitle(messages: Message[]): string {
  const firstBrief = messages.find((m) => m.kind === "user")?.text ?? "Новый чат";
  return firstBrief.length > 40 ? firstBrief.slice(0, 40) + "…" : firstBrief;
}

export default function Home() {
  const [input, setInput] = useState("");
  // 0 = auto: the server derives it from the talk length (or uses 10).
  const [slideCount, setSlideCount] = useState(0);
  const [mode, setMode] = useState("");
  const [thinkingText, setThinkingText] = useState<string>(THINKING_PHRASES[0] ?? "Думаю…");
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [templateId, setTemplateId] = useState(AUTO_TEMPLATE_OPTION);
  const [inspecting, setInspecting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [packs, setPacks] = useState<BrandPack[]>([]);
  const [packId, setPackId] = useState(NO_PACK_OPTION);
  const [packError, setPackError] = useState<string | null>(null);
  const [materials, setMaterials] = useState<TaskMaterials>(EMPTY_MATERIALS);
  const [materialsOpen, setMaterialsOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const packInputRef = useRef<HTMLInputElement>(null);
  const materialsInputRef = useRef<HTMLInputElement>(null);
  // Each chat owns its own messages/busy/stages — a generation started for
  // one session writes into that session by id, never into "whatever's on
  // screen right now", so switching chats mid-generation can't bleed one
  // chat's output into another's history.
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const viewingIdRef = useRef<string | null>(null);

  useEffect(() => {
    viewingIdRef.current = viewingId;
  }, [viewingId]);

  const active = sessions.find((s) => s.id === viewingId) ?? null;
  const messages = active?.messages ?? [];
  const busy = active?.busy ?? false;
  const stages = active?.stages ?? {};

  function updateSession(id: string, updater: (s: ChatSession) => ChatSession) {
    setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }

  function appendMessage(id: string, msg: Message) {
    updateSession(id, (s) => {
      const nextMessages = [...s.messages, msg];
      const title = s.messages.length === 0 && msg.kind === "user" ? sessionTitle(nextMessages) : s.title;
      return { ...s, messages: nextMessages, title };
    });
  }

  function setSessionStage(id: string, key: string, status: StageStatus) {
    updateSession(id, (s) => ({ ...s, stages: { ...s.stages, [key]: status } }));
  }

  function refreshTemplates(selectId?: string) {
    return fetch(`${API_URL}/api/templates`)
      .then((r) => r.json())
      .then((data: { templates: TemplateInfo[] }) => {
        setTemplates(data.templates);
        if (selectId && data.templates.some((t) => t.id === selectId)) {
          setTemplateId(selectId);
        } else if (
          templateId !== AUTO_TEMPLATE_OPTION &&
          data.templates.length > 0 &&
          !data.templates.some((t) => t.id === templateId)
        ) {
          setTemplateId(data.templates[0]?.id ?? templateId);
        }
      })
      .catch(() => {
        // No API server yet, or it's down — the composer still works once
        // it comes up; the sidebar just falls back to the default id below.
      });
  }

  function refreshPacks(selectId?: string) {
    return fetch(`${API_URL}/api/brand-packs`)
      .then((r) => r.json())
      .then((data: { packs: BrandPack[] }) => {
        setPacks(data.packs);
        if (selectId) setPackId(selectId);
      })
      .catch(() => {});
  }

  useEffect(() => {
    void refreshTemplates();
    void refreshPacks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A pack builds in the background on the server (LLM extraction over its
  // documents) — poll until none is still building, then pick up its
  // templates in the template list too.
  const anyPackBuilding = packs.some((p) => p.status === "building");
  useEffect(() => {
    if (!anyPackBuilding) return;
    const interval = setInterval(() => {
      void refreshPacks().then(() => refreshTemplates());
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyPackBuilding]);

  async function handlePackUpload(file: File | undefined) {
    if (!file) return;
    setPackError(null);
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setPackError("Бренд-пакет загружается одним .zip-архивом");
      return;
    }
    const suggested = file.name.replace(/\.[^.]+$/, "");
    const name = window.prompt("Название бренд-пакета", suggested);
    if (!name) return;
    try {
      const body = new FormData();
      body.append("name", name);
      body.append("file", file);
      const res = await fetch(`${API_URL}/api/brand-packs`, { method: "POST", body });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `${res.status} ${res.statusText}`);
      }
      const { id } = (await res.json()) as BrandPack;
      await refreshPacks(id);
      await refreshTemplates();
    } catch (e) {
      setPackError(e instanceof Error ? e.message : String(e));
    }
  }

  async function uploadMaterials(m: TaskMaterials): Promise<string> {
    const body = new FormData();
    body.append("story", m.story);
    for (const f of m.files) body.append("files", f);
    const res = await fetch(`${API_URL}/api/sources`, { method: "POST", body });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? `${res.status} ${res.statusText}`);
    }
    const { id } = (await res.json()) as { id: string };
    return id;
  }

  async function handleTemplateUpload(file: File) {
    setUploadError(null);
    setUploading(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${API_URL}/api/templates`, { method: "POST", body });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `${res.status} ${res.statusText}`);
      }
      const { id } = (await res.json()) as { id: string; label: string };
      await refreshTemplates(id);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  useEffect(() => {
    if (!busy) return;
    const tick = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(tick);
  }, [busy]);

  useEffect(() => {
    if (!busy) return;
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % THINKING_PHRASES.length;
      setThinkingText(THINKING_PHRASES[i] ?? "Думаю…");
    }, 2600);
    return () => clearInterval(interval);
  }, [busy]);

  function scrollToBottom(forSessionId: string) {
    if (viewingIdRef.current !== forSessionId) return;
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  }

  async function runPipeline(
    sessionId: string,
    brief: string,
    density: Density,
    taskMaterials: TaskMaterials,
  ) {
    updateSession(sessionId, (s) => ({ ...s, busy: true, stages: {}, startedAt: Date.now() }));
    setThinkingText(THINKING_PHRASES[0] ?? "Думаю…");
    scrollToBottom(sessionId);

    let lastStage = "parse";
    setSessionStage(sessionId, lastStage, "active");
    scrollToBottom(sessionId);

    try {
      // Materials become text on the server first (no LLM, seconds); the
      // generation request then only carries the resulting id.
      const sourceId = hasMaterials(taskMaterials) ? await uploadMaterials(taskMaterials) : "";
      const res = await fetch(`${API_URL}/api/audit/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: templateId,
          brief,
          // Auto (0) lets the server derive it from the talk length; an
          // explicit count wins over that.
          slide_count: slideCount || null,
          duration_minutes: duration || null,
          mode: mode || null,
          density,
          brand_pack_id: packId,
          source_id: sourceId,
        }),
      });

      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
      }

      // Real progress from the backend: each `stage` event fires the moment
      // that stage actually starts/finishes on the server, not a guessed
      // local approximation. Stream ends with either `result` or `error`.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let audit: DeckAudit | null = null;
      let streamError: string | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let sepIndex: number;
        while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
          const rawEvent = buffer.slice(0, sepIndex);
          buffer = buffer.slice(sepIndex + 2);

          let eventName = "message";
          let data = "";
          for (const line of rawEvent.split("\n")) {
            if (line.startsWith("event: ")) eventName = line.slice(7);
            else if (line.startsWith("data: ")) data += line.slice(6);
          }
          if (!data) continue;
          const payload = JSON.parse(data);

          if (eventName === "stage") {
            lastStage = payload.stage;
            setSessionStage(sessionId, payload.stage, payload.status);
            scrollToBottom(sessionId);
          } else if (eventName === "result") {
            audit = payload as DeckAudit;
          } else if (eventName === "error") {
            streamError = payload.detail ?? "unknown error";
          }
        }
      }

      if (streamError) throw new Error(streamError);
      if (!audit) throw new Error("stream ended without a result");

      appendMessage(sessionId, { id: uid(), kind: "audit", audit, density });
    } catch (e) {
      setSessionStage(sessionId, lastStage, "error");
      appendMessage(sessionId, {
        id: uid(),
        kind: "error",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      updateSession(sessionId, (s) => ({ ...s, busy: false }));
      scrollToBottom(sessionId);
    }
  }

  function ensureSession(): string {
    let id = viewingId;
    if (!id) {
      id = uid();
      setSessions((prev) => [
        { id: id!, title: "Новый чат", messages: [], busy: false, stages: {}, startedAt: null },
        ...prev,
      ]);
      setViewingId(id);
    }
    return id;
  }

  function handleSend() {
    const brief = input.trim();
    if (!brief || busy) return;
    setInput("");
    const taskMaterials = materials;
    setMaterials(EMPTY_MATERIALS);
    setMaterialsOpen(false);
    const id = ensureSession();
    const attached = [
      ...taskMaterials.files.map((f) => f.name),
      ...(taskMaterials.story.trim() ? ["история команды"] : []),
    ];
    appendMessage(id, {
      id: uid(),
      kind: "user",
      text: attached.length ? `${brief}\n\n📎 ${attached.join(", ")}` : brief,
    });

    const density = detectDensity(brief);
    if (density) {
      void runPipeline(id, brief, density, taskMaterials);
      return;
    }
    appendMessage(id, {
      id: uid(),
      kind: "density-question",
      brief,
      answered: null,
      materials: taskMaterials,
    });
  }

  function handleDensityAnswer(
    sessionId: string,
    questionId: string,
    brief: string,
    density: Density,
    taskMaterials: TaskMaterials,
  ) {
    const label = VARIANTS.find((v) => v.key === density)?.label ?? density;
    updateSession(sessionId, (s) => ({
      ...s,
      messages: s.messages.flatMap((m) =>
        m.id === questionId && m.kind === "density-question"
          ? [{ ...m, answered: density }, { id: uid(), kind: "user" as const, text: label }]
          : [m],
      ),
    }));
    void runPipeline(sessionId, brief, density, taskMaterials);
  }

  const isEmpty = messages.length === 0;
  const lastAudit = [...messages].reverse().find((m) => m.kind === "audit");
  const lastTotal = lastAudit?.kind === "audit" ? lastAudit.audit.timings?.total ?? null : null;

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--background)" }}>
      {/* Sidebar */}
      <aside
        style={{
          width: 220,
          borderRight: "1px solid var(--border)",
          padding: "1.25rem 1rem",
          display: "flex",
          flexDirection: "column",
          gap: "1.5rem",
          flexShrink: 0,
          overflowY: "auto",
        }}
      >
        <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>project-preza</div>
        <button
          onClick={() => setViewingId(null)}
          style={{
            background: "#151515",
            color: "var(--foreground)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "0.5rem 0.75rem",
            fontSize: "0.85rem",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          + Новая сессия
        </button>
        <div>
          <div style={{ fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
            Бренд-пакет
          </div>
          <select
            value={packId}
            onChange={(e) => {
              if (e.target.value === UPLOAD_PACK_OPTION) {
                packInputRef.current?.click();
                return;
              }
              setPackId(e.target.value);
              // A pack brings its own template — let the server pick it.
              setTemplateId(AUTO_TEMPLATE_OPTION);
            }}
            disabled={busy}
            style={{
              width: "100%",
              background: "#151515",
              color: "var(--foreground)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "0.4rem 0.5rem",
              fontSize: "0.8rem",
              cursor: busy ? "default" : "pointer",
            }}
          >
            <option value={NO_PACK_OPTION}>Без пакета</option>
            {packs.map((p) => (
              <option key={p.id} value={p.id} disabled={p.status !== "ready"}>
                {p.name}
                {p.status === "building" ? " — собирается…" : p.status === "error" ? " — ошибка" : ""}
              </option>
            ))}
            <option value={UPLOAD_PACK_OPTION}>+ Загрузить контент-пакет (.zip)…</option>
          </select>
          <input
            ref={packInputRef}
            type="file"
            accept=".zip"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              void handlePackUpload(file);
            }}
            style={{ display: "none" }}
          />
          <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: "0.3rem", lineHeight: 1.35 }}>
            {anyPackBuilding
              ? "Пакет собирается: извлекаем стиль, термины и структуру…"
              : "Один .zip: шаблоны, брендбук, логотипы, шрифты — загружается заранее."}
          </div>
          {packError && (
            <div style={{ fontSize: "0.72rem", color: "#ff8080", marginTop: "0.3rem" }}>{packError}</div>
          )}
        </div>
        <div>
          <div style={{ fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
            Шаблон
          </div>
          <select
            value={templateId}
            onChange={(e) => {
              if (e.target.value === UPLOAD_OPTION) {
                fileInputRef.current?.click();
                return;
              }
              setTemplateId(e.target.value);
            }}
            disabled={busy || uploading}
            style={{
              width: "100%",
              background: "#151515",
              color: "var(--foreground)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "0.4rem 0.5rem",
              fontSize: "0.8rem",
              cursor: busy || uploading ? "default" : "pointer",
            }}
          >
            <option value={AUTO_TEMPLATE_OPTION}>
              {packId ? "Из бренд-пакета" : "Авто (по теме брифа)"}
            </option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}.pptx
              </option>
            ))}
            <option value={UPLOAD_OPTION}>
              {uploading ? "Загрузка…" : "+ Загрузить свой шаблон…"}
            </option>
          </select>
          {templateId && templateId !== UPLOAD_OPTION && (
            <button
              onClick={() => setInspecting(true)}
              style={{
                marginTop: "0.4rem",
                width: "100%",
                background: "transparent",
                border: "1px solid var(--border)",
                borderRadius: 6,
                color: "var(--foreground)",
                padding: "0.3rem 0.5rem",
                fontSize: "0.75rem",
                cursor: "pointer",
              }}
            >
              🔍 Посмотреть структуру шаблона
            </button>
          )}
          {inspecting && templateId && (
            <TemplateInspector templateId={templateId} onClose={() => setInspecting(false)} />
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pptx"
            disabled={uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void handleTemplateUpload(file);
            }}
            style={{ display: "none" }}
          />
          {uploadError && (
            <div style={{ fontSize: "0.72rem", color: "#ff8080", marginTop: "0.3rem" }}>{uploadError}</div>
          )}
        </div>
        <div>
          <div style={{ fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
            История запросов
          </div>
          {sessions.length === 0 ? (
            <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Пока пусто</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setViewingId(s.id)}
                  style={{
                    background: s.id === viewingId ? "#1d1d1d" : "transparent",
                    color: "var(--foreground)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "0.4rem 0.55rem",
                    fontSize: "0.78rem",
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  {s.title}
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* Main chat column */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "2rem" }}>
          {isEmpty ? (
            <div style={{ maxWidth: 640, margin: "4rem auto 0" }}>
              <h1 style={{ fontSize: "1.6rem", marginBottom: "0.5rem" }}>О чём должна быть презентация?</h1>
              <p style={{ color: "var(--muted)", marginBottom: "2rem" }}>
                Заранее загрузи бренд-пакет слева: шаблоны, брендбук, логотипы.
                Потом приложи материалы задачи (репозиторий, документацию, историю
                команды), выбери длительность выступления и опиши повод. На выходе —
                слайды в стиле бренда и текст выступления к каждому.
              </p>
            </div>
          ) : (
            <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>
              {messages.map((m) => (
                <MessageView
                  key={m.id}
                  message={m}
                  onAnswerDensity={
                    m.kind === "density-question"
                      ? (density) => handleDensityAnswer(active!.id, m.id, m.brief, density, m.materials)
                      : undefined
                  }
                />
              ))}
              {busy && <ThinkingBubble text={thinkingText} />}
            </div>
          )}
        </div>

        {/* Composer */}
        <div style={{ borderTop: "1px solid var(--border)", padding: "1rem 2rem" }}>
          <div style={{ maxWidth: 720, margin: "0 auto" }}>
            <MaterialsPanel
              open={materialsOpen}
              onToggle={() => setMaterialsOpen((o) => !o)}
              materials={materials}
              onChange={setMaterials}
              onPickFiles={() => materialsInputRef.current?.click()}
              disabled={busy}
            />
            <input
              ref={materialsInputRef}
              type="file"
              multiple
              accept=".zip,.md,.txt,.pdf,.docx,.pptx,.rst,.csv"
              onChange={(e) => {
                const picked = Array.from(e.target.files ?? []);
                e.target.value = "";
                setMaterials((m) => ({ ...m, files: [...m.files, ...picked] }));
              }}
              style={{ display: "none" }}
            />
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                background: "#151515",
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: "0.6rem",
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "0.25rem",
                  padding: "0 0.75rem 0 0.15rem",
                  borderRight: "1px solid var(--border)",
                  flexShrink: 0,
                }}
              >
                <span style={{ fontSize: "0.68rem", color: "var(--muted)", whiteSpace: "nowrap" }}>выступление</span>
                <select
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  title="Длительность выступления: задаёт число слайдов и объём текста к каждому"
                  style={{
                    width: 72,
                    background: "#0a0a0a",
                    color: "var(--foreground)",
                    border: "1px solid var(--border)",
                    borderRadius: 4,
                    padding: "0.15rem",
                    textAlign: "center",
                    fontSize: "0.72rem",
                  }}
                >
                  {DURATIONS.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "0.25rem",
                  padding: "0 0.75rem 0 0.15rem",
                  borderRight: "1px solid var(--border)",
                  flexShrink: 0,
                }}
              >
                <span style={{ fontSize: "0.68rem", color: "var(--muted)", whiteSpace: "nowrap" }}>слайдов</span>
                <select
                  value={slideCount}
                  title="Авто — по длительности выступления (без неё — 10)"
                  onChange={(e) => setSlideCount(Number(e.target.value))}
                  style={{
                    width: 60,
                    background: "#0a0a0a",
                    color: "var(--foreground)",
                    border: "1px solid var(--border)",
                    borderRadius: 4,
                    padding: "0.15rem",
                    textAlign: "center",
                  }}
                >
                  <option value={0}>авто</option>
                  {Array.from({ length: 15 }, (_, i) => i + 1).map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "0.25rem",
                  padding: "0 0.75rem 0 0.15rem",
                  borderRight: "1px solid var(--border)",
                  flexShrink: 0,
                }}
              >
                <span style={{ fontSize: "0.68rem", color: "var(--muted)", whiteSpace: "nowrap" }}>режим</span>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  style={{
                    width: 110,
                    background: "#0a0a0a",
                    color: "var(--foreground)",
                    border: "1px solid var(--border)",
                    borderRadius: 4,
                    padding: "0.15rem",
                    textAlign: "center",
                    fontSize: "0.72rem",
                  }}
                >
                  {MODES.map((m) => (
                    <option key={m.key} value={m.key}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={
                  hasMaterials(materials)
                    ? "Что за выступление? Например: финал хакатона, жюри, 7 минут"
                    : "Опиши, какую презентацию хочешь…"
                }
                rows={2}
                style={{
                  flex: 1,
                  minWidth: 0,
                  resize: "none",
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  color: "var(--foreground)",
                  fontFamily: "inherit",
                  fontSize: "0.9rem",
                }}
              />
              <div style={{ display: "flex", alignItems: "flex-end" }}>
                <button
                  onClick={handleSend}
                  disabled={busy || !input.trim()}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    minWidth: 84,
                    background: busy || !input.trim() ? "#333" : "#ededed",
                    color: busy || !input.trim() ? "var(--muted)" : "#0a0a0a",
                    border: "none",
                    borderRadius: 6,
                    padding: "0.5rem 1rem",
                    fontWeight: 600,
                    fontSize: "0.85rem",
                    cursor: busy || !input.trim() ? "default" : "pointer",
                  }}
                >
                  {busy ? (
                    <span style={{ display: "flex", gap: "4px" }}>
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          style={{
                            width: 5,
                            height: 5,
                            borderRadius: "50%",
                            background: "var(--muted)",
                            animation: "dot-blink 1.2s infinite",
                            animationDelay: `${i * 0.15}s`,
                          }}
                        />
                      ))}
                    </span>
                  ) : (
                    "Отправить"
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Right panel: pipeline progress */}
      <aside
        style={{
          width: 240,
          borderLeft: "1px solid var(--border)",
          padding: "1.25rem 1rem",
          flexShrink: 0,
        }}
      >
        <div style={{ fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.75rem" }}>
          Пайплайн
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {PIPELINE_STAGES.map((s) => {
            const status: StageStatus = s.disabled ? "idle" : stages[s.key] ?? "idle";
            return (
              <div key={s.key} style={{ display: "flex", alignItems: "center", gap: "0.5rem", opacity: s.disabled ? 0.4 : 1 }}>
                <StageDot status={status} />
                <span style={{ fontSize: "0.82rem" }}>{s.label}</span>
              </div>
            );
          })}
        </div>
        <BudgetTimer
          busy={busy}
          startedAt={active?.startedAt ?? null}
          now={now}
          lastTotal={lastTotal}
        />
        <div style={{ marginTop: "2rem", fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
          Модель
        </div>
        {/* Static label, not read from the backend — keep in sync with the
            model + fallback_models in each skill's config.yaml. */}
        <div style={{ fontSize: "0.78rem", color: "var(--muted)", lineHeight: 1.4 }}>
          qwen3-30b-a3b через OpenRouter; без баланса — цепочка бесплатных (qwen3.8, gemma-4, glm-5.2, nemotron)
        </div>
      </aside>
    </div>
  );
}

function MaterialsPanel({
  open,
  onToggle,
  materials,
  onChange,
  onPickFiles,
  disabled,
}: {
  open: boolean;
  onToggle: () => void;
  materials: TaskMaterials;
  onChange: (m: TaskMaterials) => void;
  onPickFiles: () => void;
  disabled: boolean;
}) {
  const count =
    materials.files.length +
    (materials.story.trim() ? 1 : 0);
  const field = {
    width: "100%",
    background: "#0a0a0a",
    color: "var(--foreground)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "0.4rem 0.5rem",
    fontFamily: "inherit",
    fontSize: "0.8rem",
  } as const;
  return (
    <div style={{ marginBottom: "0.5rem" }}>
      <button
        onClick={onToggle}
        disabled={disabled}
        style={{
          background: "transparent",
          color: count ? "var(--foreground)" : "var(--muted)",
          border: "none",
          padding: 0,
          fontSize: "0.78rem",
          cursor: disabled ? "default" : "pointer",
        }}
      >
        {open ? "▾" : "▸"} Материалы задачи{count ? ` (${count})` : ""} — репозиторий (.zip), документация, история
      </button>
      {open && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            marginTop: "0.5rem",
            padding: "0.75rem",
            border: "1px solid var(--border)",
            borderRadius: 10,
            background: "#111",
          }}
        >
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <button
              onClick={onPickFiles}
              disabled={disabled}
              style={{
                background: "#1d1d1d",
                color: "var(--foreground)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.35rem 0.7rem",
                fontSize: "0.78rem",
                cursor: "pointer",
              }}
            >
              + Файлы (.zip репозитория, .md, .pdf, .docx, .pptx)
            </button>
            {materials.files.map((f, i) => (
              <span
                key={`${f.name}-${i}`}
                style={{
                  fontSize: "0.72rem",
                  border: "1px solid var(--border)",
                  borderRadius: 999,
                  padding: "0.15rem 0.5rem",
                  display: "flex",
                  gap: "0.35rem",
                  alignItems: "center",
                }}
              >
                {f.name}
                <button
                  onClick={() => onChange({ ...materials, files: materials.files.filter((_, j) => j !== i) })}
                  aria-label={`Убрать ${f.name}`}
                  style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", padding: 0 }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
          <textarea
            value={materials.story}
            onChange={(e) => onChange({ ...materials, story: e.target.value })}
            placeholder="История команды: кто вы, как пришли к решению, что пробовали и что не сработало, чем гордитесь"
            rows={3}
            style={{ ...field, resize: "vertical" }}
          />
        </div>
      )}
    </div>
  );
}

function BudgetTimer({
  busy,
  startedAt,
  now,
  lastTotal,
}: {
  busy: boolean;
  startedAt: number | null;
  now: number;
  lastTotal: number | null;
}) {
  const elapsed = busy && startedAt ? (now - startedAt) / 1000 : lastTotal;
  if (elapsed === null) return null;
  const share = Math.min(1, elapsed / GENERATION_BUDGET_SECONDS);
  const over = elapsed > GENERATION_BUDGET_SECONDS;
  return (
    <div style={{ marginTop: "1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.3rem" }}>
        <span style={{ color: "var(--muted)" }}>{busy ? "Идёт генерация" : "Сгенерировано за"}</span>
        <span style={{ color: over ? "#f87171" : "var(--foreground)" }}>
          {formatSeconds(elapsed)} / {formatSeconds(GENERATION_BUDGET_SECONDS)}
        </span>
      </div>
      <div style={{ height: 4, background: "#222", borderRadius: 2, overflow: "hidden" }}>
        <div
          style={{
            width: `${share * 100}%`,
            height: "100%",
            background: over ? "#f87171" : "#4ade80",
            transition: "width 0.5s linear",
          }}
        />
      </div>
    </div>
  );
}

function StageDot({ status }: { status: StageStatus }) {
  const color = { idle: "#333", active: "#e8c547", done: "#4ade80", error: "#f87171" }[status];
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
        animation: status === "active" ? "pulse-ring 1.4s ease-out infinite" : "none",
      }}
    />
  );
}

function ThinkingBubble({ text }: { text: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "0.75rem 1rem",
        background: "#111",
        width: "fit-content",
      }}
    >
      <span style={{ display: "flex", gap: "3px" }}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 5,
              height: 5,
              borderRadius: "50%",
              background: "#e8c547",
              animation: "dot-blink 1.2s infinite",
              animationDelay: `${i * 0.15}s`,
            }}
          />
        ))}
      </span>
      <span
        style={{
          fontSize: "0.82rem",
          background:
            "linear-gradient(90deg, var(--muted) 40%, var(--foreground) 50%, var(--muted) 60%)",
          backgroundSize: "200% auto",
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          color: "transparent",
          animation: "shimmer 2.2s linear infinite",
        }}
      >
        {text}
      </span>
    </div>
  );
}

function DensityQuestion({
  answered,
  onPick,
}: {
  answered: Density | null;
  onPick: (density: Density) => void;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "1rem",
        background: "#111",
        width: "fit-content",
      }}
    >
      <div style={{ fontSize: "0.85rem", marginBottom: answered ? 0 : "0.75rem" }}>
        Насколько подробной должна быть презентация?
      </div>
      {!answered && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {VARIANTS.map((v) => (
            <button
              key={v.key}
              onClick={() => onPick(v.key)}
              style={{
                background: "#1d1d1d",
                color: "var(--foreground)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.4rem 0.8rem",
                fontSize: "0.82rem",
                cursor: "pointer",
              }}
            >
              {v.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

type PreviewStatus = "loading" | "ready" | "unavailable" | "error";

// The exported .pptx rendered to images by the server (LibreOffice) — the
// only preview that matches the downloaded file: backgrounds, master art,
// theme colours and charts the in-browser drawing can't reproduce.
function useDeckPreview(deck: Deck | null): { images: string[] | null; status: PreviewStatus } {
  const [state, setState] = useState<{ images: string[] | null; status: PreviewStatus }>({
    images: null,
    status: "loading",
  });
  useEffect(() => {
    if (!deck) return;
    let cancelled = false;
    setState({ images: null, status: "loading" });
    fetch(`${API_URL}/api/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(deck),
    })
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 501) return setState({ images: null, status: "unavailable" });
        if (!res.ok) return setState({ images: null, status: "error" });
        const data = (await res.json()) as { slides: string[] };
        if (!cancelled) setState({ images: data.slides, status: "ready" });
      })
      .catch(() => !cancelled && setState({ images: null, status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [deck]);
  return state;
}

function SlidePreview({
  image,
  status,
  slide,
  deck,
  width,
}: {
  image: string | undefined;
  status: PreviewStatus;
  slide: Slide;
  deck: Deck;
  width: number;
}) {
  if (image) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={image}
        alt=""
        style={{ width, display: "block", borderRadius: 4 }}
      />
    );
  }
  return (
    <div style={{ position: "relative", width }}>
      <SlideCanvas
        slide={slide}
        slideWidth={deck.slide_width}
        slideHeight={deck.slide_height}
        width={width}
        themeColors={deck.theme_colors}
      />
      {status === "loading" && (
        <span
          style={{
            position: "absolute",
            right: 6,
            bottom: 6,
            fontSize: "0.65rem",
            background: "rgba(0,0,0,0.65)",
            color: "#fff",
            borderRadius: 4,
            padding: "2px 6px",
          }}
        >
          рендер .pptx…
        </span>
      )}
    </div>
  );
}

function MessageView({
  message,
  onAnswerDensity,
}: {
  message: Message;
  onAnswerDensity?: (density: Density) => void;
}) {
  // Hooks can't follow an early return (Rules of Hooks) — called
  // unconditionally here even though only the "audit" branch uses it.
  const [zoomedSlide, setZoomedSlide] = useState<number | null>(null);
  const previewDeck = message.kind === "audit" ? message.audit[message.density].deck : null;
  const preview = useDeckPreview(previewDeck);

  if (message.kind === "density-question") {
    return (
      <DensityQuestion answered={message.answered} onPick={(d) => onAnswerDensity?.(d)} />
    );
  }

  if (message.kind === "user") {
    return (
      <div style={{ alignSelf: "flex-end", maxWidth: "85%", marginLeft: "auto" }}>
        <div
          style={{
            background: "#1d1d1d",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "0.75rem 1rem",
            fontSize: "0.9rem",
          }}
        >
          {message.text}
        </div>
      </div>
    );
  }

  if (message.kind === "error") {
    return (
      <div
        style={{
          border: "1px solid #7a2020",
          background: "#2a1010",
          borderRadius: 8,
          padding: "0.75rem 1rem",
          color: "#ff8080",
          fontSize: "0.85rem",
        }}
      >
        {message.text}
      </div>
    );
  }

  const { audit, density } = message;
  const { deck, findings } = audit[density];
  const slideCount = deck.slides.length;
  const densityLabel = VARIANTS.find((v) => v.key === density)?.label ?? density;
  const planned = audit.slide_seconds ?? [];
  const spoken = audit.spoken_seconds ?? [];
  const spokenTotal = spoken.reduce((a, b) => a + b, 0);
  const plannedTotal = planned.reduce((a, b) => a + b, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
          {slideCount} слайдов · плотность: {densityLabel} · {findings.length} находок аудита
          {audit.timings?.total !== undefined && <> · готово за {formatSeconds(audit.timings.total)}</>}
          {spokenTotal > 0 && (
            <>
              {" "}
              · речь ≈ {formatSeconds(spokenTotal)}
              {plannedTotal > 0 && <> из {formatSeconds(plannedTotal)}</>}
            </>
          )}
        </div>
        <ExportButton deck={deck} />
      </div>
      {audit.fact_sheet?.one_liner && (
        <div style={{ fontSize: "0.78rem", color: "var(--muted)", borderLeft: "2px solid var(--border)", paddingLeft: "0.6rem" }}>
          Из материалов: {audit.fact_sheet.one_liner}
        </div>
      )}
      {deck.slides.map((slide, i) => {
        const slideFindings = findings.filter((f) => f.slide_index === i);
        return (
          <div
            key={i}
            onClick={() => setZoomedSlide(i)}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "1rem",
              background: "#111",
              cursor: "pointer",
              width: "fit-content",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.6rem" }}>
              <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>
                Слайд {i + 1}
                {planned[i] ? ` · ${formatSeconds(planned[i]!)}` : ""}
              </span>
              <span style={{ fontSize: "0.68rem", color: "var(--muted)", textTransform: "uppercase" }}>
                {slide.layout_name}
              </span>
            </div>
            <SlidePreview
              image={preview.images?.[i]}
              status={preview.status}
              slide={slide}
              deck={deck}
              width={400}
            />
            {slideFindings.length > 0 && (
              <div
                title={slideFindings.map((f) => f.message).join("\n")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.25rem",
                  fontSize: "0.68rem",
                  color: "#f0b84a",
                  marginTop: "0.4rem",
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#f0b84a", flexShrink: 0 }} />
                {slideFindings.length} находк{slideFindings.length === 1 ? "а" : "и"}
              </div>
            )}
            {slide.notes && (
              <div
                onClick={(e) => e.stopPropagation()}
                style={{
                  maxWidth: 400,
                  marginTop: "0.6rem",
                  paddingTop: "0.5rem",
                  borderTop: "1px solid var(--border)",
                  fontSize: "0.78rem",
                  lineHeight: 1.45,
                  cursor: "text",
                }}
              >
                <div style={{ fontSize: "0.66rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.25rem" }}>
                  Текст выступления{spoken[i] ? ` · ≈ ${formatSeconds(spoken[i]!)}` : ""}
                </div>
                {slide.notes}
              </div>
            )}
          </div>
        );
      })}
      {zoomedSlide !== null && (
        <SlideZoomModal
          audit={audit}
          slideIndex={zoomedSlide}
          variantKey={density}
          image={preview.images?.[zoomedSlide]}
          status={preview.status}
          onClose={() => setZoomedSlide(null)}
        />
      )}
    </div>
  );
}

function ExportButton({ deck }: { deck: Deck }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  async function download() {
    setState("busy");
    try {
      const res = await fetch(`${API_URL}/api/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(deck),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "presentation.pptx";
      a.click();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("error");
    }
  }
  return (
    <button
      onClick={download}
      disabled={state === "busy"}
      style={{
        background: "#ededed",
        color: "#0a0a0a",
        border: "none",
        borderRadius: 6,
        padding: "0.3rem 0.7rem",
        fontSize: "0.75rem",
        fontWeight: 600,
        cursor: state === "busy" ? "default" : "pointer",
      }}
    >
      {state === "busy" ? "Экспорт…" : state === "error" ? "Ошибка — ещё раз" : "Скачать .pptx с текстом"}
    </button>
  );
}

function SlideZoomModal({
  audit,
  slideIndex,
  variantKey,
  image,
  status,
  onClose,
}: {
  audit: DeckAudit;
  slideIndex: number;
  variantKey: Density;
  image: string | undefined;
  status: PreviewStatus;
  onClose: () => void;
}) {
  const { deck } = audit[variantKey];
  const slide = deck.slides[slideIndex];
  const variantLabel = VARIANTS.find((v) => v.key === variantKey)?.label ?? variantKey;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (!slide) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.75)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
        padding: "2rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
          maxWidth: "90vw",
          maxHeight: "90vh",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--foreground)" }}>
            Слайд {slideIndex + 1} · {variantLabel} · {slide.layout_name}
          </span>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: 6,
              color: "var(--foreground)",
              padding: "0.25rem 0.6rem",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            Закрыть ✕
          </button>
        </div>
        <SlidePreview image={image} status={status} slide={slide} deck={deck} width={800} />
      </div>
    </div>
  );
}

// EMU is PowerPoint's base unit (914400 per inch). Font sizes are in points;
// 1pt = 12700 EMU. The renderer scales EMU geometry to pixels by a single
// factor and derives px-per-point from it, so coordinates and font sizes stay
// in one consistent scaled space.
const EMU_PER_PT = 12700;

function runText(runs: TextRun[]): string {
  return runs.map((r) => r.text).join("");
}

// A run/shape frequently has no explicit color — PowerPoint would resolve it
// from the placeholder's own style, which the IR doesn't carry. A fixed dark
// fallback looked fine against the (accidentally always-white) test template,
// but is invisible on a template with a genuinely dark slide background — so
// the fallback text color tracks the resolved slide background's luminance.
function readableTextColor(bgHex: string): string {
  const clean = bgHex.replace("#", "");
  if (clean.length !== 6) return "#1a1a1a";
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? "#1a1a1a" : "#f5f5f5";
}

function colorToCss(
  color: Color | null | undefined,
  fallback: string,
  themeColors: Record<string, string> = {},
): string {
  if (color?.kind === "rgb" && color.rgb) return `#${color.rgb}`;
  if (color?.kind === "theme" && color.theme_color) {
    const hex = themeColors[color.theme_color];
    if (hex) return `#${hex}`;
  }
  return fallback;
}

// A real photo could be light or dark; we don't have it, only a
// placeholder. Guess which shade this slide needs from whichever text
// overlaps the shape: light run colors mean the real image is meant to be
// dark behind them (a photo), so a light placeholder would hide that text —
// pick the placeholder shade that keeps it legible instead of defaulting
// to one fixed tone.
function imagePlaceholderStyle(
  shape: Shape,
  slide: Slide,
  themeColors: Record<string, string>,
): React.CSSProperties {
  const overlapping = slide.shapes.filter(
    (s) =>
      (s.kind === "text_box" || s.kind === "autoshape") &&
      s.left < shape.left + shape.width &&
      s.left + s.width > shape.left &&
      s.top < shape.top + shape.height &&
      s.top + s.height > shape.top,
  );
  let lightRuns = 0;
  let darkRuns = 0;
  for (const s of overlapping) {
    if (s.kind !== "text_box" && s.kind !== "autoshape") continue;
    for (const p of s.paragraphs) {
      for (const r of p.runs) {
        if (!r.text.trim()) continue;
        const css = colorToCss(r.color, "", themeColors);
        const hex = css.startsWith("#") ? css.slice(1) : "";
        if (hex.length !== 6) continue;
        const lum =
          (0.299 * parseInt(hex.slice(0, 2), 16) +
            0.587 * parseInt(hex.slice(2, 4), 16) +
            0.114 * parseInt(hex.slice(4, 6), 16)) /
          255;
        if (lum > 0.6) lightRuns++;
        else if (lum < 0.4) darkRuns++;
      }
    }
  }
  const needsDarkPlaceholder = lightRuns > darkRuns;
  return {
    background: needsDarkPlaceholder
      ? "linear-gradient(135deg, #4a4a4a, #2b2b2b)"
      : "linear-gradient(135deg, #ececec, #dcdcdc)",
    border: "1px solid rgba(0,0,0,0.08)",
  };
}

function alignToCss(alignment: string | null): "left" | "center" | "right" {
  const a = alignment?.toLowerCase() ?? "";
  if (a.startsWith("center")) return "center";
  if (a.startsWith("right")) return "right";
  return "left";
}

// PowerPoint shrinks text to fit its placeholder ("Shrink text on overflow").
// The IR carries no such flag, and a fixed font size clips long generated
// titles mid-line (the box is sized for the template's shorter copy). So we
// measure the rendered text against its box and scale it down to fit. Reading
// scrollHeight/scrollWidth (layout metrics, unaffected by CSS transforms) keeps
// the measurement stable across scale changes, so there is no oscillation.
function AutoFitText({
  shape,
  ptPx,
  themeColors,
  defaultColor,
  groupKey,
  sharedScale,
  onMeasured,
}: {
  shape: TextBoxShape | AutoShape;
  ptPx: number;
  themeColors: Record<string, string>;
  defaultColor: string;
  // Card/column groups (see SlideCanvas) must render at one shared font
  // size — a set of "parallel" cards where one happens to hold more text
  // looking visibly smaller than its siblings reads as broken, not as a
  // feature (confirmed live: two same-size cards independently scaled to
  // 1.0 and 0.52, same font, same box — jarring next to each other). Ungrouped
  // shapes (title, single body box, ...) still fit independently.
  groupKey?: string;
  sharedScale?: number;
  onMeasured?: (groupKey: string, neededScale: number) => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [localScale, setLocalScale] = useState(1);
  const textKey = shape.paragraphs.map((p) => p.runs.map((r) => r.text).join("")).join("|");

  useLayoutEffect(() => {
    const box = boxRef.current;
    const inner = innerRef.current;
    if (!box || !inner) return;
    const bh = box.clientHeight;
    const bw = box.clientWidth;
    const ih = inner.scrollHeight;
    const iw = inner.scrollWidth;
    if (bh <= 0 || bw <= 0 || ih <= 0 || iw <= 0) return;
    const needed = ih > bh || iw > bw ? Math.max(0.3, Math.min(bh / ih, bw / iw, 1)) : 1;
    setLocalScale((prev) => (Math.abs(prev - needed) > 0.01 ? needed : prev));
    if (groupKey && onMeasured) onMeasured(groupKey, needed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textKey, ptPx]);

  const scale = groupKey ? (sharedScale ?? localScale) : localScale;

  return (
    <div
      ref={boxRef}
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <div ref={innerRef} style={{ width: "100%", transform: `scale(${scale})`, transformOrigin: "center center" }}>
        {shape.paragraphs.map((p, pi) => (
          <div
            key={pi}
            style={{
              textAlign: alignToCss(p.alignment),
              paddingLeft: `${p.level * ptPx * 20}px`,
              lineHeight: 1.3,
              margin: 0,
            }}
          >
            {p.runs.length === 0 ? " " : null}
            {p.runs.map((r, ri) => (
              <span
                key={ri}
                style={{
                  fontSize: `${(r.font_size_pt ?? 14) * ptPx}px`,
                  fontWeight: r.bold ? 700 : 400,
                  fontStyle: r.italic ? "italic" : "normal",
                  textDecoration: r.underline ? "underline" : "none",
                  color: colorToCss(r.color, defaultColor, themeColors),
                  fontFamily: r.font_name ? `"${r.font_name}", sans-serif` : "inherit",
                }}
              >
                {r.text}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// Renders the template's own embedded photo/3D-render/illustration — parser
// extracts real image bytes for every Picture shape (confirmed live: 100%
// across every real sample template), so a template with genuine photography
// or custom art (like the polished decks this should look like) already has
// it; the only thing missing was actually drawing it instead of a flat gray
// placeholder box. Crop fractions (PowerPoint's own image cropping) are
// honored by rendering the image oversized and shifted within an
// overflow:hidden box, matching how PowerPoint itself crops in place.
function UnsplashAttribution({ shape }: { shape: PictureShape }) {
  if (!shape.attribution_text) return null;
  return (
    <a
      href={shape.attribution_url ?? undefined}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        position: "absolute",
        bottom: 2,
        right: 4,
        fontSize: 8,
        lineHeight: 1.2,
        color: "rgba(255,255,255,0.85)",
        background: "rgba(0,0,0,0.45)",
        padding: "1px 4px",
        borderRadius: 2,
        textDecoration: "none",
        pointerEvents: "auto",
        zIndex: 1,
      }}
    >
      {shape.attribution_text}
    </a>
  );
}

function SlidePicture({ shape }: { shape: PictureShape }) {
  if (!shape.image_bytes_b64) {
    // No embedded bytes (e.g. an external/linked image the parser couldn't
    // inline) — a plain placeholder is honest here, nothing to render.
    return <div style={{ width: "100%", height: "100%", background: "linear-gradient(135deg, #2a2a2a, #1a1a1a)" }} />;
  }
  const mime = shape.content_type || "image/png";
  const src = `data:${mime};base64,${shape.image_bytes_b64}`;
  const { crop_left: cl, crop_top: ct, crop_right: cr, crop_bottom: cb } = shape;
  const hasCrop = cl > 0 || ct > 0 || cr > 0 || cb > 0;
  if (!hasCrop) {
    return (
      <div style={{ position: "relative", width: "100%", height: "100%" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
        <UnsplashAttribution shape={shape} />
      </div>
    );
  }
  const scaleX = 1 / Math.max(0.05, 1 - cl - cr);
  const scaleY = 1 / Math.max(0.05, 1 - ct - cb);
  return (
    <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        style={{
          position: "absolute",
          left: `${-cl * scaleX * 100}%`,
          top: `${-ct * scaleY * 100}%`,
          width: `${scaleX * 100}%`,
          height: `${scaleY * 100}%`,
          objectFit: "cover",
        }}
      />
      <UnsplashAttribution shape={shape} />
    </div>
  );
}

function SlideTable({ shape, scale }: { shape: TableShape; scale: number }) {
  return (
    <table
      style={{
        width: "100%",
        height: "100%",
        borderCollapse: "collapse",
        tableLayout: "fixed",
        fontSize: `${Math.max(7, 11 * scale * EMU_PER_PT)}px`,
      }}
    >
      <tbody>
        {shape.rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td
                key={ci}
                style={{
                  border: "1px solid rgba(0,0,0,0.15)",
                  padding: "2px 4px",
                  color: "#1a1a1a",
                  fontWeight: ri === 0 ? 700 : 400,
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                }}
              >
                {cell.paragraphs.map((p) => runText(p.runs)).join(" ")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// HTML render of one composed slide: absolutely-positioned divs scaled from the
// slide's EMU geometry. Replaces an earlier SVG+foreignObject renderer that
// hard-clipped overflowing text and fought Chrome's font-size clamp. Kept as
// `SlideCanvas` so call sites are unchanged.
function SlideCanvas({
  slide,
  slideWidth,
  slideHeight,
  width,
  themeColors,
  roles,
}: {
  slide: Slide;
  slideWidth: number;
  slideHeight: number;
  width: number;
  themeColors: Record<string, string>;
  roles?: Record<string, string>;
}) {
  const scale = width / slideWidth; // px per EMU
  const ptPx = scale * EMU_PER_PT; // px per point
  const height = slideHeight * scale;
  const sorted = [...slide.shapes].sort((a, b) => a.z_order - b.z_order);
  const bg = colorToCss(slide.background, "#fff", themeColors);
  const defaultTextColor = readableTextColor(bg);

  // Card/column groups: >=2 text shapes of identical kind+size that already
  // carry text — same "parallel slot" signal the composer uses server-side
  // (packages/design_system/slots.py) to decide these are one set, not
  // independent boxes. Grouped shapes report their individually-needed
  // scale up via onMeasured; SlideCanvas keeps the group's running minimum
  // so every member renders at the same font size once all have measured.
  const groupKeyByShapeId = new Map<number, string>();
  {
    const bySize = new Map<string, number>();
    for (const s of slide.shapes) {
      if (s.kind !== "text_box" && s.kind !== "autoshape") continue;
      const hasText = s.paragraphs.some((p) => p.runs.some((r) => r.text.trim()));
      if (!hasText) continue;
      const key = `${s.kind}:${s.width}:${s.height}`;
      bySize.set(key, (bySize.get(key) ?? 0) + 1);
    }
    for (const s of slide.shapes) {
      if (s.kind !== "text_box" && s.kind !== "autoshape") continue;
      const key = `${s.kind}:${s.width}:${s.height}`;
      if ((bySize.get(key) ?? 0) >= 2) groupKeyByShapeId.set(s.shape_id, key);
    }
  }
  const [groupScales, setGroupScales] = useState<Record<string, number>>({});
  const handleMeasured = (groupKey: string, needed: number) => {
    setGroupScales((prev) =>
      prev[groupKey] !== undefined && prev[groupKey] <= needed
        ? prev
        : { ...prev, [groupKey]: needed },
    );
  };

  return (
    <div
      style={{
        position: "relative",
        width,
        height,
        background: bg,
        borderRadius: 4,
        border: "1px solid var(--border)",
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      {sorted.map((shape) => {
        const box: React.CSSProperties = {
          position: "absolute",
          left: shape.left * scale,
          top: shape.top * scale,
          width: shape.width * scale,
          height: shape.height * scale,
        };

        if (shape.kind === "picture") {
          return (
            <div key={shape.shape_id} style={{ ...box, overflow: "hidden", background: "#1a1a1a" }}>
              <SlidePicture shape={shape} />
            </div>
          );
        }
        if (shape.kind === "passthrough") {
          // A shape our parser couldn't classify (often a background photo
          // wrapped in a <p:grpSp> group — we don't recurse into groups).
          // Small ones (icons, thin decorative lines) are fine left
          // invisible, but a large one is very often exactly the dark photo
          // a slide's white-on-dark text was designed to sit on — skipping
          // it entirely left that text invisible on the plain white slide
          // background behind it. Give it the same placeholder treatment as
          // a real Picture once it's big enough to plausibly be that photo.
          const areaFrac = (shape.width * shape.height) / (slideWidth * slideHeight);
          if (areaFrac < 0.1) return null;
          return (
            <div key={shape.shape_id} style={{ ...box, ...imagePlaceholderStyle(shape, slide, themeColors) }} />
          );
        }
        if (shape.kind === "table") {
          return (
            <div key={shape.shape_id} style={box}>
              <SlideTable shape={shape} scale={scale} />
            </div>
          );
        }

        const fill =
          shape.kind === "autoshape" && shape.fill_color
            ? colorToCss(shape.fill_color, "transparent", themeColors)
            : "transparent";
        const groupKey = groupKeyByShapeId.get(shape.shape_id);
        return (
          <div key={shape.shape_id} style={{ ...box, background: fill }}>
            <AutoFitText
              shape={shape}
              ptPx={ptPx}
              themeColors={themeColors}
              defaultColor={defaultTextColor}
              groupKey={groupKey}
              sharedScale={groupKey ? groupScales[groupKey] : undefined}
              onMeasured={handleMeasured}
            />
          </div>
        );
      })}
      {roles &&
        sorted.map((shape) => {
          const role = roles[String(shape.shape_id)];
          const style = role ? ROLE_STYLE[role] : undefined;
          if (!style) return null;
          return (
            <div
              key={`role-${shape.shape_id}`}
              title={`${style[1]} — ${style[2]}`}
              style={{
                position: "absolute",
                left: shape.left * scale,
                top: shape.top * scale,
                width: shape.width * scale,
                height: shape.height * scale,
                border: `2px dashed ${style[0]}`,
                background: `${style[0]}22`,
                pointerEvents: "none",
                zIndex: 5,
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  fontSize: 10,
                  lineHeight: 1.2,
                  padding: "1px 4px",
                  background: style[0],
                  color: "#000",
                  whiteSpace: "nowrap",
                }}
              >
                {style[1]}
              </span>
            </div>
          );
        })}
    </div>
  );
}


function TemplateInspector({ templateId, onClose }: { templateId: string; onClose: () => void }) {
  const [data, setData] = useState<InspectedTemplate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [showOverlay, setShowOverlay] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/templates/${encodeURIComponent(templateId)}/inspect`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: InspectedTemplate) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(String(e.message ?? e)));
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setSelected((i) => (data ? Math.min(i + 1, data.slides.length - 1) : i));
      if (e.key === "ArrowLeft") setSelected((i) => Math.max(i - 1, 0));
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, data]);

  const slide = data?.deck.slides[selected];
  const info = data?.slides[selected];
  const usedRoles = info ? Array.from(new Set(Object.values(info.roles))).filter((r) => ROLE_STYLE[r]) : [];
  const counts = (role: string) => Object.values(info?.roles ?? {}).filter((r) => r === role).length;

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 60, display: "flex", padding: "1.5rem" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          display: "flex",
          gap: "1rem",
          width: "100%",
          background: "#0d0d0d",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "1rem",
          overflow: "hidden",
        }}
      >
        <div style={{ width: 190, overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.5rem", flexShrink: 0 }}>
          {data?.deck.slides.map((sl, i) => (
            <div
              key={sl.index}
              onClick={() => setSelected(i)}
              style={{
                cursor: "pointer",
                outline: i === selected ? "2px solid var(--foreground)" : "1px solid var(--border)",
                borderRadius: 4,
              }}
            >
              <SlideCanvas
                slide={sl}
                slideWidth={data.deck.slide_width}
                slideHeight={data.deck.slide_height}
                width={186}
                themeColors={data.deck.theme_colors}
              />
              <div style={{ fontSize: "0.65rem", color: "var(--muted)", padding: "2px 4px" }}>
                {i + 1}. {sl.layout_name}
              </div>
            </div>
          ))}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "0.75rem", overflowY: "auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
            <span style={{ fontSize: "0.85rem" }}>
              {templateId} · слайд {selected + 1}/{data?.slides.length ?? "…"} · <b>{info?.layout_name}</b>
            </span>
            <span style={{ display: "flex", gap: "0.5rem" }}>
              <label style={{ fontSize: "0.75rem", display: "flex", gap: 4, alignItems: "center", cursor: "pointer" }}>
                <input type="checkbox" checked={showOverlay} onChange={(e) => setShowOverlay(e.target.checked)} />
                Показать роли
              </label>
              <button
                onClick={onClose}
                style={{ background: "transparent", border: "1px solid var(--border)", borderRadius: 6, color: "var(--foreground)", padding: "0.25rem 0.6rem", fontSize: "0.8rem", cursor: "pointer" }}
              >
                Закрыть ✕
              </button>
            </span>
          </div>
          {error && <div style={{ color: "#ff8080", fontSize: "0.8rem" }}>Не удалось загрузить шаблон: {error}</div>}
          {!data && !error && <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>Загружаю шаблон…</div>}
          {slide && info && data && (
            <>
              <SlideCanvas
                slide={slide}
                slideWidth={data.deck.slide_width}
                slideHeight={data.deck.slide_height}
                width={860}
                themeColors={data.deck.theme_colors}
                roles={showOverlay ? info.roles : undefined}
              />
              <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", fontSize: "0.78rem" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {usedRoles.map((r) => (
                    <div key={r} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span style={{ width: 12, height: 12, border: `2px dashed ${ROLE_STYLE[r]![0]}`, display: "inline-block" }} />
                      <span>
                        <b>{ROLE_STYLE[r]![1]}</b> ×{counts(r)} — {ROLE_STYLE[r]![2]}
                      </span>
                    </div>
                  ))}
                </div>
                <div style={{ color: "var(--muted)", display: "flex", flexDirection: "column", gap: 2 }}>
                  <span>Карточек: {info.slots.card_slots} · Текстовых областей: {info.slots.body_slots}</span>
                  <span>Таблица: {info.slots.has_table ? "да" : "нет"} · Картинка: {info.slots.has_picture ? "да" : "нет"}</span>
                  {info.slots.body_lines != null && (
                    <span>
                      Вместимость текста: ~{info.slots.body_lines} стр. по ~{info.slots.body_chars_per_line} симв.
                    </span>
                  )}
                  {info.slots.title_font_size_pt != null && (
                    <span>Крупный заголовок {Math.round(info.slots.title_font_size_pt)}pt — пишем коротко</span>
                  )}
                  <span style={{ fontSize: "0.7rem" }}>Навигация: ← → · Esc — закрыть</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
