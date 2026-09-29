import { useEffect, useState, type CSSProperties } from "react";
import { fetchStorage, saveStorage, syncStorage, testStorage } from "../lib/api";
import { errorMessage } from "../lib/format";
import { closeButton, prominentButton } from "../lib/styles";
import type { StorageIn, StorageOut } from "../lib/types";

// An S3 bucket (AWS, Yandex Object Storage, MinIO, R2, ...) where finished
// generations and uploaded templates are kept, so they outlive the page.
// The secret key is write-only: the server never sends it back.

const field: CSSProperties = {
  width: "100%",
  minHeight: "var(--hit)",
  background: "var(--fill-2)",
  color: "var(--label)",
  border: "0.5px solid var(--separator)",
  borderRadius: "var(--r-sm)",
  padding: "0 var(--s3)",
  fontSize: "var(--t-callout)",
};
const label: CSSProperties = { fontSize: "var(--t-footnote)", fontWeight: 500, color: "var(--label-2)", marginBottom: "var(--s1)", display: "block" };
const hint: CSSProperties = { fontSize: "var(--t-footnote)", color: "var(--label-2)", marginTop: "var(--s1)", lineHeight: 1.4 };

export function StorageSettings({ onChanged }: { onChanged: () => void }) {
  const [server, setServer] = useState<StorageOut | null>(null);
  const [form, setForm] = useState<StorageIn | null>(null);
  const [secret, setSecret] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function fill(s: StorageOut) {
    setServer(s);
    setForm({
      endpoint_url: s.endpoint_url,
      region: s.region,
      bucket: s.bucket,
      access_key: s.access_key,
      prefix: s.prefix,
      path_style: s.path_style,
    });
    setSecret("");
  }

  useEffect(() => {
    fetchStorage().then(fill).catch((e) => setNote({ ok: false, text: errorMessage(e) }));
  }, []);

  if (!server || !form) return null;
  const body = (): StorageIn => ({ ...form, ...(secret ? { secret_key: secret } : {}) });
  const edit = (patch: Partial<StorageIn>) => {
    setForm({ ...form, ...patch });
    setNote(null);
  };

  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setNote({ ok: false, text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  const input = (id: string, title: string, key: keyof StorageIn, placeholder = "") => (
    <div>
      <label style={label} htmlFor={id}>{title}</label>
      <input id={id} style={field} value={(form[key] as string) ?? ""} placeholder={placeholder}
        onChange={(e) => edit({ [key]: e.target.value })} />
    </div>
  );

  return (
    <section style={{ marginTop: "1.5rem", paddingTop: "1.25rem", borderTop: "1px solid var(--border)" }}>
      <strong style={{ fontSize: "0.9rem" }}>Хранилище S3</strong>
      <div style={{ ...hint, marginBottom: "0.9rem" }}>
        Без него ничего не сохраняется: чаты и результаты пропадают при закрытии страницы. С ним каждая готовая презентация
        (запрос и три варианта) и загруженные шаблоны кладутся в бакет и возвращаются после перезапуска.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
        {input("s3-endpoint", "Адрес сервиса (пусто — Amazon S3)", "endpoint_url", "https://storage.yandexcloud.net")}
        <div style={{ display: "flex", gap: "0.6rem" }}>
          <div style={{ flex: 1 }}>{input("s3-bucket", "Бакет", "bucket", "my-preza")}</div>
          <div style={{ flex: 1 }}>{input("s3-region", "Регион", "region", "us-east-1")}</div>
        </div>
        {input("s3-access", "Ключ доступа (Access key ID)", "access_key")}
        <div>
          <label style={label} htmlFor="s3-secret">Секретный ключ</label>
          <input id="s3-secret" style={field} type="password" autoComplete="off" value={secret}
            placeholder={server.has_secret ? "•••••••• (пусто — не менять)" : ""}
            onChange={(e) => { setSecret(e.target.value); setNote(null); }} />
        </div>
        {input("s3-prefix", "Папка в бакете", "prefix", "preza/")}
        <label style={{ display: "flex", gap: "0.5rem", fontSize: "0.8rem" }}>
          <span className="switch"><input type="checkbox" checked={form.path_style} onChange={(e) => edit({ path_style: e.target.checked })} /></span>
          <span>Адресация по пути (для MinIO и похожих)</span>
        </label>
      </div>
      {note && <div style={{ fontSize: "0.78rem", marginTop: "0.7rem", color: note.ok ? "var(--green)" : "var(--red)" }}>{note.text}</div>}
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.9rem" }}>
        <button style={closeButton} disabled={busy} onClick={() => run(async () => {
          const r = await testStorage(body());
          setNote({ ok: r.ok, text: r.ok ? "Бакет доступен, запись работает." : `Не получилось: ${r.error}` });
        })}>Проверить</button>
        <button style={prominentButton} disabled={busy}
          onClick={() => run(async () => {
            const saved = await saveStorage(body());
            fill(saved);
            const sync = saved.connected ? await syncStorage() : null;
            setNote({ ok: true, text: sync
              ? `Сохранено. Шаблонов отправлено: ${sync.uploaded}, получено: ${sync.downloaded}.`
              : "Сохранено." });
            onChanged();
          })}>Подключить и сохранить</button>
        {server.connected && (
          <button style={closeButton} disabled={busy} onClick={() => run(async () => {
            fill(await saveStorage({ ...body(), bucket: "", access_key: "", secret_key: "" }));
            setNote({ ok: true, text: "Хранилище отключено. Уже сохранённое остаётся в бакете." });
            onChanged();
          })}>Отключить</button>
        )}
      </div>
    </section>
  );
}
