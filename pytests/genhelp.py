"""Помощники тестов генераторов: запуск генератора в каталог, чтение результатов."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from iolistgen import __version__
from iolistgen.config import Config
from iolistgen.generators import Generator, GeneratorContext, resolve_options
from iolistgen.model import IoList
from iolistgen.validate import check_file
from pytests.helpers import DATA

KNS = DATA / "kns_mini.csv"
FIXTURE = DATA / "gen_fixture.csv"


def load(path: Path) -> IoList:
    result = check_file(path)
    assert result.model is not None, [item.render() for item in result.diagnostics]
    return result.model


def run(
    generator: Generator,
    model: IoList,
    out_dir: Path,
    options: Mapping[str, object] | None = None,
    *,
    timestamp: str | None = None,
) -> GeneratorContext:
    """Запустить генератор и вернуть контекст (файлы — ``ctx.outputs``)."""
    ctx = GeneratorContext(
        generator=generator.name,
        out_dir=out_dir,
        options=resolve_options(generator, options),
        config=Config(),
        source=model.source,
        version=__version__,
        timestamp=timestamp,
    )
    generator.generate(model, out_dir, ctx)
    return ctx


def texts(out_dir: Path) -> dict[str, str]:
    """Все файлы каталога: путь (POSIX, от каталога) → текст."""
    return {
        path.relative_to(out_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(out_dir.rglob("*"))
        if path.is_file()
    }


def lint_layout(root: Path) -> tuple[list[tuple[str, str]], int]:
    """st_lint по ``root/src`` с настройками репозитория: (правило, сообщение) и число файлов.

    Инструменты шаблона требуют Python 3.11+ (tomllib): на 3.10 тест пропускается.
    """
    if sys.version_info < (3, 11):
        pytest.skip("инструменты шаблона (st_lint) требуют Python 3.11+")
    import st_lint

    config = st_lint.load_config(st_lint.DEFAULT_CONFIG_PATH)
    findings, files = st_lint.lint(str(root), config, ["src"])
    return [(finding.rule, finding.format()) for finding in findings], files
