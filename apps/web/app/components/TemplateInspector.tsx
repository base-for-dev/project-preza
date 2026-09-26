"use client";

import { useEffect, useState } from "react";
import { API_URL } from "../lib/config";
import { InspectedTemplate, ROLE_STYLE } from "../lib/model";
import { SlideCanvas } from "./slide/SlideCanvas";

export function TemplateInspector({ templateId, onClose }: { templateId: string; onClose: () => void }) {
  const [data, setData] = useState<InspectedTemplate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [showOverlay, setShowOverlay] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/templates/${encodeURIComponent(templateId)}/inspect`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: InspectedTemplate) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(String(e.message ?? e)));
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setSelected((i) => (data ? Math.min(i + 1, data.slides.length - 1) : i));
      if (e.key === "ArrowLeft") setSelected((i) => Math.max(i - 1, 0));
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, data]);

  const slide = data?.deck.slides[selected];
  const info = data?.slides[selected];
  const usedRoles = info ? Array.from(new Set(Object.values(info.roles))).filter((r) => ROLE_STYLE[r]) : [];
  const counts = (role: string) => Object.values(info?.roles ?? {}).filter((r) => r === role).length;

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 60, display: "flex", padding: "1.5rem" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          display: "flex",
          gap: "1rem",
          width: "100%",
          background: "#0d0d0d",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "1rem",
          overflow: "hidden",
        }}
      >
        <div style={{ width: 190, overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.5rem", flexShrink: 0 }}>
          {data?.deck.slides.map((sl, i) => (
            <div
              key={sl.index}
              onClick={() => setSelected(i)}
              style={{
                cursor: "pointer",
                outline: i === selected ? "2px solid var(--foreground)" : "1px solid var(--border)",
                borderRadius: 4,
              }}
            >
              <SlideCanvas
                slide={sl}
                slideWidth={data.deck.slide_width}
                slideHeight={data.deck.slide_height}
                width={186}
                themeColors={data.deck.theme_colors}
              />
              <div style={{ fontSize: "0.65rem", color: "var(--muted)", padding: "2px 4px" }}>
                {i + 1}. {sl.layout_name}
              </div>
            </div>
          ))}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "0.75rem", overflowY: "auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
            <span style={{ fontSize: "0.85rem" }}>
              {templateId} · слайд {selected + 1}/{data?.slides.length ?? "…"} · <b>{info?.layout_name}</b>
            </span>
            <span style={{ display: "flex", gap: "0.5rem" }}>
              <label style={{ fontSize: "0.75rem", display: "flex", gap: 4, alignItems: "center", cursor: "pointer" }}>
                <input type="checkbox" checked={showOverlay} onChange={(e) => setShowOverlay(e.target.checked)} />
                Показать роли
              </label>
              <button
                onClick={onClose}
                style={{ background: "transparent", border: "1px solid var(--border)", borderRadius: 6, color: "var(--foreground)", padding: "0.25rem 0.6rem", fontSize: "0.8rem", cursor: "pointer" }}
              >
                Закрыть ✕
              </button>
            </span>
          </div>
          {error && <div style={{ color: "#ff8080", fontSize: "0.8rem" }}>Не удалось загрузить шаблон: {error}</div>}
          {!data && !error && <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>Загружаю шаблон…</div>}
          {slide && info && data && (
            <>
              <SlideCanvas
                slide={slide}
                slideWidth={data.deck.slide_width}
                slideHeight={data.deck.slide_height}
                width={860}
                themeColors={data.deck.theme_colors}
                roles={showOverlay ? info.roles : undefined}
              />
              <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", fontSize: "0.78rem" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {usedRoles.map((r) => (
                    <div key={r} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span style={{ width: 12, height: 12, border: `2px dashed ${ROLE_STYLE[r]![0]}`, display: "inline-block" }} />
                      <span>
                        <b>{ROLE_STYLE[r]![1]}</b> ×{counts(r)} — {ROLE_STYLE[r]![2]}
                      </span>
                    </div>
                  ))}
                </div>
                <div style={{ color: "var(--muted)", display: "flex", flexDirection: "column", gap: 2 }}>
                  <span>Карточек: {info.slots.card_slots} · Текстовых областей: {info.slots.body_slots}</span>
                  <span>Таблица: {info.slots.has_table ? "да" : "нет"} · Картинка: {info.slots.has_picture ? "да" : "нет"}</span>
                  {info.slots.body_lines != null && (
                    <span>
                      Вместимость текста: ~{info.slots.body_lines} стр. по ~{info.slots.body_chars_per_line} симв.
                    </span>
                  )}
                  {info.slots.title_font_size_pt != null && (
                    <span>Крупный заголовок {Math.round(info.slots.title_font_size_pt)}pt — пишем коротко</span>
                  )}
                  <span style={{ fontSize: "0.7rem" }}>Навигация: ← → · Esc — закрыть</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
