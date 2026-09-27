import { useEffect, useState } from "react";
import { renderPreview } from "../lib/api";
import type { Deck, PreviewStatus } from "../lib/types";

// The exported .pptx rendered to images by the server (LibreOffice) — the
// only preview that matches the downloaded file: backgrounds, master art,
// theme colours and charts the in-browser drawing can't reproduce.
//
// Keyed on the deck's identity: message objects are kept by reference in
// session state, so this fires once per result, not on every re-render.
export function useDeckPreview(deck: Deck | null): { images: string[] | null; status: PreviewStatus } {
  const [state, setState] = useState<{ images: string[] | null; status: PreviewStatus }>({
    images: null,
    status: "loading",
  });
  useEffect(() => {
    if (!deck) return;
    let cancelled = false;
    setState({ images: null, status: "loading" });
    renderPreview(deck)
      .then((result) => {
        if (!cancelled) setState(result);
      })
      .catch(() => {
        if (!cancelled) setState({ images: null, status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [deck]);
  return state;
}
