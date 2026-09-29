import { SECTION_BREAK } from "../lib/constants";
import { hasMaterials } from "../lib/format";
import type { TaskMaterials } from "../lib/types";
import { BlinkingDots } from "./BlinkingDots";

// The message field: a rounded, translucent bar pinned to the bottom, with a
// round send button (accent when there is something to send).
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
    <div style={{ padding: "var(--s3) var(--s5) var(--s5)" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        {SECTION_BREAK.test(input) && (
          <div className="caption" style={{ marginBottom: "var(--s2)", paddingLeft: "var(--s4)" }}>
            Строки «---» делят бриф: каждая часть станет отдельным слайдом
          </div>
        )}
        <div
          className="material"
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: "var(--s2)",
            borderRadius: 26,
            boxShadow: "var(--shadow-1)",
            padding: "var(--s2) var(--s2) var(--s2) var(--s4)",
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
                : "Опишите, какую презентацию хотите"
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
              color: "var(--label)",
              fontSize: "var(--t-body)",
              lineHeight: 1.4,
              padding: "6px 0",
              maxHeight: 160,
            }}
          />
          <button
            onClick={onSend}
            disabled={!canSend}
            aria-label="Отправить"
            aria-busy={busy}
            style={{
              width: 34,
              height: 34,
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "none",
              borderRadius: "50%",
              background: canSend ? "var(--accent)" : "var(--fill-3)",
              color: canSend ? "var(--on-accent)" : "var(--label-3)",
              opacity: 1,
            }}
          >
            {busy ? (
              <BlinkingDots color="var(--label-2)" gap="3px" />
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
                <path d="M8 13V3M8 3L3.5 7.5M8 3l4.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
