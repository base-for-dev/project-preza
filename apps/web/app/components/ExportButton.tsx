import { useState } from "react";
import { exportAs, FORMAT_LABEL, type ExportFormat } from "../lib/exportFormats";
import type { Deck } from "../lib/types";

// One button, three formats. The choice is a native <select> so it works with
// the keyboard and screen readers without extra code.
export function ExportButton({ deck }: { deck: Deck }) {
  const [format, setFormat] = useState<ExportFormat>("pptx");
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");

  async function download() {
    setState("busy");
    try {
      await exportAs(deck, format);
      setState("idle");
    } catch {
      setState("error");
    }
  }

  return (
    <span style={{ display: "inline-flex", gap: "0.3rem", alignItems: "center" }}>
      <select
        aria-label="Формат экспорта"
        value={format}
        onChange={(e) => setFormat(e.target.value as ExportFormat)}
        style={{
          background: "transparent",
          color: "var(--foreground)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "0.28rem 0.4rem",
          fontSize: "0.75rem",
        }}
      >
        {(Object.keys(FORMAT_LABEL) as ExportFormat[]).map((f) => (
          <option key={f} value={f}>
            {FORMAT_LABEL[f]}
          </option>
        ))}
      </select>
      <button
        onClick={download}
        disabled={state === "busy"}
        style={{
          background: "#ededed",
          color: "#0a0a0a",
          border: "none",
          borderRadius: 6,
          padding: "0.3rem 0.7rem",
          fontSize: "0.75rem",
          fontWeight: 600,
          cursor: state === "busy" ? "default" : "pointer",
        }}
      >
        {state === "busy" ? "Экспорт…" : state === "error" ? "Ошибка — ещё раз" : "Скачать"}
      </button>
    </span>
  );
}
