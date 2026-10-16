"""Файл настроек iolistgen.toml: значения по умолчанию, ошибки, поиск рядом с перечнем."""

from __future__ import annotations

from pathlib import Path

import pytest

from iolistgen.config import (
    DEFAULT_DEVICE_REGEX,
    DEFAULT_TAG_REGEX,
    Config,
    ConfigError,
    find_config,
    load_config,
    parse_config,
    resolve_config,
)
from iolistgen.modbus import WordOrder

DOCS = Path(__file__).resolve().parents[1] / "docs"


def test_defaults() -> None:
    config = Config()
    assert config.naming.tag_regex == DEFAULT_TAG_REGEX
    assert config.naming.device_regex == DEFAULT_DEVICE_REGEX
    assert config.modbus.address_base == 0
    assert config.modbus.default_word_order is None
    assert config.input.encoding == "utf-8"
    assert config.severity == {}


def test_parse_full_config() -> None:
    config = parse_config(
        {
            "naming": {"tag_regex": "^[A-Z0-9_]+$", "max_device_length": 16},
            "modbus": {"address_base": 1, "default_word_order": "LH"},
            "input": {"sheet": "Перечень", "ignore_columns": ["№"], "column_aliases": {"Позиция": "tag"}},
            "severity": {"IOL104": "warning", "IOL005": "off"},
            "generators": {"docs-table": {"filename": "io.md"}},
        },
        source="iolistgen.toml",
    )
    assert config.modbus.default_word_order is WordOrder.LH
    assert config.input.ignore_columns == ("№",)
    assert config.path == "iolistgen.toml"


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ({"naming": {"tag_regex": "("}}, "не компилируется"),
        ({"naming": {"tag_regx": ".*"}}, "неизвестный параметр"),
        ({"modbus": {"address_base": 2}}, "недопустимое значение"),
        ({"severity": {"IOL999": "off"}}, "нет таких правил"),
        ({"severity": {"IOL104": "fatal"}}, "недопустимое значение"),
        ({"input": {"column_aliases": {"Позиция": "position"}}}, "неизвестные колонки"),
        ({"input": {"encoding": "klingon"}}, "неизвестная кодировка"),
    ],
)
def test_invalid_config(data: dict[str, object], fragment: str) -> None:
    with pytest.raises(ConfigError, match=fragment):
        parse_config(data)


def test_load_config_errors(tmp_path: Path) -> None:
    path = tmp_path / "iolistgen.toml"
    path.write_text("[naming\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="TOML"):
        load_config(path)
    with pytest.raises(ConfigError, match="не удалось прочитать"):
        load_config(tmp_path / "missing.toml")


def test_find_config_walks_up_to_repository_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "lists").mkdir(parents=True)
    listing = repo / "docs" / "lists" / "io.csv"
    listing.write_text("", encoding="utf-8")
    assert find_config(listing) is None
    (tmp_path / "iolistgen.toml").write_text("", encoding="utf-8")  # выше корня репозитория — не ищется
    assert find_config(listing) is None
    (repo / "iolistgen.toml").write_text("[modbus]\naddress_base = 1\n", encoding="utf-8")
    assert find_config(listing) == (repo / "iolistgen.toml").resolve()
    assert resolve_config(None, listing).modbus.address_base == 1
    assert resolve_config(None, listing, search=False).modbus.address_base == 0


def test_example_config_in_docs_is_valid() -> None:
    config = load_config(DOCS / "iolistgen.example.toml")
    assert config.naming.tag_regex == DEFAULT_TAG_REGEX
    assert config.path is not None
