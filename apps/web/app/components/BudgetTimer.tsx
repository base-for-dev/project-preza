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
    <div style={{ marginTop: "var(--s5)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "var(--s2)" }}>
        <span className="caption">{busy ? "Создаём презентацию" : "Готово за"}</span>
        <span style={{ fontVariantNumeric: "tabular-nums", fontSize: "var(--t-callout)", fontWeight: 600, color: over ? "var(--red)" : "var(--label)" }}>
          {formatSeconds(elapsed)} <span style={{ color: "var(--label-3)", fontWeight: 400 }}>/ {formatSeconds(GENERATION_BUDGET_SECONDS)}</span>
        </span>
      </div>
      <div style={{ height: 4, background: "var(--fill-3)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${share * 100}%`, height: "100%", background: over ? "var(--red)" : "var(--accent)", borderRadius: 2, transition: "width 0.5s linear" }} />
      </div>
    </div>
  );
}
