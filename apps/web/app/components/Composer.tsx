import { SECTION_BREAK } from "../lib/constants";
import { hasMaterials } from "../lib/format";
import type { TaskMaterials } from "../lib/types";
import { BlinkingDots } from "./BlinkingDots";

export function Composer({
  busy,
  input,
  onInputChange,
  onSend,
  materials,
}: {
  busy: boolean;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  // Attached in the sidebar's "Дополнительные файлы"; only shapes the hint here.
  materials: TaskMaterials;
}) {
  const canSend = !busy && input.trim() !== "";

  return (
    <div style={{ borderTop: "1px solid var(--border)", padding: "1rem 2rem" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        {SECTION_BREAK.test(input) && (
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginBottom: "0.35rem" }}>
            Строки «---» делят бриф: каждая часть станет отдельным слайдом
          </div>
        )}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            background: "#151515",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "0.5rem 0.5rem 0.5rem 0.9rem",
          }}
        >
          <textarea
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
            placeholder={
              hasMaterials(materials)
                ? "Что за выступление? Например: финал хакатона, жюри"
                : "Опиши, какую презентацию хочешь…"
            }
            aria-label="Бриф презентации"
            rows={1}
            style={{
              flex: 1,
              minWidth: 0,
              resize: "none",
              background: "transparent",
              border: "none",
              outline: "none",
              color: "var(--foreground)",
              fontFamily: "inherit",
              fontSize: "0.9rem",
              lineHeight: 1.4,
              padding: "0.4rem 0",
              display: "block",
            }}
          />
          <div style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
            <button
              onClick={onSend}
              disabled={!canSend}
              aria-label="Отправить"
              aria-busy={busy}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                minWidth: 84,
                background: canSend ? "#ededed" : "#333",
                color: canSend ? "#0a0a0a" : "var(--muted)",
                border: "none",
                borderRadius: 6,
                padding: "0.5rem 1rem",
                fontWeight: 600,
                fontSize: "0.85rem",
                cursor: canSend ? "pointer" : "default",
              }}
            >
              {busy ? <BlinkingDots color="var(--muted)" gap="4px" /> : "Отправить"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
