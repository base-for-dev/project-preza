import type { Finding } from "./types";

export const FINDING_COLOR: Record<Finding["kind"], string> = {
  deterministic: "#f0b84a",
  model: "#c98bf0",
};

export function findingKey(f: Finding): string {
  return `${f.kind}|${f.check}|${f.slide_index}|${f.shape_id ?? ""}|${f.message}`;
}
