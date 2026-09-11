from __future__ import annotations

from types import SimpleNamespace

from infra.hermes.mentor_consultation_memory import context_for, record


def _source(user: str = "1", chat: str = "1"):
    return SimpleNamespace(
        platform=SimpleNamespace(value="telegram"), user_id=user, chat_id=chat
    )


def test_memory_is_scoped_and_supports_follow_up(monkeypatch, tmp_path) -> None:
    import infra.hermes.mentor_consultation_memory as memory

    monkeypatch.setattr(memory, "ROOT", tmp_path)
    record(_source(), "O que é ato administrativo?", "É uma manifestação da Administração.")
    assert "ato administrativo" in context_for(_source())
    assert context_for(_source("2", "1")) == ""
    assert context_for(_source("1", "2")) == ""


def test_memory_compacts_and_promotes_only_explicit_preference(monkeypatch, tmp_path) -> None:
    import infra.hermes.mentor_consultation_memory as memory

    monkeypatch.setattr(memory, "ROOT", tmp_path)
    for index in range(8):
        record(_source(), f"pergunta {index}", f"resposta {index}")
    record(_source(), "Lembre que prefiro exemplos curtos", "Registrado.")
    data = memory._load(_source())
    assert len(data["turns"]) <= memory.MAX_TURNS
    assert data["summary"]
    assert data["preferences"]
