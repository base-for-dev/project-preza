import type { StageStatus } from "../lib/types";

// Status dot shared by the pipeline panel and the sidebar pickers: grey idle,
// pulsing yellow while in progress, green when done, red on error.
const STAGE_COLORS: Record<StageStatus, string> = {
  idle: "var(--fill-3)",
  active: "var(--orange)",
  done: "var(--green)",
  error: "var(--red)",
};

export function StageDot({ status }: { status: StageStatus }) {
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: STAGE_COLORS[status],
        flexShrink: 0,
        animation: status === "active" ? "pulse-ring 1.4s ease-out infinite" : "none",
      }}
    />
  );
}
