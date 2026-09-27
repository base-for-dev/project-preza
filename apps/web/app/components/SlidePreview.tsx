import type { Deck, PreviewStatus, Slide } from "../lib/types";
import { SlideCanvas } from "./slide/SlideCanvas";

// The server-rendered image once it's there (see useDeckPreview); until
// then — or if the server can't render — the in-browser SlideCanvas.
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
