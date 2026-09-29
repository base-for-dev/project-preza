import { useEffect } from "react";

// The honest line about what happens to the work. Nothing here is kept unless
// an S3 bucket is connected: chats and results live in this tab only.
export function StorageNotice({
  connected,
  hasWork,
  onOpenSettings,
}: {
  connected: boolean | null;
  hasWork: boolean;
  onOpenSettings: () => void;
}) {
  // Closing or reloading the tab loses everything when nothing is stored: ask first.
  useEffect(() => {
    if (connected !== false || !hasWork) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [connected, hasWork]);

  if (connected === null) return null;
  const base = { fontSize: "0.75rem", padding: "0.45rem 1rem", lineHeight: 1.45 } as const;
  if (connected) {
    return (
      <div style={{ ...base, color: "#4ade80", borderBottom: "1px solid var(--border)" }}>
        Хранилище S3 подключено: запросы, результаты и загруженные шаблоны сохраняются.
      </div>
    );
  }
  return (
    <div style={{ ...base, background: "#2a1f0a", color: "#f0b84a", borderBottom: "1px solid #5a4514" }}>
      Ничего не сохраняется: чаты и готовые презентации живут только на этой странице и пропадут при
      закрытии или обновлении. Скачайте нужное или{" "}
      <button
        onClick={onOpenSettings}
        style={{ background: "none", border: "none", color: "inherit", textDecoration: "underline", cursor: "pointer", padding: 0, font: "inherit" }}
      >
        подключите S3 в настройках
      </button>
      .
    </div>
  );
}
