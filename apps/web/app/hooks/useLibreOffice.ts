import { useState } from "react";
import { installLibreOffice } from "../lib/api";
import { errorMessage } from "../lib/format";

// Runs the LibreOffice installer and keeps its output for display.
export function useLibreOfficeInstall(onDone: () => void) {
  const [state, setState] = useState<"idle" | "running" | "ok" | "failed">("idle");
  const [log, setLog] = useState<string[]>([]);

  async function install() {
    setState("running");
    setLog([]);
    try {
      const ok = await installLibreOffice((line) => setLog((prev) => [...prev.slice(-60), line]));
      setState(ok ? "ok" : "failed");
      if (ok) onDone();
    } catch (e) {
      setLog((prev) => [...prev, errorMessage(e)]);
      setState("failed");
    }
  }
  return { state, log, install };
}
