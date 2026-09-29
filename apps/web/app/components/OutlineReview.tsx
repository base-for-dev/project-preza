import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { formatSeconds } from "../lib/format";
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
    background: "var(--fill)",
    color: "var(--label-2)",
    border: "none",
    borderRadius: 6,
    padding: "0 var(--s2)",
    minHeight: 24,
    fontSize: "var(--t-footnote)",
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
            <SummaryField
              value={s.summary}
              disabled={confirmed}
              onChange={(summary) => update(i, { summary })}
              label={`Тезис слайда ${i + 1}`}
            />
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
        <button className="btn btn-prominent" onClick={() => onConfirm({ slides })} style={{ marginTop: "var(--s4)" }}>
          Сгенерировать слайды
        </button>
      )}
    </div>
  );
}

// One slide's thesis: grows to as many lines as its text needs (the whole
// thesis always visible), never wraps a word out of view. One paragraph —
// Enter doesn't add a line break.
function SummaryField({
  value,
  disabled,
  onChange,
  label,
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  label: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight + 2}px`; // + top/bottom border
    };
    fit();
    // The column's width changes with the window: re-fit then (only on a
    // width change — re-fitting changes the height, which would loop).
    let width = el.clientWidth;
    const observer = new ResizeObserver(() => {
      if (el.clientWidth !== width) {
        width = el.clientWidth;
        fit();
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [value]);

  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value.replace(/\n/g, " "))}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.preventDefault();
      }}
      aria-label={label}
      style={{
        flex: 1,
        background: "var(--fill-2)",
        color: "var(--foreground)",
        border: "none",
        borderRadius: "var(--r-sm)",
        padding: "6px var(--s3)",
        fontSize: "var(--t-callout)",
        fontFamily: "inherit",
        lineHeight: 1.4,
        resize: "none",
        overflow: "hidden",
        boxSizing: "border-box",
      }}
    />
  );
}
