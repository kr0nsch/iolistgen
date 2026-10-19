"""Данные приложения в GVL_Persist — опция ``persist_extra`` (контракт 18.3, правило 9; CONSUMERS G4).

Переменные из файла проекта дописываются после устройств в постоянном порядке; ``persist_check``
сверяет их с прошлой генерацией: перестановка, вставка не в конец, смена типа и удаление —
предупреждения (с ``--strict`` — отказ записи).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from iolistgen.config import Config, parse_config
from iolistgen.generators import GenerationError, resolve_options
from iolistgen.generators.persist_extra import parse_persist_extra
from iolistgen.generators.plc import build_plc
from iolistgen.generators.st_codesys import StCodesysGenerator, check_persist
from iolistgen.model import IoList
from iolistgen.validate import CheckResult
from pytests.genhelp import lint_layout, run, texts
from pytests.helpers import ai, pid

PERSIST = "src/GVLs/Generated/GVL_Persist.pvl.st"
EXTRA = """\
// данные приложения КНС
rLIC101SpOper_m : REAL := 2.0;   // задание оператора уровня, м (P-Q1)

uiStationMode : UINT;
"""


def model_of(check_rows: Callable[..., CheckResult]) -> IoList:
    result = check_rows([ai(), pid()])
    assert result.model is not None
    return result.model


def write_extra(tmp_path: Path, text: str = EXTRA, name: str = "persist_extra.txt") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_declarations() -> None:
    items = parse_persist_extra(EXTRA, "x.txt")
    assert [(i.name, i.st_type, i.init, i.comment, i.line) for i in items] == [
        ("rLIC101SpOper_m", "REAL", "2.0", "задание оператора уровня, м (P-Q1)", 2),
        ("uiStationMode", "UINT", "", "", 4),
    ]
    assert items[0].type_text == "REAL := 2.0"


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("rX REAL;", "ожидается объявление"),
        ("rX : REAL", "ожидается объявление"),
        ("rX : REAL;\nRX : REAL;", "уже объявлена в строке 1"),
        ("р1 : REAL;", "строка 1"),
    ],
)
def test_parse_errors(text: str, fragment: str) -> None:
    with pytest.raises(GenerationError, match=fragment):
        parse_persist_extra(text, "x.txt")


def test_extras_after_devices(check_rows: Callable[..., CheckResult], tmp_path: Path) -> None:
    out = tmp_path / "out"
    run(StCodesysGenerator(), model_of(check_rows), out, {"persist_extra": str(write_extra(tmp_path))})
    persist = texts(out)[PERSIST]
    assert persist.index("stLIC101Retain") < persist.index(
        "// --- данные приложения, persist_extra (persist_extra.txt)"
    )
    assert "    rLIC101SpOper_m : REAL := 2.0;  // задание оператора уровня, м (P-Q1)\n" in persist
    assert persist.index("rLIC101SpOper_m") < persist.index("uiStationMode : UINT;") < persist.index("END_VAR")
    assert "данные приложения (persist_extra)" in persist  # заголовок объекта
    findings, _ = lint_layout(out)
    assert findings == []


def test_extra_clashing_with_device_variable_is_error(check_rows: Callable[..., CheckResult], tmp_path: Path) -> None:
    path = write_extra(tmp_path, "stLIC101Cfg : REAL;\n")
    with pytest.raises(GenerationError, match=r"GVL_Persist\.stLIC101Cfg"):
        run(StCodesysGenerator(), model_of(check_rows), tmp_path / "out", {"persist_extra": str(path)})


def test_missing_file_is_error(check_rows: Callable[..., CheckResult], tmp_path: Path) -> None:
    with pytest.raises(GenerationError, match="не удалось прочитать"):
        run(StCodesysGenerator(), model_of(check_rows), tmp_path / "out", {"persist_extra": str(tmp_path / "no.txt")})


def _check(check_rows: Callable[..., CheckResult], tmp_path: Path, old: str, new: str) -> list[str]:
    out = tmp_path / "out"
    model = model_of(check_rows)
    run(StCodesysGenerator(), model, out, {"persist_extra": str(write_extra(tmp_path, old, "old.txt"))})
    previous = texts(out)[PERSIST]
    return check_persist(previous, build_plc(model), parse_persist_extra(new, "new.txt"))


def test_appending_at_end_is_silent(check_rows: Callable[..., CheckResult], tmp_path: Path) -> None:
    assert _check(check_rows, tmp_path, "rA : REAL;\nrB : REAL;\n", "rA : REAL;\nrB : REAL;\nrC : REAL := 1.0;\n") == []


def test_reorder_is_reported(check_rows: Callable[..., CheckResult], tmp_path: Path) -> None:
    messages = _check(check_rows, tmp_path, "rA : REAL;\nrB : REAL;\n", "rB : REAL;\nrA : REAL;\n")
    assert len(messages) == 1 and "порядок данных приложения" in messages[0] and "было rA, rB" in messages[0]


def test_insert_before_old_is_reported(check_rows: Callable[..., CheckResult], tmp_path: Path) -> None:
    messages = _check(check_rows, tmp_path, "rA : REAL;\nrB : REAL;\n", "rA : REAL;\nrNew : REAL;\nrB : REAL;\n")
    assert messages == [
        "GVL_Persist.rNew: новая переменная данных приложения стоит перед прежними — добавляйте новые в конец "
        "файла persist_extra (контракт 18.3, правило 1)"
    ]


def test_type_change_and_removal_are_reported(check_rows: Callable[..., CheckResult], tmp_path: Path) -> None:
    messages = _check(check_rows, tmp_path, "rA : REAL;\nuiB : UINT;\n", "rA : LREAL;\n")
    assert any("GVL_Persist.rA: тип изменился (REAL → LREAL)" in message for message in messages)
    assert any("GVL_Persist.uiB удалена" in message for message in messages)


def test_strict_generate_cancels_on_reorder(tmp_path: Path) -> None:
    """Через команду: перестановка — предупреждение, с --strict файлы не пишутся (код 1)."""
    from iolistgen.cli import main
    from pytests.helpers import write_csv

    listing = write_csv(tmp_path / "io.csv", [ai(), pid()])
    extra = write_extra(tmp_path, "rA : REAL;\nrB : REAL;\n")
    out = tmp_path / "out"
    base = ["generate", str(listing), "--no-config", "--out", str(out), "--only", "st-codesys"]
    assert main([*base, "--set", f"st-codesys.persist_extra={extra}"]) == 0
    write_extra(tmp_path, "rB : REAL;\nrA : REAL;\n")
    before = (out / PERSIST).read_text(encoding="utf-8")
    assert main([*base, "--set", f"st-codesys.persist_extra={extra}", "--strict"]) == 1
    assert (out / PERSIST).read_text(encoding="utf-8") == before
    assert main([*base, "--set", f"st-codesys.persist_extra={extra}"]) == 0  # без --strict — запись с предупреждением
    assert (out / PERSIST).read_text(encoding="utf-8").index("rB : REAL") < (out / PERSIST).read_text(
        encoding="utf-8"
    ).index("rA : REAL")


def test_path_option_is_relative_to_config(tmp_path: Path) -> None:
    config: Config = parse_config({"generators": {"st-codesys": {"persist_extra": "data/extra.txt"}}})
    values = resolve_options(StCodesysGenerator(), config.generators["st-codesys"], config_dir=tmp_path / "proj")
    assert Path(str(values["persist_extra"])) == tmp_path / "proj" / "data" / "extra.txt"
    from_cli = resolve_options(StCodesysGenerator(), None, {"persist_extra": "extra.txt"}, config_dir=tmp_path)
    assert from_cli["persist_extra"] == "extra.txt"
