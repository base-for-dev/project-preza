import type { GenerationSettings, QuestionId, QuestionOption } from "./questions";

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
export type AutoShape = ShapeBase & {
  kind: "autoshape";
  autoshape_type: string | null;
  fill_color: Color | null;
  paragraphs: Paragraph[];
};
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
export type TableShape = ShapeBase & {
  kind: "table";
  rows: TableCell[][];
  column_widths: number[];
  row_heights: number[];
};
export type PassthroughShape = ShapeBase & { kind: "passthrough"; original_shape_type: string | null };
export type ChartShape = ShapeBase & {
  kind: "chart";
  chart_type: "column" | "bar" | "line" | "pie" | "doughnut";
  title: string;
  unit: string;
  category_label: string;
  categories: string[];
  series: { name: string; values: number[] }[];
};
export type DiagramShape = ShapeBase & {
  kind: "diagram";
  diagram_type: "process" | "cycle" | "hierarchy" | "timeline" | "icons";
  items: { label: string; detail: string; icon: string }[];
};
export type Shape =
  | TextBoxShape
  | AutoShape
  | PictureShape
  | TableShape
  | PassthroughShape
  | ChartShape
  | DiagramShape;
export type Slide = { index: number; layout_name: string; shapes: Shape[]; background: Color | null; notes: string | null };
export type Deck = { slide_width: number; slide_height: number; slides: Slide[]; theme_colors: Record<string, string> };
export type Finding = {
  check: string;
  kind: "deterministic" | "model";
  slide_index: number;
  shape_id: number | null;
  related_shape_id: number | null;
  message: string;
};
// GET /api/audit/checks — what the audit can report, for titles and grouping.
export type CheckInfo = {
  id: string;
  kind: "deterministic" | "model";
  group: string;
  title: string;
  covers: string;
  fixable: boolean;
};
export type FixResponse = {
  deck: Deck;
  applied: Finding[];
  skipped: { finding: Finding; reason: string }[];
  findings: Finding[];
};
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
  skills?: Record<string, string>;
};

export type Density = "compact" | "standard" | "detailed";

// GET /api/templates/{id}/inspect — the template with each shape's slot role.
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

// Mirrors generator.outline.SlideIntent / Outline — the plan the user
// reviews before generation (Gamma-style).
export type SlideIntent = { role: string; intent: string; summary: string; seconds: number };
export type Outline = { slides: SlideIntent[] };

export type BrandPack = {
  id: string;
  name: string;
  status: "building" | "ready" | "error";
  error: string | null;
  templates: string[];
};

// `previews`: how many rendered preview images the server has ready (0 while
// they're still rendering); `tags`: picker filters (dark/light/colorful/business).
export type TemplateInfo = { id: string; label: string; previews?: number; tags?: string[] };

// What goes with a brief besides its text — see "Материалы" in the composer.
export type TaskMaterials = { files: File[]; story: string };

export type Message =
  | { id: string; kind: "user"; text: string }
  | { id: string; kind: "audit"; audit: DeckAudit; density: Density; brief: string }
  | { id: string; kind: "error"; text: string }
  | {
      id: string;
      kind: "outline-review";
      brief: string;
      settings: GenerationSettings;
      sourceId: string;
      outline: Outline;
      confirmed: boolean;
    }
  | {
      // One of the setup questions asked in the chat after a brief (see
      // lib/questions.ts). It carries the whole questionnaire state — the
      // brief, its materials, the answers so far — so answering it needs
      // nothing outside the message, and chats can't mix their answers.
      id: string;
      kind: "question";
      qid: QuestionId;
      prompt: string;
      options: QuestionOption[];
      answered: string | null;
      brief: string;
      materials: TaskMaterials;
      settings: GenerationSettings;
      asked: QuestionId[];
    };

export type QuestionMessage = Extract<Message, { kind: "question" }>;

export type OutlineReviewMessage = Extract<Message, { kind: "outline-review" }>;

export type StageStatus = "idle" | "active" | "done" | "error";

export type ChatSession = {
  id: string;
  title: string;
  messages: Message[];
  busy: boolean;
  stages: Record<string, StageStatus>;
  // Wall-clock start of the running generation (ms), for the budget timer.
  startedAt: number | null;
};

// Body shared by POST /api/outline and POST /api/audit/stream (the latter
// adds `outline`) — mirrors the server's OutlineRequest.
export type GenerationRequest = {
  template_id: string;
  brief: string;
  slide_count: number | null;
  duration_minutes: number | null;
  mode: string | null;
  density: Density;
  brand_pack_id: string;
  source_id: string;
  text_mode: string;
  // False when there is no talk: no speaker notes are generated.
  speaker_notes: boolean;
  card_split: "input_breaks" | "auto";
};

export type PreviewStatus = "loading" | "ready" | "error";

// /api/settings — the connection to the model (the key is write-only).
export type ProviderPreset = { id: string; label: string; api_base: string; needs_key: boolean; hint: string };
export type SettingsOut = {
  provider: string;
  api_base: string;
  has_key: boolean;
  key_hint: string;
  model: string;
  vision_model: string;
  skill_models: Record<string, string>;
  only_my_model: boolean;
  request_timeout: number | null;
  presets: ProviderPreset[];
  default_api_base: string;
  skills: { name: string; model: string; modality: string }[];
  key_source: "app" | "env" | "none";
};
export type SettingsIn = {
  provider: string;
  api_base: string;
  // undefined keeps the stored key, "" removes it.
  api_key?: string;
  model: string;
  vision_model: string;
  skill_models: Record<string, string>;
  only_my_model: boolean;
  request_timeout: number | null;
};
export type ConnectionTest = { ok: boolean; model: string; seconds: number | null; reply: string; error: string };
