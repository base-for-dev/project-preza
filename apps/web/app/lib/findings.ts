import type { Deck, Finding, Shape } from "./types";

// Where a finding sits on its slide, as fractions of the slide (0..1), so the
// same box can be drawn over a preview of any size.
export type Highlight = { left: number; top: number; width: number; height: number; kind: Finding["kind"] };

// The shapes a finding is about: its own, plus the other one of an overlapping pair.
function shapeIds(finding: Finding): number[] {
  return [finding.shape_id, finding.related_shape_id].filter((id): id is number => id !== null);
}

export function highlightsFor(deck: Deck, slideIndex: number, findings: Finding[]): Highlight[] {
  const slide = deck.slides[slideIndex];
  if (!slide) return [];
  const out: Highlight[] = [];
  for (const finding of findings) {
    for (const id of shapeIds(finding)) {
      const shape: Shape | undefined = slide.shapes.find((s) => s.shape_id === id);
      if (!shape) continue;
      out.push({
        left: shape.left / deck.slide_width,
        top: shape.top / deck.slide_height,
        width: shape.width / deck.slide_width,
        height: shape.height / deck.slide_height,
        kind: finding.kind,
      });
    }
  }
  return out;
}

export const FINDING_COLOR: Record<Finding["kind"], string> = {
  deterministic: "#f0b84a",
  model: "#c98bf0",
};

export function findingKey(f: Finding): string {
  return `${f.kind}|${f.check}|${f.slide_index}|${f.shape_id ?? ""}|${f.message}`;
}
