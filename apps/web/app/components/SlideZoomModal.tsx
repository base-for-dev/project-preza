import { useEffect } from "react";
import { densityLabel } from "../lib/format";
import { closeButton } from "../lib/styles";
import type { DeckAudit, Density, PreviewStatus } from "../lib/types";
import { SlidePreview } from "./SlidePreview";

export function SlideZoomModal({
  audit,
  slideIndex,
  variantKey,
  node,
  size,
  status,
  onClose,
}: {
  audit: DeckAudit;
  slideIndex: number;
  variantKey: Density;
  node: HTMLElement | undefined;
  size: { width: number; height: number } | null;
  status: PreviewStatus;
  onClose: () => void;
}) {
  const { deck } = audit[variantKey];
  const slide = deck.slides[slideIndex];
  const variantLabel = densityLabel(variantKey);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (!slide) return null;
  const title = [`Слайд ${slideIndex + 1}`, variantLabel].filter(Boolean).join(" · ");

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
        role="dialog"
        aria-modal="true"
        aria-label={title}
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
          <span style={{ fontSize: "0.85rem", color: "var(--foreground)" }}>{title}</span>
          <button onClick={onClose} style={closeButton}>
            Закрыть ✕
          </button>
        </div>
        <SlidePreview node={node} size={size} status={status} slide={slide} deck={deck} width={800} />
      </div>
    </div>
  );
}
