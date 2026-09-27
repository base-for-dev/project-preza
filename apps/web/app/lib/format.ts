import { PURPOSE_LABELS, VARIANTS } from "./constants";
import type { Density, Message, TaskMaterials } from "./types";

export function slideKind(layoutName: string): string {
  const match = /^([a-z]+)-\d+$/.exec(layoutName);
  return match ? PURPOSE_LABELS[match[1]!] ?? "" : "";
}

export function hasMaterials(m: TaskMaterials): boolean {
  return m.files.length > 0 || m.story.trim() !== "";
}

export function formatSeconds(total: number): string {
  // Round once up front so 59.6 s reads "1:00", not "0:60".
  const rounded = Math.round(total);
  const m = Math.floor(rounded / 60);
  const s = rounded % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function densityLabel(density: Density): string {
  return VARIANTS.find((v) => v.key === density)?.label ?? density;
}

// Best-effort keyword read of the brief's own wording — no LLM call, just
// scans for words a person would naturally use to ask for more/less detail.
// Returns null when the brief doesn't say either way, so the caller can ask
// instead of silently guessing.
export function detectDensity(brief: string): Density | null {
  const text = brief.toLowerCase();
  if (/сжат|кратк|коротк|минимал/.test(text)) return "compact";
  if (/подробн|детальн|развёрнут|развернут|максимал/.test(text)) return "detailed";
  if (/стандарт|обычн|средн/.test(text)) return "standard";
  return null;
}

export function uid() {
  return Math.random().toString(36).slice(2);
}

export function sessionTitle(messages: Message[]): string {
  const firstBrief = messages.find((m) => m.kind === "user")?.text ?? "Новый чат";
  return firstBrief.length > 40 ? firstBrief.slice(0, 40) + "…" : firstBrief;
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
