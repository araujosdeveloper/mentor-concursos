from apps.api.src.practice import review_interval_days


def test_review_schedule_is_deterministic() -> None:
    assert review_interval_days(False, 0) == 1
    assert review_interval_days(True, 1) == 3
    assert review_interval_days(True, 2) == 7
    assert review_interval_days(True, 3) == 15
    assert review_interval_days(True, 4) == 30
