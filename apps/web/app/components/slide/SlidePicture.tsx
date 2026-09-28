import type { PictureShape } from "../../lib/types";

function UnsplashAttribution({ shape }: { shape: PictureShape }) {
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

// Renders the template's own embedded photo/3D-render/illustration — parser
// extracts real image bytes for every Picture shape (confirmed live: 100%
// across every real sample template), so a template with genuine photography
// or custom art (like the polished decks this should look like) already has
// it; the only thing missing was actually drawing it instead of a flat gray
// placeholder box. Crop fractions (PowerPoint's own image cropping) are
// honored by rendering the image oversized and shifted within an
// overflow:hidden box, matching how PowerPoint itself crops in place.
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
