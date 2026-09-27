import { useState, type CSSProperties } from "react";
import { formatSeconds, slideKind } from "../lib/format";
import { card } from "../lib/styles";
import type { Outline, SlideIntent } from "../lib/types";

// Gamma-style plan review: the user edits summaries, reorders or drops
// slides, then confirms — generation then writes exactly this plan.
export function OutlineReview({
  initial,
  confirmed,
  onConfirm,
}: {
  initial: Outline;
  confirmed: boolean;
  onConfirm: (outline: Outline) => void;
}) {
  const [slides, setSlides] = useState<SlideIntent[]>(initial.slides);
  const total = slides.reduce((a, s) => a + (s.seconds || 0), 0);

  function update(i: number, patch: Partial<SlideIntent>) {
    setSlides((prev) => prev.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  }
  function move(i: number, delta: number) {
    setSlides((prev) => {
      const next = [...prev];
      const j = i + delta;
      if (j < 0 || j >= next.length) return prev;
      [next[i], next[j]] = [next[j]!, next[i]!];
      return next;
    });
  }
  const small: CSSProperties = {
    background: "transparent",
    color: "var(--muted)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "0 0.4rem",
    fontSize: "0.72rem",
    cursor: confirmed ? "default" : "pointer",
  };

  return (
    <div style={card}>
      <div style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
        План презентации — {slides.length} слайдов{total ? ` · ${formatSeconds(total)}` : ""}
        {!confirmed && (
          <span style={{ color: "var(--muted)" }}> · поправь тезисы, порядок или убери лишнее</span>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
        {slides.map((s, i) => (
          <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <span style={{ width: 22, fontSize: "0.72rem", color: "var(--muted)" }}>{i + 1}</span>
            <input
              value={s.summary}
              disabled={confirmed}
              onChange={(e) => update(i, { summary: e.target.value })}
              aria-label={`Тезис слайда ${i + 1}`}
              style={{
                flex: 1,
                background: "#0a0a0a",
                color: "var(--foreground)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.35rem 0.5rem",
                fontSize: "0.82rem",
              }}
            />
            <span title="Тип слайда из шаблона" style={{ fontSize: "0.66rem", color: "var(--muted)", width: 90 }}>
              {[slideKind(s.role), s.seconds ? `${s.seconds} с` : ""].filter(Boolean).join(" · ")}
            </span>
            {!confirmed && (
              <>
                <button style={small} onClick={() => move(i, -1)} aria-label="Выше">↑</button>
                <button style={small} onClick={() => move(i, 1)} aria-label="Ниже">↓</button>
                <button
                  style={small}
                  onClick={() => setSlides((prev) => prev.filter((_, j) => j !== i))}
                  aria-label="Удалить слайд"
                  disabled={slides.length <= 1}
                >
                  ✕
                </button>
              </>
            )}
          </div>
        ))}
      </div>
      {!confirmed && (
        <button
          onClick={() => onConfirm({ slides })}
          style={{
            marginTop: "0.85rem",
            background: "#ededed",
            color: "#0a0a0a",
            border: "none",
            borderRadius: 6,
            padding: "0.45rem 0.9rem",
            fontWeight: 600,
            fontSize: "0.82rem",
            cursor: "pointer",
          }}
        >
          Сгенерировать слайды
        </button>
      )}
    </div>
  );
}
