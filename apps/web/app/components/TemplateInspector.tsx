import { useEffect, useRef, useState } from "react";
import { onActivateKey } from "../lib/a11y";
import { inspectTemplate, templateSlideUrl } from "../lib/api";
import { closeButton } from "../lib/styles";
import type { InspectedTemplate } from "../lib/types";
import { SlideCanvas } from "./slide/SlideCanvas";

// Modal: every slide of a template as it really renders, the selected one
// filling the space. Slot roles (what generation writes where) are still
// computed server-side and returned with the template, just not drawn.
export function TemplateInspector({ templateId, onClose }: { templateId: string; onClose: () => void }) {
  const [data, setData] = useState<InspectedTemplate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  // The selected slide fills this area at the slide's own aspect ratio.
  const stageRef = useRef<HTMLDivElement>(null);
  const [stage, setStage] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry!.contentRect;
      setStage({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [data]);

  useEffect(() => {
    let cancelled = false;
    inspectTemplate(templateId)
      .then((d) => !cancelled && setData(d))
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
  const aspect = data ? data.deck.slide_width / data.deck.slide_height : 16 / 9;
  const slideWidth = Math.floor(Math.min(stage.width, stage.height * aspect));

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 60, display: "flex", padding: "1.5rem" }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Структура шаблона"
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
              role="button"
              tabIndex={0}
              aria-label={`Слайд ${i + 1}`}
              aria-pressed={i === selected}
              onClick={() => setSelected(i)}
              onKeyDown={onActivateKey(() => setSelected(i))}
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
                backdropUrl={templateSlideUrl(templateId, sl.index)}
              />
              <div style={{ fontSize: "0.65rem", color: "var(--muted)", padding: "2px 4px" }}>
                Слайд {i + 1}
              </div>
            </div>
          ))}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
            <span style={{ fontSize: "0.85rem" }}>
              {templateId.split(":").pop()} · слайд {selected + 1}/{data?.slides.length ?? "…"}
              <span style={{ color: "var(--muted)", fontSize: "0.7rem", marginLeft: "0.75rem" }}>
                ← → · Esc — закрыть
              </span>
            </span>
            <button onClick={onClose} style={closeButton}>
              Закрыть ✕
            </button>
          </div>
          {error && <div style={{ color: "#ff8080", fontSize: "0.8rem" }}>Не удалось загрузить шаблон: {error}</div>}
          {!data && !error && <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>Загружаю шаблон…</div>}
          <div
            ref={stageRef}
            style={{ flex: 1, minHeight: 0, display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            {slide && data && slideWidth > 0 && (
              <SlideCanvas
                slide={slide}
                slideWidth={data.deck.slide_width}
                slideHeight={data.deck.slide_height}
                width={slideWidth}
                themeColors={data.deck.theme_colors}
                backdropUrl={templateSlideUrl(templateId, slide.index)}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
