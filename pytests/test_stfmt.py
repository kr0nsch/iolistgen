"""Запись текста ST: нормализация, комментарии, инициализаторы в несколько строк, вызовы."""

from __future__ import annotations

from iolistgen.generators import stfmt
from iolistgen.generators.plc import OutAssign, Pin
from iolistgen.model import InitGroup, InitItem, default_cfg


def test_normalize() -> None:
    assert stfmt.normalize("a  \r\nb\t\r\n\n\n") == "a\nb\n"
    assert stfmt.normalize("\n\n") == ""


def test_comment_lines_wrap_and_flatten() -> None:
    lines = stfmt.comment_lines("слово " * 40 + "\nхвост", indent="    ", width=60)
    assert all(len(line) <= 60 and line.startswith("    // ") for line in lines)
    assert lines[-1].endswith("хвост")
    assert stfmt.comment_lines("   ") == []


def test_with_comment_moves_long_comment_above() -> None:
    assert stfmt.with_comment("    x := 1;", "коротко") == ["    x := 1;  // коротко"]
    long_comment = "очень длинный комментарий " * 6
    lines = stfmt.with_comment("    x := 1;", long_comment, width=80)
    assert lines[-1] == "    x := 1;"
    assert all(line.startswith("    // ") and len(line) <= 80 for line in lines[:-1])
    assert stfmt.with_comment("x;", "") == ["x;"]


def test_declaration_one_line_when_it_fits() -> None:
    init = InitGroup(open="(", close=")", items=(InitItem(name="tMinStop", value="T#30S"),))
    assert stfmt.declaration("stP1Cfg", "PL.ST_MotorCfg", init) == [
        "    stP1Cfg : PL.ST_MotorCfg := (tMinStop := T#30S);"
    ]
    assert stfmt.declaration("x", "BOOL", comment="флаг") == ["    x : BOOL;  // флаг"]


def test_declaration_breaks_arrays_with_slot_comments() -> None:
    cfg = default_cfg("ST_AnalogInputCfg")
    values = tuple(
        item.model_copy(update={"value": "Critical"}) if item.path == "astAlarm[0].ePriority" else item
        for item in cfg.values
    )
    tree = cfg.model_copy(update={"values": values}).initializer_tree()
    lines = stfmt.declaration("stLT1Cfg", "PL.ST_AnalogInputCfg", tree)
    assert lines[0] == "    stLT1Cfg : PL.ST_AnalogInputCfg := ("
    assert "            (ePriority := PL.E_AlarmPriority.Critical),  // 0 HH" in lines
    assert "            (ePriority := PL.E_AlarmPriority.None)  // 7 (резерв)" in lines
    assert lines[-1] == "    );"
    assert all(len(line) <= stfmt.MAX_LINE for line in lines)


def test_call_aligns_parameters() -> None:
    lines = stfmt.call(
        "GVL_Devices.fbLS1",
        [Pin("xIn", "GVL_IO.xLS1"), Pin("xChannelFault", "FALSE", "нет строки CHF"), Pin("stCmd", "GVL_Hmi.stLS1Cmd")],
    )
    assert lines == [
        "GVL_Devices.fbLS1(",
        "    xIn           := GVL_IO.xLS1,",
        "    xChannelFault := FALSE,  // нет строки CHF",
        "    stCmd         := GVL_Hmi.stLS1Cmd);",
    ]
    assert stfmt.call("GVL_Devices.fbX", []) == ["GVL_Devices.fbX();"]


def test_assignments_align_targets() -> None:
    lines = stfmt.assignments(
        [OutAssign("GVL_IO.xP1_RUN", "xQRun"), OutAssign("GVL_IO.rP1_SpeedRef_pct", "rSpeedRef_pct")],
        "GVL_Devices.fbP1",
    )
    assert lines == [
        "GVL_IO.xP1_RUN          := GVL_Devices.fbP1.xQRun;",
        "GVL_IO.rP1_SpeedRef_pct := GVL_Devices.fbP1.rSpeedRef_pct;",
    ]


def test_list_text_cannot_trigger_lint_markers() -> None:
    text = "Насос TODO уточнить," + chr(10) + "FIXME; lint:allow STL008"
    assert stfmt.one_line(text) == "Насос todo уточнить, fixme; lint-allow STL008"
