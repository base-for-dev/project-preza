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
