"""Geração de PDF de aula a partir de markdown (fpdf2 + DejaVu)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Response
from fpdf import FPDF
from pydantic import Field

from .academic import StrictModel, TokenDep, UserDep

router = APIRouter(prefix="/api/v1/lessons", tags=["lessons"])

_FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


class LessonPdfRequest(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_000_000)


def render_lesson_pdf(title: str, markdown: str) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("DejaVu", "", _FONT_REGULAR)
    pdf.add_font("DejaVu", "B", _FONT_BOLD)
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 15)
    pdf.multi_cell(0, 8, title)
    pdf.ln(3)

    body = 10.5
    pdf.set_font("DejaVu", "", body)
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(2.5)
        elif line.startswith("### "):
            pdf.set_font("DejaVu", "B", 11.5)
            pdf.multi_cell(0, 6.5, line[4:])
            pdf.set_font("DejaVu", "", body)
        elif line.startswith("## "):
            pdf.set_font("DejaVu", "B", 12.5)
            pdf.multi_cell(0, 7, line[3:])
            pdf.set_font("DejaVu", "", body)
        elif line.startswith("# "):
            pdf.set_font("DejaVu", "B", 14)
            pdf.multi_cell(0, 8, line[2:])
            pdf.set_font("DejaVu", "", body)
        elif _BULLET.match(line):
            text = _BULLET.sub("", line, count=1)
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(0, 6, "\u2022 " + text, markdown=True)
        else:
            pdf.multi_cell(0, 6, line, markdown=True)
    return bytes(pdf.output())


@router.post("/pdf")
def lesson_pdf(
    body: LessonPdfRequest,
    _: TokenDep,
    _user: UserDep,
) -> Response:
    content = render_lesson_pdf(body.title, body.content)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="aula.pdf"'},
    )
