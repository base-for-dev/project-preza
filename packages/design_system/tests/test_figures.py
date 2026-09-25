"""Numeric-claim extraction.

uv run pytest packages/design_system
"""

from __future__ import annotations

from design_system import figures


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
