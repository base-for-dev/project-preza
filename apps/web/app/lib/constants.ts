import type { Density, TaskMaterials } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const UPLOAD_OPTION = "__upload__";
// Empty string, not a sentinel token — matches the backend's OutlineRequest
// default (""), which means "pick a template from the brief's topic" (see
// server/main.py's `_choose_template`).
export const AUTO_TEMPLATE_OPTION = "";

export const NO_PACK_OPTION = "";
export const UPLOAD_PACK_OPTION = "__upload_pack__";

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
  { key: "parse", label: "Изучаем шаблон" },
  { key: "digest", label: "Читаем ваши материалы" },
  { key: "outline", label: "Составляем план" },
  { key: "content", label: "Пишем текст слайдов и выступления" },
  { key: "layout", label: "Раскладываем по слайдам" },
  { key: "audit", label: "Проверяем результат" },
  // Client-side only: lit when the finished deck is shown in the chat.
  { key: "ready", label: "Готово" },
];

// The generation budget from the task statement: everything after the
// context is prepared must finish within five minutes.
export const GENERATION_BUDGET_SECONDS = 300;

export const DURATIONS: { value: number; label: string }[] = [
  { value: 0, label: "—" },
  ...[3, 5, 7, 10, 15, 20].map((m) => ({ value: m, label: `${m} мин` })),
];

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

// Gamma-style text mode: write from a topic, condense the user's long text,
// or keep the user's own wording (see generator.outline.TEXT_MODES).
export const TEXT_MODES: { key: string; label: string }[] = [
  { key: "generate", label: "Создать" },
  { key: "condense", label: "Сжать мой текст" },
  { key: "preserve", label: "Мой текст дословно" },
];

// Readable names for a catalogued slide's purpose (role ids look like
// "team-09", see design_system.catalog). Raw template layout names — "空白",
// "Пустой с заголовком", "Title and Content" — are the template file's
// internals and are never shown.
export const PURPOSE_LABELS: Record<string, string> = {
  title: "Титул",
  agenda: "Содержание",
  section: "Раздел",
  problem: "Проблема",
  solution: "Решение",
  features: "Возможности",
  stats: "Цифры",
  steps: "Этапы",
  timeline: "Хронология",
  comparison: "Сравнение",
  team: "Команда",
  demo: "Демо",
  quote: "Цитата",
  image: "Изображение",
  content: "Контент",
  contacts: "Контакты",
  closing: "Финал",
};

// A line of three or more dashes splits the brief into one slide per part.
// (No `g` flag: `.test()` stays stateless, so it's safe to reuse.)
export const SECTION_BREAK = /^\s*-{3,}\s*$/m;

export const EMPTY_MATERIALS: TaskMaterials = { files: [], story: "" };

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

// Files accepted as task materials (see /api/sources).
export const MATERIALS_ACCEPT = ".zip,.md,.txt,.pdf,.docx,.pptx,.rst,.csv,.png,.jpg,.jpeg,.webp";
