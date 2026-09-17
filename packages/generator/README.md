# preza-generator

Бриф -> outline -> контент по каждому слайду, через промпты `skills/`.

Используется `apps/server`. См. `ARCHITECTURE.md` в корне репозитория — как этот пакет встроен в пайплайн.

## Генерация outline

`generate_outline(brief, slide_count, available_patterns)` вызывает скилл
`outline-generation` (промпт в `skills/outline-generation/SKILL.md`,
конфиг модели в `skills/outline-generation/config.yaml`) через
`preza-inference` и возвращает `Outline` — упорядоченный список
`SlideIntent{role, intent, summary}`. `Outline`/`SlideIntent` живут в
`generator.outline`, а не в `packages/ir_schema`: это рабочие данные между
собственными этапами `generator`'а (outline -> content), а не общий
IR-контракт между пакетами пайплайна.

Требует `INFERENCE_API_KEY` в `.env` во время выполнения (см. `.env.example`);
см. `evals/demo_outline.py` — ручная демонстрация на реальном шаблоне.
