"use client";

import { GENERATION_BUDGET_SECONDS } from "../lib/config";
import { Density, TaskMaterials, formatSeconds, VARIANTS, StageStatus } from "../lib/model";

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
  const count =
    materials.files.length +
    (materials.story.trim() ? 1 : 0);
  const field = {
    width: "100%",
    background: "#0a0a0a",
    color: "var(--foreground)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "0.4rem 0.5rem",
    fontFamily: "inherit",
    fontSize: "0.8rem",
  } as const;
  return (
    <div style={{ marginBottom: "0.5rem" }}>
      <button
        onClick={onToggle}
        disabled={disabled}
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
              + Файлы (.zip репозитория, .md, .pdf, .docx, .pptx)
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
            rows={3}
            style={{ ...field, resize: "vertical" }}
          />
        </div>
      )}
    </div>
  );
}

export function BudgetTimer({
  busy,
  startedAt,
  now,
  lastTotal,
}: {
  busy: boolean;
  startedAt: number | null;
  now: number;
  lastTotal: number | null;
}) {
  const elapsed = busy && startedAt ? (now - startedAt) / 1000 : lastTotal;
  if (elapsed === null) return null;
  const share = Math.min(1, elapsed / GENERATION_BUDGET_SECONDS);
  const over = elapsed > GENERATION_BUDGET_SECONDS;
  return (
    <div style={{ marginTop: "1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.3rem" }}>
        <span style={{ color: "var(--muted)" }}>{busy ? "Идёт генерация" : "Сгенерировано за"}</span>
        <span style={{ color: over ? "#f87171" : "var(--foreground)" }}>
          {formatSeconds(elapsed)} / {formatSeconds(GENERATION_BUDGET_SECONDS)}
        </span>
      </div>
      <div style={{ height: 4, background: "#222", borderRadius: 2, overflow: "hidden" }}>
        <div
          style={{
            width: `${share * 100}%`,
            height: "100%",
            background: over ? "#f87171" : "#4ade80",
            transition: "width 0.5s linear",
          }}
        />
      </div>
    </div>
  );
}

export function StageDot({ status }: { status: StageStatus }) {
  const color = { idle: "#333", active: "#e8c547", done: "#4ade80", error: "#f87171" }[status];
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
        animation: status === "active" ? "pulse-ring 1.4s ease-out infinite" : "none",
      }}
    />
  );
}

export function ThinkingBubble({ text }: { text: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "0.75rem 1rem",
        background: "#111",
        width: "fit-content",
      }}
    >
      <span style={{ display: "flex", gap: "3px" }}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 5,
              height: 5,
              borderRadius: "50%",
              background: "#e8c547",
              animation: "dot-blink 1.2s infinite",
              animationDelay: `${i * 0.15}s`,
            }}
          />
        ))}
      </span>
      <span
        style={{
          fontSize: "0.82rem",
          background:
            "linear-gradient(90deg, var(--muted) 40%, var(--foreground) 50%, var(--muted) 60%)",
          backgroundSize: "200% auto",
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          color: "transparent",
          animation: "shimmer 2.2s linear infinite",
        }}
      >
        {text}
      </span>
    </div>
  );
}

export function DensityQuestion({
  answered,
  onPick,
}: {
  answered: Density | null;
  onPick: (density: Density) => void;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "1rem",
        background: "#111",
        width: "fit-content",
      }}
    >
      <div style={{ fontSize: "0.85rem", marginBottom: answered ? 0 : "0.75rem" }}>
        Насколько подробной должна быть презентация?
      </div>
      {!answered && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {VARIANTS.map((v) => (
            <button
              key={v.key}
              onClick={() => onPick(v.key)}
              style={{
                background: "#1d1d1d",
                color: "var(--foreground)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.4rem 0.8rem",
                fontSize: "0.82rem",
                cursor: "pointer",
              }}
            >
              {v.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
