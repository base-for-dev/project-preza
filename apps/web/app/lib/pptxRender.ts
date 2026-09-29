import { toPng } from "html-to-image";
import { init } from "pptx-preview";
import { API_URL } from "./constants";
import type { Deck } from "./types";

// Renders the *exported .pptx itself* in the browser — no server-side office
// suite needed, so the preview never depends on what's installed on the
// machine running the server. The deck is exported through the same
// endpoint as the download, then drawn by pptx-preview; slides are rendered
// once into an off-screen host and cloned into whatever card shows them.
// Falls back to the in-browser IR reconstruction (SlideCanvas) if this fails
// for any reason (an exotic shape the library can't draw, a network hiccup).

export const RENDER_WIDTH = 960;

export type RenderedDeck = { host: HTMLElement; slides: HTMLElement[]; height: number };

const cache = new Map<string, Promise<RenderedDeck>>();
const CACHE_LIMIT = 8;

async function keyOf(deck: Deck): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(deck));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function render(deck: Deck): Promise<RenderedDeck> {
  const res = await fetch(`${API_URL}/api/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(deck),
  });
  if (!res.ok) throw new Error(`export failed: ${res.status}`);
  const buffer = await res.arrayBuffer();

  const height = Math.round((RENDER_WIDTH * deck.slide_height) / deck.slide_width);
  const host = document.createElement("div");
  host.style.cssText = `position:fixed;left:-100000px;top:0;width:${RENDER_WIDTH}px;pointer-events:none;`;
  document.body.appendChild(host);
  const previewer = init(host, { width: RENDER_WIDTH, height, mode: "list" });
  await previewer.preview(buffer);
  const slides = Array.from(host.querySelectorAll<HTMLElement>(".pptx-preview-slide-wrapper"));
  if (slides.length === 0) {
    host.remove();
    throw new Error("renderer produced no slides");
  }
  return { host, slides, height };
}

export function renderDeck(deck: Deck): Promise<RenderedDeck> {
  return keyOf(deck).then((key) => {
    let hit = cache.get(key);
    if (!hit) {
      hit = render(deck);
      hit.catch(() => cache.delete(key));
      cache.set(key, hit);
      if (cache.size > CACHE_LIMIT) {
        const oldest = cache.keys().next().value as string;
        cache
          .get(oldest)
          ?.then((r) => r.host.remove())
          .catch(() => {});
        cache.delete(oldest);
      }
    }
    return hit;
  });
}

// Every slide of `deck` as a PNG data URL, drawn from the same render the user
// sees — what the model-graded audit looks at, so it needs no server-side
// renderer. Rejects if any slide cannot be captured (the caller then lets the
// server try its own).
export async function captureSlideImages(deck: Deck): Promise<string[]> {
  const { slides } = await renderDeck(deck);
  const images: string[] = [];
  for (const node of slides) {
    images.push(await toPng(node, { pixelRatio: 1, cacheBust: false }));
  }
  return images;
}
