import { memo, useCallback, useState } from "react";
import { useDeckPreview } from "../hooks/useDeckPreview";
import { onActivateKey } from "../lib/a11y";
import { runDeepAudit } from "../lib/api";
import { captureSlideImages } from "../lib/pptxRender";
import { densityLabel, errorMessage, formatSeconds, slideKind } from "../lib/format";
import { card } from "../lib/styles";
import type { DeckAudit, Density, Finding } from "../lib/types";
import { ExportButton } from "./ExportButton";
import { SlidePreview } from "./SlidePreview";
import { SlideZoomModal } from "./SlideZoomModal";

type DeepAuditState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; findings: Finding[] }
  | { status: "error"; message: string };

// A finished generation: summary line, export, and every slide with its
// audit findings and speaker notes. Memoized — `audit` is kept by reference
// in session state, so typing in the composer doesn't re-render the slides.
export const AuditResult = memo(function AuditResult({
  audit,
  density,
  brief,
}: {
  audit: DeckAudit;
  density: Density;
  brief: string;
}) {
  const [zoomedSlide, setZoomedSlide] = useState<number | null>(null);
  const closeZoom = useCallback(() => setZoomedSlide(null), []);
  const { deck, findings } = audit[density];
  const preview = useDeckPreview(deck);
  const slideCount = deck.slides.length;
  const planned = audit.slide_seconds ?? [];
  const spoken = audit.spoken_seconds ?? [];
  const spokenTotal = spoken.reduce((a, b) => a + b, 0);
  const plannedTotal = planned.reduce((a, b) => a + b, 0);

  const [deep, setDeep] = useState<DeepAuditState>({ status: "idle" });
  async function runDeep() {
    setDeep({ status: "loading" });
    try {
      // The images come from this browser's own render of the .pptx; if that
      // fails the server tries to render them itself.
      const images = await captureSlideImages(deck).catch(() => undefined);
      const found = await runDeepAudit(deck, brief, images);
      setDeep({ status: "done", findings: found });
    } catch (e) {
      setDeep({ status: "error", message: errorMessage(e) });
    }
  }
  const allFindings = deep.status === "done" ? [...findings, ...deep.findings] : findings;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
          {slideCount} слайдов · плотность: {densityLabel(density)} · {allFindings.length} находок аудита
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
        <button
          onClick={runDeep}
          disabled={deep.status === "loading" || deep.status === "done"}
          title="Проверяет смысл и факты моделью по картинке каждого слайда — заголовок, соответствие теме, опечатки, связность с соседями. Отдельно от генерации, может занять минуту-две."
          style={{
            background: "transparent",
            border: "1px solid var(--border)",
            borderRadius: 6,
            color: "var(--foreground)",
            padding: "0.3rem 0.7rem",
            fontSize: "0.75rem",
            cursor: deep.status === "loading" || deep.status === "done" ? "default" : "pointer",
            opacity: deep.status === "loading" ? 0.6 : 1,
          }}
        >
          {deep.status === "loading"
            ? "Проверяю смысл и факты…"
            : deep.status === "done"
              ? `Углублённый аудит: ${deep.findings.length} находок`
              : "Проверить смысл и факты"}
        </button>
      </div>
      {deep.status === "error" && (
        <div style={{ fontSize: "0.75rem", color: "#ff8080" }}>{deep.message}</div>
      )}
      {audit.fact_sheet?.one_liner && (
        <div style={{ fontSize: "0.78rem", color: "var(--muted)", borderLeft: "2px solid var(--border)", paddingLeft: "0.6rem" }}>
          Из материалов: {audit.fact_sheet.one_liner}
        </div>
      )}
      {deck.slides.map((slide, i) => {
        const slideFindings = allFindings.filter((f) => f.slide_index === i);
        const deterministicCount = slideFindings.filter((f) => f.kind === "deterministic").length;
        const modelCount = slideFindings.filter((f) => f.kind === "model").length;
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
              node={preview.slides?.[i]}
              size={preview.size}
              status={preview.status}
              slide={slide}
              deck={deck}
              width={400}
            />
            {slideFindings.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", marginTop: "0.4rem" }}>
                {deterministicCount > 0 && (
                  <div
                    title={slideFindings.filter((f) => f.kind === "deterministic").map((f) => f.message).join("\n")}
                    style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.68rem", color: "#f0b84a" }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#f0b84a", flexShrink: 0 }} />
                    {deterministicCount} находк{deterministicCount === 1 ? "а" : "и"}
                  </div>
                )}
                {modelCount > 0 && (
                  <div
                    title={slideFindings.filter((f) => f.kind === "model").map((f) => f.message).join("\n")}
                    style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.68rem", color: "#c98bf0" }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#c98bf0", flexShrink: 0 }} />
                    {modelCount} по смыслу
                  </div>
                )}
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
          node={preview.slides?.[zoomedSlide]}
          size={preview.size}
          status={preview.status}
          onClose={closeZoom}
        />
      )}
    </div>
  );
});
