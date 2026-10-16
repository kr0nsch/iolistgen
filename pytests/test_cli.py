"""Командная строка: validate, generate, schema, коды выхода, справка по-русски."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

from iolistgen import __version__
from iolistgen.cli import main
from iolistgen.generators import ENTRY_POINT_GROUP
from pytests.helpers import DATA, ai, write_csv

ROOT = Path(__file__).resolve().parents[1]


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_validate_ok(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "validate", str(DATA / "kns_mini.csv"), "--no-config")
    assert code == 0
    assert "26 сигналов, 13 устройств — ошибок нет" in out


def test_validate_errors_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "validate", str(DATA / "kns_errors.csv"), "--no-config")
    assert code == 1
    assert "IOL204 [ошибка]" in out
    assert "как исправить:" in out


def test_validate_quiet_and_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_csv(tmp_path / "list.csv", [ai(), ai("LT102", 2, units="")])
    code, out, _ = run(capsys, "validate", str(path), "--no-config", "-q")
    assert code == 1
    assert out.strip().splitlines() == [f"{path}: 2 сигнала, 2 устройства — 1 ошибка"]
    warn_only = write_csv(tmp_path / "warn.csv", [ai(), ai("LT102", 2, mb_slave=1)])
    assert run(capsys, "validate", str(warn_only), "--no-config")[0] == 0
    assert run(capsys, "validate", str(warn_only), "--no-config", "--strict")[0] == 1


def test_validate_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "reports"
    code, out, _ = run(
        capsys, "validate", str(DATA / "kns_errors.csv"), "--no-config", "--report", "both", "--out", str(out_dir)
    )
    assert code == 1
    md = out_dir / "kns_errors.validation.md"
    html = out_dir / "kns_errors.validation.html"
    assert md.is_file() and html.is_file()
    assert f"отчёт: {md}" in out
    assert md.read_text(encoding="utf-8").startswith("# Проверка перечня сигналов")
    assert html.read_bytes().startswith(b"<!doctype html>")


def test_validate_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "validate", str(DATA / "kns_errors.csv"), "--no-config", "--format", "json")
    assert code == 1
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["errors"] == len([d for d in payload["diagnostics"] if d["severity"] == "error"])
    first = payload["diagnostics"][0]
    assert {"code", "severity", "message", "hint", "source"} <= set(first)
    assert payload["stats"]["signals"] == 16


def test_validate_input_errors_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "validate", str(tmp_path / "missing.csv"))
    assert code == 2 and "не найден" in err
    bad_config = tmp_path / "iolistgen.toml"
    bad_config.write_text("[naming]\ntag_regx = '.*'\n", encoding="utf-8")
    code, _, err = run(capsys, "validate", str(DATA / "kns_mini.csv"), "--config", str(bad_config))
    assert code == 2 and "tag_regx" in err
    code, _, err = run(capsys, "validate", str(DATA / "kns_mini.csv"), "--encoding", "no-such-codec")
    assert code == 2 and "кодировка" in err


def test_validate_finds_config_next_to_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "iolistgen.toml").write_text('[severity]\nIOL206 = "warning"\n', encoding="utf-8")
    sub = tmp_path / "docs"
    sub.mkdir()
    path = write_csv(sub / "list.csv", [ai(units="")])
    code, out, _ = run(capsys, "validate", str(path))
    assert code == 0
    assert "IOL206 [предупреждение]" in out
    assert run(capsys, "validate", str(path), "--no-config")[0] == 1


def test_validate_encoding_option(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "list.csv"
    path.write_bytes(
        "tag;description;signal_type;device_type;dev_no;role\nLS101;Поплавок;DI;DigitalInput;1;IN\n".encode("cp1251")
    )
    assert run(capsys, "validate", str(path), "--no-config")[0] == 1
    assert run(capsys, "validate", str(path), "--no-config", "--encoding", "cp1251")[0] == 0


def test_generate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "gen"
    code, out, _ = run(capsys, "generate", str(DATA / "kns_mini.csv"), "--out", str(out_dir), "--no-config")
    assert code == 0, out
    assert "docs-table: docs/signal_list.md — записан" in out
    assert "st-codesys: src/GVLs/Generated/GVL_IO.gvl.st — записан" in out
    assert "modbus-map: docs/modbus_map.md — записан" in out
    assert "scada-csv: scada/scada_tags.csv — записан" in out
    assert "alarm-list: docs/alarms.csv — записан" in out
    assert "файлов: 17, изменено: 17" in out
    code, out, _ = run(capsys, "generate", str(DATA / "kns_mini.csv"), "--out", str(out_dir), "--no-config")
    assert "без изменений" in out and "изменено: 0" in out
    assert "записан" not in out.replace("не записан", "")


def test_generate_with_options(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "gen"
    code, _, _ = run(
        capsys,
        "generate",
        str(DATA / "kns_mini.csv"),
        "--out",
        str(out_dir),
        "--no-config",
        "--only",
        "docs-table",
        "--set",
        "docs-table.filename=io.md",
        "--set",
        "docs-table.group_by_device=false",
    )
    assert code == 0
    assert (out_dir / "io.md").is_file()


def test_generate_options_from_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "cfg.toml"
    config.write_text('[generators.docs-table]\nfilename = "from_config.md"\n', encoding="utf-8")
    code, _, _ = run(
        capsys, "generate", str(DATA / "kns_mini.csv"), "--out", str(tmp_path / "g"), "--config", str(config)
    )
    assert code == 0
    assert (tmp_path / "g" / "from_config.md").is_file()


def test_generate_refuses_invalid_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "gen"
    code, out, _ = run(capsys, "generate", str(DATA / "kns_errors.csv"), "--out", str(out_dir), "--no-config")
    assert code == 1
    assert "генерация отменена" in out
    assert not out_dir.exists()


def test_generate_strict_refuses_warnings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_csv(tmp_path / "warn.csv", [ai(mb_slave=1)])
    code, out, _ = run(capsys, "generate", str(path), "--out", str(tmp_path / "g"), "--no-config", "--strict")
    assert code == 1 and "--strict" in out


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        (["--only", "nope"], "недоступен"),
        (["--set", "docs-table.colour=red"], "нет опции"),
        (["--set", "nope.x=1"], "нет генератора"),
        (["--set", "broken"], "ГЕНЕРАТОР.ОПЦИЯ=ЗНАЧЕНИЕ"),
    ],
)
def test_generate_argument_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: list[str], fragment: str
) -> None:
    code, _, err = run(capsys, "generate", str(DATA / "kns_mini.csv"), "--out", str(tmp_path), "--no-config", *args)
    assert code == 2
    assert fragment in err


def test_generate_requires_list_and_out(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "generate")
    assert code == 2 and "--out" in err


def test_generate_list(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    broken = metadata.EntryPoint(name="broken-plugin", value="no_such_module_xyz:G", group=ENTRY_POINT_GROUP)
    monkeypatch.setattr(metadata, "entry_points", lambda *, group: [broken])
    code, out, _ = run(capsys, "generate", "--list")
    assert code == 0
    assert "docs-table" in out and "встроенный" in out
    assert "filename = docs/signal_list.md" in out
    assert "st-codesys" in out and "modbus-map" in out and "scada-csv" in out and "alarm-list" in out
    assert "broken-plugin" in out and "НЕ ЗАГРУЖЕН" in out


def test_generate_skips_broken_plugins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = metadata.EntryPoint(name="broken-plugin", value="no_such_module_xyz:G", group=ENTRY_POINT_GROUP)
    monkeypatch.setattr(metadata, "entry_points", lambda *, group: [broken])
    code, _, err = run(capsys, "generate", str(DATA / "kns_mini.csv"), "--out", str(tmp_path), "--no-config")
    assert code == 0
    assert "broken-plugin" in err and "пропущен" in err
    code, _, err = run(
        capsys, "generate", str(DATA / "kns_mini.csv"), "--out", str(tmp_path), "--no-config", "--only", "broken-plugin"
    )
    assert code == 2 and "ModuleNotFoundError" in err


def test_generate_reports_generator_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from iolistgen.generators.docs_table import DocsTableGenerator

    def explode(self: DocsTableGenerator, *args: object) -> list[Path]:
        raise RuntimeError("сбой шаблона")

    monkeypatch.setattr(DocsTableGenerator, "generate", explode)
    code, _, err = run(capsys, "generate", str(DATA / "kns_mini.csv"), "--out", str(tmp_path), "--no-config")
    assert code == 1
    assert "RuntimeError: сбой шаблона" in err


def test_schema_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "schema")
    assert code == 0
    for title in ("## Колонки перечня", "## Роли сигналов", "## Параметры Cfg", "## Правила проверки"):
        assert title in out
    code, out, _ = run(capsys, "schema", "--section", "rules")
    assert "## Правила проверки" in out and "## Колонки перечня" not in out


def test_schema_json_to_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "schema.json"
    code, out, _ = run(capsys, "schema", "--format", "json", "--output", str(target))
    assert code == 0 and str(target) in out
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["library_namespace"] == "PL"
    assert {c["name"] for c in data["columns"]} >= {"tag", "device", "dev_no", "role", "params"}


def test_version_and_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip() == f"iolistgen {__version__}"
    with pytest.raises(SystemExit):
        main(["validate", "--help"])
    help_text = capsys.readouterr().out
    assert help_text.startswith("использование: iolistgen validate")
    assert "примеры:" in help_text and "параметры:" in help_text and "аргументы:" in help_text


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "коды выхода" in capsys.readouterr().out


def test_bad_arguments_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["validate", "x.csv", "--report", "pdf"])
    assert info.value.code == 2
    assert "ошибка:" in capsys.readouterr().err


def test_python_module_entry_point(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-m", "iolistgen", "validate", str(DATA / "kns_mini.csv"), "--no-config"],
        capture_output=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0
    assert "ошибок нет" in result.stdout.decode("utf-8")
