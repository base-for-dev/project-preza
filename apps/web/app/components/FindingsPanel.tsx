import { useEffect, useMemo, useState } from "react";
import { FINDING_COLOR, findingKey } from "../lib/findings";
import type { CheckInfo, Finding } from "../lib/types";

const KIND_TITLE: Record<Finding["kind"], string> = {
  deterministic: "Проверки по правилам",
  model: "Проверки смысла моделью",
};
const KIND_NOTE: Record<Finding["kind"], string> = {
  deterministic: "Детерминированные: один и тот же слайд всегда даёт один и тот же результат, модель не участвует.",
  model: "Недетерминированные: модель смотрит на картинку слайда. Исправить их может только человек.",
};

const button = {
  background: "var(--fill)",
  border: "none",
  borderRadius: "var(--r-sm)",
  color: "var(--label)",
  minHeight: 28,
  padding: "0 var(--s3)",
  fontSize: "var(--t-subhead)",
  fontWeight: 500,
} as const;

// Every finding of a deck, split into rule-based and model-judged, each with a
// checkbox when an automatic repair exists. The user ticks what to fix; nothing
// changes until they press the button.
export function FindingsPanel({
  findings,
  checks,
  busy,
  report,
  canUndo,
  focusedKey,
  onFocus,
  onFix,
  onUndo,
}: {
  findings: Finding[];
  checks: Record<string, CheckInfo>;
  busy: boolean;
  report: string | null;
  canUndo: boolean;
  focusedKey: string | null;
  onFocus: (finding: Finding | null) => void;
  onFix: (selected: Finding[]) => void;
  onUndo: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => setSelected(new Set()), [findings]);

  const fixable = useMemo(() => findings.filter((f) => checks[f.check]?.fixable), [findings, checks]);
  const chosen = fixable.filter((f) => selected.has(findingKey(f)));

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  if (findings.length === 0 && !report) {
    return <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Аудит не нашёл замечаний.</div>;
  }

  return (
    <section
      aria-label="Находки аудита"
      style={{ borderRadius: "var(--r-lg)", padding: "var(--s4)", background: "var(--bg-3)", boxShadow: "var(--shadow-1)", maxWidth: 640 }}
    >
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.6rem" }}>
        <strong style={{ fontSize: "0.85rem" }}>Аудит: {findings.length} находок</strong>
        <span style={{ flex: 1 }} />
        <button
          style={button}
          disabled={fixable.length === 0 || busy}
          onClick={() => setSelected(new Set(fixable.map(findingKey)))}
        >
          Выбрать все исправимые ({fixable.length})
        </button>
        <button
          style={{ ...button, background: "var(--accent)", color: "var(--on-accent)", fontWeight: 600 }}
          disabled={chosen.length === 0 || busy}
          onClick={() => onFix(chosen)}
        >
          {busy ? "Исправляю…" : `Исправить выбранное (${chosen.length})`}
        </button>
        {canUndo && (
          <button style={button} disabled={busy} onClick={onUndo}>
            Отменить
          </button>
        )}
      </div>
      {report && <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginBottom: "0.6rem", whiteSpace: "pre-line" }}>{report}</div>}

      {(["deterministic", "model"] as const).map((kind) => {
        const rows = findings.filter((f) => f.kind === kind);
        if (rows.length === 0) return null;
        return (
          <div key={kind} style={{ marginTop: "0.7rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.72rem", color: FINDING_COLOR[kind], textTransform: "uppercase" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: FINDING_COLOR[kind] }} />
              {KIND_TITLE[kind]} · {rows.length}
            </div>
            <div style={{ fontSize: "0.68rem", color: "var(--muted)", margin: "0.15rem 0 0.4rem" }}>{KIND_NOTE[kind]}</div>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              {rows.map((f) => {
                const key = findingKey(f);
                const info = checks[f.check];
                const canFix = info?.fixable ?? false;
                return (
                  <li
                    key={key}
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      alignItems: "flex-start",
                      padding: "0.3rem 0.4rem",
                      borderRadius: "var(--r-sm)",
                      background: focusedKey === key ? "var(--fill)" : "transparent",
                      cursor: "pointer",
                    }}
                    onClick={() => onFocus(focusedKey === key ? null : f)}
                  >
                    <input
                      type="checkbox"
                      aria-label={`Исправить: ${info?.title ?? f.check}, слайд ${f.slide_index + 1}`}
                      disabled={!canFix || busy}
                      checked={selected.has(key)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => toggle(key)}
                      title={canFix ? "Можно исправить автоматически" : "Автоматического исправления нет"}
                      style={{ marginTop: 3 }}
                    />
                    <div style={{ fontSize: "0.76rem", lineHeight: 1.4 }}>
                      <span style={{ color: "var(--muted)" }}>Слайд {f.slide_index + 1} · </span>
                      {info?.title ?? f.check}
                      <div style={{ fontSize: "0.7rem", color: "var(--muted)" }}>{f.message}</div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
