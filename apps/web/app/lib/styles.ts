// Inline style objects shared by more than one component. They only compose
// the design tokens in globals.css (colours, radii, spacing, type sizes).
import type { CSSProperties } from "react";

// Small caption above a sidebar / pipeline section.
export const sectionLabel: CSSProperties = {
  fontSize: "var(--t-footnote)",
  fontWeight: 600,
  color: "var(--label-2)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  marginBottom: "var(--s2)",
};

// Inline error line under a control.
export const inlineError: CSSProperties = {
  fontSize: "var(--t-footnote)",
  color: "var(--red)",
  marginTop: "var(--s1)",
};

// A picker-style button: a field with a label, used in the sidebar.
export function sidebarSelect(disabled: boolean): CSSProperties {
  return {
    width: "100%",
    minHeight: "var(--hit)",
    background: "var(--fill-2)",
    color: "var(--label)",
    border: "0.5px solid var(--separator)",
    borderRadius: "var(--r-sm)",
    padding: "0 var(--s3)",
    fontSize: "var(--t-callout)",
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.5 : 1,
  };
}

// A grouped surface: outline review, questions, slide results.
export const card: CSSProperties = {
  borderRadius: "var(--r-lg)",
  padding: "var(--s4)",
  background: "var(--bg-3)",
  boxShadow: "var(--shadow-1)",
};

// Secondary button ("Закрыть", "Отменить", ...): a tinted fill, no border.
export const closeButton: CSSProperties = {
  background: "var(--fill)",
  border: "none",
  borderRadius: "var(--r-sm)",
  color: "var(--label)",
  minHeight: 28,
  padding: "0 var(--s3)",
  fontSize: "var(--t-subhead)",
  fontWeight: 500,
  cursor: "pointer",
};

// The filled, accent-coloured primary action.
export const prominentButton: CSSProperties = {
  ...closeButton,
  background: "var(--accent)",
  color: "var(--on-accent)",
  fontWeight: 600,
};

// A full-screen scrim with a centred sheet (see .scrim / .sheet in globals.css).
export const scrimStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 50,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "var(--s5)",
};
