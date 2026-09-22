"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const UPLOAD_OPTION = "__upload__";


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
  { key: "outline", label: "Генерация outline" },
  { key: "content", label: "Генерация контента" },
  { key: "layout", label: "Сборка вёрстки" },
  { key: "audit", label: "Аудит" },
  { key: "export", label: "Экспорт .pptx", disabled: true },
];

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
type PictureShape = ShapeBase & { kind: "picture"; image_bytes_b64: string | null; content_type: string | null };
type TableCell = { paragraphs: Paragraph[] };
type TableShape = ShapeBase & { kind: "table"; rows: TableCell[][]; column_widths: number[]; row_heights: number[] };
type PassthroughShape = ShapeBase & { kind: "passthrough"; original_shape_type: string | null };
type Shape = TextBoxShape | AutoShape | PictureShape | TableShape | PassthroughShape;
type Slide = { index: number; layout_name: string; shapes: Shape[]; background: Color | null };
type Deck = { slide_width: number; slide_height: number; slides: Slide[]; theme_colors: Record<string, string> };
type Finding = { check: string; kind: "deterministic"; slide_index: number; shape_id: number | null; message: string };
type VariantResult = { deck: Deck; findings: Finding[] };
type DeckAudit = { compact: VariantResult; standard: VariantResult; detailed: VariantResult };

type Density = keyof DeckAudit;

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
  | { id: string; kind: "density-question"; brief: string; answered: Density | null };

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
};

function sessionTitle(messages: Message[]): string {
  const firstBrief = messages.find((m) => m.kind === "user")?.text ?? "Новый чат";
  return firstBrief.length > 40 ? firstBrief.slice(0, 40) + "…" : firstBrief;
}

export default function Home() {
  const [input, setInput] = useState("");
  const [slideCount, setSlideCount] = useState(10);
  const [mode, setMode] = useState("");
  const [thinkingText, setThinkingText] = useState<string>(THINKING_PHRASES[0] ?? "Думаю…");
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [templateId, setTemplateId] = useState("portrait-regiona");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
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
        } else if (data.templates.length > 0 && !data.templates.some((t) => t.id === templateId)) {
          setTemplateId(data.templates[0]?.id ?? templateId);
        }
      })
      .catch(() => {
        // No API server yet, or it's down — the composer still works once
        // it comes up; the sidebar just falls back to the default id below.
      });
  }

  useEffect(() => {
    void refreshTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  async function runPipeline(sessionId: string, brief: string, density: Density) {
    updateSession(sessionId, (s) => ({ ...s, busy: true, stages: {} }));
    setThinkingText(THINKING_PHRASES[0] ?? "Думаю…");
    scrollToBottom(sessionId);

    let lastStage = "parse";
    setSessionStage(sessionId, lastStage, "active");
    scrollToBottom(sessionId);

    try {
      const res = await fetch(`${API_URL}/api/audit/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: templateId,
          brief,
          slide_count: slideCount,
          mode: mode || null,
          density,
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
      setSessions((prev) => [{ id: id!, title: "Новый чат", messages: [], busy: false, stages: {} }, ...prev]);
      setViewingId(id);
    }
    return id;
  }

  function handleSend() {
    const brief = input.trim();
    if (!brief || busy) return;
    setInput("");
    const id = ensureSession();
    appendMessage(id, { id: uid(), kind: "user", text: brief });

    const density = detectDensity(brief);
    if (density) {
      void runPipeline(id, brief, density);
      return;
    }
    appendMessage(id, { id: uid(), kind: "density-question", brief, answered: null });
  }

  function handleDensityAnswer(sessionId: string, questionId: string, brief: string, density: Density) {
    const label = VARIANTS.find((v) => v.key === density)?.label ?? density;
    updateSession(sessionId, (s) => ({
      ...s,
      messages: s.messages.flatMap((m) =>
        m.id === questionId && m.kind === "density-question"
          ? [{ ...m, answered: density }, { id: uid(), kind: "user" as const, text: label }]
          : [m],
      ),
    }));
    void runPipeline(sessionId, brief, density);
  }

  const isEmpty = messages.length === 0;

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
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}.pptx
              </option>
            ))}
            <option value={UPLOAD_OPTION}>
              {uploading ? "Загрузка…" : "+ Загрузить свой шаблон…"}
            </option>
          </select>
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
                Опиши бриф. Он разбирается против паттернов слайдов шаблона,
                превращается в outline и дальше в полный контент по каждому слайду —
                настоящий пайплайн, тестовый шаблон, живой вызов LLM.
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
                      ? (density) => handleDensityAnswer(active!.id, m.id, m.brief, density)
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
                <span style={{ fontSize: "0.68rem", color: "var(--muted)", whiteSpace: "nowrap" }}>слайдов</span>
                <select
                  value={slideCount}
                  onChange={(e) => setSlideCount(Number(e.target.value))}
                  style={{
                    width: 48,
                    background: "#0a0a0a",
                    color: "var(--foreground)",
                    border: "1px solid var(--border)",
                    borderRadius: 4,
                    padding: "0.15rem",
                    textAlign: "center",
                  }}
                >
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
                placeholder="Опиши, какую презентацию хочешь…"
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
        <div style={{ marginTop: "2rem", fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
          Модель
        </div>
        {/* Static label, not read from the backend — keep in sync with
            skills/outline-generation/config.yaml + skills/slide-content/config.yaml. */}
        <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>qwen/qwen3-30b-a3b-instruct-2507 через OpenRouter</div>
      </aside>
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
        {slideCount} слайдов · плотность: {densityLabel} · {findings.length} находок аудита
      </div>
      {deck.slides.map((slide, i) => {
        const slideFindings = findings.filter((f) => f.slide_index === i);
        return (
          <div
            key={i}
            onClick={() => setZoomedSlide(i)}
            style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "1rem", background: "#111", cursor: "pointer" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.6rem" }}>
              <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>Слайд {i + 1}</span>
              <span style={{ fontSize: "0.68rem", color: "var(--muted)", textTransform: "uppercase" }}>
                {slide.layout_name}
              </span>
            </div>
            <SlideCanvas
              slide={slide}
              slideWidth={deck.slide_width}
              slideHeight={deck.slide_height}
              width={400}
              themeColors={deck.theme_colors}
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
          </div>
        );
      })}
      {zoomedSlide !== null && (
        <SlideZoomModal
          audit={audit}
          slideIndex={zoomedSlide}
          variantKey={density}
          onClose={() => setZoomedSlide(null)}
        />
      )}
    </div>
  );
}

function SlideZoomModal({
  audit,
  slideIndex,
  variantKey,
  onClose,
}: {
  audit: DeckAudit;
  slideIndex: number;
  variantKey: keyof DeckAudit;
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
        <SlideCanvas
          slide={slide}
          slideWidth={deck.slide_width}
          slideHeight={deck.slide_height}
          width={800}
          themeColors={deck.theme_colors}
        />
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
}: {
  slide: Slide;
  slideWidth: number;
  slideHeight: number;
  width: number;
  themeColors: Record<string, string>;
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
            <div
              key={shape.shape_id}
              style={{
                ...box,
                background: "linear-gradient(135deg, #ececec, #dcdcdc)",
                border: "1px solid rgba(0,0,0,0.08)",
              }}
            />
          );
        }
        if (shape.kind === "passthrough") return null;
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
    </div>
  );
}

