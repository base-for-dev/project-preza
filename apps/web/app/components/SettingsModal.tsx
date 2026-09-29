import { useEffect, useState, type CSSProperties } from "react";
import { fetchModelList, fetchSettings, saveSettings, testSettings } from "../lib/api";
import { errorMessage } from "../lib/format";
import { closeButton } from "../lib/styles";
import type { ConnectionTest, SettingsIn, SettingsOut } from "../lib/types";

// Where the model lives and which one to use: pick a provider (OpenRouter, VK,
// a local Ollama or LM Studio, any OpenAI-compatible server), give it an
// address and a key, choose the model — for everything, for pictures, or for
// one step — and check the connection before saving. The key is write-only:
// the server never sends it back.

const field: CSSProperties = {
  width: "100%",
  background: "#0a0a0a",
  color: "var(--foreground)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "0.45rem 0.6rem",
  fontSize: "0.82rem",
};
const label: CSSProperties = { fontSize: "0.72rem", color: "var(--muted)", marginBottom: "0.25rem", display: "block" };
const hint: CSSProperties = { fontSize: "0.7rem", color: "var(--muted)", marginTop: "0.25rem", lineHeight: 1.4 };
const group: CSSProperties = { display: "flex", flexDirection: "column", gap: "0.9rem" };

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [server, setServer] = useState<SettingsOut | null>(null);
  const [form, setForm] = useState<SettingsIn | null>(null);
  const [newKey, setNewKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [modelsNote, setModelsNote] = useState("");
  const [test, setTest] = useState<ConnectionTest | "busy" | null>(null);
  const [saving, setSaving] = useState<"idle" | "busy" | "saved" | "error">("idle");
  const [error, setError] = useState("");

  function fill(s: SettingsOut) {
    setServer(s);
    setForm({
      provider: s.provider,
      api_base: s.api_base,
      model: s.model,
      vision_model: s.vision_model,
      skill_models: s.skill_models,
      only_my_model: s.only_my_model,
      request_timeout: s.request_timeout,
    });
    setNewKey("");
  }

  useEffect(() => {
    fetchSettings()
      .then(fill)
      .catch((e) => setError(errorMessage(e)));
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!server || !form) {
    return <Shell onClose={onClose}>{error ? <div style={{ color: "#ff8080" }}>{error}</div> : "Загрузка…"}</Shell>;
  }

  const preset = server.presets.find((p) => p.id === form.provider);
  const address = form.api_base || preset?.api_base || "";
  const onDefaultProvider = address.replace(/\/$/, "") === server.default_api_base.replace(/\/$/, "");
  const body = (): SettingsIn => ({ ...form, ...(newKey ? { api_key: newKey } : {}) });
  const set = (patch: Partial<SettingsIn>) => {
    setForm({ ...form, ...patch });
    setSaving("idle");
    setTest(null);
  };
  const textSkills = server.skills.filter((s) => s.modality === "text");

  function pickProvider(id: string) {
    const p = server?.presets.find((x) => x.id === id);
    set({ provider: id, api_base: p?.api_base ?? "" });
    setModels([]);
    setModelsNote("");
  }

  async function loadModels() {
    setModelsNote("Загружаю список…");
    try {
      const r = await fetchModelList(body());
      setModels(r.models);
      setModelsNote(r.error ? `Сервер не отдал список: ${r.error}` : `Моделей на сервере: ${r.models.length}`);
    } catch (e) {
      setModelsNote(errorMessage(e));
    }
  }

  async function runTest() {
    setTest("busy");
    try {
      setTest(await testSettings(body()));
    } catch (e) {
      setTest({ ok: false, model: form!.model, seconds: null, reply: "", error: errorMessage(e) });
    }
  }

  async function save(): Promise<boolean> {
    setSaving("busy");
    try {
      fill(await saveSettings(body()));
      setSaving("saved");
      return true;
    } catch (e) {
      setError(errorMessage(e));
      setSaving("error");
      return false;
    }
  }

  async function reset() {
    setSaving("busy");
    fill(
      await saveSettings({
        provider: "openrouter",
        api_base: "",
        api_key: "",
        model: "",
        vision_model: "",
        skill_models: {},
        only_my_model: false,
        request_timeout: null,
      }),
    );
    setSaving("saved");
    setTest(null);
  }

  const keyState = newKey
    ? "Новый ключ будет сохранён"
    : server.has_key
      ? `Ключ сохранён (…${server.key_hint})`
      : server.key_source === "env"
        ? "Используется ключ из .env"
        : preset && !preset.needs_key
          ? "Для локального сервера ключ не нужен"
          : "Ключа нет";

  return (
    <Shell onClose={onClose}>
      <div style={group}>
        <section>
          <label style={label} htmlFor="provider">Провайдер</label>
          <select id="provider" style={field} value={form.provider} onChange={(e) => pickProvider(e.target.value)}>
            {server.presets.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
          {preset?.hint && <div style={hint}>{preset.hint}</div>}
        </section>

        <section>
          <label style={label} htmlFor="base">Адрес API (OpenAI-совместимый)</label>
          <input id="base" style={field} value={address} placeholder="https://…/v1" onChange={(e) => set({ api_base: e.target.value })} />
        </section>

        <section>
          <label style={label} htmlFor="key">API-ключ</label>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <input
              id="key"
              style={field}
              type={showKey ? "text" : "password"}
              value={newKey}
              placeholder={server.has_key ? "•••••••• (оставьте пустым, чтобы не менять)" : "sk-…"}
              autoComplete="off"
              onChange={(e) => {
                setNewKey(e.target.value);
                setSaving("idle");
                setTest(null);
              }}
            />
            <button style={closeButton} onClick={() => setShowKey(!showKey)} type="button">{showKey ? "Скрыть" : "Показать"}</button>
          </div>
          <div style={hint}>
            {keyState}. Ключ хранится только на этом компьютере (<code>data/inference.json</code>) и никогда не возвращается в браузер.
            {server.has_key && (
              <>
                {" "}
                <button style={{ ...closeButton, padding: "0 0.4rem", fontSize: "0.7rem" }} type="button"
                  onClick={async () => fill(await saveSettings({ ...body(), api_key: "" }))}>
                  Удалить ключ
                </button>
              </>
            )}
          </div>
        </section>

        <section>
          <label style={label} htmlFor="model">Модель для всех шагов</label>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <input id="model" style={field} list="model-list" value={form.model}
              placeholder={onDefaultProvider ? "по умолчанию — свои у каждого шага" : "например, qwen3:30b"}
              onChange={(e) => set({ model: e.target.value })} />
            <button style={closeButton} type="button" onClick={loadModels}>Список</button>
          </div>
          <datalist id="model-list">{models.map((m) => <option key={m} value={m} />)}</datalist>
          {modelsNote && <div style={hint}>{modelsNote}</div>}
          <div style={hint}>
            По ТЗ конкурса допустимы открытые модели под Apache 2.0/MIT до 35B; выбранная здесь не проверяется на это.
          </div>
        </section>

        <section>
          <label style={label} htmlFor="vision">Модель, которая смотрит на картинки слайдов (проверка смысла и фактов)</label>
          <input id="vision" style={field} list="model-list" value={form.vision_model}
            placeholder={server.skills.find((s) => s.modality === "vision")?.model ?? ""}
            onChange={(e) => set({ vision_model: e.target.value })} />
          <div style={hint}>Нужна модель с поддержкой изображений (VLM). Пусто — стандартная.</div>
        </section>

        <label style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.8rem" }}>
          <input type="checkbox" checked={form.only_my_model} onChange={(e) => set({ only_my_model: e.target.checked })} />
          <span>
            Только моя модель, без запасных
            <div style={hint}>
              {onDefaultProvider
                ? "Выключено: если ваша модель не ответит, попробуются стандартные запасные."
                : "На другом сервере запасных моделей нет: там существуют только ваши."}
            </div>
          </span>
        </label>

        <details>
          <summary style={{ cursor: "pointer", fontSize: "0.8rem" }}>Дополнительно: своя модель для отдельного шага</summary>
          <div style={{ ...group, marginTop: "0.7rem" }}>
            {textSkills.map((s) => (
              <div key={s.name}>
                <label style={label} htmlFor={`skill-${s.name}`}>{s.name}</label>
                <input id={`skill-${s.name}`} style={field} list="model-list"
                  value={form.skill_models[s.name] ?? ""} placeholder={s.model}
                  onChange={(e) => set({ skill_models: { ...form.skill_models, [s.name]: e.target.value } })} />
              </div>
            ))}
            <div>
              <label style={label} htmlFor="timeout">Таймаут одного вызова, секунд</label>
              <input id="timeout" style={{ ...field, width: 120 }} type="number" min={10} max={900}
                value={form.request_timeout ?? ""} placeholder="270"
                onChange={(e) => set({ request_timeout: e.target.value ? Number(e.target.value) : null })} />
            </div>
          </div>
        </details>

        {test === "busy" && <div style={hint}>Проверяю подключение…</div>}
        {test && test !== "busy" && (
          <div style={{ fontSize: "0.78rem", color: test.ok ? "#4ade80" : "#ff8080", lineHeight: 1.4 }}>
            {test.ok
              ? `Подключено: ${test.model} ответила за ${test.seconds} с («${test.reply}»)`
              : `Не получилось (${test.model}): ${test.error}`}
          </div>
        )}
        {saving === "saved" && <div style={{ fontSize: "0.78rem", color: "#4ade80" }}>Сохранено — действует со следующего запроса.</div>}
        {saving === "error" && <div style={{ fontSize: "0.78rem", color: "#ff8080" }}>{error}</div>}

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button style={{ ...closeButton, background: "#ededed", color: "#0a0a0a", fontWeight: 600 }}
            disabled={saving === "busy"} onClick={save}>Сохранить</button>
          <button style={closeButton} disabled={test === "busy"} onClick={runTest}>Проверить подключение</button>
          <span style={{ flex: 1 }} />
          <button style={closeButton} onClick={reset}>Сбросить</button>
        </div>
      </div>
    </Shell>
  );
}

function Shell({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 50, display: "flex",
        alignItems: "center", justifyContent: "center", padding: "1.5rem" }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Настройки модели"
        onClick={(e) => e.stopPropagation()}
        style={{ background: "#111", border: "1px solid var(--border)", borderRadius: 12, padding: "1.25rem",
          width: "min(560px, 100%)", maxHeight: "90vh", overflowY: "auto" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1rem" }}>
          <strong style={{ fontSize: "0.95rem" }}>Настройки модели</strong>
          <button onClick={onClose} style={closeButton}>Закрыть ✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
