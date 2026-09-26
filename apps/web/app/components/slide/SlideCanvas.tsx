"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { Color, TextRun, TextBoxShape, AutoShape, PictureShape, TableShape, Shape, Slide, ROLE_STYLE } from "../../lib/model";

// EMU is PowerPoint's base unit (914400 per inch). Font sizes are in points;
// 1pt = 12700 EMU. The renderer scales EMU geometry to pixels by a single
// factor and derives px-per-point from it, so coordinates and font sizes stay
// in one consistent scaled space.
export const EMU_PER_PT = 12700;

export function runText(runs: TextRun[]): string {
  return runs.map((r) => r.text).join("");
}

// A run/shape frequently has no explicit color — PowerPoint would resolve it
// from the placeholder's own style, which the IR doesn't carry. A fixed dark
// fallback looked fine against the (accidentally always-white) test template,
// but is invisible on a template with a genuinely dark slide background — so
// the fallback text color tracks the resolved slide background's luminance.
export function readableTextColor(bgHex: string): string {
  const clean = bgHex.replace("#", "");
  if (clean.length !== 6) return "#1a1a1a";
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
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
): React.CSSProperties {
  const overlapping = slide.shapes.filter(
    (s) =>
      (s.kind === "text_box" || s.kind === "autoshape") &&
      s.left < shape.left + shape.width &&
      s.left + s.width > shape.left &&
      s.top < shape.top + shape.height &&
      s.top + s.height > shape.top,
  );
  let lightRuns = 0;
  let darkRuns = 0;
  for (const s of overlapping) {
    if (s.kind !== "text_box" && s.kind !== "autoshape") continue;
    for (const p of s.paragraphs) {
      for (const r of p.runs) {
        if (!r.text.trim()) continue;
        const css = colorToCss(r.color, "", themeColors);
        const hex = css.startsWith("#") ? css.slice(1) : "";
        if (hex.length !== 6) continue;
        const lum =
          (0.299 * parseInt(hex.slice(0, 2), 16) +
            0.587 * parseInt(hex.slice(2, 4), 16) +
            0.114 * parseInt(hex.slice(4, 6), 16)) /
          255;
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

// PowerPoint shrinks text to fit its placeholder ("Shrink text on overflow").
// The IR carries no such flag, and a fixed font size clips long generated
// titles mid-line (the box is sized for the template's shorter copy). So we
// measure the rendered text against its box and scale it down to fit. Reading
// scrollHeight/scrollWidth (layout metrics, unaffected by CSS transforms) keeps
// the measurement stable across scale changes, so there is no oscillation.
export function AutoFitText({
  shape,
  ptPx,
  themeColors,
  defaultColor,
  groupKey,
  sharedScale,
  onMeasured,
}: {
  shape: TextBoxShape | AutoShape;
  ptPx: number;
  themeColors: Record<string, string>;
  defaultColor: string;
  // Card/column groups (see SlideCanvas) must render at one shared font
  // size — a set of "parallel" cards where one happens to hold more text
  // looking visibly smaller than its siblings reads as broken, not as a
  // feature (confirmed live: two same-size cards independently scaled to
  // 1.0 and 0.52, same font, same box — jarring next to each other). Ungrouped
  // shapes (title, single body box, ...) still fit independently.
  groupKey?: string;
  sharedScale?: number;
  onMeasured?: (groupKey: string, neededScale: number) => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [localScale, setLocalScale] = useState(1);
  const textKey = shape.paragraphs.map((p) => p.runs.map((r) => r.text).join("")).join("|");

  useLayoutEffect(() => {
    const box = boxRef.current;
    const inner = innerRef.current;
    if (!box || !inner) return;
    const bh = box.clientHeight;
    const bw = box.clientWidth;
    const ih = inner.scrollHeight;
    const iw = inner.scrollWidth;
    if (bh <= 0 || bw <= 0 || ih <= 0 || iw <= 0) return;
    const needed = ih > bh || iw > bw ? Math.max(0.3, Math.min(bh / ih, bw / iw, 1)) : 1;
    setLocalScale((prev) => (Math.abs(prev - needed) > 0.01 ? needed : prev));
    if (groupKey && onMeasured) onMeasured(groupKey, needed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textKey, ptPx]);

  const scale = groupKey ? (sharedScale ?? localScale) : localScale;

  return (
    <div
      ref={boxRef}
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <div ref={innerRef} style={{ width: "100%", transform: `scale(${scale})`, transformOrigin: "center center" }}>
        {shape.paragraphs.map((p, pi) => (
          <div
            key={pi}
            style={{
              textAlign: alignToCss(p.alignment),
              paddingLeft: `${p.level * ptPx * 20}px`,
              lineHeight: 1.3,
              margin: 0,
            }}
          >
            {p.runs.length === 0 ? " " : null}
            {p.runs.map((r, ri) => (
              <span
                key={ri}
                style={{
                  fontSize: `${(r.font_size_pt ?? 14) * ptPx}px`,
                  fontWeight: r.bold ? 700 : 400,
                  fontStyle: r.italic ? "italic" : "normal",
                  textDecoration: r.underline ? "underline" : "none",
                  color: colorToCss(r.color, defaultColor, themeColors),
                  fontFamily: r.font_name ? `"${r.font_name}", sans-serif` : "inherit",
                }}
              >
                {r.text}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// Renders the template's own embedded photo/3D-render/illustration — parser
// extracts real image bytes for every Picture shape (confirmed live: 100%
// across every real sample template), so a template with genuine photography
// or custom art (like the polished decks this should look like) already has
// it; the only thing missing was actually drawing it instead of a flat gray
// placeholder box. Crop fractions (PowerPoint's own image cropping) are
// honored by rendering the image oversized and shifted within an
// overflow:hidden box, matching how PowerPoint itself crops in place.
export function UnsplashAttribution({ shape }: { shape: PictureShape }) {
  if (!shape.attribution_text) return null;
  return (
    <a
      href={shape.attribution_url ?? undefined}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        position: "absolute",
        bottom: 2,
        right: 4,
        fontSize: 8,
        lineHeight: 1.2,
        color: "rgba(255,255,255,0.85)",
        background: "rgba(0,0,0,0.45)",
        padding: "1px 4px",
        borderRadius: 2,
        textDecoration: "none",
        pointerEvents: "auto",
        zIndex: 1,
      }}
    >
      {shape.attribution_text}
    </a>
  );
}

export function SlidePicture({ shape }: { shape: PictureShape }) {
  if (!shape.image_bytes_b64) {
    // No embedded bytes (e.g. an external/linked image the parser couldn't
    // inline) — a plain placeholder is honest here, nothing to render.
    return <div style={{ width: "100%", height: "100%", background: "linear-gradient(135deg, #2a2a2a, #1a1a1a)" }} />;
  }
  const mime = shape.content_type || "image/png";
  const src = `data:${mime};base64,${shape.image_bytes_b64}`;
  const { crop_left: cl, crop_top: ct, crop_right: cr, crop_bottom: cb } = shape;
  const hasCrop = cl > 0 || ct > 0 || cr > 0 || cb > 0;
  if (!hasCrop) {
    return (
      <div style={{ position: "relative", width: "100%", height: "100%" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
        <UnsplashAttribution shape={shape} />
      </div>
    );
  }
  const scaleX = 1 / Math.max(0.05, 1 - cl - cr);
  const scaleY = 1 / Math.max(0.05, 1 - ct - cb);
  return (
    <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        style={{
          position: "absolute",
          left: `${-cl * scaleX * 100}%`,
          top: `${-ct * scaleY * 100}%`,
          width: `${scaleX * 100}%`,
          height: `${scaleY * 100}%`,
          objectFit: "cover",
        }}
      />
      <UnsplashAttribution shape={shape} />
    </div>
  );
}

export function SlideTable({ shape, scale }: { shape: TableShape; scale: number }) {
  return (
    <table
      style={{
        width: "100%",
        height: "100%",
        borderCollapse: "collapse",
        tableLayout: "fixed",
        fontSize: `${Math.max(7, 11 * scale * EMU_PER_PT)}px`,
      }}
    >
      <tbody>
        {shape.rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td
                key={ci}
                style={{
                  border: "1px solid rgba(0,0,0,0.15)",
                  padding: "2px 4px",
                  color: "#1a1a1a",
                  fontWeight: ri === 0 ? 700 : 400,
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                }}
              >
                {cell.paragraphs.map((p) => runText(p.runs)).join(" ")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// HTML render of one composed slide: absolutely-positioned divs scaled from the
// slide's EMU geometry. Replaces an earlier SVG+foreignObject renderer that
// hard-clipped overflowing text and fought Chrome's font-size clamp. Kept as
// `SlideCanvas` so call sites are unchanged.
export function SlideCanvas({
  slide,
  slideWidth,
  slideHeight,
  width,
  themeColors,
  roles,
}: {
  slide: Slide;
  slideWidth: number;
  slideHeight: number;
  width: number;
  themeColors: Record<string, string>;
  roles?: Record<string, string>;
}) {
  const scale = width / slideWidth; // px per EMU
  const ptPx = scale * EMU_PER_PT; // px per point
  const height = slideHeight * scale;
  const sorted = [...slide.shapes].sort((a, b) => a.z_order - b.z_order);
  const bg = colorToCss(slide.background, "#fff", themeColors);
  const defaultTextColor = readableTextColor(bg);

  // Card/column groups: >=2 text shapes of identical kind+size that already
  // carry text — same "parallel slot" signal the composer uses server-side
  // (packages/design_system/slots.py) to decide these are one set, not
  // independent boxes. Grouped shapes report their individually-needed
  // scale up via onMeasured; SlideCanvas keeps the group's running minimum
  // so every member renders at the same font size once all have measured.
  const groupKeyByShapeId = new Map<number, string>();
  {
    const bySize = new Map<string, number>();
    for (const s of slide.shapes) {
      if (s.kind !== "text_box" && s.kind !== "autoshape") continue;
      const hasText = s.paragraphs.some((p) => p.runs.some((r) => r.text.trim()));
      if (!hasText) continue;
      const key = `${s.kind}:${s.width}:${s.height}`;
      bySize.set(key, (bySize.get(key) ?? 0) + 1);
    }
    for (const s of slide.shapes) {
      if (s.kind !== "text_box" && s.kind !== "autoshape") continue;
      const key = `${s.kind}:${s.width}:${s.height}`;
      if ((bySize.get(key) ?? 0) >= 2) groupKeyByShapeId.set(s.shape_id, key);
    }
  }
  const [groupScales, setGroupScales] = useState<Record<string, number>>({});
  const handleMeasured = (groupKey: string, needed: number) => {
    setGroupScales((prev) =>
      prev[groupKey] !== undefined && prev[groupKey] <= needed
        ? prev
        : { ...prev, [groupKey]: needed },
    );
  };

  return (
    <div
      style={{
        position: "relative",
        width,
        height,
        background: bg,
        borderRadius: 4,
        border: "1px solid var(--border)",
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      {sorted.map((shape) => {
        const box: React.CSSProperties = {
          position: "absolute",
          left: shape.left * scale,
          top: shape.top * scale,
          width: shape.width * scale,
          height: shape.height * scale,
        };

        if (shape.kind === "picture") {
          return (
            <div key={shape.shape_id} style={{ ...box, overflow: "hidden", background: "#1a1a1a" }}>
              <SlidePicture shape={shape} />
            </div>
          );
        }
        if (shape.kind === "passthrough") {
          // A shape our parser couldn't classify (often a background photo
          // wrapped in a <p:grpSp> group — we don't recurse into groups).
          // Small ones (icons, thin decorative lines) are fine left
          // invisible, but a large one is very often exactly the dark photo
          // a slide's white-on-dark text was designed to sit on — skipping
          // it entirely left that text invisible on the plain white slide
          // background behind it. Give it the same placeholder treatment as
          // a real Picture once it's big enough to plausibly be that photo.
          const areaFrac = (shape.width * shape.height) / (slideWidth * slideHeight);
          if (areaFrac < 0.1) return null;
          return (
            <div key={shape.shape_id} style={{ ...box, ...imagePlaceholderStyle(shape, slide, themeColors) }} />
          );
        }
        if (shape.kind === "table") {
          return (
            <div key={shape.shape_id} style={box}>
              <SlideTable shape={shape} scale={scale} />
            </div>
          );
        }

        const fill =
          shape.kind === "autoshape" && shape.fill_color
            ? colorToCss(shape.fill_color, "transparent", themeColors)
            : "transparent";
        const groupKey = groupKeyByShapeId.get(shape.shape_id);
        return (
          <div key={shape.shape_id} style={{ ...box, background: fill }}>
            <AutoFitText
              shape={shape}
              ptPx={ptPx}
              themeColors={themeColors}
              defaultColor={defaultTextColor}
              groupKey={groupKey}
              sharedScale={groupKey ? groupScales[groupKey] : undefined}
              onMeasured={handleMeasured}
            />
          </div>
        );
      })}
      {roles &&
        sorted.map((shape) => {
          const role = roles[String(shape.shape_id)];
          const style = role ? ROLE_STYLE[role] : undefined;
          if (!style) return null;
          return (
            <div
              key={`role-${shape.shape_id}`}
              title={`${style[1]} — ${style[2]}`}
              style={{
                position: "absolute",
                left: shape.left * scale,
                top: shape.top * scale,
                width: shape.width * scale,
                height: shape.height * scale,
                border: `2px dashed ${style[0]}`,
                background: `${style[0]}22`,
                pointerEvents: "none",
                zIndex: 5,
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  fontSize: 10,
                  lineHeight: 1.2,
                  padding: "1px 4px",
                  background: style[0],
                  color: "#000",
                  whiteSpace: "nowrap",
                }}
              >
                {style[1]}
              </span>
            </div>
          );
        })}
    </div>
  );
}
