import { useEffect, useState } from "react";
import { renderDeck, RENDER_WIDTH } from "../lib/pptxRender";
import type { Deck, PreviewStatus } from "../lib/types";

// The exported .pptx drawn in the browser (see lib/pptxRender.ts) — what the
// download actually contains: backgrounds, master art, theme colours,
// grouped shapes — with no server-side office suite. Falls back to the
// in-browser IR reconstruction if the render fails.
//
// Keyed on the deck's identity: message objects are kept by reference in
// session state, so this fires once per result, not on every re-render.
export function useDeckPreview(deck: Deck | null): {
  slides: HTMLElement[] | null;
  size: { width: number; height: number } | null;
  status: PreviewStatus;
} {
  const [state, setState] = useState<{
    slides: HTMLElement[] | null;
    size: { width: number; height: number } | null;
    status: PreviewStatus;
  }>({ slides: null, size: null, status: "loading" });
  useEffect(() => {
    if (!deck) return;
    let cancelled = false;
    setState({ slides: null, size: null, status: "loading" });
    renderDeck(deck)
      .then((r) => {
        if (!cancelled) {
          setState({
            slides: r.slides,
            size: { width: RENDER_WIDTH, height: r.height },
            status: "ready",
          });
        }
      })
      .catch(() => {
        if (!cancelled) setState({ slides: null, size: null, status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [deck]);
  return state;
}
