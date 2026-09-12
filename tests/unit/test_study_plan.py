from datetime import date

import pytest

from apps.api.src.study_plan import distribute_minutes, plan_metrics

DISCIPLINES = [
    {"subject": "lingua_portuguesa", "weight": 10},
    {"subject": "direito_tributario", "weight": 20},
]


def test_plan_metrics_computes_weeks_and_minutes() -> None:
    weeks, minutes = plan_metrics(date(2026, 12, 31), date(2026, 1, 1), 5, 2)
    assert minutes == 600
    assert weeks == 52


def test_plan_metrics_rejects_past_deadline() -> None:
    with pytest.raises(ValueError, match="deadline_must_be_future"):
        plan_metrics(date(2025, 1, 1), date(2026, 1, 1), 5, 2)


def test_distribute_minutes_proportional_to_weight() -> None:
    allocation = distribute_minutes(600, DISCIPLINES)
    assert allocation["direito_tributario"] > allocation["lingua_portuguesa"]
    assert sum(allocation.values()) == pytest.approx(600, abs=20)


def test_distribute_minutes_has_floor() -> None:
    allocation = distribute_minutes(60, [{"subject": "x", "weight": 0}])
    assert allocation["x"] == 10
