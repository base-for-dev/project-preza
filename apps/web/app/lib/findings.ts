import type { Finding } from "./types";

export const FINDING_COLOR: Record<Finding["kind"], string> = {
  deterministic: "var(--orange)",
  model: "var(--purple)",
};

export function findingKey(f: Finding): string {
  return `${f.kind}|${f.check}|${f.slide_index}|${f.shape_id ?? ""}|${f.message}`;
}
