"""Шаблоны Jinja2 генераторов: данные пакета ``iolistgen/templates/`` и каталог пользователя.

Каталог из опции ``template_dir`` просматривается первым: файл с тем же именем перекрывает
шаблон пакета, остальные берутся из пакета. Так проект меняет, например, заголовки или раскладку
комментариев без своего плагина.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import BaseLoader, ChoiceLoader, Environment, FileSystemLoader, PackageLoader, StrictUndefined

from iolistgen.generators.base import GenerationError


def environment(template_dir: str = "") -> Environment:
    """Окружение Jinja2 для текстов ST, CSV и Markdown (без экранирования HTML)."""
    loaders: list[BaseLoader] = []
    if template_dir:
        directory = Path(template_dir)
        if not directory.is_dir():
            raise GenerationError(f"template_dir: нет каталога шаблонов {directory}")
        loaders.append(FileSystemLoader(str(directory)))
    loaders.append(PackageLoader("iolistgen", "templates"))
    # вывод — ST, CSV и Markdown, не HTML: экранирование не нужно
    return Environment(
        loader=ChoiceLoader(loaders),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
