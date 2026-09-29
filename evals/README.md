# Evals

Сквозные тесты пайплайна на настоящих файлах. Главный риск проекта — генерализация: работает ли всё на шаблоне, которого раньше не видели, без правки кода.

```
evals/
  templates/                   — шаблоны-образцы; *.pptx в git не хранятся, на чистом клоне
                                 их собирает generate_behance_templates.py
  test_unseen_template.py      — два шаблона, собранные с нуля (4:3 и 16:9, другие шрифты,
                                 палитры, названия макетов); весь пайплайн без модели
  test_roundtrip.py            — .pptx → IR → .pptx на реальном шаблоне
  build_submission.py          — один бриф × шаблоны × 3 варианта → submission/
  validate_pptx.py             — структурная проверка файлов (`export.validate`)
  demo_*.py                    — запуск отдельного этапа руками, для отладки
```

Запуск: `uv run pytest evals`.

## Сдача: N шаблонов × 3 варианта

При запущенном сервере (`make start`):

```bash
make submission                      # 3 шаблона по умолчанию → submission/
uv run python evals/build_submission.py --templates vktech vk-education --out submission
uv run python evals/validate_pptx.py submission/*.pptx
```

В `submission/` (в git не попадает) лежит по `.pptx` на каждый вариант и `summary.json`: время генерации, число и тексты находок аудита по каждому варианту.
