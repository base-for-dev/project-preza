import { useEffect, useMemo, useState } from "react";
import { templatePreviewUrl } from "../lib/api";
import { AUTO_TEMPLATE_OPTION } from "../lib/constants";
import { closeButton } from "../lib/styles";
import type { TemplateInfo } from "../lib/types";
import { TemplateInspector } from "./TemplateInspector";

// Theme picker modal: a searchable, filterable grid of real rendered template
// covers on the left, a stacked preview of the selected template's slides on
// the right, and "Подробнее" (the selected template's structure) / "Выбрать
// тему" at the bottom. The choice is only applied on "Выбрать тему" —
// browsing never changes the current template.

const FILTERS: { key: string; label: string }[] = [
  { key: "dark", label: "Тёмные" },
  { key: "light", label: "Светлые" },
  { key: "business", label: "Деловые" },
  { key: "colorful", label: "Яркие" },
];

// App palette (see globals.css / lib/styles.ts): dark panels, hairline
// borders, light primary button.
const INK = "var(--foreground)";
const MUTED = "var(--muted)";
const PANEL = "#111";
const FIELD = "#0a0a0a";
const CARD = "#151515";
const CARD_ACTIVE = "#1d1d1d";

export function prettyName(label: string): string {
  const name = label.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function TemplatePicker({
  templates,
  currentId,
  autoLabel,
  uploading,
  onUpload,
  onChoose,
  onClose,
}: {
  templates: TemplateInfo[];
  currentId: string;
  // "Авто (по теме брифа)" or "Из бренд-пакета", depending on the sidebar.
  autoLabel: string;
  uploading: boolean;
  onUpload: () => void;
  onChoose: (templateId: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<string[]>([]);
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

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return templates.filter(
      (t) =>
        (!q || prettyName(t.label).toLowerCase().includes(q)) &&
        filters.every((f) => (t.tags ?? []).includes(f)),
    );
  }, [templates, query, filters]);

  const current = templates.find((t) => t.id === selected);

  function toggleFilter(key: string) {
    setFilters((prev) => (prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key]));
  }

  function shuffle() {
    const pool = visible.filter((t) => t.id !== selected);
    const pick = pool[Math.floor(Math.random() * pool.length)];
    if (pick) setSelected(pick.id);
  }

  return (
    <>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Выбор шаблона"
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.6)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 60,
          padding: "2rem",
        }}
      >
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            width: "min(1140px, 96vw)",
            height: "min(800px, 92vh)",
            display: "grid",
            gridTemplateColumns: "minmax(300px, 38%) minmax(0, 1fr)",
            gridTemplateRows: "1fr auto",
            borderRadius: 10,
            overflow: "hidden",
            border: "1px solid var(--border)",
            boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
          }}
        >
          {/* Left: search, filters, grid */}
          <div style={{ background: PANEL, color: INK, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ padding: "1.1rem 1.2rem 0.6rem" }}>
              <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>Все темы</div>
              <div style={{ fontSize: "0.85rem", color: MUTED, margin: "0.3rem 0 0.9rem" }}>
                Просмотреть и выбрать из всех тем
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Поиск темы"
                  aria-label="Поиск темы"
                  autoFocus
                  style={{
                    flex: 1,
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "0.5rem 0.7rem",
                    fontSize: "0.85rem",
                    background: FIELD,
                    color: INK,
                    outline: "none",
                  }}
                />
                <button
                  onClick={shuffle}
                  title="Случайная тема"
                  aria-label="Случайная тема"
                  style={{
                    width: 38,
                    borderRadius: 6,
                    border: "1px solid var(--border)",
                    background: FIELD,
                    color: INK,
                    fontSize: "1rem",
                    cursor: "pointer",
                  }}
                >
                  ⤮
                </button>
              </div>
              <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                {FILTERS.map((f) => {
                  const on = filters.includes(f.key);
                  return (
                    <button
                      key={f.key}
                      onClick={() => toggleFilter(f.key)}
                      aria-pressed={on}
                      style={{
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        padding: "0.25rem 0.6rem",
                        fontSize: "0.78rem",
                        cursor: "pointer",
                        background: on ? "#ededed" : CARD,
                        color: on ? "#0a0a0a" : INK,
                      }}
                    >
                      {f.label}
                    </button>
                  );
                })}
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
                  <Cover template={t} n={0} />
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
              background: "#0a0a0a",
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
              style={{ ...closeButton, position: "absolute", top: 12, right: 12, zIndex: 2, background: "#111" }}
            >
              Закрыть ✕
            </button>
            {current ? (
              <PreviewStack template={current} />
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
                borderRadius: 6,
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
                borderRadius: 6,
                border: "none",
                background: "#ededed",
                color: "#0a0a0a",
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
          : `1px solid ${active ? "#ededed" : "var(--border)"}`,
        borderRadius: 8,
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

function Cover({ template, n }: { template: TemplateInfo; n: number }) {
  const [failed, setFailed] = useState(false);
  if (!template.previews || failed) {
    return (
      <div style={placeholderArt("#1a1a1a")}>
        <span style={{ fontSize: "0.72rem", color: MUTED }}>
          {template.previews === 0 ? "готовим превью…" : "нет превью"}
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
function PreviewStack({ template }: { template: TemplateInfo }) {
  const count = Math.min(template.previews ?? 0, 4);
  if (count === 0) {
    return <div style={{ color: MUTED }}>Готовим превью этого шаблона…</div>;
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
            borderRadius: 8,
            boxShadow: "0 12px 40px rgba(0,0,0,0.55)",
            opacity: i === 0 ? 1 : 0.9,
          }}
        />
      ))}
    </div>
  );
}
