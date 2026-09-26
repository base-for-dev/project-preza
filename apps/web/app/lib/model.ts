

// Mirrors packages/ir_schema/src/ir_schema/models.py — the pipeline's IR.
export type Color = { kind: "rgb" | "theme"; rgb: string | null; theme_color: string | null };
export type TextRun = {
  text: string;
  font_name: string | null;
  font_size_pt: number | null;
  bold: boolean | null;
  italic: boolean | null;
  underline: boolean | null;
  color: Color | null;
};
export type Paragraph = { runs: TextRun[]; alignment: string | null; level: number };
export type ShapeBase = {
  shape_id: number;
  name: string;
  z_order: number;
  left: number;
  top: number;
  width: number;
  height: number;
  rotation: number;
  is_placeholder: boolean;
  placeholder_type: string | null;
  placeholder_idx: number | null;
};
export type TextBoxShape = ShapeBase & { kind: "text_box"; paragraphs: Paragraph[] };
export type AutoShape = ShapeBase & { kind: "autoshape"; autoshape_type: string | null; fill_color: Color | null; paragraphs: Paragraph[] };
export type PictureShape = ShapeBase & {
  kind: "picture";
  image_bytes_b64: string | null;
  content_type: string | null;
  crop_left: number;
  crop_top: number;
  crop_right: number;
  crop_bottom: number;
  attribution_text: string | null;
  attribution_url: string | null;
};
export type TableCell = { paragraphs: Paragraph[] };
export type TableShape = ShapeBase & { kind: "table"; rows: TableCell[][]; column_widths: number[]; row_heights: number[] };
export type PassthroughShape = ShapeBase & { kind: "passthrough"; original_shape_type: string | null };
export type Shape = TextBoxShape | AutoShape | PictureShape | TableShape | PassthroughShape;
export type Slide = { index: number; layout_name: string; shapes: Shape[]; background: Color | null; notes: string | null };
export type Deck = { slide_width: number; slide_height: number; slides: Slide[]; theme_colors: Record<string, string> };
export type Finding = { check: string; kind: "deterministic"; slide_index: number; shape_id: number | null; message: string };
export type VariantResult = { deck: Deck; findings: Finding[] };
export type FactSheet = { project_name: string; one_liner: string } & Record<string, unknown>;
export type DeckAudit = {
  compact: VariantResult;
  standard: VariantResult;
  detailed: VariantResult;
  slide_seconds: number[];
  spoken_seconds: number[];
  fact_sheet: FactSheet | null;
  timings: Record<string, number>;
};

export type Density = "compact" | "standard" | "detailed";

export type SlotInfo = {
  has_title: boolean;
  body_slots: number;
  card_slots: number;
  has_table: boolean;
  has_picture: boolean;
  title_font_size_pt: number | null;
  body_lines: number | null;
  body_chars_per_line: number | null;
};
export type InspectedSlide = { index: number; layout_name: string; roles: Record<string, string>; slots: SlotInfo };
export type InspectedTemplate = { deck: Deck; slides: InspectedSlide[] };

// role -> [outline color, Russian label, what generation does with it]
export const ROLE_STYLE: Record<string, [string, string, string]> = {
  title: ["#ff5c8a", "Заголовок", "сюда пишется заголовок слайда"],
  body: ["#4da3ff", "Текст", "сюда идут пункты или абзац"],
  card: ["#3ddc97", "Карточка", "повторяющийся слот: по одному пункту в каждый"],
  table: ["#ffb020", "Таблица", "сюда встаёт таблица с данными"],
  picture: ["#b48cff", "Картинка", "фото по теме слайда (Unsplash)"],
  chrome: ["#8a8a8a", "QR / лого / ссылка", "служебный элемент — не трогаем"],
  display_accent: ["#8a8a8a", "Акцент-надпись", "крупная декоративная надпись — не трогаем"],
  data_placeholder: ["#8a8a8a", "«ХХ%» на графике", "метка данных графика — не трогаем"],
  text: ["#e0e0e0", "Прочий текст", "используется только в крайнем случае"],
};

export type BrandPack = { id: string; name: string; status: "building" | "ready" | "error"; error: string | null; templates: string[] };

// What goes with a brief besides its text — see "Материалы" in the composer.
export type TaskMaterials = { files: File[]; story: string };
export const EMPTY_MATERIALS: TaskMaterials = { files: [], story: "" };

export function hasMaterials(m: TaskMaterials): boolean {
  return m.files.length > 0 || m.story.trim() !== "";
}

export function formatSeconds(total: number): string {
  const m = Math.floor(total / 60);
  const s = Math.round(total % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s} с`;
}

export const VARIANTS: { key: Density; label: string }[] = [
  { key: "compact", label: "Сжато" },
  { key: "standard", label: "Стандарт" },
  { key: "detailed", label: "Подробно" },
];

// Mirrors generator.outline.MODES — see "Content modes" in
// skills/outline-generation/SKILL.md for what each one does to the writing.
export const MODES: { key: string; label: string }[] = [
  { key: "", label: "Авто (по брифу)" },
  { key: "briefing", label: "Статус-отчёт" },
  { key: "narrative", label: "История / питч" },
  { key: "pyramid", label: "Выводы вперёд" },
  { key: "showcase", label: "Витрина / анонс" },
  { key: "instructional", label: "Обучение" },
];

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

export type Message =
  | { id: string; kind: "user"; text: string }
  | { id: string; kind: "audit"; audit: DeckAudit; density: Density }
  | { id: string; kind: "error"; text: string }
  | {
      id: string;
      kind: "density-question";
      brief: string;
      answered: Density | null;
      materials: TaskMaterials;
    };

export type StageStatus = "idle" | "active" | "done" | "error";

export function uid() {
  return Math.random().toString(36).slice(2);
}

export type TemplateInfo = { id: string; label: string };

export type ChatSession = {
  id: string;
  title: string;
  messages: Message[];
  busy: boolean;
  stages: Record<string, StageStatus>;
  // Wall-clock start of the running generation (ms), for the budget timer.
  startedAt: number | null;
};

export function sessionTitle(messages: Message[]): string {
  const firstBrief = messages.find((m) => m.kind === "user")?.text ?? "Новый чат";
  return firstBrief.length > 40 ? firstBrief.slice(0, 40) + "…" : firstBrief;
}
