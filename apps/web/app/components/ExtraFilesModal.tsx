import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { Library } from "../hooks/useLibrary";
import { MATERIALS_ACCEPT, NO_PACK_OPTION } from "../lib/constants";
import { closeButton, inlineError } from "../lib/styles";
import type { TaskMaterials } from "../lib/types";

// Every extra file goes in here, dropped or picked: brand packs (a .zip of
// templates, brand book, logos, fonts — kept for later decks) and the
// material for this presentation (documents, a repository .zip, images for
// the slides, the team's story). A .zip can be either, so each one dropped
// gets a switch; the default is guessed from its name.

const BRAND_ZIP = /brand|бренд|pack|пакет|guide|гайд|logo|лого|identity|стиль/i;

const PANEL = "var(--bg-3)";
const FIELD = "var(--fill-2)";

const chip: CSSProperties = {
  fontSize: "0.75rem",
  border: "1px solid var(--border)",
  borderRadius: 999,
  padding: "0.2rem 0.55rem",
  display: "inline-flex",
  gap: "0.4rem",
  alignItems: "center",
};

const chipButton: CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--muted)",
  cursor: "pointer",
  padding: 0,
  fontSize: "0.72rem",
};

export function ExtraFilesModal({
  library,
  materials,
  onMaterialsChange,
  onClose,
}: {
  library: Library;
  materials: TaskMaterials;
  onMaterialsChange: (m: TaskMaterials) => void;
  onClose: () => void;
}) {
  const { packs, packId, selectPack, packError, anyPackBuilding, handlePackUpload } = library;
  const inputRef = useRef<HTMLInputElement>(null);
  const packInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function add(files: File[]) {
    const packZips = files.filter((f) => f.name.toLowerCase().endsWith(".zip") && BRAND_ZIP.test(f.name));
    const rest = files.filter((f) => !packZips.includes(f));
    for (const zip of packZips) void uploadAsPack(zip);
    if (rest.length) onMaterialsChange({ ...materials, files: [...materials.files, ...rest] });
  }

  async function uploadAsPack(file: File) {
    await handlePackUpload(file, file.name.replace(/\.[^.]+$/, ""));
  }

  function moveToPack(index: number) {
    const file = materials.files[index]!;
    onMaterialsChange({ ...materials, files: materials.files.filter((_, j) => j !== index) });
    void uploadAsPack(file);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Дополнительные файлы"
      onClick={onClose}
      className="scrim"
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 60,
        padding: "2rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="sheet"
        style={{
          width: "min(720px, 96vw)",
          maxHeight: "92vh",
          overflowY: "auto",
          padding: "var(--s5)",
          display: "flex",
          flexDirection: "column",
          gap: "1.1rem",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: "var(--t-title-3)", letterSpacing: "-0.02em" }}>Дополнительные файлы</div>
          </div>
          <button onClick={onClose} style={closeButton} aria-label="Закрыть">
            Готово
          </button>
        </div>

        {/* Drop zone */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            add(Array.from(e.dataTransfer.files));
          }}
          style={{
            border: `1.5px dashed ${dragging ? "var(--foreground)" : "var(--border)"}`,
            borderRadius: "var(--r-md)",
            background: dragging ? "var(--fill-2)" : FIELD,
            padding: "1.8rem 1rem",
            textAlign: "center",
            cursor: "pointer",
          }}
        >
          <div style={{ fontSize: "0.9rem" }}>Перетащите файлы сюда или нажмите, чтобы выбрать</div>
          <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: "0.35rem", lineHeight: 1.45 }}>
            .zip бренд-пакета или репозитория · .md · .txt · .pdf · .docx · .pptx · .csv · картинки для слайдов
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={MATERIALS_ACCEPT}
          onChange={(e) => {
            const picked = Array.from(e.target.files ?? []);
            e.target.value = "";
            add(picked);
          }}
          style={{ display: "none" }}
        />

        {/* Brand packs */}
        <section>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.45rem" }}>
            Бренд-пакет
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginBottom: "0.5rem", lineHeight: 1.4 }}>
            {anyPackBuilding
              ? "Пакет собирается: извлекаем стиль, термины и структуру…"
              : "Один .zip: шаблоны, брендбук, логотипы, шрифты — сохраняется для следующих презентаций."}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {[{ id: NO_PACK_OPTION, name: "Без пакета", status: "ready" as const }, ...packs].map((p) => {
              const active = p.id === packId;
              const ready = p.status === "ready";
              return (
                <button
                  key={p.id}
                  onClick={() => ready && selectPack(p.id)}
                  disabled={!ready}
                  aria-pressed={active}
                  style={{
                    ...chip,
                    background: active ? "var(--accent)" : "transparent",
                    color: active ? "var(--on-accent)" : "var(--foreground)",
                    cursor: ready ? "pointer" : "default",
                    opacity: ready ? 1 : 0.6,
                  }}
                >
                  {p.name}
                  {p.status === "building" ? " — собирается…" : p.status === "error" ? " — ошибка" : ""}
                </button>
              );
            })}
            <button
              onClick={() => packInputRef.current?.click()}
              style={{ ...chip, background: "transparent", color: "var(--foreground)", cursor: "pointer", borderStyle: "dashed" }}
            >
              + Загрузить свой (.zip)
            </button>
          </div>
          <input
            ref={packInputRef}
            type="file"
            accept=".zip"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void uploadAsPack(file);
            }}
            style={{ display: "none" }}
          />
          {packError && <div style={inlineError}>{packError}</div>}
        </section>

        {/* Materials for this presentation */}
        <section>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.45rem" }}>
            Материалы для этой презентации
          </div>
          {materials.files.length === 0 ? (
            <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Пока нет файлов</div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
              {materials.files.map((f, i) => (
                <span key={`${f.name}-${i}`} style={chip}>
                  {f.name}
                  {f.name.toLowerCase().endsWith(".zip") && (
                    <button
                      onClick={() => moveToPack(i)}
                      style={{ ...chipButton, textDecoration: "underline" }}
                      title="Загрузить этот архив как бренд-пакет"
                    >
                      это бренд-пакет
                    </button>
                  )}
                  <button
                    onClick={() => onMaterialsChange({ ...materials, files: materials.files.filter((_, j) => j !== i) })}
                    aria-label={`Убрать ${f.name}`}
                    style={chipButton}
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}
          <div
            style={{
              fontSize: "0.72rem",
              color: "var(--muted)",
              textTransform: "uppercase",
              margin: "0.9rem 0 0.45rem",
            }}
          >
            Дополнительная информация
          </div>
          <textarea
            value={materials.story}
            onChange={(e) => onMaterialsChange({ ...materials, story: e.target.value })}
            placeholder="История команды: кто вы, как пришли к решению, что пробовали и что не сработало, чем гордитесь"
            aria-label="История команды"
            rows={3}
            style={{
              width: "100%",
              background: FIELD,
              color: "var(--foreground)",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-sm)",
              padding: "0.45rem 0.55rem",
              fontFamily: "inherit",
              fontSize: "0.8rem",
              resize: "vertical",
              boxSizing: "border-box",
            }}
          />
        </section>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              minWidth: 140,
              borderRadius: "var(--r-sm)",
              border: "none",
              background: "var(--accent)",
              color: "var(--on-accent)",
              padding: "0.5rem 1rem",
              fontSize: "0.85rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Готово
          </button>
        </div>
      </div>
    </div>
  );
}
