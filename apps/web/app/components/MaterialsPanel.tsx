import type { CSSProperties } from "react";
import type { TaskMaterials } from "../lib/types";

const storyField: CSSProperties = {
  width: "100%",
  background: "#0a0a0a",
  color: "var(--foreground)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "0.4rem 0.5rem",
  fontFamily: "inherit",
  fontSize: "0.8rem",
  resize: "vertical",
};

// "Материалы задачи": files and the team's story that go with a brief.
export function MaterialsPanel({
  open,
  onToggle,
  materials,
  onChange,
  onPickFiles,
  disabled,
}: {
  open: boolean;
  onToggle: () => void;
  materials: TaskMaterials;
  onChange: (m: TaskMaterials) => void;
  onPickFiles: () => void;
  disabled: boolean;
}) {
  const count = materials.files.length + (materials.story.trim() ? 1 : 0);
  return (
    <div style={{ marginBottom: "0.5rem" }}>
      <button
        onClick={onToggle}
        disabled={disabled}
        aria-expanded={open}
        style={{
          background: "transparent",
          color: count ? "var(--foreground)" : "var(--muted)",
          border: "none",
          padding: 0,
          fontSize: "0.78rem",
          cursor: disabled ? "default" : "pointer",
        }}
      >
        {open ? "▾" : "▸"} Материалы задачи{count ? ` (${count})` : ""} — репозиторий (.zip), документация, история
      </button>
      {open && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            marginTop: "0.5rem",
            padding: "0.75rem",
            border: "1px solid var(--border)",
            borderRadius: 10,
            background: "#111",
          }}
        >
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <button
              onClick={onPickFiles}
              disabled={disabled}
              style={{
                background: "#1d1d1d",
                color: "var(--foreground)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.35rem 0.7rem",
                fontSize: "0.78rem",
                cursor: "pointer",
              }}
            >
              + Файлы (.zip репозитория, .md, .pdf, .docx, .pptx, скриншоты)
            </button>
            {materials.files.map((f, i) => (
              <span
                key={`${f.name}-${i}`}
                style={{
                  fontSize: "0.72rem",
                  border: "1px solid var(--border)",
                  borderRadius: 999,
                  padding: "0.15rem 0.5rem",
                  display: "flex",
                  gap: "0.35rem",
                  alignItems: "center",
                }}
              >
                {f.name}
                <button
                  onClick={() => onChange({ ...materials, files: materials.files.filter((_, j) => j !== i) })}
                  aria-label={`Убрать ${f.name}`}
                  style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", padding: 0 }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
          <textarea
            value={materials.story}
            onChange={(e) => onChange({ ...materials, story: e.target.value })}
            placeholder="История команды: кто вы, как пришли к решению, что пробовали и что не сработало, чем гордитесь"
            aria-label="История команды"
            rows={3}
            style={storyField}
          />
        </div>
      )}
    </div>
  );
}
