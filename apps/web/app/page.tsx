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
  { key: "layout", label: "Сборка вёрстки", disabled: true },
  { key: "audit", label: "Аудит", disabled: true },
  { key: "export", label: "Экспорт .pptx", disabled: true },
];

type SlideContent = {
  role: string;
  title: string;
  bullets: string[];
  body: string | null;
  table: string[][] | null;
};
type DeckContent = { slides: SlideContent[] };

type Message =
  | { id: string; kind: "user"; text: string }
  | { id: string; kind: "content"; deck: DeckContent; slideCount: number }
  | { id: string; kind: "error"; text: string };

type StageStatus = "idle" | "active" | "done" | "error";

function uid() {
  return Math.random().toString(36).slice(2);
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [slideCount, setSlideCount] = useState(10);
  const [busy, setBusy] = useState(false);
  const [stages, setStages] = useState<Record<string, StageStatus>>({});
  const [thinkingText, setThinkingText] = useState<string>(THINKING_PHRASES[0] ?? "Думаю…");
  const scrollRef = useRef<HTMLDivElement>(null);

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
      const res = await fetch(`${API_URL}/api/content`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: "portrait-regiona",
          brief,
          slide_count: slideCount,
        }),
      });

      // /api/content runs parse -> design_system -> outline -> content as one
      // blocking call — there's no server-sent progress mid-request, so these
      // stage flips are a best-effort local approximation, not a true trace.
      setStage("parse", "done");
      setStage("outline", "done");
      setStage("content", "active");

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
      }

      const deck: DeckContent = await res.json();
      setStage("content", "done");
      setMessages((prev) => [...prev, { id: uid(), kind: "content", deck, slideCount }]);
    } catch (e) {
      setStage("content", "error");
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
          <div style={{ fontSize: "0.8rem" }}>portrait-regiona.pptx</div>
          <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>15 слайдов · тестовая фикстура</div>
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>{message.deck.slides.length} слайдов</div>
      {message.deck.slides.map((slide, i) => (
        <div
          key={i}
          style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "1rem 1.25rem", background: "#111" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>{i + 1}</span>
            <span style={{ fontSize: "0.68rem", color: "var(--muted)", textTransform: "uppercase" }}>{slide.role}</span>
          </div>
          <div style={{ fontWeight: 600, fontSize: "1rem", margin: "0.35rem 0 0.6rem" }}>{slide.title}</div>

          {slide.bullets.length > 0 && (
            <ul style={{ paddingLeft: "1.1rem", margin: 0, fontSize: "0.85rem" }}>
              {slide.bullets.map((b, bi) => (
                <li key={bi} style={{ marginBottom: "0.3rem" }}>
                  {b}
                </li>
              ))}
            </ul>
          )}

          {slide.body && (
            <p style={{ fontSize: "0.85rem", color: "var(--foreground)", margin: 0 }}>{slide.body}</p>
          )}

          {slide.table && slide.table.length > 0 && slide.table[0] && (
            <table style={{ borderCollapse: "collapse", marginTop: "0.6rem", fontSize: "0.8rem", width: "100%" }}>
              <thead>
                <tr>
                  {slide.table[0].map((cell, ci) => (
                    <th
                      key={ci}
                      style={{ border: "1px solid var(--border)", padding: "0.3rem 0.5rem", textAlign: "left", color: "var(--muted)" }}
                    >
                      {cell}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {slide.table.slice(1).map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => (
                      <td key={ci} style={{ border: "1px solid var(--border)", padding: "0.3rem 0.5rem" }}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}
