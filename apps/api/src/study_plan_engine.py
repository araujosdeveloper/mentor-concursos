"""Motor puro, inteiro e determinístico do calendário adaptativo de estudos."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DEFAULT_SHARES = {"study": 50, "exercise": 25, "review": 20, "recovery": 5}
PRIORITY_FACTOR = {"low": 80, "normal": 100, "high": 125}
ACTIVITY_ORDER = ("study", "review", "exercise")


class PlanValidationError(ValueError):
    """Erro de domínio seguro para apresentação pela API."""


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise PlanValidationError("timezone_invalid") from exc
    return value


def validate_availability(value: dict[str, int]) -> dict[str, int]:
    if set(value) != set(WEEKDAYS):
        raise PlanValidationError("availability_weekdays_invalid")
    normalized: dict[str, int] = {}
    for day in WEEKDAYS:
        minutes = value[day]
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise PlanValidationError("availability_minutes_invalid")
        if minutes != 0 and not 15 <= minutes <= 960:
            raise PlanValidationError("availability_daily_limit")
        normalized[day] = minutes
    if not any(normalized.values()):
        raise PlanValidationError("availability_empty")
    if sum(normalized.values()) > 6720:
        raise PlanValidationError("availability_weekly_limit")
    return normalized


def validate_shares(value: dict[str, int]) -> dict[str, int]:
    if set(value) != set(DEFAULT_SHARES):
        raise PlanValidationError("activity_shares_invalid")
    if any(
        isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 100 for v in value.values()
    ):
        raise PlanValidationError("activity_shares_invalid")
    if sum(value.values()) != 100 or value["study"] < 20 or value["recovery"] > 20:
        raise PlanValidationError("activity_shares_total")
    return dict(value)


def largest_remainder(total: int, weights: list[tuple[str, int]]) -> dict[str, int]:
    """Rateio inteiro exato; desempate estável pela ordem recebida e pela chave."""
    if total < 0 or not weights or any(weight < 0 for _, weight in weights):
        raise PlanValidationError("allocation_invalid")
    weight_sum = sum(weight for _, weight in weights)
    if weight_sum <= 0:
        weights = [(key, 1) for key, _ in weights]
        weight_sum = len(weights)
    base = {key: total * weight // weight_sum for key, weight in weights}
    missing = total - sum(base.values())
    ranked = sorted(
        enumerate(weights),
        key=lambda item: (-(total * item[1][1] % weight_sum), item[0], item[1][0]),
    )
    for _, (key, _) in ranked[:missing]:
        base[key] += 1
    return base


def horizon(start_date: date, *, end_date: date | None, total_days: int | None) -> date:
    if (end_date is None) == (total_days is None):
        raise PlanValidationError("exactly_one_deadline_required")
    if total_days is not None:
        if isinstance(total_days, bool) or not 1 <= total_days <= 1826:
            raise PlanValidationError("total_days_invalid")
        return start_date + timedelta(days=total_days - 1)
    assert end_date is not None
    if end_date < start_date:
        raise PlanValidationError("deadline_expired")
    if (end_date - start_date).days > 1825:
        raise PlanValidationError("horizon_too_long")
    return end_date


def _blocks(minutes: int, preferred: int) -> list[int]:
    result: list[int] = []
    while minutes:
        block = min(preferred, minutes)
        remainder = minutes - block
        if 0 < remainder < 15:
            block -= 15 - remainder
        if block < 15:
            if result:
                result[-1] += minutes
            break
        result.append(block)
        minutes -= block
    return result


def _adaptive_weight(subject: dict[str, Any]) -> int:
    base = max(1, int(subject.get("weight") or 1))
    priority = PRIORITY_FACTOR.get(str(subject.get("priority") or "normal"), 100)
    state = str(subject.get("mastery_state") or "not_started")
    mastery = {"not_started": 120, "in_progress": 110, "review": 95, "consolidated": 75}.get(
        state, 100
    )
    accuracy = subject.get("accuracy_percent")
    performance = 100
    if isinstance(accuracy, int):
        performance = max(80, min(120, 110 - (accuracy - 50) // 5))
    overdue = min(15, max(0, int(subject.get("overdue_items") or 0)) * 3)
    evidence = min(110, 100 + max(0, 5 - int(subject.get("evidence_count") or 0)) * 2)
    studied = int(subject.get("studied_seconds") or 0)
    studied_factor = 110 if studied < 3600 else (90 if studied > 72_000 else 100)
    return max(
        1,
        base
        * priority
        * mastery
        * (performance + overdue)
        * evidence
        * studied_factor
        // 10_000_000_000,
    )


def build_plan(
    *,
    start_date: date,
    end_date: date | None,
    total_days: int | None,
    timezone: str,
    availability: dict[str, int],
    preferred_block_minutes: int,
    shares: dict[str, int],
    subjects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Gera calendário sem I/O e sem criar conteúdo acadêmico."""
    validate_timezone(timezone)
    availability = validate_availability(availability)
    shares = validate_shares(shares)
    if not 15 <= preferred_block_minutes <= 240:
        raise PlanValidationError("block_duration_invalid")
    if not subjects:
        raise PlanValidationError("subjects_missing")
    finish = horizon(start_date, end_date=end_date, total_days=total_days)
    seen: set[str] = set()
    normalized_subjects: list[dict[str, Any]] = []
    for ordinal, raw in enumerate(subjects, 1):
        subject_id = str(raw.get("subject_id") or "")
        if not subject_id or subject_id in seen:
            raise PlanValidationError("subject_invalid")
        seen.add(subject_id)
        topics = [str(topic) for topic in raw.get("topic_ids") or []]
        normalized_subjects.append(
            {
                **raw,
                "subject_id": subject_id,
                "topic_ids": topics,
                "ordinal": int(raw.get("ordinal") or ordinal),
            }
        )

    calendar: list[dict[str, Any]] = []
    current = start_date
    while current <= finish:
        minutes = availability[WEEKDAYS[current.weekday()]]
        if minutes:
            calendar.append({"date": current.isoformat(), "capacity_minutes": minutes})
        current += timedelta(days=1)
    if not calendar:
        raise PlanValidationError("horizon_has_no_available_days")

    total_capacity = sum(day["capacity_minutes"] for day in calendar)
    activity_budget = largest_remainder(total_capacity, list(shares.items()))
    schedulable = total_capacity - activity_budget["recovery"]
    subject_weights = [
        (item["subject_id"], _adaptive_weight(item))
        for item in sorted(normalized_subjects, key=lambda s: (s["ordinal"], s["subject_id"]))
    ]
    subject_budget = largest_remainder(schedulable, subject_weights)
    activity_remaining = {key: activity_budget[key] for key in ACTIVITY_ORDER}
    subject_remaining = dict(subject_budget)
    subject_lookup = {item["subject_id"]: item for item in normalized_subjects}
    topic_cursor: defaultdict[str, int] = defaultdict(int)
    items: list[dict[str, Any]] = []
    ordinal = 0

    for day in calendar:
        usable = day["capacity_minutes"]
        day_items: list[dict[str, Any]] = []
        for block in _blocks(usable, preferred_block_minutes):
            candidates = [(k, v) for k, v in activity_remaining.items() if v > 0]
            if not candidates:
                break
            activity = min(candidates, key=lambda pair: (-pair[1], ACTIVITY_ORDER.index(pair[0])))[
                0
            ]
            subject_candidates = [(k, v) for k, v in subject_remaining.items() if v > 0]
            if not subject_candidates:
                break
            subject_id = min(subject_candidates, key=lambda pair: (-pair[1], pair[0]))[0]
            planned = min(block, activity_remaining[activity], subject_remaining[subject_id])
            if planned < 15:
                # Restos pequenos entram no rateio seguinte; nunca viram item inválido.
                activity_remaining[activity] = 0
                continue
            subject = subject_lookup[subject_id]
            topics = subject["topic_ids"]
            topic_id = topics[topic_cursor[subject_id] % len(topics)] if topics else None
            topic_cursor[subject_id] += 1
            ordinal += 1
            item = {
                "ordinal": ordinal,
                "planned_for": day["date"],
                "subject_id": subject_id,
                "topic_id": topic_id,
                "activity_type": activity,
                "planned_minutes": planned,
            }
            items.append(item)
            day_items.append(item)
            activity_remaining[activity] -= planned
            subject_remaining[subject_id] -= planned
        day["planned_minutes"] = sum(item["planned_minutes"] for item in day_items)
        day["items"] = day_items

    actual_activity = {key: 0 for key in shares}
    actual_activity["recovery"] = total_capacity - sum(item["planned_minutes"] for item in items)
    actual_subject = {key: 0 for key in subject_budget}
    for item in items:
        actual_activity[item["activity_type"]] += item["planned_minutes"]
        actual_subject[item["subject_id"]] += item["planned_minutes"]
    exercise_items = [item for item in items if item["activity_type"] == "exercise"]
    for index, item in enumerate(exercise_items, 1):
        item["activity_detail"] = (
            "simulation" if len(calendar) >= 14 and index % 5 == 0 else "questions"
        )
    for item in items:
        if item["activity_type"] == "study":
            item["activity_detail"] = "new_content"
        elif item["activity_type"] == "review":
            item["activity_detail"] = "spaced_review"
    warnings: list[str] = []
    if len(calendar) < 3:
        warnings.append("Horizonte curto: revisões e simulados podem ser limitados.")
    if actual_activity["exercise"] < preferred_block_minutes:
        warnings.append(
            "Capacidade insuficiente para reservar um bloco completo de questões/simulado."
        )
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": finish.isoformat(),
            "calendar_days": (finish - start_date).days + 1,
            "available_days": len(calendar),
        },
        "timezone": timezone,
        "total_capacity_minutes": total_capacity,
        "average_weekly_minutes": total_capacity * 7 // ((finish - start_date).days + 1),
        "activity_minutes": actual_activity,
        "subject_minutes": actual_subject,
        "blocks": len(items),
        "calendar": calendar,
        "items": items,
        "warnings": warnings,
        "assumptions": [
            "Simulados usam a parcela de questões.",
            "A margem de recuperação permanece sem item obrigatório.",
        ],
        "missing_fields": [],
    }
