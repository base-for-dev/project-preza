import { useEffect, useRef, useState } from "react";
import type { Library } from "../hooks/useLibrary";
import { NO_PACK_OPTION, UPLOAD_PACK_OPTION } from "../lib/constants";
import { inlineError, sectionLabel, sidebarSelect } from "../lib/styles";
import type { ChatSession } from "../lib/types";
import { TemplateInspector } from "./TemplateInspector";
import { prettyName, TemplatePicker } from "./TemplatePicker";

// Left column: new session, brand pack, template, chat history.
export function Sidebar({
  library,
  busy,
  sessions,
  viewingId,
  onSelectSession,
}: {
  library: Library;
  busy: boolean;
  sessions: ChatSession[];
  viewingId: string | null;
  // null = "new session": the next brief starts a fresh chat.
  onSelectSession: (id: string | null) => void;
}) {
  const {
    templates,
    templateId,
    setTemplateId,
    uploading,
    uploadError,
    handleTemplateUpload,
    packs,
    packId,
    selectPack,
    packError,
    anyPackBuilding,
    handlePackUpload,
    refreshTemplates,
  } = library;
  const [inspecting, setInspecting] = useState(false);
  const [picking, setPicking] = useState(false);
  const autoLabel = packId ? "Из бренд-пакета" : "Авто (по теме брифа)";
  const chosen = templates.find((t) => t.id === templateId);
  const currentLabel = chosen ? prettyName(chosen.label) : library.templateChosen ? autoLabel : "Выбрать шаблон";

  // Template previews render in the background on the server; while the
  // picker is open and some are still missing, keep refreshing the list.
  const previewsPending = templates.some((t) => !t.previews);
  useEffect(() => {
    if (!picking || !previewsPending) return;
    const interval = setInterval(() => void refreshTemplates(), 4000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picking, previewsPending]);
  const packInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <aside
      style={{
        width: 220,
        borderRight: "1px solid var(--border)",
        padding: "1.25rem 1rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
        flexShrink: 0,
        overflowY: "auto",
      }}
    >
      <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>PREZA</div>
      <button
        onClick={() => onSelectSession(null)}
        style={{
          background: "#151515",
          color: "var(--foreground)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "0.5rem 0.75rem",
          fontSize: "0.85rem",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        + Новая сессия
      </button>
      <div>
        <div style={sectionLabel}>Шаблон</div>
        <button
          onClick={() => {
            void refreshTemplates();
            setPicking(true);
          }}
          disabled={busy || uploading}
          aria-haspopup="dialog"
          title="Выбрать шаблон с предпросмотром"
          style={{
            ...sidebarSelect(busy || uploading),
            textAlign: "left",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {uploading ? "Загрузка…" : currentLabel}
        </button>
        {picking && (
          <TemplatePicker
            templates={templates}
            currentId={templateId}
            autoLabel={autoLabel}
            uploading={uploading}
            onUpload={() => fileInputRef.current?.click()}
            onChoose={(id) => {
              library.chooseTemplate(id);
              setPicking(false);
            }}
            onClose={() => setPicking(false)}
          />
        )}
        {templateId && (
          <button
            onClick={() => setInspecting(true)}
            style={{
              marginTop: "0.4rem",
              width: "100%",
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: 6,
              color: "var(--foreground)",
              padding: "0.3rem 0.5rem",
              fontSize: "0.75rem",
              cursor: "pointer",
            }}
          >
            🔍 Посмотреть структуру шаблона
          </button>
        )}
        {inspecting && templateId && (
          <TemplateInspector templateId={templateId} onClose={() => setInspecting(false)} />
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pptx"
          disabled={uploading}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void handleTemplateUpload(file);
          }}
          style={{ display: "none" }}
        />
        {uploadError && <div style={inlineError}>{uploadError}</div>}
      </div>
      <div>
        <div style={sectionLabel}>Бренд-пакет</div>
        <select
          value={packId}
          aria-label="Бренд-пакет"
          onChange={(e) => {
            if (e.target.value === UPLOAD_PACK_OPTION) {
              packInputRef.current?.click();
              return;
            }
            selectPack(e.target.value);
          }}
          disabled={busy}
          style={sidebarSelect(busy)}
        >
          <option value={NO_PACK_OPTION}>Без пакета</option>
          {packs.map((p) => (
            <option key={p.id} value={p.id} disabled={p.status !== "ready"}>
              {p.name}
              {p.status === "building" ? " — собирается…" : p.status === "error" ? " — ошибка" : ""}
            </option>
          ))}
          <option value={UPLOAD_PACK_OPTION}>+ Загрузить контент-пакет (.zip)…</option>
        </select>
        <input
          ref={packInputRef}
          type="file"
          accept=".zip"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            void handlePackUpload(file);
          }}
          style={{ display: "none" }}
        />
        <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: "0.3rem", lineHeight: 1.35 }}>
          {anyPackBuilding
            ? "Пакет собирается: извлекаем стиль, термины и структуру…"
            : "Один .zip: шаблоны, брендбук, логотипы, шрифты — загружается заранее."}
        </div>
        {packError && <div style={inlineError}>{packError}</div>}
      </div>
      <div>
        <div style={sectionLabel}>История запросов</div>
        {sessions.length === 0 ? (
          <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Пока пусто</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                aria-current={s.id === viewingId ? "true" : undefined}
                style={{
                  background: s.id === viewingId ? "#1d1d1d" : "transparent",
                  color: "var(--foreground)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  padding: "0.4rem 0.55rem",
                  fontSize: "0.78rem",
                  textAlign: "left",
                  cursor: "pointer",
                }}
              >
                {s.title}
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
