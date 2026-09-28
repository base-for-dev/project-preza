import type { QuestionOption } from "../lib/questions";
import type { Message, Outline } from "../lib/types";
import { AuditResult } from "./AuditResult";
import { OutlineReview } from "./OutlineReview";
import { QuestionCard } from "./QuestionCard";

export function MessageView({
  message,
  onAnswer,
  onConfirmOutline,
}: {
  message: Message;
  onAnswer?: (option: QuestionOption) => void;
  onConfirmOutline?: (outline: Outline) => void;
}) {
  switch (message.kind) {
    case "outline-review":
      return (
        <OutlineReview
          initial={message.outline}
          confirmed={message.confirmed}
          onConfirm={(outline) => onConfirmOutline?.(outline)}
        />
      );
    case "question":
      return (
        <QuestionCard
          prompt={message.prompt}
          options={message.options}
          answered={message.answered}
          onPick={(o) => onAnswer?.(o)}
        />
      );
    case "user":
      return (
        <div style={{ alignSelf: "flex-end", maxWidth: "85%", marginLeft: "auto" }}>
          <div
            style={{
              background: "#1d1d1d",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "0.75rem 1rem",
              fontSize: "0.9rem",
              whiteSpace: "pre-wrap",
            }}
          >
            {message.text}
          </div>
        </div>
      );
    case "error":
      return (
        <div
          style={{
            border: "1px solid #7a2020",
            background: "#2a1010",
            borderRadius: 8,
            padding: "0.75rem 1rem",
            color: "#ff8080",
            fontSize: "0.85rem",
          }}
        >
          {message.text}
        </div>
      );
    case "audit":
      return <AuditResult audit={message.audit} density={message.density} />;
  }
}
