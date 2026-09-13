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


def test_render_lesson_pdf_handles_long_content_and_links() -> None:
    markdown = (
        "# Aula\n\n"
        "Texto normal com **negrito** e _itálico_.\n"
        "- item com URL https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm sem espaço\n"
        "- outro item [link](https://example.com/pagina-muito-longa-que-pode-quebrar)\n"
        + "\n".join(f"parágrafo {i} " * 20 for i in range(50))
    )
    content = render_lesson_pdf("Aula longa", markdown)
    assert content.startswith(b"%PDF")
    assert len(content) > 1000
