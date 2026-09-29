import { useEffect, useState } from "react";
import { GENERATION_BUDGET_SECONDS } from "../lib/constants";
import { formatSeconds } from "../lib/format";

// Elapsed time of the running generation against the five-minute budget,
// or the last result's total once it's done. Ticks locally so only this
// component re-renders twice a second, not the whole page.
export function BudgetTimer({
  busy,
  startedAt,
  lastTotal,
}: {
  busy: boolean;
  startedAt: number | null;
  lastTotal: number | null;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!busy) return;
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(tick);
  }, [busy]);

  const elapsed = busy && startedAt ? (now - startedAt) / 1000 : lastTotal;
  if (elapsed === null) return null;
  const share = Math.min(1, elapsed / GENERATION_BUDGET_SECONDS);
  const over = elapsed > GENERATION_BUDGET_SECONDS;
  return (
    <div style={{ marginTop: "1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.3rem" }}>
        <span style={{ color: "var(--muted)" }}>{busy ? "Создаём презентацию" : "Готово за"}</span>
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
