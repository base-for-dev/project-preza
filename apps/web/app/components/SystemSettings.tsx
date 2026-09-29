import { useEffect, useState } from "react";
import { fetchSystem, fetchUpdate, openDataFolder } from "../lib/api";
import type { SystemInfo, UpdateInfo } from "../lib/types";
import { useLibreOfficeInstall } from "../hooks/useLibreOffice";

// The machine the app runs on: version, where data lives, LibreOffice (which
// draws template previews and vector PDFs) with a one-click install, updates.
export function SystemSettings({ onChanged }: { onChanged?: () => void }) {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [update, setUpdate] = useState<UpdateInfo | "busy" | null>(null);
  const load = () => fetchSystem().then(setInfo).catch(() => {});
  const office = useLibreOfficeInstall(() => {
    void load();
    onChanged?.();
  });
  useEffect(() => {
    void load();
  }, []);
  if (!info) return null;
  const lo = info.libreoffice;

  const row = (title: string, value: React.ReactNode, action?: React.ReactNode) => (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)", padding: "var(--s3) var(--s4)" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--t-callout)" }}>{title}</div>
        <div className="caption" style={{ overflowWrap: "anywhere" }}>{value}</div>
      </div>
      {action}
    </div>
  );

  return (
    <section style={{ marginTop: "var(--s6)", paddingTop: "var(--s5)", borderTop: "0.5px solid var(--separator)" }}>
      <strong style={{ fontSize: "var(--t-headline)" }}>Система</strong>
      <div className="list" style={{ marginTop: "var(--s3)", background: "var(--fill-2)", boxShadow: "none" }}>
        {row("Версия", `${info.version} · ${info.platform}`, (
          <button className="btn btn-sm" disabled={update === "busy"} onClick={async () => {
            setUpdate("busy");
            setUpdate(await fetchUpdate());
          }}>
            Проверить обновления
          </button>
        ))}
        {update && update !== "busy" && (
          <div className="caption" style={{ padding: "var(--s2) var(--s4)", color: update.newer ? "var(--orange)" : "var(--label-2)" }}>
            {update.error
              ? "Не удалось проверить: нет связи с GitHub."
              : update.newer
                ? <>Есть версия {update.latest}. <a href={update.url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>Скачать</a></>
                : "У вас последняя версия."}
          </div>
        )}
        {row("Папка данных", info.data_dir, <button className="btn btn-sm" onClick={() => openDataFolder()}>Показать</button>)}
        {row(
          "LibreOffice",
          lo.installed ? `Установлен: ${lo.path}` : "Не найден: превью шаблонов и PDF рисует браузер, чуть медленнее и проще.",
          !lo.installed && (
            <button className="btn btn-sm btn-prominent" disabled={office.state === "running" || !lo.installer} onClick={office.install}
              title={lo.installer ? `Установка через ${lo.installer}` : "На этой системе автоустановка недоступна"}>
              {office.state === "running" ? "Устанавливаю…" : "Установить"}
            </button>
          ),
        )}
      </div>
      {!lo.installer && !lo.installed && (
        <div className="caption" style={{ marginTop: "var(--s2)" }}>
          Автоустановка недоступна на этой системе — скачайте LibreOffice на libreoffice.org.
        </div>
      )}
      {office.log.length > 0 && (
        <pre style={{ margin: "var(--s3) 0 0", padding: "var(--s3)", borderRadius: "var(--r-sm)", background: "var(--fill-2)", maxHeight: 140, overflow: "auto", fontSize: "var(--t-caption)", whiteSpace: "pre-wrap" }}>
          {office.log.join("\n")}
        </pre>
      )}
      {office.state === "ok" && <div className="caption" style={{ color: "var(--green)", marginTop: "var(--s2)" }}>LibreOffice установлен. Превью появятся через минуту.</div>}
    </section>
  );
}
