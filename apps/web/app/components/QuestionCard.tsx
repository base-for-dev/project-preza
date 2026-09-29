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
    <div
      style={{
        alignSelf: "flex-start",
        maxWidth: "88%",
        background: "var(--fill)",
        borderRadius: "20px 20px 20px 6px",
        padding: "var(--s3) var(--s4)",
      }}
    >
      <div style={{ fontSize: "var(--t-body)" }}>{prompt}</div>
      {answered === null && (
        <div style={{ display: "flex", gap: "var(--s2)", flexWrap: "wrap", marginTop: "var(--s3)" }}>
          {options.map((o) => (
            <button
              key={o.value}
              className="chip"
              onClick={() => onPick(o)}
              style={{ background: "var(--bg-3)", boxShadow: "var(--shadow-1)", minHeight: 32, fontWeight: 500 }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
