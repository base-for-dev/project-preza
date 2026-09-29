from generator.timing import normalize_seconds, slide_count_for, words_for


def test_slide_count_for_talk_length():
    # The automatic count stays inside the ТЗ's 10-15 slides.
    assert slide_count_for(7) == 10
    assert slide_count_for(1) == 10
    assert slide_count_for(12) == 14
    assert slide_count_for(60) == 15


def test_normalize_seconds_sums_exactly():
    shares = normalize_seconds([20, 60, 0, 60, 20], 420)
    assert sum(shares) == 420
    assert shares[1] > shares[0]


def test_words_for_seconds():
    assert words_for(60) == 120
    assert words_for(1) == 15


def test_trim_to_words_keeps_whole_sentences():
    from generator.timing import trim_to_words

    text = "Раз два три. Четыре пять шесть. Семь восемь девять."
    assert trim_to_words(text, 7) == "Раз два три. Четыре пять шесть."
    assert trim_to_words(text, 100) == text


def test_trim_to_words_cuts_a_single_long_sentence():
    from generator.timing import trim_to_words

    assert trim_to_words("a b c d e f", 3) == "a b c."
