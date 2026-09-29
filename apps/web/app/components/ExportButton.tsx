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
    <span style={{ display: "inline-flex", gap: "var(--s2)", alignItems: "center" }}>
      <select
        className="btn btn-sm"
        aria-label="Формат экспорта"
        value={format}
        onChange={(e) => setFormat(e.target.value as ExportFormat)}
        style={{ paddingRight: "var(--s2)" }}
      >
        {(Object.keys(FORMAT_LABEL) as ExportFormat[]).map((f) => (
          <option key={f} value={f}>
            {FORMAT_LABEL[f]}
          </option>
        ))}
      </select>
      <button className="btn btn-sm btn-prominent" onClick={download} disabled={state === "busy"}>
        {state === "busy" ? "Экспорт…" : state === "error" ? "Ошибка — ещё раз" : "Скачать"}
      </button>
    </span>
  );
}
