"""Отчёты проверки перечня: Markdown и самодостаточный HTML.

Оба отчёта строятся из одного контекста (``build_context``) и детерминированы: время прогона
в отчёт не пишется, вместо него — SHA-256 перечня и версия iolistgen. Повторная проверка
того же файла даёт побайтно тот же отчёт.
"""

from __future__ import annotations

from iolistgen.report.context import (
    ReportRow,
    RuleCount,
    build_context,
    count_text,
    plural,
    summary_line,
)
from iolistgen.report.html import render_html
from iolistgen.report.markdown import render_markdown

__all__ = [
    "ReportRow",
    "RuleCount",
    "build_context",
    "count_text",
    "plural",
    "render_html",
    "render_markdown",
    "summary_line",
]
