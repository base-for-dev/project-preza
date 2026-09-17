"use client";

import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const DEMO_BRIEF =
  "Трёхдневный выездной сбор инженерной команды, чтобы исправить скорость " +
  "поставки в Q4. Аудитория: руководство разработки, решающее, утверждать " +
  "ли бюджет. Аргументировать, что рассинхрон и технический долг стоят " +
  "дороже, чем сам сбор, и разложить, что реально дадут эти три дня.";

const EXAMPLE_PROMPTS = [
  { title: "Выездной сбор Q4", subtitle: "Питч бюджета руководству", brief: DEMO_BRIEF },
  {
    title: "Итоги запуска продукта",
    subtitle: "Что вышло, что сдвинуло метрики",
    brief:
      "Колода с итогами запуска продукта, который вышел 6 недель назад. " +
      "Аудитория: топ-менеджмент, решающий, финансировать ли следующий этап. " +
      "Покрыть, что вышло, как идёт adoption, и что говорят данные насчёт удвоения ставки.",
  },
  {
    title: "Онбординг нового сотрудника",
    subtitle: "Колода первой недели",
    brief:
      "Онбординг-колода для первой недели новых инженеров. Аудитория: " +
      "новые сотрудники без контекста о компании. Покрыть, что строит команда, " +
      "как планируется работа, и куда идти, если застрял.",
  },
];

const THINKING_PHRASES = [
  "Разбираю шаблон и паттерны слайдов…",
  "Прикидываю структуру колоды…",
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

const VARIANTS: { key: keyof DeckAudit; label: string }[] = [
  { key: "compact", label: "Сжато" },
  { key: "standard", label: "Стандарт" },
  { key: "detailed", label: "Подробно" },
];

type Message =
  | { id: string; kind: "user"; text: string }
  | { id: string; kind: "audit"; audit: DeckAudit }
  | { id: string; kind: "error"; text: string };

type StageStatus = "idle" | "active" | "done" | "error";

function uid() {
  return Math.random().toString(36).slice(2);
}

type TemplateInfo = { id: string; label: string };

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [slideCount, setSlideCount] = useState(10);
  const [busy, setBusy] = useState(false);
  const [stages, setStages] = useState<Record<string, StageStatus>>({});
  const [thinkingText, setThinkingText] = useState<string>(THINKING_PHRASES[0] ?? "Думаю…");
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [templateId, setTemplateId] = useState("portrait-regiona");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/templates`)
      .then((r) => r.json())
      .then((data: { templates: TemplateInfo[] }) => {
        setTemplates(data.templates);
        if (data.templates.length > 0 && !data.templates.some((t) => t.id === templateId)) {
          setTemplateId(data.templates[0]?.id ?? templateId);
        }
      })
      .catch(() => {
        // No API server yet, or it's down — the composer still works once
        // it comes up; the sidebar just falls back to the default id below.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!busy) return;
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % THINKING_PHRASES.length;
      setThinkingText(THINKING_PHRASES[i] ?? "Думаю…");
    }, 2600);
    return () => clearInterval(interval);
  }, [busy]);

  function setStage(key: string, status: StageStatus) {
    setStages((prev) => ({ ...prev, [key]: status }));
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  }

  async function runPipeline(brief: string) {
    setBusy(true);
    setStages({});
    setThinkingText(THINKING_PHRASES[0] ?? "Думаю…");
    setMessages((prev) => [...prev, { id: uid(), kind: "user", text: brief }]);
    scrollToBottom();

    setStage("parse", "active");
    scrollToBottom();

    try {
      const res = await fetch(`${API_URL}/api/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: templateId,
          brief,
          slide_count: slideCount,
        }),
      });

      // /api/audit runs parse -> design_system -> outline -> content -> layout
      // -> audit as one blocking call — there's no server-sent progress
      // mid-request, so these stage flips are a best-effort local
      // approximation, not a true trace.
      setStage("parse", "done");
      setStage("outline", "done");
      setStage("content", "done");
      setStage("layout", "done");
      setStage("audit", "active");

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
      }

      const audit: DeckAudit = await res.json();
      setStage("audit", "done");
      setMessages((prev) => [...prev, { id: uid(), kind: "audit", audit }]);
    } catch (e) {
      setStage("audit", "error");
      setMessages((prev) => [
        ...prev,
        { id: uid(), kind: "error", text: e instanceof Error ? e.message : String(e) },
      ]);
    } finally {
      setBusy(false);
      scrollToBottom();
    }
  }

  function handleSend() {
    const brief = input.trim();
    if (!brief || busy) return;
    setInput("");
    void runPipeline(brief);
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
        }}
      >
        <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>project-preza</div>
        <button
          onClick={() => {
            setMessages([]);
            setStages({});
          }}
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
          {templates.length > 0 ? (
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
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
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}.pptx
                </option>
              ))}
            </select>
          ) : (
            <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>{templateId}.pptx</div>
          )}
          <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: "0.3rem" }}>тестовая фикстура</div>
        </div>
      </aside>

      {/* Main chat column */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "2rem" }}>
          {isEmpty ? (
            <div style={{ maxWidth: 640, margin: "4rem auto 0" }}>
              <h1 style={{ fontSize: "1.6rem", marginBottom: "0.5rem" }}>О чём должна быть колода?</h1>
              <p style={{ color: "var(--muted)", marginBottom: "2rem" }}>
                Опиши бриф. Он разбирается против паттернов слайдов шаблона,
                превращается в outline и дальше в полный контент по каждому слайду —
                настоящий пайплайн, тестовый шаблон, живой вызов LLM.
              </p>
              {EXAMPLE_PROMPTS.map((ex) => (
                <button
                  key={ex.title}
                  onClick={() => void runPipeline(ex.brief)}
                  disabled={busy}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    background: "#111",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: "0.9rem 1.1rem",
                    marginBottom: "0.6rem",
                    cursor: busy ? "default" : "pointer",
                    color: "var(--foreground)",
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>{ex.title}</div>
                  <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>{ex.subtitle}</div>
                </button>
              ))}
            </div>
          ) : (
            <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>
              {messages.map((m) => (
                <MessageView key={m.id} message={m} />
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
                <input
                  type="number"
                  min={3}
                  max={20}
                  value={slideCount}
                  onChange={(e) => setSlideCount(Number(e.target.value))}
                  style={{
                    width: 44,
                    background: "#0a0a0a",
                    color: "var(--foreground)",
                    border: "1px solid var(--border)",
                    borderRadius: 4,
                    padding: "0.15rem",
                    textAlign: "center",
                  }}
                />
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
                placeholder="Опиши, какую колоду хочешь…"
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
        <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>qwen/qwen3-32b через OpenRouter</div>
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

function MessageView({ message }: { message: Message }) {
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

  const { audit } = message;
  const slideCount = audit.standard.deck.slides.length;
  const totalFindings = VARIANTS.reduce((sum, v) => sum + audit[v.key].findings.length, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
        {slideCount} слайдов · 3 варианта плотности рядом · {totalFindings} находок аудита
      </div>
      {Array.from({ length: slideCount }, (_, i) => (
        <div
          key={i}
          style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "1rem", background: "#111" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.6rem" }}>
            <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>Слайд {i + 1}</span>
            <span style={{ fontSize: "0.68rem", color: "var(--muted)", textTransform: "uppercase" }}>
              {audit.standard.deck.slides[i]?.layout_name}
            </span>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            {VARIANTS.map((v) => {
              const { deck, findings } = audit[v.key];
              const slide = deck.slides[i];
              if (!slide) return null;
              const slideFindings = findings.filter((f) => f.slide_index === i);
              return (
                <div key={v.key} style={{ display: "flex", flexDirection: "column", gap: "0.3rem", maxWidth: 200 }}>
                  <SlideCanvas
                    slide={slide}
                    slideWidth={deck.slide_width}
                    slideHeight={deck.slide_height}
                    width={200}
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
                        cursor: "default",
                      }}
                    >
                      <span
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          background: "#f0b84a",
                          flexShrink: 0,
                        }}
                      />
                      {slideFindings.length} находк{slideFindings.length === 1 ? "а" : "и"}
                    </div>
                  )}
                  <span style={{ fontSize: "0.68rem", color: "var(--muted)", textAlign: "center" }}>{v.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// SVG viewBox is expressed in points (not EMU) with 1 viewBox unit == 1px for
// foreignObject content — using raw EMU values as font-size/coordinates makes
// font-size run into the tens/hundreds of thousands, and Chrome silently
// clamps computed font-size at 5000px, collapsing all text to a fraction of a
// pixel once the SVG's own viewBox-to-width scale is applied. Points keep
// every value (coordinates and font sizes alike) in a normal, unclamped range.
const EMU_PER_PT = 12700;
const emuToPt = (v: number) => v / EMU_PER_PT;

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

function ShapeText({
  shape,
  themeColors,
  defaultColor,
}: {
  shape: TextBoxShape | AutoShape;
  themeColors: Record<string, string>;
  defaultColor: string;
}) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        boxSizing: "border-box",
      }}
    >
      {shape.paragraphs.map((p, pi) => (
        <div
          key={pi}
          style={{
            textAlign: (p.alignment?.toLowerCase() as "left" | "center" | "right") ?? "left",
            paddingLeft: `${p.level * 16}px`,
            lineHeight: 1.25,
          }}
        >
          {p.runs.length === 0 ? " " : null}
          {p.runs.map((r, ri) => (
            <span
              key={ri}
              style={{
                fontSize: `${r.font_size_pt ?? 14}px`,
                fontWeight: r.bold ? 700 : 400,
                fontStyle: r.italic ? "italic" : "normal",
                textDecoration: r.underline ? "underline" : "none",
                color: colorToCss(r.color, defaultColor, themeColors),
                fontFamily: r.font_name ?? "inherit",
              }}
            >
              {r.text}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

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
  const vbWidth = emuToPt(slideWidth);
  const vbHeight = emuToPt(slideHeight);
  const height = width * (slideHeight / slideWidth);
  const sorted = [...slide.shapes].sort((a, b) => a.z_order - b.z_order);
  const bg = colorToCss(slide.background, "#fff", themeColors);
  const defaultTextColor = readableTextColor(bg);

  return (
    <svg
      viewBox={`0 0 ${vbWidth} ${vbHeight}`}
      width={width}
      height={height}
      style={{ background: bg, borderRadius: 4, border: "1px solid var(--border)", display: "block" }}
    >
      {sorted.map((shape) => {
        const key = shape.shape_id;
        const x = emuToPt(shape.left);
        const y = emuToPt(shape.top);
        const w = emuToPt(shape.width);
        const h = emuToPt(shape.height);

        if (shape.kind === "picture") {
          return <rect key={key} x={x} y={y} width={w} height={h} fill="#e5e5e5" stroke="#ccc" />;
        }

        if (shape.kind === "passthrough") {
          return null;
        }

        if (shape.kind === "table") {
          const rows = shape.rows;
          const colCount = rows[0]?.length ?? 0;
          const colWidth = colCount > 0 ? w / colCount : 0;
          const rowHeight = rows.length > 0 ? h / rows.length : 0;
          return (
            <g key={key}>
              {rows.map((row, ri) =>
                row.map((cell, ci) => (
                  <foreignObject
                    key={`${ri}-${ci}`}
                    x={x + ci * colWidth}
                    y={y + ri * rowHeight}
                    width={colWidth}
                    height={rowHeight}
                  >
                    <div
                      style={{
                        width: "100%",
                        height: "100%",
                        boxSizing: "border-box",
                        border: "1px solid #ddd",
                        padding: "2%",
                        fontSize: "10px",
                        color: "#1a1a1a",
                        fontWeight: ri === 0 ? 700 : 400,
                        overflow: "hidden",
                      }}
                    >
                      {cell.paragraphs.map((p) => runText(p.runs)).join(" ")}
                    </div>
                  </foreignObject>
                )),
              )}
            </g>
          );
        }

        // text_box / autoshape
        return (
          <g key={key}>
            {shape.kind === "autoshape" && shape.fill_color && (
              <rect x={x} y={y} width={w} height={h} fill={colorToCss(shape.fill_color, "transparent", themeColors)} />
            )}
            <foreignObject x={x} y={y} width={w} height={h}>
              <ShapeText shape={shape} themeColors={themeColors} defaultColor={defaultTextColor} />
            </foreignObject>
          </g>
        );
      })}
    </svg>
  );
}
