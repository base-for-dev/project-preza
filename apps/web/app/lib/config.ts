

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const UPLOAD_OPTION = "__upload__";
// Empty string, not a sentinel token — matches the backend's OutlineRequest
// default (""), which means "pick a template from the brief's topic" (see
// server/main.py's `_choose_template`).
export const AUTO_TEMPLATE_OPTION = "";


export const THINKING_PHRASES = [
  "Разбираю шаблон и паттерны слайдов…",
  "Прикидываю структуру презентации…",
  "Пишу outline по брифу…",
  "Раскладываю контент по слайдам…",
  "Подбираю формулировки для заголовков…",
  "Проверяю плотность буллетов…",
  "Почти готово…",
];

export const PIPELINE_STAGES: { key: string; label: string; disabled?: boolean }[] = [
  { key: "parse", label: "Разбор шаблона" },
  { key: "digest", label: "Разбор материалов" },
  { key: "outline", label: "Генерация outline" },
  { key: "content", label: "Слайды + текст выступления" },
  { key: "layout", label: "Сборка вёрстки" },
  { key: "audit", label: "Аудит" },
];

// The generation budget from the task statement: everything after the
// context is prepared must finish within five minutes.
export const GENERATION_BUDGET_SECONDS = 300;

export const DURATIONS: { value: number; label: string }[] = [
  { value: 0, label: "—" },
  ...[3, 5, 7, 10, 15, 20].map((m) => ({ value: m, label: `${m} мин` })),
];

export const NO_PACK_OPTION = "";
export const UPLOAD_PACK_OPTION = "__upload_pack__";
