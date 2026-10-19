#!/usr/bin/env python3
"""Создать объект Persistent Variables в проекте ``cds.py`` импортом PLCopenXML (CODESYS 3.5.17.30).

Сгенерированный ``GVL_Persist.pvl.st`` должен быть объектом Persistent Variables (контракт
plc-process-lib 18.1, зонд P18). Скриптом CODESYS 3.5.17.30 такой объект не создаётся: у API нет
``create_persistentvars`` (tools/README.md), поэтому ``cds.py import`` пропускает файл ``*.pvl.st``
с предупреждением, пока объекта нет, а существующий — обновляет. Импорт PLCopenXML объект
Persistent Variables создаёт (проверено на 3.5.17.30 в проекте переноса КНС, проект 03, и здесь).

Скрипт заменяет ручной шаг «Application → Добавить объект → Persistent Variables»:

1. находит в раскладке ``src/`` объекты ``*.pvl.st``;
2. для каждого, которого ещё нет в приложении проекта ``cds.py`` (``build/<имя>.project``, с
   ``--tests`` — ``build/<имя>-tests.project``), пишет файл PLCopenXML с его текстом и импортирует
   его в приложение (``tools_project/codesys_pvl_cds.py`` в CODESYS, без окна);
3. сохраняет проект и запоминает его состояние, как ``cds.py import`` (иначе следующий импорт
   принял бы сохранение за правку в IDE).

Порядок: ``cds.py import`` (создаёт проект) → этот скрипт (один раз) → ``cds.py build``. Повторный
запуск ничего не меняет. Блокировка рабочей копии и запуск CODESYS — те же, что у ``cds.py``
(``tools/codesys/cdshost``). Python 3.11+.

Коды выхода: 0 — объекты есть или созданы, 1 — CODESYS не создал объект, 2 — нет проекта
(сначала ``cds.py import``), 3 и выше — как у ``cds.py`` (окружение, таймаут, блокировка).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent.parent
TOOLS_CODESYS = ROOT / "tools" / "codesys"
sys.path[:0] = [str(TOOLS_CODESYS)]

import stlayout as L  # noqa: E402
from cdshost import cli  # noqa: E402

SCRIPT = Path(__file__).resolve().with_name("codesys_pvl_cds.py")
NS_TC6 = "http://www.plcopen.org/xml/tc6_0200"
NS_XHTML = "http://www.w3.org/1999/xhtml"
CDS_GLOBALVARS = "http://www.3s-software.com/plcopenxml/globalvars"
CDS_PLAINTEXT = "http://www.3s-software.com/plcopenxml/interfaceasplaintext"
# Отметка времени в заголовке PLCopenXML: постоянная, файл не зависит от момента запуска
FIXED_TIME = "2026-01-01T00:00:00"
EXIT_NO_PROJECT = 2


def persistent_objects(root: Path) -> list[L.StObject]:
    """Объекты Persistent Variables раскладки ``src/``."""
    result = L.scan(str(root), "src")
    if not result.ok:
        raise SystemExit("codesys_pvl: раскладка не читается: " + "; ".join(i.format() for i in result.issues))
    return [obj for obj in result.objects if obj.kind == L.KIND_PVL]


def plcopen_xml(name: str, declaration: str) -> bytes:
    """PLCopenXML (TC6 2.00, расширение CODESYS) с одним объектом Persistent Variables и его текстом.

    Разметка — как у экспорта CODESYS «объявления как обычный текст»: импорт берёт текст объявления.
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<project xmlns="{NS_TC6}">',
        '  <fileHeader companyName="" productName="iolistgen tools_project/codesys_pvl.py" productVersion="1" '
        f'creationDateTime="{FIXED_TIME}" />',
        f'  <contentHeader name={quoteattr(name)} modificationDateTime="{FIXED_TIME}">',
        "    <coordinateInfo>",
        '      <fbd><scaling x="1" y="1" /></fbd>',
        '      <ld><scaling x="1" y="1" /></ld>',
        '      <sfc><scaling x="1" y="1" /></sfc>',
        "    </coordinateInfo>",
        "  </contentHeader>",
        "  <types><dataTypes /><pous /></types>",
        "  <instances><configurations /></instances>",
        "  <addData>",
        f'    <data name="{CDS_GLOBALVARS}" handleUnknown="implementation">',
        f'      <globalVars name={quoteattr(name)} persistent="true" retain="true">',
        "        <addData>",
        f'          <data name="{CDS_PLAINTEXT}" handleUnknown="implementation">',
        "            <InterfaceAsPlainText>",
        f'              <xhtml xmlns="{NS_XHTML}">{escape(declaration)}</xhtml>',
        "            </InterfaceAsPlainText>",
        "          </data>",
        "        </addData>",
        "      </globalVars>",
        "    </data>",
        "  </addData>",
        "</project>",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows по умолчанию пишет в консоль cp1251
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="codesys_pvl.py",
        description="Создать объекты Persistent Variables раскладки в проекте cds.py импортом PLCopenXML.",
    )
    parser.add_argument("--tests", action="store_true", help="проект режима test (build/<имя>-tests.project)")
    args = parser.parse_args(argv)
    settings = cli.make_settings(ROOT)
    project = settings.project_path(args.tests)
    objects = persistent_objects(ROOT)
    if not objects:
        print("codesys_pvl: в src/ нет объектов Persistent Variables (*.pvl.st)")
        return 0
    if not project.exists():
        command = "python tools/codesys/cds.py import" + (" --tests" if args.tests else "")
        print(f"codesys_pvl: нет проекта {project}: сначала {command}")
        return EXIT_NO_PROJECT
    work = ROOT / "build" / "codesys" / "pvl"
    work.mkdir(parents=True, exist_ok=True)
    items = []
    for obj in objects:
        xml_path = work / f"{obj.name}.xml"
        xml_path.write_bytes(plcopen_xml(obj.name, obj.decl))
        items.append({"name": obj.name, "xml": str(xml_path)})
    job = {"tools_codesys": str(TOOLS_CODESYS), "project": str(project), "objects": items}
    try:
        with cli.repo_lock(settings, "persistent-vars"):
            cli.check_project_state(settings, project, force=False)
            result = cli.run_codesys(settings, str(SCRIPT), job, "pvl")
            if result.get("created"):
                cli.record_project_state(settings, project, cli.layout_subdirs(args.tests))
    except cli.CdsError as exc:
        print(f"codesys_pvl: {exc}")
        return exc.code
    for message in result.get("messages", []):
        print(f"[cds]   импорт PLCopenXML: {message.get('level')}: {message.get('text')}")
    if not result.get("ok"):
        print(f"codesys_pvl: ОШИБКА: {result.get('error', 'CODESYS не создал объект')}")
        return 1
    for name in result.get("existing", []):
        print(f"codesys_pvl: {name} — уже есть в {project.name}")
    for name in result.get("created", []):
        print(f"codesys_pvl: {name} — создан объект Persistent Variables в {project.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
