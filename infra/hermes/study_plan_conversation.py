"""Parsing e estado determinísticos da conversa de planejamento no Telegram."""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import date

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_NAMES = {
    "segunda": "monday",
    "terca": "tuesday",
    "quarta": "wednesday",
    "quinta": "thursday",
    "sexta": "friday",
    "sabado": "saturday",
    "domingo": "sunday",
}
PLAN_KEYWORDS = re.compile(r"\b(prova|concurso|edital|estudar|estudos|rotina|prazo|preparacao)\b")
POSITIVE = {"confirmar", "confirmo", "sim, criar plano", "sim criar plano"}
AMBIGUOUS_POSITIVE = {"sim", "ok", "pode"}
DECLINES = {"nao", "agora nao", "nao quero", "depois"}


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(char for char in value if not unicodedata.combining(char))


def parse_deadline(text: str, today: date) -> dict[str, object] | None:
    value = normalize(text)
    days = re.fullmatch(r"(?:em\s+)?(\d{1,4})\s*dias?", value)
    if days:
        amount = int(days.group(1))
        return {"total_days": amount} if 1 <= amount <= 1826 else None
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if match:
        try:
            parsed = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            return None
        return {"end_date": parsed.isoformat()} if parsed >= today else None
    try:
        parsed = date.fromisoformat(value.removeprefix("ate "))
    except ValueError:
        return None
    return {"end_date": parsed.isoformat()} if parsed >= today else None


def parse_days(text: str) -> set[str] | None:
    value = normalize(text)
    if "segunda a domingo" in value or "todos os dias" in value:
        return set(WEEKDAYS)
    selected: set[str] = set()
    order = list(DAY_NAMES)
    for start_name, end_name in re.findall(
        r"(segunda|terca|quarta|quinta|sexta|sabado|domingo)\s+a\s+(segunda|terca|quarta|quinta|sexta|sabado|domingo)",
        value,
    ):
        start, end = order.index(start_name), order.index(end_name)
        if start <= end:
            selected.update(DAY_NAMES[name] for name in order[start : end + 1])
    selected.update(day for name, day in DAY_NAMES.items() if name in value)
    for name, day in DAY_NAMES.items():
        if re.search(rf"{name}\s+(?:livre|indisponivel)", value):
            selected.discard(day)
    return selected or None


def _minutes(fragment: str) -> int | None:
    value = normalize(fragment)
    compact = re.search(r"(\d{1,2})\s*h(?:\s*(\d{1,2}))?", value)
    if compact:
        return int(compact.group(1)) * 60 + int(compact.group(2) or 0)
    hours = re.search(r"(\d{1,2})\s*horas?", value)
    minutes = re.search(r"(\d{1,3})\s*minutos?", value)
    if hours or minutes:
        return int(hours.group(1) if hours else 0) * 60 + int(minutes.group(1) if minutes else 0)
    return None


def parse_availability(text: str, selected: set[str]) -> dict[str, int] | None:
    value = normalize(text)
    default = _minutes(value)
    if default is None:
        return None
    result = {day: default if day in selected else 0 for day in WEEKDAYS}
    # A última expressão específica de um dia prevalece sobre o valor geral.
    for name, day in DAY_NAMES.items():
        for match in re.finditer(
            rf"(?:e\s+)?(\d{{1,2}}\s*(?:h(?:\s*\d{{1,2}})?|horas?)(?:\s+e\s+\d{{1,3}}\s+minutos?)?)\s+(?:no\s+|na\s+)?{name}",
            value,
        ):
            parsed = _minutes(match.group(1))
            if parsed is not None and day in selected:
                result[day] = parsed
    if any(minutes != 0 and not 15 <= minutes <= 960 for minutes in result.values()):
        return None
    return result


def parse_block(text: str) -> int | None:
    value = _minutes(text)
    return value if value is not None and 15 <= value <= 240 else None


def is_explicit_confirmation(text: str, *, single_pending: bool = False) -> bool:
    value = normalize(text)
    return value in POSITIVE or (single_pending and value in AMBIGUOUS_POSITIVE)


def is_decline(text: str) -> bool:
    return normalize(text) in DECLINES


def should_offer(
    text: str,
    last_offer: float | None,
    declined_at: float | None,
    now: float | None = None,
    window_seconds: int = 86400,
) -> bool:
    current = time.time() if now is None else now
    if last_offer is not None and current - last_offer < window_seconds:
        return False
    if declined_at is not None and current - declined_at < window_seconds * 7:
        return False
    return bool(PLAN_KEYWORDS.search(normalize(text)))
