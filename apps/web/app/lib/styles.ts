// Inline style objects shared by more than one component. Kept as plain
// module-level constants so they aren't rebuilt on every render.
import type { CSSProperties } from "react";

// Small uppercase caption above a sidebar / pipeline section.
export const sectionLabel: CSSProperties = {
  fontSize: "0.7rem",
  color: "var(--muted)",
  textTransform: "uppercase",
  marginBottom: "0.5rem",
};

// Inline error line under a sidebar control.
export const inlineError: CSSProperties = { fontSize: "0.72rem", color: "#ff8080", marginTop: "0.3rem" };

export function sidebarSelect(disabled: boolean): CSSProperties {
  return {
    width: "100%",
    background: "#151515",
    color: "var(--foreground)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "0.4rem 0.5rem",
    fontSize: "0.8rem",
    cursor: disabled ? "default" : "pointer",
  };
}

// A bordered dark card: outline review, density question, slide result.
export const card: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 10,
  padding: "1rem",
  background: "#111",
};

// "Закрыть ✕" in the modals.
export const closeButton: CSSProperties = {
  background: "transparent",
  border: "1px solid var(--border)",
  borderRadius: 6,
  color: "var(--foreground)",
  padding: "0.25rem 0.6rem",
  fontSize: "0.8rem",
  cursor: "pointer",
};

