"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL, UPLOAD_OPTION, AUTO_TEMPLATE_OPTION, THINKING_PHRASES, PIPELINE_STAGES, DURATIONS, NO_PACK_OPTION, UPLOAD_PACK_OPTION } from "./lib/config";
import { DeckAudit, Density, BrandPack, TaskMaterials, EMPTY_MATERIALS, hasMaterials, VARIANTS, MODES, detectDensity, Message, StageStatus, uid, TemplateInfo, ChatSession, sessionTitle } from "./lib/model";
import { MaterialsPanel, BudgetTimer, StageDot, ThinkingBubble } from "./components/panels";
import { MessageView } from "./components/results";
import { TemplateInspector } from "./components/TemplateInspector";

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
