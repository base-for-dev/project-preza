import { useEffect, useRef } from "react";
import { FINDING_COLOR, type Highlight } from "../lib/findings";
import type { Deck, PreviewStatus, Slide } from "../lib/types";
import { SlideCanvas } from "./slide/SlideCanvas";

// The client-rendered .pptx node once it's there (see useDeckPreview); until
// then — or if the browser render fails — the in-browser SlideCanvas.
export function SlidePreview({
  node,
  size,
  status,
  slide,
  deck,
  width,
  highlights = [],
}: {
  node: HTMLElement | undefined;
  size: { width: number; height: number } | null;
  status: PreviewStatus;
  slide: Slide;
  deck: Deck;
  width: number;
  // Boxes drawn over the slide where the audit found something.
  highlights?: Highlight[];
}) {
  const holder = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = holder.current;
    if (!el || !node) return;
    el.replaceChildren(node.cloneNode(true));
  }, [node]);

  const overlay = highlights.map((h, i) => (
    <div
      key={i}
      aria-hidden
      style={{
        position: "absolute",
        left: `${h.left * 100}%`,
        top: `${h.top * 100}%`,
        width: `${h.width * 100}%`,
        height: `${h.height * 100}%`,
        border: `2px solid ${FINDING_COLOR[h.kind]}`,
        background: `${FINDING_COLOR[h.kind]}22`,
        borderRadius: 3,
        pointerEvents: "none",
      }}
    />
  ));

  if (node && size) {
    const scale = width / size.width;
    return (
      <div style={{ width, height: size.height * scale, overflow: "hidden", borderRadius: 4, position: "relative" }}>
        <div
          ref={holder}
          style={{ width: size.width, height: size.height, transform: `scale(${scale})`, transformOrigin: "top left" }}
        />
        {overlay}
      </div>
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
      {overlay}
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
