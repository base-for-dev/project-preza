import { useState } from "react";
import { ACCENTS, loadAppearance, saveAppearance, type Appearance, type Theme } from "../lib/appearance";

const THEMES: { id: Theme; label: string }[] = [
  { id: "system", label: "Как в системе" },
  { id: "light", label: "Светлое" },
  { id: "dark", label: "Тёмное" },
];

// Appearance: a segmented control for light / dark / system and a row of accent
// swatches (plus any colour of your own). Applies at once and is remembered.
export function AppearanceSettings() {
  const [value, setValue] = useState<Appearance>(() => loadAppearance());
  const set = (patch: Partial<Appearance>) => {
    const next = { ...value, ...patch };
    setValue(next);
    saveAppearance(next);
  };
  const custom = value.accent.startsWith("#");

  return (
    <section style={{ marginBottom: "var(--s6)", paddingBottom: "var(--s5)", borderBottom: "0.5px solid var(--separator)" }}>
      <strong style={{ fontSize: "var(--t-headline)" }}>Оформление</strong>

      <div role="radiogroup" aria-label="Тема" style={{ display: "flex", padding: 2, borderRadius: 9, background: "var(--fill)", marginTop: "var(--s3)" }}>
        {THEMES.map((t) => (
          <button
            key={t.id}
            role="radio"
            aria-checked={value.theme === t.id}
            onClick={() => set({ theme: t.id })}
            style={{
              flex: 1,
              minHeight: 30,
              border: "none",
              borderRadius: 7,
              fontSize: "var(--t-subhead)",
              fontWeight: value.theme === t.id ? 600 : 500,
              background: value.theme === t.id ? "var(--surface)" : "transparent",
              boxShadow: value.theme === t.id ? "var(--shadow-1)" : "none",
              color: "var(--label)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="caption" style={{ margin: "var(--s4) 0 var(--s2)" }}>Акцентный цвет</div>
      <div style={{ display: "flex", gap: "var(--s3)", alignItems: "center", flexWrap: "wrap" }} role="radiogroup" aria-label="Акцентный цвет">
        {ACCENTS.map((a) => (
          <button
            key={a.id}
            role="radio"
            aria-checked={value.accent === a.id}
            aria-label={a.label}
            title={a.label}
            onClick={() => set({ accent: a.id })}
            style={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              border: "none",
              background: `var(--${a.id})`,
              boxShadow: value.accent === a.id ? "0 0 0 2px var(--bg), 0 0 0 4px var(--label-2)" : "none",
              padding: 0,
            }}
          />
        ))}
        <label
          title="Свой цвет"
          style={{
            position: "relative",
            width: 28,
            height: 28,
            borderRadius: "50%",
            overflow: "hidden",
            background: "conic-gradient(red, yellow, lime, aqua, blue, magenta, red)",
            boxShadow: custom ? "0 0 0 2px var(--bg), 0 0 0 4px var(--label-2)" : "none",
            cursor: "pointer",
          }}
        >
          <input
            type="color"
            aria-label="Свой цвет"
            value={custom ? value.accent : "#007aff"}
            onChange={(e) => set({ accent: e.target.value })}
            style={{ position: "absolute", inset: -8, width: 48, height: 48, opacity: 0, cursor: "pointer" }}
          />
        </label>
      </div>
    </section>
  );
}
