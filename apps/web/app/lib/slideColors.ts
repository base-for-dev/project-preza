// Pure helpers for the in-browser slide renderer (components/slide/*).
import type { CSSProperties } from "react";
import type { Color, Shape, Slide, TextRun } from "./types";

// EMU is PowerPoint's base unit (914400 per inch). Font sizes are in points;
// 1pt = 12700 EMU. The renderer scales EMU geometry to pixels by a single
// factor and derives px-per-point from it, so coordinates and font sizes stay
// in one consistent scaled space.
export const EMU_PER_PT = 12700;

export function runText(runs: TextRun[]): string {
  return runs.map((r) => r.text).join("");
}

// Perceived luminance (0..1) of a 6-digit hex colour without '#', or null
// if it isn't one.
function hexLuminance(hex: string): number | null {
  if (hex.length !== 6) return null;
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

// A run/shape frequently has no explicit color — PowerPoint would resolve it
// from the placeholder's own style, which the IR doesn't carry. A fixed dark
// fallback looked fine against the (accidentally always-white) test template,
// but is invisible on a template with a genuinely dark slide background — so
// the fallback text color tracks the resolved slide background's luminance.
export function readableTextColor(bgHex: string): string {
  const luminance = hexLuminance(bgHex.replace("#", ""));
  if (luminance === null) return "#1a1a1a";
  return luminance > 0.6 ? "#1a1a1a" : "#f5f5f5";
}

export function colorToCss(
  color: Color | null | undefined,
  fallback: string,
  themeColors: Record<string, string> = {},
): string {
  if (color?.kind === "rgb" && color.rgb) return `#${color.rgb}`;
  if (color?.kind === "theme" && color.theme_color) {
    const hex = themeColors[color.theme_color];
    if (hex) return `#${hex}`;
  }
  return fallback;
}

// A real photo could be light or dark; we don't have it, only a
// placeholder. Guess which shade this slide needs from whichever text
// overlaps the shape: light run colors mean the real image is meant to be
// dark behind them (a photo), so a light placeholder would hide that text —
// pick the placeholder shade that keeps it legible instead of defaulting
// to one fixed tone.
export function imagePlaceholderStyle(
  shape: Shape,
  slide: Slide,
  themeColors: Record<string, string>,
): CSSProperties {
  let lightRuns = 0;
  let darkRuns = 0;
  for (const s of slide.shapes) {
    if (s.kind !== "text_box" && s.kind !== "autoshape") continue;
    const overlaps =
      s.left < shape.left + shape.width &&
      s.left + s.width > shape.left &&
      s.top < shape.top + shape.height &&
      s.top + s.height > shape.top;
    if (!overlaps) continue;
    for (const p of s.paragraphs) {
      for (const r of p.runs) {
        if (!r.text.trim()) continue;
        const css = colorToCss(r.color, "", themeColors);
        const lum = hexLuminance(css.startsWith("#") ? css.slice(1) : "");
        if (lum === null) continue;
        if (lum > 0.6) lightRuns++;
        else if (lum < 0.4) darkRuns++;
      }
    }
  }
  const needsDarkPlaceholder = lightRuns > darkRuns;
  return {
    background: needsDarkPlaceholder
      ? "linear-gradient(135deg, #4a4a4a, #2b2b2b)"
      : "linear-gradient(135deg, #ececec, #dcdcdc)",
    border: "1px solid rgba(0,0,0,0.08)",
  };
}

export function alignToCss(alignment: string | null): "left" | "center" | "right" {
  const a = alignment?.toLowerCase() ?? "";
  if (a.startsWith("center")) return "center";
  if (a.startsWith("right")) return "right";
  return "left";
}
