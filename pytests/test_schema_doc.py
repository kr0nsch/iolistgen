"""Справочник схемы: docs/schema.md синхронен с каталогами, JSON-схема для программ."""

from __future__ import annotations

from pathlib import Path

import pytest

from iolistgen.columns import COLUMNS
from iolistgen.diagnostics import RULES
from iolistgen.enums import DeviceType, Role
from iolistgen.schema_doc import SECTIONS, main, render_reference, schema_json, update_document

SCHEMA_MD = Path(__file__).resolve().parents[1] / "docs" / "schema.md"


def test_schema_document_is_up_to_date() -> None:
    text = SCHEMA_MD.read_text(encoding="utf-8")
    assert update_document(text) == text, "запустите: python -m iolistgen.schema_doc docs/schema.md"


def test_schema_document_has_every_generated_block() -> None:
    text = SCHEMA_MD.read_text(encoding="utf-8")
    for name in SECTIONS:
        assert f"<!-- BEGIN iolistgen:{name} -->" in text, name


def test_reference_mentions_every_column_role_and_rule() -> None:
    text = render_reference()
    for column in COLUMNS:
        assert f"`{column.name}`" in text
    for role in Role:
        assert f"`{role.value}`" in text
    for code in RULES:
        assert f"`{code}`" in text
    for device_type in DeviceType:
        assert f"`{device_type.value}`" in text


def test_reference_sections_subset() -> None:
    text = render_reference(["modbus"])
    assert "## Modbus: функции и типы данных" in text
    assert "## Колонки перечня" not in text


def test_update_document_rejects_unknown_block() -> None:
    with pytest.raises(KeyError):
        update_document("<!-- BEGIN iolistgen:nope -->\nx\n<!-- END iolistgen:nope -->\n")


def test_schema_json() -> None:
    data = schema_json()
    device_types = {item["name"]: item for item in data["device_types"]}
    assert set(device_types) == {t.value for t in DeviceType}
    vfd = device_types["MotorVfd"]
    assert vfd["main_roles"] == ["CMD_RUN", "VFD_CTW"]
    assert any(field["path"] == "stVfd.rSpeedMin_pct" for field in vfd["cfg_fields"])
    assert len(data["rules"]) == len(RULES)


def test_schema_doc_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = tmp_path / "schema.md"
    document.write_text(
        "до\n<!-- BEGIN iolistgen:rules -->\nстарое\n<!-- END iolistgen:rules -->\nпосле\n", encoding="utf-8"
    )
    assert main([str(document), "--check"]) == 1
    assert main([str(document)]) == 0
    assert "обновлено" in capsys.readouterr().out
    assert main([str(document), "--check"]) == 0
    text = document.read_text(encoding="utf-8")
    assert text.startswith("до\n") and text.endswith("после\n")
    assert "`IOL412`" in text
