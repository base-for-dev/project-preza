import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { Library } from "../hooks/useLibrary";
import { hasMaterials } from "../lib/format";
import { inlineError, sectionLabel, sidebarSelect } from "../lib/styles";
import type { ChatSession, HistoryItem, TaskMaterials } from "../lib/types";
import { ExtraFilesModal } from "./ExtraFilesModal";
import { StageDot } from "./StageDot";
import { prettyName, TemplatePicker } from "./TemplatePicker";

// A picker button sized to its label, with its status dot beside it (the
// pipeline panel's dots): grey — nothing chosen, pulsing yellow — its window
// is open, green — something is chosen.
const pickerRow: CSSProperties = { display: "flex", alignItems: "center", gap: "var(--s2)" };

function pickerButton(disabled: boolean): CSSProperties {
  return {
    ...sidebarSelect(disabled),
    width: "auto",
    flex: 1,
    minWidth: 0,
    textAlign: "left",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  };
}

// A source-list row: a quiet, rounded selection.
function rowStyle(selected: boolean): CSSProperties {
  return {
    background: selected ? "var(--fill-3)" : "transparent",
    color: "var(--label)",
    border: "none",
    borderRadius: "var(--r-sm)",
    padding: "var(--s2) var(--s3)",
    fontSize: "var(--t-callout)",
    textAlign: "left",
    lineHeight: 1.3,
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
  onOpenSettings,
  saved,
  onOpenSaved,
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
  onOpenSettings: () => void;
  // Generations kept in S3 (empty when it isn't connected).
  saved: HistoryItem[];
  onOpenSaved: (id: string) => void;
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
      // No backdrop-filter here: it would make this column the containing block of
      // the fixed-position pickers rendered inside it, squeezing them into the sidebar.
      style={{
        width: 264,
        borderRight: "0.5px solid var(--separator)",
        padding: "var(--s5) var(--s4) var(--s4)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--s5)",
        flexShrink: 0,
        overflowY: "auto",
        background: "var(--bg-2)",
      }}
    >
      <div style={{ padding: "0 var(--s1)" }}>
        <div style={{ fontWeight: 700, fontSize: "var(--t-title-3)", letterSpacing: "0.04em", lineHeight: 1.1 }}>PREZA</div>
        <div className="caption" style={{ fontSize: "var(--t-caption)", marginTop: 2 }}>By Base Dev</div>
      </div>
      <button className="btn btn-prominent" onClick={() => onSelectSession(null)} style={{ width: "100%" }}>
        Новая презентация
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
            rendererAvailable={library.rendererAvailable}
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
          <div className="caption">Пока пусто</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {sessions.map((s) => (
              <button key={s.id} onClick={() => onSelectSession(s.id)} aria-current={s.id === viewingId ? "true" : undefined} style={rowStyle(s.id === viewingId)}>
                {s.title}
              </button>
            ))}
          </div>
        )}
      </div>
      {saved.length > 0 && (
        <div>
          <div style={sectionLabel}>Сохранено в S3</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {saved.map((r) => (
              <button key={r.id} onClick={() => onOpenSaved(r.id)} title={r.brief} style={rowStyle(false)}>
                <div className="caption" style={{ fontSize: "var(--t-caption)" }}>
                  {new Date(r.created * 1000).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" })}
                </div>
                {r.brief.length > 30 ? r.brief.slice(0, 30) + "…" : r.brief}
              </button>
            ))}
          </div>
        </div>
      )}
      <button className="btn" onClick={onOpenSettings} aria-haspopup="dialog" style={{ marginTop: "auto", justifyContent: "flex-start", width: "100%" }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
        Настройки
      </button>
    </aside>
  );
}
