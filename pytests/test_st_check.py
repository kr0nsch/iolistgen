"""Проверка сгенерированного ST без CODESYS (``tests_support/check_generated_st.py``).

Без компилятора — st_lint и сборка раскладки. С RuSTy (``plc``) — проверка типов по заглушке
plc-process-lib и отрицательный контроль: намеренно испорченный вызов RuSTy должен отклонить,
иначе зелёная проверка ничего бы не значила.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

if sys.version_info < (3, 11):
    pytest.skip("инструменты шаблона (st_lint, run_rusty) требуют Python 3.11+", allow_module_level=True)

import run_rusty
from tests_support import check_generated_st as harness


def _rusty_available() -> bool:
    try:
        plc = run_rusty.find_compiler()
        run_rusty.find_stdlib(plc)
    except run_rusty.ToolMissing:
        return False
    return True


needs_rusty = pytest.mark.skipif(not _rusty_available(), reason="RuSTy (plc) не найден")


@pytest.mark.parametrize("case", harness.CASES, ids=[case.name for case in harness.CASES])
def test_lint_and_layout(tmp_path: Path, case: harness.Case) -> None:
    result = harness.run_case(case, tmp_path, with_rusty=False)
    assert result.lint_errors == []
    assert result.assemble_ok
    assert result.ok


def test_rusty_root_transforms(tmp_path: Path) -> None:
    case = harness.CASES[0]
    generated = harness.generate(case, tmp_path / "generated")
    root = harness.rusty_root(generated, tmp_path / "root")
    cfg_project = (root / "src/GVLs/Generated/GVL_CfgProject.gvl.st").read_text(encoding="utf-8")
    assert "    stLT101CfgPrj : PL.ST_AnalogInputCfg" in cfg_project
    apply = (root / "src/POUs/Generated/PRG_ApplyProjectCfg/PRG_ApplyProjectCfg.impl.st").read_text(encoding="utf-8")
    assert "GVL_Persist.stLT101Cfg  := GVL_CfgProject.stLT101CfgPrj;" in apply
    motor = (root / "src/POUs/Devices/FB_Motor/FB_Motor.decl.st").read_text(encoding="utf-8")
    assert "VAR_IN_OUT CONSTANT" not in motor
    # исходники не меняются: правки — только в копии для RuSTy
    assert "VAR_IN_OUT CONSTANT" in (harness.STUB_DIR / "src/POUs/Devices/FB_Motor/FB_Motor.decl.st").read_text(
        encoding="utf-8"
    )
    assert "stLT101CfgPrj" not in (generated / "src/GVLs/Generated/GVL_CfgProject.gvl.st").read_text(encoding="utf-8")


@pytest.mark.integration
@needs_rusty
@pytest.mark.parametrize("case", harness.CASES, ids=[case.name for case in harness.CASES])
def test_rusty_accepts_generated_code(tmp_path: Path, case: harness.Case) -> None:
    result = harness.run_case(case, tmp_path)
    assert result.rusty_code == 0
    assert result.ok


MUTANTS = {
    "неизвестный вход": ("xIn           := GVL_IO.xLS201,", "xBogus        := GVL_IO.xLS201,"),
    "нет VAR_IN_OUT": (
        "stCmd         := GVL_Hmi.stLS201Cmd,\n    stCfg         := GVL_Persist.stLS201Cfg);",
        "stCmd         := GVL_Hmi.stLS201Cmd);",
    ),
    "чужая Cfg": ("stCfg         := GVL_Persist.stLS201Cfg);", "stCfg         := GVL_Persist.stLT201Cfg);"),
    "нет переменной": ("xIn           := GVL_IO.xLS201,", "xIn           := GVL_IO.xNoSuchVar,"),
}


@pytest.mark.integration
@needs_rusty
@pytest.mark.parametrize("mutant", sorted(MUTANTS))
def test_rusty_rejects_broken_call(tmp_path: Path, mutant: str) -> None:
    case = harness.CASES[1]  # gen_fixture: LS201 с CHF
    generated = harness.generate(case, tmp_path / "generated")
    root = harness.rusty_root(generated, tmp_path / "root")
    impl = root / "src/POUs/Generated/PRG_Devices/PRG_Devices.impl.st"
    old, new = MUTANTS[mutant]
    text = impl.read_text(encoding="utf-8")
    assert old in text
    impl.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    assert harness.rusty(root, tmp_path / "rusty", optional=False, plc=None, stdlib=None) == 1


@pytest.mark.integration
@needs_rusty
def test_rusty_rejects_unknown_cfg_field(tmp_path: Path) -> None:
    case = harness.CASES[0]
    generated = harness.generate(case, tmp_path / "generated")
    root = harness.rusty_root(generated, tmp_path / "root")
    persist = root / "src/GVLs/Generated/GVL_Persist.pvl.st"
    text = persist.read_text(encoding="utf-8")
    persist.write_bytes(text.replace("tFilter := T#2S", "tFilterBogus := T#2S", 1).encode("utf-8"))
    assert harness.rusty(root, tmp_path / "rusty", optional=False, plc=None, stdlib=None) == 1


def test_main_without_rusty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = harness.main(["--out", str(tmp_path), "--no-rusty", "--case", "kns_mini"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "st_lint: без замечаний; assemble: ок; RuSTy: пропущен" in out
    shutil.rmtree(tmp_path / "kns_mini")
