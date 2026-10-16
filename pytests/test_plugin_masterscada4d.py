"""Заготовка плагина MasterSCADA 4D: находится точкой входа, файлов не пишет и объясняет почему."""

from __future__ import annotations

from pathlib import Path

import pytest

import iolistgen_masterscada4d as plugin
from iolistgen.generators import GenerationError, Generator, discover
from pytests.genhelp import KNS, load, run
from pytests.test_generators import fake_entry_points


def test_plugin_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_entry_points(monkeypatch, [("masterscada4d", "iolistgen_masterscada4d:MasterScada4dGenerator")])
    entries = discover()
    entry = entries["masterscada4d"]
    assert entry.ok and isinstance(entry.generator, Generator)
    assert entry.origin == "iolistgen_masterscada4d:MasterScada4dGenerator"
    assert "st-codesys" in entries  # встроенные генераторы на месте


def test_plugin_refuses_with_sources(tmp_path: Path) -> None:
    model = load(KNS)
    with pytest.raises(GenerationError) as error:
        run(plugin.MasterScada4dGenerator(), model, tmp_path)
    message = str(error.value)
    assert "не описан" in message and "scada-csv" in message
    assert all(url in message for url in plugin.SOURCES)
    assert not any(tmp_path.iterdir())


def test_channel_rows_draft() -> None:
    rows = plugin.channel_rows(load(KNS))
    assert list(rows[0]) == list(plugin.CHANNEL_COLUMNS)
    first = rows[0]
    assert first["Имя канала"] == "LT101.stCommon.wStatus"
    assert first["Адрес"] == "0" and first["Тип в устройстве"] == "WORD"


def test_cli_reports_skeleton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from iolistgen.cli import main

    fake_entry_points(monkeypatch, [("masterscada4d", "iolistgen_masterscada4d:MasterScada4dGenerator")])
    code = main(["generate", str(KNS), "--out", str(tmp_path), "--no-config", "--only", "masterscada4d"])
    err = capsys.readouterr().err
    assert code == 1
    assert "генератор masterscada4d: формат импорта тегов MasterSCADA 4D" in err
