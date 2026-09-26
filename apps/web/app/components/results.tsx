"use client";

import { useEffect, useState } from "react";
import { API_URL } from "../lib/config";
import { Slide, Deck, DeckAudit, Density, formatSeconds, VARIANTS, Message } from "../lib/model";
import { DensityQuestion } from "./panels";
import { SlideCanvas } from "./slide/SlideCanvas";

export type PreviewStatus = "loading" | "ready" | "unavailable" | "error";

// The exported .pptx rendered to images by the server (LibreOffice) — the
// only preview that matches the downloaded file: backgrounds, master art,
// theme colours and charts the in-browser drawing can't reproduce.
export function useDeckPreview(deck: Deck | null): { images: string[] | null; status: PreviewStatus } {
  const [state, setState] = useState<{ images: string[] | null; status: PreviewStatus }>({
    images: null,
    status: "loading",
  });
  useEffect(() => {
    if (!deck) return;
    let cancelled = false;
    setState({ images: null, status: "loading" });
    fetch(`${API_URL}/api/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(deck),
    })
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 501) return setState({ images: null, status: "unavailable" });
        if (!res.ok) return setState({ images: null, status: "error" });
        const data = (await res.json()) as { slides: string[] };
        if (!cancelled) setState({ images: data.slides, status: "ready" });
      })
      .catch(() => !cancelled && setState({ images: null, status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [deck]);
  return state;
}

export function SlidePreview({
  image,
  status,
  slide,
  deck,
  width,
}: {
  image: string | undefined;
  status: PreviewStatus;
  slide: Slide;
  deck: Deck;
  width: number;
}) {
  if (image) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={image}
        alt=""
        style={{ width, display: "block", borderRadius: 4 }}
      />
    );
  }
  return (
    <div style={{ position: "relative", width }}>
      <SlideCanvas
        slide={slide}
        slideWidth={deck.slide_width}
        slideHeight={deck.slide_height}
        width={width}
        themeColors={deck.theme_colors}
      />
      {status === "loading" && (
        <span
          style={{
            position: "absolute",
            right: 6,
            bottom: 6,
            fontSize: "0.65rem",
            background: "rgba(0,0,0,0.65)",
            color: "#fff",
            borderRadius: 4,
            padding: "2px 6px",
          }}
        >
          рендер .pptx…
        </span>
      )}
    </div>
  );
}

export function MessageView({
  message,
  onAnswerDensity,
}: {
  message: Message;
  onAnswerDensity?: (density: Density) => void;
}) {
  // Hooks can't follow an early return (Rules of Hooks) — called
  // unconditionally here even though only the "audit" branch uses it.
  const [zoomedSlide, setZoomedSlide] = useState<number | null>(null);
  const previewDeck = message.kind === "audit" ? message.audit[message.density].deck : null;
  const preview = useDeckPreview(previewDeck);

  if (message.kind === "density-question") {
    return (
      <DensityQuestion answered={message.answered} onPick={(d) => onAnswerDensity?.(d)} />
    );
  }

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

  const { audit, density } = message;
  const { deck, findings } = audit[density];
  const slideCount = deck.slides.length;
  const densityLabel = VARIANTS.find((v) => v.key === density)?.label ?? density;
  const planned = audit.slide_seconds ?? [];
  const spoken = audit.spoken_seconds ?? [];
  const spokenTotal = spoken.reduce((a, b) => a + b, 0);
  const plannedTotal = planned.reduce((a, b) => a + b, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
          {slideCount} слайдов · плотность: {densityLabel} · {findings.length} находок аудита
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
            onClick={() => setZoomedSlide(i)}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "1rem",
              background: "#111",
              cursor: "pointer",
              width: "fit-content",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.6rem" }}>
              <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>
                Слайд {i + 1}
                {planned[i] ? ` · ${formatSeconds(planned[i]!)}` : ""}
              </span>
              <span style={{ fontSize: "0.68rem", color: "var(--muted)", textTransform: "uppercase" }}>
                {slide.layout_name}
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
          onClose={() => setZoomedSlide(null)}
        />
      )}
    </div>
  );
}

export function ExportButton({ deck }: { deck: Deck }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  async function download() {
    setState("busy");
    try {
      const res = await fetch(`${API_URL}/api/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(deck),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "presentation.pptx";
      a.click();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("error");
    }
  }
  return (
    <button
      onClick={download}
      disabled={state === "busy"}
      style={{
        background: "#ededed",
        color: "#0a0a0a",
        border: "none",
        borderRadius: 6,
        padding: "0.3rem 0.7rem",
        fontSize: "0.75rem",
        fontWeight: 600,
        cursor: state === "busy" ? "default" : "pointer",
      }}
    >
      {state === "busy" ? "Экспорт…" : state === "error" ? "Ошибка — ещё раз" : "Скачать .pptx с текстом"}
    </button>
  );
}

export function SlideZoomModal({
  audit,
  slideIndex,
  variantKey,
  image,
  status,
  onClose,
}: {
  audit: DeckAudit;
  slideIndex: number;
  variantKey: Density;
  image: string | undefined;
  status: PreviewStatus;
  onClose: () => void;
}) {
  const { deck } = audit[variantKey];
  const slide = deck.slides[slideIndex];
  const variantLabel = VARIANTS.find((v) => v.key === variantKey)?.label ?? variantKey;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (!slide) return null;

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
          <span style={{ fontSize: "0.85rem", color: "var(--foreground)" }}>
            Слайд {slideIndex + 1} · {variantLabel} · {slide.layout_name}
          </span>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: 6,
              color: "var(--foreground)",
              padding: "0.25rem 0.6rem",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            Закрыть ✕
          </button>
        </div>
        <SlidePreview image={image} status={status} slide={slide} deck={deck} width={800} />
      </div>
    </div>
  );
}
