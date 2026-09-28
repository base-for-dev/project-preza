import { useEffect, useState } from "react";
import { API_URL } from "./constants";

// Template fonts (Chakra Petch, Montserrat, ...) aren't installed on the
// viewer's machine, so a slide drawn in the browser would fall back to a
// wider system font and reflow. The server keeps the template's own font
// files (decoded from the .pptx, or fetched from Google Fonts — see
// packages/export/src/export/fonts.py) and serves @font-face rules for them;
// this loads those rules once per family.
const requested = new Set<string>();

export function useTemplateFonts(families: string[]) {
  const key = [...new Set(families)].sort().join("\n");
  useEffect(() => {
    const fresh = key.split("\n").filter((f) => f && !requested.has(f));
    if (fresh.length === 0) return;
    fresh.forEach((f) => requested.add(f));
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = `${API_URL}/api/fonts.css?${fresh.map((f) => `family=${encodeURIComponent(f)}`).join("&")}`;
    document.head.appendChild(link);
  }, [key]);
}

// Bumps whenever the browser finishes loading fonts, so text measured before
// its real font arrived (AutoFitText) can measure again.
export function useFontsLoaded(): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (typeof document === "undefined" || !document.fonts) return;
    const bump = () => setTick((t) => t + 1);
    document.fonts.addEventListener("loadingdone", bump);
    return () => document.fonts.removeEventListener("loadingdone", bump);
  }, []);
  return tick;
}
