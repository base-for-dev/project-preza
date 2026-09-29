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
        <div style={{ alignSelf: "flex-end", maxWidth: "80%", marginLeft: "auto" }}>
          <div
            style={{
              background: "var(--accent)",
              color: "var(--on-accent)",
              borderRadius: "20px 20px 6px 20px",
              padding: "var(--s3) var(--s4)",
              fontSize: "var(--t-body)",
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
          role="alert"
          style={{
            background: "color-mix(in srgb, var(--red) 12%, transparent)",
            borderRadius: "var(--r-md)",
            padding: "var(--s3) var(--s4)",
            color: "var(--red)",
            fontSize: "var(--t-callout)",
          }}
        >
          {message.text}
        </div>
      );
    case "audit":
      return <AuditResult audit={message.audit} density={message.density} brief={message.brief} />;
  }
}
