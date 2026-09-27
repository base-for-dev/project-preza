import { useLayoutEffect, useRef, useState } from "react";
import { alignToCss, colorToCss } from "../../lib/slideColors";
import type { AutoShape, TextBoxShape } from "../../lib/types";

// PowerPoint shrinks text to fit its placeholder ("Shrink text on overflow").
// The IR carries no such flag, and a fixed font size clips long generated
// titles mid-line (the box is sized for the template's shorter copy). So we
// measure the rendered text against its box and scale it down to fit. Reading
// scrollHeight/scrollWidth (layout metrics, unaffected by CSS transforms) keeps
// the measurement stable across scale changes, so there is no oscillation.
export function AutoFitText({
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
            {p.runs.length === 0 ? " " : null}
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
