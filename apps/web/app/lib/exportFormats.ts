import { toJpeg } from "html-to-image";
import { jsPDF } from "jspdf";
import { API_URL } from "./constants";
import { exportDeck, exportDeckPdf } from "./api";
import { renderDeck, RENDER_WIDTH } from "./pptxRender";
import type { Deck } from "./types";

// The three export formats. .pptx and (when the server can) .pdf come from the
// server; .html and the browser-drawn .pdf come from the very same render the
// user previews, so what they save is what they saw.

export type ExportFormat = "pptx" | "html" | "pdf";

export const FORMAT_LABEL: Record<ExportFormat, string> = {
  pptx: ".pptx — редактируемый",
  html: ".html — одним файлом",
  pdf: ".pdf",
};

function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

async function toDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

// `blob:` and remote URLs die with the page, so a saved file must carry its
// pictures itself.
async function inlineUrl(url: string): Promise<string> {
  if (url.startsWith("data:")) return url;
  return toDataUrl(await (await fetch(url)).blob());
}

const BIG_IMAGE_CHARS = 400_000;

// A large opaque PNG (a template's background artwork, typically) as a JPEG:
// an order of magnitude smaller, indistinguishable on a slide. Anything with
// transparency, or that fails to decode, is kept as it is.
async function shrunk(dataUri: string): Promise<string> {
  if (!dataUri.startsWith("data:image/png") || dataUri.length < BIG_IMAGE_CHARS) return dataUri;
  try {
    const image = new Image();
    image.src = dataUri;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return dataUri;
    ctx.drawImage(image, 0, 0);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    for (let i = 3; i < pixels.length; i += 4) if (pixels[i]! < 255) return dataUri;
    const jpeg = canvas.toDataURL("image/jpeg", 0.88);
    return jpeg.length < dataUri.length ? jpeg : dataUri;
  } catch {
    return dataUri;
  }
}

// Every distinct picture is stored once, as a CSS variable; slides refer to it.
// (Template artwork repeats on many slides, and a copy per slide made the file
// tens of megabytes.)
class Assets {
  private names = new Map<string, string>();
  async register(url: string): Promise<string> {
    const data = await shrunk(await inlineUrl(url));
    let name = this.names.get(data);
    if (!name) {
      name = `--asset-${this.names.size}`;
      this.names.set(data, name);
    }
    return name;
  }
  css(): string {
    return `:root{${[...this.names].map(([data, name]) => `${name}:url("${data}")`).join(";")}}`;
  }
}

async function inlineImages(root: HTMLElement, assets: Assets) {
  for (const img of Array.from(root.querySelectorAll("img"))) {
    if (!img.src) continue;
    const name = await assets.register(img.src).catch(() => null);
    if (name) {
      img.removeAttribute("src");
      img.setAttribute("data-asset", name);
    }
  }
  for (const el of [root, ...Array.from(root.querySelectorAll<HTMLElement>("*"))]) {
    const match = el.style.backgroundImage && /url\(["']?([^"')]+)["']?\)/.exec(el.style.backgroundImage);
    if (match) {
      const name = await assets.register(match[1]!).catch(() => null);
      if (name) el.style.backgroundImage = `var(${name})`;
    }
  }
}

function fontFamilies(root: HTMLElement): string[] {
  const families = new Set<string>();
  for (const el of Array.from(root.querySelectorAll<HTMLElement>("*"))) {
    const first = el.style.fontFamily.split(",")[0]?.replace(/["']/g, "").trim();
    if (first) families.add(first);
  }
  return [...families];
}

// The template fonts as @font-face rules with the font files inlined, so the
// saved page reads the same on a machine that lacks them.
async function embeddedFontCss(families: string[]): Promise<string> {
  if (families.length === 0) return "";
  const query = families.map((f) => `family=${encodeURIComponent(f)}`).join("&");
  const css = await fetch(`${API_URL}/api/fonts.css?${query}`)
    .then((r) => (r.ok ? r.text() : ""))
    .catch(() => "");
  const urls = [...new Set([...css.matchAll(/url\("([^"]+)"\)/g)].map((m) => m[1]!))];
  let out = css;
  for (const url of urls) {
    const data = await inlineUrl(url.startsWith("http") ? url : `${API_URL}${url}`).catch(() => null);
    if (data) out = out.split(url).join(data);
  }
  return out;
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}

export async function buildHtml(deck: Deck, title = "Презентация"): Promise<string> {
  const { slides, height } = await renderDeck(deck);
  const sections: string[] = [];
  const assets = new Assets();
  for (const [i, node] of slides.entries()) {
    const clone = node.cloneNode(true) as HTMLElement;
    await inlineImages(clone, assets);
    const notes = deck.slides[i]?.notes;
    sections.push(
      `<section class="slide"><div class="frame"><div class="canvas">${clone.outerHTML}</div></div>` +
        (notes ? `<details><summary>Текст выступления</summary><p>${escapeHtml(notes)}</p></details>` : "") +
        `</section>`,
    );
  }
  const fonts = await embeddedFontCss([...new Set(slides.flatMap(fontFamilies))]);
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
${fonts}
${assets.css()}
body{margin:0;background:#111;color:#eee;font:14px/1.5 system-ui,sans-serif}
main{max-width:${RENDER_WIDTH}px;margin:0 auto;padding:16px}
.slide{margin:0 0 28px}
.frame{width:100%;aspect-ratio:${RENDER_WIDTH}/${height};overflow:hidden;position:relative;background:#fff}
.canvas{width:${RENDER_WIDTH}px;height:${height}px;transform-origin:0 0;position:absolute;left:0;top:0}
details{margin-top:8px}summary{cursor:pointer;color:#aaa}
@page{size:${RENDER_WIDTH}px ${height}px;margin:0}
@media print{body{background:#fff}main{padding:0;max-width:none}.slide{margin:0;break-after:page}details{display:none}}
</style></head><body><main>
${sections.join("\n")}
</main><script>
document.querySelectorAll("img[data-asset]").forEach(function(img){var v=getComputedStyle(document.documentElement).getPropertyValue(img.dataset.asset).trim();var m=/^url\\("?(.*?)"?\\)$/.exec(v);if(m)img.src=m[1]});
function fit(){document.querySelectorAll(".frame").forEach(function(f){f.firstChild.style.transform="scale("+f.clientWidth/${RENDER_WIDTH}+")"})}
addEventListener("resize",fit);addEventListener("beforeprint",fit);fit();
</script></body></html>`;
}

// Vector PDF from the server when it can convert; otherwise one picture per
// page, drawn from the browser's render (always available, looks the same).
async function buildPdf(deck: Deck): Promise<Blob> {
  const fromServer = await exportDeckPdf(deck);
  if (fromServer) return fromServer;
  const { slides, height } = await renderDeck(deck);
  const pdf = new jsPDF({
    orientation: RENDER_WIDTH >= height ? "landscape" : "portrait",
    unit: "px",
    format: [RENDER_WIDTH, height],
    hotfixes: ["px_scaling"],
  });
  for (const [i, node] of slides.entries()) {
    if (i > 0) pdf.addPage([RENDER_WIDTH, height]);
    const image = await toJpeg(node, { pixelRatio: 2, quality: 0.92, cacheBust: false });
    pdf.addImage(image, "JPEG", 0, 0, RENDER_WIDTH, height);
  }
  return pdf.output("blob");
}

export async function exportAs(deck: Deck, format: ExportFormat, name = "presentation") {
  if (format === "pptx") return save(await exportDeck(deck), `${name}.pptx`);
  if (format === "html") {
    const html = await buildHtml(deck, name);
    return save(new Blob([html], { type: "text/html;charset=utf-8" }), `${name}.html`);
  }
  save(await buildPdf(deck), `${name}.pdf`);
}
