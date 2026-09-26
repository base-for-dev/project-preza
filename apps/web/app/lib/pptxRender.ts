import { init } from "pptx-preview";
import { API_URL } from "./config";
import type { Deck } from "./model";

// Renders the *exported .pptx* in the browser (no server-side office suite):
// the deck is exported through the same endpoint as the download, then drawn by
// pptx-preview, so backgrounds, master artwork and grouped shapes come from
// the real file. Slides are rendered once into an off-screen host and cloned
// into whatever card shows them.

export const RENDER_WIDTH = 960;

type Rendered = { host: HTMLElement; slides: HTMLElement[]; height: number };
const cache = new Map<string, Promise<Rendered>>();
const CACHE_LIMIT = 8;

async function keyOf(deck: Deck): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(deck));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function render(deck: Deck): Promise<Rendered> {
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
  if (slides.length === 0) throw new Error("renderer produced no slides");
  return { host, slides, height };
}

export function renderDeck(deck: Deck): Promise<Rendered> {
  return keyOf(deck).then((key) => {
    let hit = cache.get(key);
    if (!hit) {
      hit = render(deck);
      hit.catch(() => cache.delete(key));
      cache.set(key, hit);
      if (cache.size > CACHE_LIMIT) {
        const oldest = cache.keys().next().value as string;
        cache.get(oldest)?.then((r) => r.host.remove()).catch(() => {});
        cache.delete(oldest);
      }
    }
    return hit;
  });
}
