import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { Library } from "../hooks/useLibrary";
import { hasMaterials } from "../lib/format";
import { inlineError, sectionLabel, sidebarSelect } from "../lib/styles";
import type { ChatSession, TaskMaterials } from "../lib/types";
import { ExtraFilesModal } from "./ExtraFilesModal";
import { StageDot } from "./StageDot";
import { prettyName, TemplatePicker } from "./TemplatePicker";

// A picker button sized to its label, with its status dot beside it (the
// pipeline panel's dots): grey — nothing chosen, pulsing yellow — its window
// is open, green — something is chosen.
const pickerRow: CSSProperties = { display: "flex", alignItems: "center", gap: "0.5rem" };

function pickerButton(disabled: boolean): CSSProperties {
  return {
    ...sidebarSelect(disabled),
    width: "auto",
    maxWidth: "calc(100% - 16px)",
    textAlign: "left",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  };
}

// Left column: new session, brand pack, template, chat history.
export function Sidebar({
  library,
  busy,
  sessions,
  viewingId,
  onSelectSession,
  materials,
  onMaterialsChange,
}: {
  library: Library;
  busy: boolean;
  sessions: ChatSession[];
  viewingId: string | null;
  // null = "new session": the next brief starts a fresh chat.
  onSelectSession: (id: string | null) => void;
  // Files and story for the next presentation (sent with the next brief).
  materials: TaskMaterials;
  onMaterialsChange: (m: TaskMaterials) => void;
}) {
  const {
    templates,
    templateId,
    setTemplateId,
    uploading,
    uploadError,
    handleTemplateUpload,
    packId,
    anyPackBuilding,
    refreshTemplates,
  } = library;
  const [picking, setPicking] = useState(false);
  const [addingFiles, setAddingFiles] = useState(false);
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
        <div style={pickerRow}>
          <button
            onClick={() => {
              void refreshTemplates();
              setPicking(true);
            }}
            disabled={busy || uploading}
            aria-haspopup="dialog"
            title="Выбрать шаблон с предпросмотром"
            style={pickerButton(busy || uploading)}
          >
            {uploading ? "Загрузка…" : currentLabel}
          </button>
          <StageDot status={picking || uploading ? "active" : library.templateChosen ? "done" : "idle"} />
        </div>
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
        <div style={sectionLabel}>Дополнительные файлы</div>
        <div style={pickerRow}>
          <button
            onClick={() => setAddingFiles(true)}
            disabled={busy}
            aria-haspopup="dialog"
            title="Бренд-пакеты и материалы для презентации"
            style={pickerButton(busy)}
          >
            Выбрать файлы
          </button>
          <StageDot
            status={addingFiles ? "active" : packId || hasMaterials(materials) ? "done" : "idle"}
          />
        </div>
        {anyPackBuilding && (
          <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: "0.3rem", lineHeight: 1.35 }}>
            Бренд-пакет собирается…
          </div>
        )}
        {addingFiles && (
          <ExtraFilesModal
            library={library}
            materials={materials}
            onMaterialsChange={onMaterialsChange}
            onClose={() => setAddingFiles(false)}
          />
        )}
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
