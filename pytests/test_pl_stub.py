"""Заглушка plc-process-lib (``tests_support/pl_stub``) совпадает с каталогом пакета.

Заглушка написана по тексту ``API.md``, каталог (``catalog.py``, ``fbapi.py``) — тоже. Тест
сверяет их друг с другом: имена и типы полей Cfg, Cmd, Sts и Retain, значения по умолчанию Cfg,
перечисления, входы и выходы ФБ. Расхождение значит, что одна из сторон отстала от контракта.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import stlayout as L
from iolistgen.catalog import DEVICE_TYPES, GVL_CONST, ST_TYPES, STRUCTS, FieldSpec
from iolistgen.enums import DeviceType
from iolistgen.fbapi import ENUMS, FB_INTERFACES
from iolistgen.fbapi import STRUCTS as FB_STRUCTS
from pytests.genhelp import lint_layout

STUB = Path(__file__).resolve().parent.parent / "tests_support" / "pl_stub"


@pytest.fixture(scope="module")
def objects() -> dict[str, L.StObject]:
    result = L.scan(str(STUB), "src")
    assert result.ok, [issue.format() for issue in result.issues]
    return {obj.name: obj for obj in result.objects}


def _members(obj: L.StObject) -> dict[str, L.VarDecl]:
    decl = L.parse_type_decl(obj.decl)
    assert decl is not None
    return {name: member for member in decl.members for name in member.name_list}


def _enum_values(obj: L.StObject) -> list[tuple[str, int]]:
    decl = L.parse_type_decl(obj.decl)
    assert decl is not None and decl.kind == "enum"
    return [(name, int(value or "0")) for name, value, _ in decl.enum_values]


def test_stub_is_lint_clean() -> None:
    findings, files = lint_layout(STUB)
    assert files > 50
    assert findings == []


CATALOG_ENUMS = {t.name: list(zip(t.members, t.values, strict=True)) for t in ST_TYPES.values() if t.kind == "enum"}


@pytest.mark.parametrize("name", sorted(set(ENUMS) | set(CATALOG_ENUMS) | {"E_AiAlarm", "E_MotorAlarm"}))
def test_enums(objects: dict[str, L.StObject], name: str) -> None:
    from iolistgen import catalog

    expected = CATALOG_ENUMS.get(name) or list(ENUMS.get(name, ()))
    if not expected:
        index_enums = {
            "E_AiAlarm": catalog.E_AI_ALARM,
            "E_MotorAlarm": catalog.E_MOTOR_ALARM,
        }
        enum = index_enums[name]
        expected = list(zip(enum.members, enum.values, strict=True))
    assert _enum_values(objects[name]) == expected


def _expected_type(spec: FieldSpec) -> str:
    if spec.st_type is not None:
        return spec.st_type.name
    assert spec.struct is not None
    if spec.array is None:
        return spec.struct
    return f"ARRAY OF {spec.struct}"


def _normalize_type(text: str) -> str:
    return re.sub(r"ARRAY\s*\[[^\]]*\]\s*OF\s+", "ARRAY OF ", " ".join(text.split()))


@pytest.mark.parametrize("name", sorted(STRUCTS))
def test_cfg_structs(objects: dict[str, L.StObject], name: str) -> None:
    members = _members(objects[name])
    assert list(members) == [spec.name for spec in STRUCTS[name]]
    for spec in STRUCTS[name]:
        member = members[spec.name]
        assert _normalize_type(member.type_text) == _expected_type(spec), spec.name
        if spec.st_type is not None:
            default = spec.default if spec.default is not None else False
            if member.init_text is None:
                assert default in (False, 0, 0.0), f"{name}.{spec.name}: в заглушке нет начального значения"
            else:
                assert spec.st_type.parse(member.init_text) == default, f"{name}.{spec.name}"
        elif spec.element_defaults:
            assert member.init_text is not None
            priorities = re.findall(r"ePriority\s*:=\s*E_AlarmPriority\.(\w+)", member.init_text)
            assert priorities == [str(item["ePriority"]) for item in spec.element_defaults], f"{name}.{spec.name}"


@pytest.mark.parametrize("name", sorted(FB_STRUCTS))
def test_cmd_sts_retain_structs(objects: dict[str, L.StObject], name: str) -> None:
    members = _members(objects[name])
    assert [(key, _normalize_type(member.type_text)) for key, member in members.items()] == [
        (field.name, _normalize_type(field.st_type)) for field in FB_STRUCTS[name]
    ]


def _blocks(obj: L.StObject) -> dict[str, list[L.VarDecl]]:
    blocks: dict[str, list[L.VarDecl]] = {}
    for block in L.parse_var_blocks(obj.decl):
        key = " ".join([block.keyword, *block.modifiers])
        blocks.setdefault(key, []).extend(block.decls)
    return blocks


@pytest.mark.parametrize("device_type", list(DeviceType))
def test_fb_interfaces(objects: dict[str, L.StObject], device_type: DeviceType) -> None:
    api = FB_INTERFACES[device_type]
    spec = DEVICE_TYPES[device_type]
    obj = objects[api.fb]
    assert obj.header is not None
    assert obj.header.extends == [api.extends]
    blocks = _blocks(obj)

    def rows(key: str) -> list[tuple[str, str, str]]:
        return [(d.name_list[0], d.type_text, d.init_text or "") for d in blocks.get(key, [])]

    assert rows("VAR_INPUT") == [(f.name, f.st_type, f.default) for f in api.inputs]
    assert rows("VAR_OUTPUT") == [(f.name, f.st_type, f.default) for f in api.outputs]
    if device_type is DeviceType.MOTOR_VFD:  # VAR_IN_OUT наследуются от FB_Motor
        assert "VAR_IN_OUT" not in blocks
        return
    in_out = {d.name_list[0]: d.type_text for d in blocks["VAR_IN_OUT"]}
    expected = {"stCmd": spec.cmd} | ({"stRetain": "ST_DeviceRetain"} if spec.has_retain else {})
    assert in_out == expected
    assert rows("VAR_IN_OUT CONSTANT") == [("stCfg", spec.cfg, "")]


def test_constants_match_catalog(objects: dict[str, L.StObject]) -> None:
    """GVL_Const заглушки — таблица 5.1 каталога: имена по порядку, типы и литералы."""
    blocks = _blocks(objects["GVL_Const"])
    rows = [(d.name_list[0], d.type_text, d.init_text) for d in blocks["VAR_GLOBAL CONSTANT"]]
    assert rows == [(c.name, c.st_type, c.value) for c in GVL_CONST]


def test_base_has_time_source(objects: dict[str, L.StObject]) -> None:
    base = objects["FB_DeviceBase"]
    assert base.header is not None
    assert "ABSTRACT" in base.header.modifiers
    assert [(d.name_list[0], d.type_text) for d in _blocks(base)["VAR_INPUT"]] == [("itfTime", "I_TimeSource")]
