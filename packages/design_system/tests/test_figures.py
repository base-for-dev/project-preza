"""Numeric-claim extraction.

uv run pytest packages/design_system
"""

from __future__ import annotations

from design_system import figures, strip_unsupported


def test_digits_are_normalised():
    assert figures("Рост 42 % и 12 000 клиентов") == {"42", "12000"}


def test_precise_number_words_count_as_figures():
    assert "пятьдесят" in figures("Пятьдесят тысяч бронирований в месяц")
    assert "тысяч" in figures("Пятьдесят тысяч бронирований в месяц")
    assert figures("рост в десять раз") == {"десять"}


def test_vague_quantities_are_not_figures():
    assert figures("Десятки коворкингов и сотни пользователей, несколько городов") == set()


def test_number_words_grounded_by_the_brief_are_allowed():
    assert figures("пятьдесят тысяч") - figures("нам нужно пятьдесят тысяч рублей") == set()


def test_ordinary_words_are_not_mistaken_for_numbers():
    assert figures("стоимость сорванных состязаний тысячелетия процентная ставка") == set()


def test_unit_word_after_a_digit_is_not_counted_twice():
    assert figures("10 тысяч") == {"10"}


# --- strip_unsupported ---------------------------------------------------


def test_strip_unsupported_removes_only_the_ungrounded_figure():
    text = "Привлечение первых 5 000 пользователей через партнерства"
    out = strip_unsupported(text, allowed=set())
    assert "5 000" not in out and "5000" not in out
    assert "пользователей" in out and "партнерства" in out


def test_strip_unsupported_keeps_a_figure_the_brief_grounds():
    text = "Ищем 5 млн рублей на запуск"
    out = strip_unsupported(text, allowed=figures("нам нужно 5 млн рублей"))
    assert out == text  # nothing removed — the figure is grounded


def test_strip_unsupported_removes_a_number_word_too():
    text = "Рост в десять раз за квартал"
    out = strip_unsupported(text, allowed=set())
    assert "десять" not in out.lower()
    assert "Рост" in out and "квартал" in out


def test_strip_unsupported_leaves_no_double_spaces_or_stray_punctuation():
    text = "Тестирование: 30 садов в Казани"
    out = strip_unsupported(text, allowed=set())
    assert "  " not in out
    assert not out.startswith((" ", ",", "-"))
    assert not out.endswith((" ", ",", "-"))


def test_strip_unsupported_removes_the_dangling_unit_word_too():
    # Deleting just "10" would leave "тысяч" stranded and meaningless on its
    # own — confirmed live: exactly this produced "Рост до тысяч пользователей".
    text = "Рост до 10 тысяч пользователей"
    out = strip_unsupported(text, allowed=set())
    assert "тысяч" not in out.lower()
    assert "10" not in out
    assert "Рост" in out and "пользователей" in out


def test_strip_unsupported_keeps_a_grounded_number_and_its_unit():
    text = "Рост до 10 тысяч пользователей"
    out = strip_unsupported(text, allowed=figures("мы ждём 10 тысяч пользователей"))
    assert out == text
