import type { KeyboardEvent } from "react";

// Activate a clickable non-button element from the keyboard (Enter/Space),
// only when the element itself is focused — not a control inside it.
export function onActivateKey(action: () => void) {
  return (e: KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      action();
    }
  };
}
