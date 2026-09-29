import { useEffect, useState } from "react";
import { inspectTemplate, templatePreviewUrl } from "../lib/api";
import { AUTO_TEMPLATE_OPTION } from "../lib/constants";
import { closeButton } from "../lib/styles";
import type { TemplateInfo } from "../lib/types";
import { SlideCanvas } from "./slide/SlideCanvas";
import { TemplateInspector } from "./TemplateInspector";

// Theme picker modal: a grid of real rendered template covers on the left, a
// stacked preview of the selected template's slides on the right, and
// "Подробнее" (the selected template's structure) / "Выбрать тему" at the
// bottom. The choice is only applied on "Выбрать тему" — browsing never
// changes the current template.

// App palette (see globals.css / lib/styles.ts): dark panels, hairline
// borders, light primary button.
const INK = "var(--foreground)";
const MUTED = "var(--muted)";
const PANEL = "var(--bg-3)";
const CARD = "var(--fill-2)";
const CARD_ACTIVE = "var(--fill)";

export function prettyName(label: string): string {
  const name = label.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function TemplatePicker({
  templates,
  currentId,
  autoLabel,
  uploading,
  rendererAvailable,
  onUpload,
  onChoose,
  onClose,
}: {
  templates: TemplateInfo[];
  currentId: string;
  // "Авто (по теме брифа)" or "Из бренд-пакета", depending on the sidebar.
  autoLabel: string;
  uploading: boolean;
  // False when the server has no LibreOffice to render real template
  // thumbnails with — the picker then skips straight to a client-drawn
  // fallback instead of showing a "готовим превью…" that will never resolve.
  rendererAvailable: boolean;
  onUpload: () => void;
  onChoose: (templateId: string) => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(currentId);
  const [inspecting, setInspecting] = useState(false);

  useEffect(() => {
    // While the inspector is open, Escape is its to handle — closing it
    // should land back in the picker, not close both.
    if (inspecting) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, inspecting]);

  const visible = templates;
  const current = templates.find((t) => t.id === selected);

  return (
    <>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Выбор шаблона"
        onClick={onClose}
        className="scrim"
        style={{
          position: "fixed",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 60,
          padding: "2rem",
        }}
      >
        <div
          onClick={(e) => e.stopPropagation()}
          className="sheet"
          style={{
            width: "min(1140px, 96vw)",
            height: "min(800px, 92vh)",
            display: "grid",
            gridTemplateColumns: "minmax(300px, 38%) minmax(0, 1fr)",
            gridTemplateRows: "1fr auto",
            overflow: "hidden",
          }}
        >
          {/* Left: grid */}
          <div style={{ background: PANEL, color: INK, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ padding: "1.1rem 1.2rem 0.6rem" }}>
              <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>Все темы</div>
              <div style={{ fontSize: "0.85rem", color: MUTED, margin: "0.3rem 0 0.9rem" }}>
                Просмотреть и выбрать из всех тем
              </div>
            </div>
            <div
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "0.4rem 0.6rem 1rem",
                display: "grid",
                gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                gap: "0.5rem",
                alignContent: "start",
              }}
            >
              <PickerCard
                active={selected === AUTO_TEMPLATE_OPTION}
                title={autoLabel}
                onClick={() => setSelected(AUTO_TEMPLATE_OPTION)}
              >
                <div style={placeholderArt(CARD_ACTIVE)}>
                  <span style={{ fontSize: "1.6rem" }}>✨</span>
                  <span style={{ fontSize: "0.72rem", color: MUTED, textAlign: "center" }}>
                    подберём по теме
                  </span>
                </div>
              </PickerCard>
              {visible.map((t) => (
                <PickerCard
                  key={t.id}
                  active={selected === t.id}
                  title={prettyName(t.label)}
                  onClick={() => setSelected(t.id)}
                  onDoubleClick={() => onChoose(t.id)}
                >
                  <Cover template={t} n={0} rendererAvailable={rendererAvailable} />
                </PickerCard>
              ))}
              <PickerCard active={false} title={uploading ? "Загрузка…" : "Свой шаблон"} onClick={onUpload} dashed>
                <div style={placeholderArt("transparent")}>
                  <span style={{ fontSize: "1.6rem" }}>＋</span>
                  <span style={{ fontSize: "0.72rem", color: MUTED }}>загрузить .pptx</span>
                </div>
              </PickerCard>
              {visible.length === 0 && (
                <div style={{ gridColumn: "1 / -1", fontSize: "0.85rem", color: MUTED, padding: "1rem" }}>
                  Ничего не нашлось — измените поиск или фильтры.
                </div>
              )}
            </div>
          </div>

          {/* Right: preview */}
          <div
            style={{
              position: "relative",
              background: "var(--fill-2)",
              borderLeft: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              overflow: "hidden",
            }}
          >
            <button
              onClick={onClose}
              aria-label="Закрыть"
              style={{ ...closeButton, position: "absolute", top: 12, right: 12, zIndex: 2, background: "var(--bg-3)" }}
            >
              Закрыть ✕
            </button>
            {current ? (
              <PreviewStack template={current} rendererAvailable={rendererAvailable} />
            ) : (
              <div style={{ color: MUTED, textAlign: "center", maxWidth: 380, lineHeight: 1.5 }}>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, marginBottom: "0.5rem", color: INK }}>
                  {autoLabel}
                </div>
                Шаблон подберём сами по теме брифа{autoLabel.includes("пакет") ? " из вашего бренд-пакета" : ""}.
              </div>
            )}
          </div>

          {/* Footer */}
          <div
            style={{
              gridColumn: "1 / -1",
              background: PANEL,
              borderTop: "1px solid var(--border)",
              display: "flex",
              justifyContent: "flex-end",
              gap: "0.6rem",
              padding: "0.8rem 1rem",
            }}
          >
            <button
              onClick={() => setInspecting(true)}
              disabled={selected === AUTO_TEMPLATE_OPTION}
              title={
                selected === AUTO_TEMPLATE_OPTION
                  ? "Шаблон подбирается автоматически — выберите конкретный, чтобы посмотреть его структуру"
                  : "Структура шаблона: какие поля заполнит генерация на каждом слайде"
              }
              style={{
                minWidth: 140,
                borderRadius: "var(--r-sm)",
                border: "1px solid var(--border)",
                background: "transparent",
                color: INK,
                padding: "0.5rem 1rem",
                fontSize: "0.85rem",
                fontWeight: 600,
                cursor: selected === AUTO_TEMPLATE_OPTION ? "not-allowed" : "pointer",
                opacity: selected === AUTO_TEMPLATE_OPTION ? 0.4 : 1,
              }}
            >
              Подробнее
            </button>
            <button
              onClick={() => onChoose(selected)}
              style={{
                minWidth: 140,
                borderRadius: "var(--r-sm)",
                border: "none",
                background: "var(--accent)",
                color: "var(--on-accent)",
                padding: "0.5rem 1rem",
                fontSize: "0.85rem",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Выбрать тему
            </button>
          </div>
        </div>
      </div>
      {/* A sibling, not a child: clicks inside it must not reach the picker's
          backdrop, and being later in the DOM puts it on top at the same z-index. */}
      {inspecting && selected !== AUTO_TEMPLATE_OPTION && (
        <TemplateInspector templateId={selected} onClose={() => setInspecting(false)} />
      )}
    </>
  );
}

function placeholderArt(background: string) {
  return {
    aspectRatio: "16 / 9",
    background,
    borderRadius: 4,
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    gap: "0.2rem",
    color: INK,
  };
}

function PickerCard({
  active,
  title,
  onClick,
  onDoubleClick,
  dashed,
  children,
}: {
  active: boolean;
  title: string;
  onClick: () => void;
  onDoubleClick?: () => void;
  dashed?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      aria-pressed={active}
      style={{
        minWidth: 0,
        textAlign: "left",
        background: active ? CARD_ACTIVE : CARD,
        border: dashed
          ? "1px dashed var(--border)"
          : `1px solid ${active ? "var(--label)" : "var(--border)"}`,
        borderRadius: "var(--r-sm)",
        padding: 6,
        cursor: "pointer",
        color: INK,
      }}
    >
      {children}
      <div
        style={{
          fontSize: "0.82rem",
          marginTop: 6,
          color: active ? INK : MUTED,
          fontWeight: active ? 600 : 400,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {active ? "✓ " : ""}
        {title}
      </div>
    </button>
  );
}

function Cover({
  template,
  n,
  rendererAvailable,
}: {
  template: TemplateInfo;
  n: number;
  rendererAvailable: boolean;
}) {
  const [failed, setFailed] = useState(false);
  if (!template.previews || failed) {
    return (
      <div style={placeholderArt("var(--fill-2)")}>
        <span style={{ fontSize: "0.72rem", color: MUTED }}>
          {template.previews === 0 && rendererAvailable ? "готовим превью…" : prettyName(template.label)}
        </span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={templatePreviewUrl(template.id, n)}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      style={{ width: "100%", aspectRatio: "16 / 9", objectFit: "cover", display: "block", borderRadius: 4 }}
    />
  );
}

// Cover in front, a few more slides fanned out behind it — like leafing
// through the deck.
function PreviewStack({
  template,
  rendererAvailable,
}: {
  template: TemplateInfo;
  rendererAvailable: boolean;
}) {
  const count = Math.min(template.previews ?? 0, 4);
  if (count === 0) {
    return rendererAvailable ? (
      <div style={{ color: MUTED }}>Готовим превью этого шаблона…</div>
    ) : (
      <ClientPreview templateId={template.id} />
    );
  }
  const layers = Array.from({ length: count }, (_, i) => i).reverse();
  return (
    <div style={{ position: "relative", width: "78%", aspectRatio: "16 / 11" }}>
      {layers.map((i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={`${template.id}-${i}`}
          src={templatePreviewUrl(template.id, i)}
          alt={i === 0 ? `Обложка шаблона ${prettyName(template.label)}` : ""}
          style={{
            position: "absolute",
            width: i === 0 ? "88%" : "70%",
            left: i === 0 ? "6%" : `${2 + (i - 1) * 14}%`,
            top: i === 0 ? "22%" : `${2 + (i - 1) * 3}%`,
            transform: i === 0 ? "none" : `rotate(${(i - 2) * 2}deg)`,
            borderRadius: "var(--r-sm)",
            boxShadow: "0 12px 40px rgba(0,0,0,0.55)",
            opacity: i === 0 ? 1 : 0.9,
          }}
        />
      ))}
    </div>
  );
}


// Fallback for when the server has no LibreOffice to render real thumbnails:
// the first slide drawn client-side from the template's own IR, same
// reconstruction the audit result and inspector already fall back to.
function ClientPreview({ templateId }: { templateId: string }) {
  const [state, setState] = useState<
    { status: "loading" } | { status: "error" } | { status: "ready"; data: Awaited<ReturnType<typeof inspectTemplate>> }
  >({ status: "loading" });
  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    inspectTemplate(templateId)
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch(() => !cancelled && setState({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  if (state.status === "loading") return <div style={{ color: MUTED }}>Загружаю шаблон…</div>;
  if (state.status === "error") return <div style={{ color: MUTED }}>Нет предпросмотра</div>;
  const { deck } = state.data;
  const slide = deck.slides[0];
  if (!slide) return <div style={{ color: MUTED }}>Нет предпросмотра</div>;
  return (
    <SlideCanvas
      slide={slide}
      slideWidth={deck.slide_width}
      slideHeight={deck.slide_height}
      width={420}
      themeColors={deck.theme_colors}
    />
  );
}
