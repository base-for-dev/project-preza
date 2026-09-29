import { PIPELINE_STAGES } from "../lib/constants";
import { sectionLabel } from "../lib/styles";
import type { StageStatus } from "../lib/types";
import { BudgetTimer } from "./BudgetTimer";
import { StageDot } from "./StageDot";

// Right panel (an inspector): pipeline progress of the chat on screen.
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
        width: 248,
        borderLeft: "0.5px solid var(--separator)",
        padding: "var(--s5) var(--s4)",
        flexShrink: 0,
        overflowY: "auto",
      }}
    >
      <div style={sectionLabel}>Ход работы</div>
      <div className="list" style={{ background: "var(--fill-2)", boxShadow: "none" }}>
        {PIPELINE_STAGES.map((s) => {
          const status: StageStatus = s.disabled ? "idle" : stages[s.key] ?? "idle";
          return (
            <div
              key={s.key}
              style={{ display: "flex", alignItems: "center", gap: "var(--s3)", padding: "var(--s2) var(--s3)", opacity: s.disabled ? 0.4 : 1 }}
            >
              <StageDot status={status} />
              <span style={{ fontSize: "var(--t-callout)" }}>{s.label}</span>
            </div>
          );
        })}
      </div>
      <BudgetTimer busy={busy} startedAt={startedAt} lastTotal={lastTotal} />
      <div style={{ ...sectionLabel, marginTop: "var(--s5)" }}>Нейросеть</div>
      {/* Static label, not read from the backend — keep in sync with the
          model + fallback_models in each skill's config.yaml. */}
      <div className="caption">Используется Qwen3 30B</div>
    </aside>
  );
}
