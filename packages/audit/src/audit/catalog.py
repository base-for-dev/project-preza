"""Every check the audit can report, in one list.

The single source for what AUDIT.md describes and what the web app shows next
to a finding (a plain-language title, the group, whether "fix" works). A test
keeps this list, the checks in code and AUDIT.md from drifting apart: a check
without an entry here, or an entry without a check, fails the suite.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from audit.fixes import fixable


class CheckInfo(BaseModel):
    id: str
    kind: Literal["deterministic", "model"]
    group: str
    title: str
    covers: str
    fixable: bool = False


def _det(id: str, group: str, title: str, covers: str) -> CheckInfo:
    return CheckInfo(id=id, kind="deterministic", group=group, title=title, covers=covers)


LAYOUT = "Вёрстка"
TEMPLATE = "Соответствие шаблону"
DENSITY = "Плотность"
INTEGRITY = "Целостность"
MEANING = "Смысл (модель по картинке слайда)"

_CHECKS = [
    _det(
        "shape_out_of_bounds",
        LAYOUT,
        "Вышло за край слайда",
        "Текст или таблица выходят за границы слайда. Картинки и декор, уходящие за край, — приём дизайна, не ошибка.",
    ),
    _det(
        "shapes_overlap",
        LAYOUT,
        "Тексты наложились",
        "Два блока с текстом перекрываются там, где стоят слова (а не только их рамки) больше чем на 5% меньшего из них.",
    ),
    _det(
        "text_overflow",
        LAYOUT,
        "Текст не помещается в рамку",
        "Оценка высоты текста с переносами больше высоты блока; собственные плотные подписи шаблона не считаются.",
    ),
    _det(
        "margin_violation",
        LAYOUT,
        "Текст в поле у края",
        "Сдвинутый текст ближе к краю слайда, чем шаблон когда-либо ставит текст.",
    ),
    _det(
        "misaligned",
        LAYOUT,
        "Не по направляющим шаблона",
        "Левый край сдвинутого текста не совпадает ни с одной линией, которой пользуется шаблон.",
    ),
    _det(
        "image_distorted",
        LAYOUT,
        "Картинка растянута",
        "Вставленная картинка показана в пропорциях, отличных от её собственных более чем на 10%.",
    ),
    _det(
        "low_contrast",
        LAYOUT,
        "Низкий контраст текста",
        "Контраст цвета текста и цвета за ним ниже 4.5:1 (для крупного текста — 3:1), по WCAG.",
    ),
    _det(
        "font_not_in_template",
        TEMPLATE,
        "Шрифт не из шаблона",
        "Гарнитура, которой нет в наборе шаблона.",
    ),
    _det(
        "too_many_font_families",
        TEMPLATE,
        "Слишком много гарнитур",
        "В колоде больше гарнитур, чем использует сам шаблон (но не меньше двух).",
    ),
    _det(
        "size_not_in_scale",
        TEMPLATE,
        "Кегль не из шкалы шаблона",
        "Размер шрифта, которого нет в типографической шкале шаблона (допуск 0.5 пт).",
    ),
    _det(
        "color_not_in_palette",
        TEMPLATE,
        "Цвет не из палитры",
        "Цвет текста или заливки, которого нет в палитре шаблона.",
    ),
    _det(
        "layout_not_from_template",
        TEMPLATE,
        "Макета нет в шаблоне",
        "Слайд собран на макете, которого в шаблоне не существует.",
    ),
    _det(
        "brand_element_moved",
        TEMPLATE,
        "Сдвинут логотип или колонтитул",
        "Мелкий элемент, который шаблон закрепляет у края слайда, оказался не на своём месте.",
    ),
    _det(
        "too_many_bullets",
        DENSITY,
        "Слишком много пунктов",
        "Больше 6 пунктов в одном текстовом блоке.",
    ),
    _det("bullet_too_long", DENSITY, "Слишком длинный пункт", "Пункт длиннее 15 слов."),
    _det("table_too_large", DENSITY, "Слишком большая таблица", "Больше 7 строк или 5 колонок."),
    _det(
        "chart_too_many_series",
        DENSITY,
        "Слишком много рядов на диаграмме",
        "Больше 5 рядов данных.",
    ),
    _det(
        "slide_fill_ratio",
        DENSITY,
        "Слайд заполнен не так, как в шаблоне",
        "Занятая площадь выходит за диапазон, который встречается в слайдах самого шаблона.",
    ),
    _det(
        "file_not_openable",
        INTEGRITY,
        "Файл .pptx повреждён",
        "Структура экспортированного файла нарушена (битые связи, повторные id, части без типа) — PowerPoint предложил бы «восстановить».",
    ),
    _det(
        "placeholder_text_left",
        INTEGRITY,
        "Остался текст-заглушка",
        "lorem ipsum, XXX, TODO, «вставьте текст».",
    ),
    _det(
        "empty_or_title_only_slide",
        INTEGRITY,
        "Пустой слайд или только заголовок",
        "Кроме титульного и заключительного слайдов: слайд без содержательного текста.",
    ),
    _det(
        "slide_is_picture",
        INTEGRITY,
        "Слайд — одна картинка",
        "Картинка на весь слайд без редактируемого текста и таблиц.",
    ),
    _det(
        "chart_missing_labels",
        INTEGRITY,
        "У диаграммы нет подписей",
        "Диаграмма с подставленными данными без подписей осей, а с несколькими рядами — без легенды.",
    ),
    _det(
        "duplicate_slide",
        INTEGRITY,
        "Два одинаковых слайда",
        "Слайды с тем же заголовком и тем же текстом.",
    ),
    _det(
        "unsupported_figure",
        INTEGRITY,
        "Цифра, которой нет в брифе",
        "Число, процент, сумма или срок на слайде, которых нет в исходных материалах (вероятно, выдумка модели).",
    ),
    _det(
        "language_drift",
        INTEGRITY,
        "Текст не на языке брифа",
        "Слайд написан не на том языке, на котором бриф.",
    ),
]

_MODEL_CHECKS = [
    (
        "title_not_a_conclusion",
        "Заголовок — тема, а не вывод",
        "Заголовок содержит вывод, а не просто называет тему.",
    ),
    (
        "content_off_title",
        "Содержимое не поддерживает заголовок",
        "Содержимое слайда соответствует заголовку.",
    ),
    (
        "no_single_point",
        "Слайд не сводится к одной мысли",
        "Слайд пересказывается одним предложением.",
    ),
    (
        "untraceable_fact",
        "Факт не прослеживается до источника",
        "Каждая цифра или факт на слайде прослеживается до исходных материалов.",
    ),
    (
        "title_only_content",
        "Кроме заголовка нет содержания",
        "На слайде есть реальный контент, а не только заголовок.",
    ),
    (
        "image_off_topic",
        "Картинка не по теме",
        "Картинки и иконки относятся к теме слайда (если их нет — не применяется).",
    ),
    ("leftover_junk", "Служебный мусор на слайде", "Нет реплик спикера и кусков промпта."),
    ("typo", "Опечатка", "Нет опечаток."),
    (
        "table_row_off_point",
        "Строка таблицы или пункт легенды не по делу",
        "Каждая строка таблицы и пункт легенды работают на мысль слайда (если их нет — не применяется).",
    ),
    (
        "disconnected_slide",
        "Слайд не связан с соседними",
        "Соседние слайды связаны между собой логически.",
    ),
]

CATALOG: list[CheckInfo] = [
    *(c.model_copy(update={"fixable": fixable(c.id)}) for c in _CHECKS),
    *(
        CheckInfo(id=i, kind="model", group=MEANING, title=title, covers=covers)
        for i, title, covers in _MODEL_CHECKS
    ),
]
