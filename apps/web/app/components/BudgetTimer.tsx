import { useEffect, useState } from "react";
import { GENERATION_BUDGET_SECONDS } from "../lib/constants";
import { formatSeconds } from "../lib/format";

// Elapsed time of the running generation (red once past the five-minute
// budget), or the last result's total once it's done. Ticks locally so only this
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
  const over = elapsed > GENERATION_BUDGET_SECONDS;
  return (
    <div style={{ marginTop: "1.25rem", display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
      <span style={{ color: "var(--muted)" }}>{busy ? "Создаём презентацию" : "Готово за"}</span>
      <span style={{ color: over ? "#f87171" : "var(--foreground)" }}>{formatSeconds(elapsed)}</span>
    </div>
  );
}
