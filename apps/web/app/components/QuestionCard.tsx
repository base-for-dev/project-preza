import { card } from "../lib/styles";
import type { QuestionOption } from "../lib/questions";

// One setup question in the chat (see lib/questions.ts): the prompt and a row
// of answer buttons. Once answered, only the prompt stays — the answer itself
// appears as the user's reply right below it.
export function QuestionCard({
  prompt,
  options,
  answered,
  onPick,
}: {
  prompt: string;
  options: QuestionOption[];
  answered: string | null;
  onPick: (option: QuestionOption) => void;
}) {
  return (
    <div style={{ ...card, width: "fit-content", maxWidth: "100%" }}>
      <div style={{ fontSize: "0.85rem", marginBottom: answered !== null ? 0 : "0.75rem" }}>{prompt}</div>
      {answered === null && (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {options.map((o) => (
            <button
              key={o.value}
              onClick={() => onPick(o)}
              style={{
                background: "#1d1d1d",
                color: "var(--foreground)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.4rem 0.8rem",
                fontSize: "0.82rem",
                cursor: "pointer",
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
