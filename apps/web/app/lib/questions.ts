// The questions the assistant asks in the chat after a brief is sent, in the
// order a person would decide them: how long the talk is, then how many
// slides that means, what to do with their own text, the delivery style, and
// how detailed to be. Each option's first entry is the default, so a quick
// run through is just "first button" every time. A question is skipped when
// the brief already answers it.
import { DURATIONS, MODES, SECTION_BREAK, TEXT_MODES, VARIANTS } from "./constants";
import { detectDensity } from "./format";
import type { Density } from "./types";

// Generation knobs the questions fill in.
export type GenerationSettings = {
  // Talk length in minutes; 0 = no talk.
  duration: number;
  // 0 = auto: the server derives it from the talk length (or uses 10).
  slideCount: number;
  textMode: string;
  mode: string;
  density: Density;
  // The template this generation uses, fixed when the plan is requested so
  // the plan and the slides written for it always agree. Unset until then
  // (the sidebar's current choice applies).
  templateId?: string;
};

export const DEFAULT_SETTINGS: GenerationSettings = {
  duration: 0,
  slideCount: 0,
  textMode: "generate",
  mode: "",
  density: "standard",
};

export type QuestionId = "duration" | "slideCount" | "textMode" | "mode" | "density" | "template";

// Asked last, only when no template was chosen and no brand pack supplies one.
export const TEMPLATE_QUESTION = {
  id: "template" as const,
  prompt: "Вы не выбрали шаблон. Выбрать его сейчас?",
  options: [
    { value: "pick", label: "Выбрать шаблон" },
    { value: "auto", label: "Подобрать автоматически" },
  ],
};

export type QuestionOption = { value: string; label: string };

type QuestionDef = {
  id: QuestionId;
  prompt: string;
  options: (answers: GenerationSettings) => QuestionOption[];
  // True when the brief already settles this question.
  skip?: (brief: string) => boolean;
  apply: (answers: GenerationSettings, value: string) => GenerationSettings;
};

export const QUESTIONS: QuestionDef[] = [
  {
    id: "duration",
    prompt: "Сколько минут будет длиться выступление?",
    options: () =>
      DURATIONS.map((d) => ({
        value: String(d.value),
        label: d.value === 0 ? "Выступления не будет" : d.label,
      })),
    apply: (a, v) => ({ ...a, duration: Number(v) }),
  },
  {
    id: "slideCount",
    prompt: "Сколько слайдов сделать?",
    options: (a) => [
      { value: "0", label: a.duration ? "Авто" : "На ваше усмотрение" },
      ...[5, 7, 10, 12, 15].map((n) => ({ value: String(n), label: String(n) })),
    ],
    // "---" breaks in the brief already fix one slide per part.
    skip: (brief) => SECTION_BREAK.test(brief),
    apply: (a, v) => ({ ...a, slideCount: Number(v) }),
  },
  {
    id: "textMode",
    prompt: "Что сделать с текстом, который вы прислали?",
    options: () =>
      TEXT_MODES.map((m) => ({
        value: m.key,
        label: m.key === "generate" ? "Создать по заданной теме" : m.label,
      })),
    apply: (a, v) => ({ ...a, textMode: v }),
  },
  {
    id: "mode",
    prompt: "В каком стиле подать материал?",
    options: () =>
      MODES.map((m) => ({ value: m.key, label: m.key === "" ? "Подберите сами" : m.label })),
    apply: (a, v) => ({ ...a, mode: v }),
  },
  {
    id: "density",
    prompt: "Насколько подробной должна быть презентация?",
    options: () => VARIANTS.map((v) => ({ value: v.key, label: v.label })),
    skip: (brief) => detectDensity(brief) !== null,
    apply: (a, v) => ({ ...a, density: v as Density }),
  },
];

// Settings the brief itself implies, before any question is asked.
export function settingsFromBrief(brief: string): GenerationSettings {
  return { ...DEFAULT_SETTINGS, density: detectDensity(brief) ?? DEFAULT_SETTINGS.density };
}

// The next question to ask after `answered`, or null when all are settled.
export function nextQuestion(brief: string, answered: QuestionId[]): QuestionDef | null {
  return QUESTIONS.find((q) => !answered.includes(q.id) && !q.skip?.(brief)) ?? null;
}

export function questionById(id: QuestionId): QuestionDef {
  return QUESTIONS.find((q) => q.id === id)!;
}
