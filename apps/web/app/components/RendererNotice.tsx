import { useState } from "react";
import { useLibreOfficeInstall } from "../hooks/useLibreOffice";

// LibreOffice draws the template previews and the vector PDF. When it is
// missing the app still works (the browser draws both), and offers to install it.
export function RendererNotice({ missing, onInstalled }: { missing: boolean; onInstalled: () => void }) {
  const [dismissed, setDismissed] = useState(false);
  const office = useLibreOfficeInstall(onInstalled);
  if (!missing || dismissed || office.state === "ok") return null;
  return (
    <div
      role="status"
      style={{
        margin: "var(--s2) var(--s5) 0",
        padding: "var(--s2) var(--s4)",
        borderRadius: "var(--r-md)",
        background: "var(--fill-2)",
        fontSize: "var(--t-subhead)",
        display: "flex",
        alignItems: "center",
        gap: "var(--s3)",
      }}
    >
      <span style={{ flex: 1, lineHeight: 1.4 }}>
        {office.state === "running"
          ? `Устанавливаю LibreOffice… ${office.log.at(-1) ?? ""}`
          : office.state === "failed"
            ? `Не получилось установить: ${office.log.at(-1) ?? ""}`
            : "LibreOffice не найден: превью шаблонов и PDF рисует браузер. С ним будет точнее и быстрее."}
      </span>
      {office.state !== "running" && (
        <button className="btn btn-sm btn-prominent" onClick={office.install}>Установить</button>
      )}
      <button className="btn btn-sm btn-plain" onClick={() => setDismissed(true)}>Скрыть</button>
    </div>
  );
}
