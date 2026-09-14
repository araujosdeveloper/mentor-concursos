from datetime import date
from uuid import UUID

import pytest

from apps.api.src.study_plan import ProposalCreate, _json
from apps.api.src.study_plan_engine import (
    DEFAULT_SHARES,
    PlanValidationError,
    build_plan,
    largest_remainder,
    validate_availability,
)

SUBJECTS = [
    {
        "subject_id": str(UUID(int=1)),
        "weight": 1,
        "priority": "normal",
        "ordinal": 1,
        "topic_ids": [str(UUID(int=11))],
    },
    {
        "subject_id": str(UUID(int=2)),
        "weight": 2,
        "priority": "high",
        "ordinal": 2,
        "topic_ids": [],
    },
]
AVAILABILITY = {
    "monday": 180,
    "tuesday": 90,
    "wednesday": 180,
    "thursday": 90,
    "friday": 180,
    "saturday": 300,
    "sunday": 0,
}


def plan(**overrides):
    data = {
        "start_date": date(2026, 12, 28),
        "end_date": None,
        "total_days": 14,
        "timezone": "America/Sao_Paulo",
        "availability": AVAILABILITY,
        "preferred_block_minutes": 60,
        "shares": DEFAULT_SHARES,
        "subjects": SUBJECTS,
    }
    data.update(overrides)
    return build_plan(**data)


def test_days_horizon_crosses_year_and_never_uses_sunday() -> None:
    result = plan()
    assert result["period"] == {
        "start_date": "2026-12-28",
        "end_date": "2027-01-10",
        "calendar_days": 14,
        "available_days": 12,
    }
    assert all(date.fromisoformat(day["date"]).weekday() != 6 for day in result["calendar"])


def test_date_horizon_handles_leap_day_and_month_change() -> None:
    result = plan(start_date=date(2028, 2, 27), end_date=date(2028, 3, 1), total_days=None)
    assert result["period"]["calendar_days"] == 4
    assert any(day["date"] == "2028-02-29" for day in result["calendar"])


def test_variable_minutes_and_daily_capacity_are_respected() -> None:
    result = plan()
    for day in result["calendar"]:
        assert day["planned_minutes"] <= day["capacity_minutes"]
        assert sum(item["planned_minutes"] for item in day["items"]) == day["planned_minutes"]


def test_total_capacity_and_all_activities_share_one_budget() -> None:
    result = plan()
    assert sum(result["activity_minutes"].values()) == result["total_capacity_minutes"]
    assert (
        sum(item["planned_minutes"] for item in result["items"]) <= result["total_capacity_minutes"]
    )
    assert result["activity_minutes"]["recovery"] >= 0
    assert {item["activity_detail"] for item in result["items"]} >= {
        "new_content",
        "questions",
        "spaced_review",
    }


def test_simulation_uses_exercise_budget_only_on_adequate_horizon() -> None:
    long = plan(total_days=35)
    simulations = [item for item in long["items"] if item["activity_detail"] == "simulation"]
    assert simulations
    assert all(item["activity_type"] == "exercise" for item in simulations)
    assert not any(item["activity_detail"] == "simulation" for item in plan(total_days=7)["items"])


def test_weight_and_priority_increase_allocation() -> None:
    result = plan()
    assert result["subject_minutes"][str(UUID(int=2))] > result["subject_minutes"][str(UUID(int=1))]


def test_topic_always_belongs_to_its_subject_snapshot() -> None:
    result = plan()
    for item in result["items"]:
        if item["subject_id"] == str(UUID(int=1)):
            assert item["topic_id"] == str(UUID(int=11))
        else:
            assert item["topic_id"] is None


def test_determinism_and_integer_rounding() -> None:
    assert plan() == plan()
    allocation = largest_remainder(10, [("a", 1), ("b", 1), ("c", 1)])
    assert allocation == {"a": 4, "b": 3, "c": 3}
    assert sum(allocation.values()) == 10


def test_final_blocks_are_never_below_minimum() -> None:
    result = plan(availability={**AVAILABILITY, "monday": 95}, preferred_block_minutes=40)
    assert all(item["planned_minutes"] >= 15 for item in result["items"])


@pytest.mark.parametrize("minutes", [1, 14, 961])
def test_rejects_daily_capacity_outside_limits(minutes: int) -> None:
    with pytest.raises(PlanValidationError, match="availability_daily_limit"):
        validate_availability({**AVAILABILITY, "monday": minutes})


def test_rejects_zero_capacity_and_unknown_weekday() -> None:
    with pytest.raises(PlanValidationError, match="availability_empty"):
        validate_availability(dict.fromkeys(AVAILABILITY, 0))
    with pytest.raises(PlanValidationError, match="availability_weekdays_invalid"):
        validate_availability({**AVAILABILITY, "feriado": 60})


def test_rejects_expired_and_excessive_horizons() -> None:
    with pytest.raises(PlanValidationError, match="deadline_expired"):
        plan(start_date=date(2026, 2, 2), end_date=date(2026, 2, 1), total_days=None)
    with pytest.raises(PlanValidationError, match="horizon_too_long"):
        plan(start_date=date(2026, 1, 1), end_date=date(2032, 1, 1), total_days=None)


def test_short_horizon_warns_but_stays_within_capacity() -> None:
    result = plan(total_days=1)
    assert result["warnings"]
    assert all(item["planned_for"] == "2026-12-28" for item in result["items"])


def test_rejects_missing_subjects_and_invalid_percentages() -> None:
    with pytest.raises(PlanValidationError, match="subjects_missing"):
        plan(subjects=[])
    with pytest.raises(PlanValidationError, match="activity_shares_total"):
        plan(shares={"study": 50, "exercise": 25, "review": 30, "recovery": 5})


def test_api_payload_requires_exactly_one_scope_and_horizon() -> None:
    with pytest.raises(ValueError):
        ProposalCreate(
            goal_id=UUID(int=1), exam_id=UUID(int=2), total_days=30, availability=AVAILABILITY
        )
    with pytest.raises(ValueError):
        ProposalCreate(
            goal_id=UUID(int=1),
            total_days=30,
            end_date=date(2026, 12, 1),
            availability=AVAILABILITY,
        )


def test_api_json_snapshot_serializes_uuid_as_string() -> None:
    assert _json({"subject_id": UUID(int=1)}) == {"subject_id": str(UUID(int=1))}


def test_mastery_and_performance_adjustment_is_bounded() -> None:
    weak = [
        {**SUBJECTS[0], "accuracy_percent": 0, "overdue_items": 100},
        {**SUBJECTS[1], "accuracy_percent": 100},
    ]
    result = plan(subjects=weak)
    values = list(result["subject_minutes"].values())
    assert max(values) < min(values) * 5
