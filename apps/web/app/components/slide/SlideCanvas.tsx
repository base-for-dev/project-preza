import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { ROLE_STYLE } from "../../lib/constants";
import { EMU_PER_PT, colorToCss, imagePlaceholderStyle, readableTextColor } from "../../lib/slideColors";
import { useTemplateFonts } from "../../lib/templateFonts";
import type { Slide } from "../../lib/types";
import { AutoFitText } from "./AutoFitText";
import { SlidePicture } from "./SlidePicture";
import { SlideTable } from "./SlideTable";

// Card/column groups: >=2 text shapes of identical kind+size that already
// carry text — same "parallel slot" signal the composer uses server-side
// (packages/design_system/slots.py) to decide these are one set, not
// independent boxes. Grouped shapes report their individually-needed
// scale up via onMeasured; SlideCanvas keeps the group's running minimum
// so every member renders at the same font size once all have measured.
function groupKeysByShapeId(slide: Slide): Map<number, string> {
  const groupKeyByShapeId = new Map<number, string>();
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
  return groupKeyByShapeId;
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
  backdropUrl,
}: {
  slide: Slide;
  slideWidth: number;
  slideHeight: number;
  width: number;
  themeColors: Record<string, string>;
  // shape_id -> slot role; draws the template inspector's role overlay.
  roles?: Record<string, string>;
  // The slide as the file really renders (LibreOffice image). Drawn instead of
  // our own reconstruction once it loads — that can't show group/freeform
  // artwork, picture-filled shapes or master decoration — with the role
  // overlay on top. Falls back to the reconstruction if it fails to load.
  backdropUrl?: string;
}) {
  const [backdrop, setBackdrop] = useState<"loading" | "ok" | "failed">("loading");
  useEffect(() => setBackdrop("loading"), [backdropUrl]);
  const showShapes = !backdropUrl || backdrop !== "ok";
  const scale = width / slideWidth; // px per EMU
  const ptPx = scale * EMU_PER_PT; // px per point
  const height = slideHeight * scale;
  const sorted = useMemo(() => [...slide.shapes].sort((a, b) => a.z_order - b.z_order), [slide]);
  const bg = colorToCss(slide.background, "#fff", themeColors);
  const defaultTextColor = readableTextColor(bg);

  const groupKeyByShapeId = useMemo(() => groupKeysByShapeId(slide), [slide]);
  const fontFamilies = useMemo(
    () =>
      slide.shapes.flatMap((s) =>
        "paragraphs" in s ? s.paragraphs.flatMap((p) => p.runs.map((r) => r.font_name ?? "")) : [],
      ),
    [slide],
  );
  useTemplateFonts(fontFamilies);
  const [groupScales, setGroupScales] = useState<Record<string, number>>({});
  const handleMeasured = useCallback((groupKey: string, needed: number) => {
    setGroupScales((prev) =>
      prev[groupKey] !== undefined && prev[groupKey] <= needed
        ? prev
        : { ...prev, [groupKey]: needed },
    );
  }, []);

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
      {backdropUrl && backdrop !== "failed" && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={backdropUrl}
          alt=""
          onLoad={() => setBackdrop("ok")}
          onError={() => setBackdrop("failed")}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "fill",
            zIndex: 4,
            opacity: backdrop === "ok" ? 1 : 0,
          }}
        />
      )}
      {showShapes && sorted.map((shape) => {
        const box: CSSProperties = {
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
        if (shape.kind === "chart" || shape.kind === "diagram") {
          // Drawn by the exporter as native objects; this fallback preview
          // only marks where they go and what they hold.
          const label = shape.kind === "chart" ? `График: ${shape.title || shape.chart_type}` : `Диаграмма: ${shape.diagram_type}`;
          const words = shape.kind === "chart" ? shape.categories : shape.items.map((i) => i.label);
          return (
            <div
              key={shape.shape_id}
              style={{
                ...box,
                border: "1px dashed #8884",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                color: defaultTextColor,
                textAlign: "center",
                overflow: "hidden",
              }}
            >
              <strong>{label}</strong>
              <span>{words.join(" · ")}</span>
            </div>
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
