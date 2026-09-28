import { PIPELINE_STAGES } from "../lib/constants";
import { sectionLabel } from "../lib/styles";
import type { StageStatus } from "../lib/types";
import { BudgetTimer } from "./BudgetTimer";
import { StageDot } from "./StageDot";

// Right panel: pipeline progress of the chat on screen.
export function PipelinePanel({
  stages,
  busy,
  startedAt,
  lastTotal,
}: {
  stages: Record<string, StageStatus>;
  busy: boolean;
  startedAt: number | null;
  lastTotal: number | null;
}) {
  return (
    <aside
      style={{
        width: 240,
        borderLeft: "1px solid var(--border)",
        padding: "1.25rem 1rem",
        flexShrink: 0,
      }}
    >
      <div style={{ ...sectionLabel, marginBottom: "0.75rem" }}>Что происходит</div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        {PIPELINE_STAGES.map((s) => {
          const status: StageStatus = s.disabled ? "idle" : stages[s.key] ?? "idle";
          return (
            <div key={s.key} style={{ display: "flex", alignItems: "center", gap: "0.5rem", opacity: s.disabled ? 0.4 : 1 }}>
              <StageDot status={status} />
              <span style={{ fontSize: "0.82rem" }}>{s.label}</span>
            </div>
          );
        })}
      </div>
      <BudgetTimer busy={busy} startedAt={startedAt} lastTotal={lastTotal} />
      <div style={{ ...sectionLabel, marginTop: "2rem" }}>Нейросеть</div>
      {/* Static label, not read from the backend — keep in sync with the
          model + fallback_models in each skill's config.yaml. */}
      <div style={{ fontSize: "0.78rem", color: "var(--muted)", lineHeight: 1.4 }}>
        Используется Qwen3 30B
      </div>
    </aside>
  );
}
