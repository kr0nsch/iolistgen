"""Раскладка src/ репозитория — пример КНС-1, сгенерированный iolistgen, и ручной PRG_Main.

src/ собирается в CODESYS 3.5.17.30 с библиотекой plc-process-lib 1.0.0.0 (``cds.py build``, ``cds.py check``,
наборы coUnit в ``tests/``; docs/MANUAL_STEPS.md, раздел 9). Тесты здесь держат её в согласии с генератором:
файлы ``src/*/Generated`` — побайтно вывод ``st-codesys`` по ``examples/kns/io_list.csv`` той же командой, что в
README; объект Persistent Variables для ``cds.py`` создаёт ``tools_project/codesys_pvl.py``.
"""

from __future__ import annotations

import xml.dom.minidom
from pathlib import Path

import codesys_pvl
from iolistgen.cli import main
from pytests.genhelp import lint_layout

ROOT = Path(__file__).resolve().parent.parent
KNS = ROOT / "examples" / "kns" / "io_list.csv"
GENERATED = ("src/GVLs/Generated", "src/POUs/Generated")


def _files(root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for folder in GENERATED:
        for path in sorted((root / folder).rglob("*.st")):
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def test_generated_src_matches_generator(tmp_path: Path) -> None:
    """``iolistgen generate examples/kns/io_list.csv --out . --only st-codesys --set st-codesys.doc=…``."""
    args = ["generate", str(KNS), "--out", str(tmp_path), "--only", "st-codesys"]
    assert main([*args, "--set", "st-codesys.doc=docs/MANUAL_STEPS.md"]) == 0
    expected = _files(tmp_path)
    assert len(expected) == 10
    assert _files(ROOT) == expected, (
        "src/*/Generated устарели: python -m iolistgen generate examples/kns/io_list.csv --out . "
        "--only st-codesys --set st-codesys.doc=docs/MANUAL_STEPS.md"
    )


def test_repository_src_is_lint_clean() -> None:
    findings, files = lint_layout(ROOT)
    assert findings == [] and files >= len(GENERATED)


def test_persistent_variables_object_for_cds() -> None:
    objects = codesys_pvl.persistent_objects(ROOT)
    assert [obj.name for obj in objects] == ["GVL_Persist"]
    data = codesys_pvl.plcopen_xml("GVL_Persist", objects[0].decl)
    document = xml.dom.minidom.parseString(data)
    gvl = document.getElementsByTagName("globalVars")[0]
    assert gvl.getAttribute("name") == "GVL_Persist" and gvl.getAttribute("persistent") == "true"
    text = document.getElementsByTagName("xhtml")[0].firstChild
    assert text is not None and text.nodeValue == objects[0].decl  # текст объявления без потерь
    assert codesys_pvl.plcopen_xml("GVL_Persist", objects[0].decl) == data  # постоянный файл
