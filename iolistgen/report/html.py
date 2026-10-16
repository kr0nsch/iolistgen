"""Отчёт проверки в HTML: один файл без внешних ресурсов (стили, иконки и сценарий внутри)."""

from __future__ import annotations

from functools import cache

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from iolistgen.report.context import build_context
from iolistgen.validate import CheckResult


@cache
def environment() -> Environment:
    """Окружение Jinja2 для шаблонов пакета (``iolistgen/templates``), с экранированием HTML."""
    return Environment(
        loader=PackageLoader("iolistgen", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_html(result: CheckResult, version: str) -> str:
    """Отчёт целиком."""
    template = environment().get_template("report.html.j2")
    return template.render(ctx=build_context(result, version))
