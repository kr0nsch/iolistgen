"""``iolistgen generate``: все встроенные генераторы, --timestamp, предупреждения и ошибки генераторов."""

from __future__ import annotations

from pathlib import Path

import pytest

from iolistgen.cli import main
from pytests.genhelp import KNS
from pytests.helpers import di, motor_vfd, write_csv


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_generate_project_layout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "generate", str(KNS), "--out", str(tmp_path), "--no-config")
    assert code == 0, out
    for name in (
        "src/GVLs/Generated/GVL_IO.gvl.st",
        "src/GVLs/Generated/GVL_Persist.pvl.st",
        "src/POUs/Generated/PRG_Devices/PRG_Devices.impl.st",
        "docs/modbus_map.md",
        "docs/alarms.csv",
        "docs/signal_list.md",
        "scada/scada_tags.csv",
    ):
        assert (tmp_path / name).is_file(), name
    assert "предупреждение" not in out


def test_timestamp_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = run(
        capsys, "generate", str(KNS), "--out", str(tmp_path), "--no-config", "--only", "docs-table", "--timestamp"
    )
    assert code == 0
    text = (tmp_path / "docs/signal_list.md").read_text(encoding="utf-8")
    assert "Время генерации: 20" in text.split("-->")[0]


def test_generator_warnings_are_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    persist = tmp_path / "src/GVLs/Generated/GVL_Persist.pvl.st"
    persist.parent.mkdir(parents=True)
    persist.write_text(
        "VAR_GLOBAL PERSISTENT RETAIN\n    // --- dev_no 90: OLD9 — x (DigitalInput, без Retain) ---\n"
        "    stOLD9Cfg : PL.ST_DigitalInputCfg;\nEND_VAR\n",
        encoding="utf-8",
    )
    code, out, _ = run(capsys, "generate", str(KNS), "--out", str(tmp_path), "--no-config", "--only", "st-codesys")
    assert code == 0
    assert "st-codesys: предупреждение: GVL_Persist.stOLD9Cfg удалена" in out
    assert "st-codesys: предупреждение: новое устройство LT101 получило dev_no 1" in out


def test_generation_error_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_csv(tmp_path / "clash.csv", [*motor_vfd("P101", 11), di("P101_COMMOK", 2)])
    code, _, err = run(capsys, "generate", str(path), "--out", str(tmp_path / "out"), "--no-config")
    assert code == 1
    assert "генератор st-codesys: GVL_IO: имена «xP101_COMMOK»" in err and "«xP101_CommOk»" in err
    assert "Traceback" not in err


def test_set_option_for_new_generators(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = run(
        capsys,
        "generate",
        str(KNS),
        "--out",
        str(tmp_path),
        "--no-config",
        "--only",
        "modbus-map,scada-csv",
        "--set",
        "modbus-map.slave_layout=dev_no",
        "--set",
        "scada-csv.separator=_",
    )
    assert code == 0
    assert "LT101_Value" in (tmp_path / "scada/scada_tags.csv").read_text(encoding="utf-8")
    assert "dev_no · 40" in (tmp_path / "docs/modbus_map.md").read_text(encoding="utf-8")


def test_failing_generator_leaves_previous_files_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Генераторы пишут файлы только все вместе: сбой последнего не оставляет новый ST со старыми картами."""
    from iolistgen.generators.docs_table import DocsTableGenerator

    def explode(self: DocsTableGenerator, *args: object) -> list[Path]:
        raise RuntimeError("сбой шаблона")

    monkeypatch.setattr(DocsTableGenerator, "generate", explode)
    code, _, err = run(capsys, "generate", str(KNS), "--out", str(tmp_path), "--no-config")
    assert code == 1 and "RuntimeError: сбой шаблона" in err
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []
    assert "файлы не записаны" in err


def test_strict_fails_on_generator_warnings_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    persist = tmp_path / "src/GVLs/Generated/GVL_Persist.pvl.st"
    persist.parent.mkdir(parents=True)
    old = (
        "VAR_GLOBAL PERSISTENT RETAIN\n    // --- dev_no 90: OLD9 — x (DigitalInput, без Retain) ---\n"
        "    stOLD9Cfg : PL.ST_DigitalInputCfg;\nEND_VAR\n"
    )
    persist.write_bytes(old.encode("utf-8"))
    code, out, _ = run(
        capsys, "generate", str(KNS), "--out", str(tmp_path), "--no-config", "--only", "st-codesys", "--strict"
    )
    assert code == 1
    assert "st-codesys: предупреждение: GVL_Persist.stOLD9Cfg удалена" in out
    assert "--strict" in out
    assert persist.read_bytes() == old.encode("utf-8")
    assert not (tmp_path / "src/GVLs/Generated/GVL_IO.gvl.st").exists()


def test_two_generators_writing_one_file_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, _, err = run(
        capsys,
        "generate",
        str(KNS),
        "--out",
        str(tmp_path),
        "--no-config",
        "--only",
        "alarm-list,docs-table",
        "--set",
        "docs-table.filename=docs/alarms.csv",
    )
    assert code == 1
    assert "docs/alarms.csv" in err and "alarm-list" in err and "docs-table" in err
    assert not (tmp_path / "docs").exists()
