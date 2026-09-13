from __future__ import annotations

from apps.api.src.pdf import render_lesson_pdf


def test_render_lesson_pdf_produces_valid_pdf() -> None:
    content = render_lesson_pdf(
        "Aula 1 — Sistema Financeiro Nacional",
        "# Visão geral\n\n**texto em negrito** e texto normal.\n- item 1\n- item 2\n\n### Detalhe",
    )
    assert content.startswith(b"%PDF")
    assert len(content) > 500


def test_render_lesson_pdf_handles_headings_and_bullets() -> None:
    content = render_lesson_pdf("T", "## Subtítulo\n\n- a\n- b\n\n1. c\n2. d")
    assert content.startswith(b"%PDF")
