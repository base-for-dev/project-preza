# preza-audit

Проверки IR сгенерированной колоды, исправления по выбору пользователя и каталог проверок.

Полное описание каждой проверки, различие между детерминированными и модельными и что делает кнопка «Исправить» — в [`AUDIT.md`](../../AUDIT.md). Здесь — интерфейс пакета.

```python
from audit import CATALOG, Finding, apply_fixes, run_checks, run_model_checks

findings = run_checks(deck, template_deck, source_text=brief)  # 25 детерминированных проверок
findings = run_model_checks(deck, brief, slide_images)  # 10 модельных, по картинкам
report = apply_fixes(
    deck, template_deck, chosen_findings, brief
)  # исправления: копия колоды + отчёт
```

- `deck` — собранная колода (`layout.compose_deck`); `template_deck` — разобранный шаблон, из которого выведены допустимые шрифты, размеры, цвета, поля и направляющие.
- `Finding(check, kind, slide_index, shape_id, message)`; `kind` — `deterministic` или `model`.
- `run_checks` не рендерит и не ходит в сеть. Проверка `file_not_openable` требует экспорта, поэтому её запускает сервер (`export.validate`).
- `run_model_checks` принимает картинки слайдов от вызывающего (`{slide.index: data-URI}`): пакет сам ничего не рисует. Один вызов VLM на слайд; сбой вызова — пропущенное мнение, а не ошибка.
- `apply_fixes` работает на копии, возвращает `FixReport(deck, applied, skipped)`; невозможное исправление попадает в `skipped` с причиной по-русски.
- `CATALOG` — список всех 36 проверок (название, группа, описание, исправима ли); `test_check_catalog.py` держит его, код и `AUDIT.md` синхронными.

| Модуль | Содержимое |
| --- | --- |
| `checks.py` | границы, наложения, переполнение, шаблон (шрифт/размер/цвет), плотность, целостность, `run_checks` |
| `design_rules.py` | контраст, поля, направляющие, растянутые картинки, слайд-картинка, макеты и гарнитуры, логотипы, графики |
| `content_validation.py` | десять модельных проверок |
| `fixes.py` | исправления |
| `catalog.py` | каталог |
