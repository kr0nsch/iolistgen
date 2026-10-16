"""docs/GENERATORS.md описывает каждую опцию каждого встроенного генератора."""

from __future__ import annotations

from pathlib import Path

import pytest

from iolistgen.generators import Generator, builtin_generators

DOC = Path(__file__).resolve().parent.parent / "docs" / "GENERATORS.md"


@pytest.mark.parametrize("generator", builtin_generators(), ids=lambda g: g.name)
def test_options_documented(generator: Generator) -> None:
    text = DOC.read_text(encoding="utf-8")
    name = generator.name
    assert f"`{name}`" in text
    section = text[text.index(f"## `{name}`") :]
    following = section.find("\n## ", 1)
    section = section if following < 0 else section[:following]
    for option in generator.options:
        assert f"`{option.name}`" in section, f"{name}.{option.name} не описана в docs/GENERATORS.md"
