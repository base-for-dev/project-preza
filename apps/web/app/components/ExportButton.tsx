import { useState } from "react";
import { exportDeck } from "../lib/api";
import type { Deck } from "../lib/types";

export function ExportButton({ deck }: { deck: Deck }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  async function download() {
    setState("busy");
    try {
      const url = URL.createObjectURL(await exportDeck(deck));
      const a = document.createElement("a");
      a.href = url;
      a.download = "presentation.pptx";
      a.click();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("error");
    }
  }
  return (
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
      {state === "busy" ? "Экспорт…" : state === "error" ? "Ошибка — ещё раз" : "Скачать .pptx с текстом"}
    </button>
  );
}
