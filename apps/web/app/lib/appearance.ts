// The user's look: light / dark / follow the system, and the accent colour.
// Kept in this browser (localStorage) and applied to <html> before first paint
// (see the inline script in layout.tsx) so there is no flash.

export type Theme = "system" | "light" | "dark";
export type Appearance = { theme: Theme; accent: string };

export const DEFAULT_APPEARANCE: Appearance = { theme: "system", accent: "blue" };

// Named system colours follow the theme (each has a light and a dark value in
// globals.css); anything else is a custom #rrggbb.
export const ACCENTS: { id: string; label: string }[] = [
  { id: "blue", label: "Синий" },
  { id: "purple", label: "Фиолетовый" },
  { id: "pink", label: "Розовый" },
  { id: "red", label: "Красный" },
  { id: "orange", label: "Оранжевый" },
  { id: "green", label: "Зелёный" },
  { id: "teal", label: "Бирюзовый" },
];

const KEY = "preza-appearance";

export function loadAppearance(): Appearance {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULT_APPEARANCE, ...JSON.parse(raw) } : DEFAULT_APPEARANCE;
  } catch {
    return DEFAULT_APPEARANCE;
  }
}

export function accentValue(accent: string): string {
  return accent.startsWith("#") ? accent : `var(--${accent})`;
}

export function applyAppearance(a: Appearance): void {
  const root = document.documentElement;
  if (a.theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", a.theme);
  root.style.setProperty("--accent", accentValue(a.accent));
}

export function saveAppearance(a: Appearance): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(a));
  } catch {
    // private mode: the choice just lasts until the page closes
  }
  applyAppearance(a);
}

// Runs in <head> before the page paints.
export const BOOT_SCRIPT = `try{var a=JSON.parse(localStorage.getItem("${KEY}")||"null");if(a){var r=document.documentElement;if(a.theme==="light"||a.theme==="dark")r.setAttribute("data-theme",a.theme);if(a.accent)r.style.setProperty("--accent",a.accent.charAt(0)==="#"?a.accent:"var(--"+a.accent+")")}}catch(e){}`;
