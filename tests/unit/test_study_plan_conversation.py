import importlib.util
from datetime import date
from pathlib import Path


def module():
    path = Path(__file__).parents[2] / "infra" / "hermes" / "study_plan_conversation.py"
    spec = importlib.util.spec_from_file_location("study_plan_conversation_test", path)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_parses_days_or_brazilian_deadline() -> None:
    parser = module()
    assert parser.parse_deadline("90 dias", date(2026, 9, 14)) == {"total_days": 90}
    assert parser.parse_deadline("até 20/12/2026", date(2026, 9, 14)) == {"end_date": "2026-12-20"}


def test_parses_week_range_and_free_sunday() -> None:
    parser = module()
    days = parser.parse_days("segunda a sábado, domingo livre")
    assert days == {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}


def test_parses_hours_and_minutes_without_float() -> None:
    parser = module()
    days = set(parser.WEEKDAYS[:-1])
    availability = parser.parse_availability("2h30 por dia", days)
    assert availability["monday"] == 150
    assert availability["sunday"] == 0


def test_specific_saturday_overrides_weekday_time() -> None:
    parser = module()
    days = set(parser.WEEKDAYS[:-1])
    availability = parser.parse_availability("3 horas de segunda a sexta e 5 horas no sábado", days)
    assert availability["monday"] == 180
    assert availability["saturday"] == 300


def test_confirmation_is_unambiguous_except_single_pending_context() -> None:
    parser = module()
    assert parser.is_explicit_confirmation("Confirmo")
    assert not parser.is_explicit_confirmation("sim")
    assert parser.is_explicit_confirmation("sim", single_pending=True)
    assert not parser.is_explicit_confirmation("talvez")


def test_proactive_offer_has_cooldown_and_respects_decline() -> None:
    parser = module()
    assert parser.should_offer("Vou começar a estudar para concurso", None, None, now=100_000)
    assert not parser.should_offer("concurso", 99_999, None, now=100_000)
    assert not parser.should_offer("concurso", None, 99_999, now=100_000)
    assert not parser.should_offer("conversa casual", None, None, now=100_000)
    assert parser.is_decline("Agora não")
