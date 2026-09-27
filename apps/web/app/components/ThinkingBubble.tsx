import { useEffect, useState } from "react";
import { THINKING_PHRASES } from "../lib/constants";
import { BlinkingDots } from "./BlinkingDots";

// Shown only while the viewed chat is busy, so it mounts at the start of a
// run: the phrase rotation lives here rather than in the page, which would
// otherwise re-render every message and slide on each tick.
export function ThinkingBubble() {
  const [phrase, setPhrase] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setPhrase((i) => (i + 1) % THINKING_PHRASES.length), 2600);
    return () => clearInterval(interval);
  }, []);
  const text = THINKING_PHRASES[phrase] ?? "Думаю…";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "0.75rem 1rem",
        background: "#111",
        width: "fit-content",
      }}
    >
      <BlinkingDots color="#e8c547" gap="3px" />
      <span
        style={{
          fontSize: "0.82rem",
          background:
            "linear-gradient(90deg, var(--muted) 40%, var(--foreground) 50%, var(--muted) 60%)",
          backgroundSize: "200% auto",
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          color: "transparent",
          animation: "shimmer 2.2s linear infinite",
        }}
      >
        {text}
      </span>
    </div>
  );
}
