import { memo, useCallback, useState } from "react";
import { useDeckPreview } from "../hooks/useDeckPreview";
import { onActivateKey } from "../lib/a11y";
import { densityLabel, formatSeconds, slideKind } from "../lib/format";
import { card } from "../lib/styles";
import type { DeckAudit, Density } from "../lib/types";
import { ExportButton } from "./ExportButton";
import { SlidePreview } from "./SlidePreview";
import { SlideZoomModal } from "./SlideZoomModal";

// A finished generation: summary line, export, and every slide with its
// audit findings and speaker notes. Memoized — `audit` is kept by reference
// in session state, so typing in the composer doesn't re-render the slides.
export const AuditResult = memo(function AuditResult({ audit, density }: { audit: DeckAudit; density: Density }) {
  const [zoomedSlide, setZoomedSlide] = useState<number | null>(null);
  const closeZoom = useCallback(() => setZoomedSlide(null), []);
  const { deck, findings } = audit[density];
  const preview = useDeckPreview(deck);
  const slideCount = deck.slides.length;
  const planned = audit.slide_seconds ?? [];
  const spoken = audit.spoken_seconds ?? [];
  const spokenTotal = spoken.reduce((a, b) => a + b, 0);
  const plannedTotal = planned.reduce((a, b) => a + b, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
          {slideCount} слайдов · плотность: {densityLabel(density)} · {findings.length} находок аудита
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
            role="button"
            tabIndex={0}
            aria-label={`Слайд ${i + 1} — открыть крупно`}
            onClick={() => setZoomedSlide(i)}
            onKeyDown={onActivateKey(() => setZoomedSlide(i))}
            style={{ ...card, cursor: "pointer", width: "fit-content" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.6rem" }}>
              <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>
                Слайд {i + 1}
                {planned[i] ? ` · ${formatSeconds(planned[i]!)}` : ""}
              </span>
              <span style={{ fontSize: "0.68rem", color: "var(--muted)" }}>
                {slideKind(slide.layout_name)}
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
          onClose={closeZoom}
        />
      )}
    </div>
  );
});
