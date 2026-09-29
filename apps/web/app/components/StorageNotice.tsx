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
  const tint = connected ? "var(--green)" : "var(--orange)";
  return (
    <div
      role="status"
      style={{
        margin: "var(--s3) var(--s5) 0",
        padding: "var(--s2) var(--s4)",
        borderRadius: "var(--r-md)",
        background: `color-mix(in srgb, ${tint} 13%, transparent)`,
        color: "var(--label)",
        fontSize: "var(--t-subhead)",
        lineHeight: 1.4,
        display: "flex",
        alignItems: "center",
        gap: "var(--s3)",
      }}
    >
      <span aria-hidden style={{ width: 8, height: 8, borderRadius: "50%", background: tint, flexShrink: 0 }} />
      {connected ? (
        <span>Хранилище S3 подключено: запросы, результаты и шаблоны сохраняются.</span>
      ) : (
        <span style={{ flex: 1 }}>
          Ничего не сохраняется: чаты и презентации живут только на этой странице и пропадут при закрытии или обновлении.
        </span>
      )}
      {!connected && (
        <button className="btn btn-plain btn-sm" onClick={onOpenSettings} style={{ flexShrink: 0 }}>
          Подключить S3
        </button>
      )}
    </div>
  );
}
