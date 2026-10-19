#!/usr/bin/env python3
"""Проверка сгенерированного ST без CODESYS: st_lint, сборка раскладки и RuSTy по заглушке библиотеки.

Для каждого случая (перечень и опции генератора ``st-codesys``):

1. ``iolistgen`` генерирует ST в ``<out>/<случай>/generated/src/`` (раскладка docs/LAYOUT.md);
2. ``tools/check/st_lint.py --strict`` — правила CONTRIBUTING.md (префиксы, заголовки POU, длина
   строк, нормализация файлов, «магические числа»);
3. ``tools/assemble.py`` (вариант ``iec``) — раскладка и заголовки объектов;
4. ``tools/check/run_rusty.py`` — RuSTy ``plc --check`` по объединённой раскладке: заглушка
   plc-process-lib (``tests_support/pl_stub/``), заглушка приложения (``tests_support/app_stub/``) и
   сгенерированный код; пространство имён ``PL.`` убирается (``--strip-namespace PL``).

Перед RuSTy копия раскладки меняется только там, где RuSTy не поддерживает конструкцию CODESYS
(в исходниках и в заглушке остаётся текст по контракту):

- ``VAR_IN_OUT CONSTANT`` → ``VAR_IN_OUT`` в заглушке: RuSTy 1.0.6 отвечает E034 «This variable
  block does not support the CONSTANT modifier»;
- константы ``GVL_CfgProject.st<DEV>Cfg`` → ``st<DEV>CfgPrj``: RuSTy не знает имён GVL (замена R3
  шаблона убирает ``GVL_Имя.``), и одноимённые переменные ``GVL_Persist`` и ``GVL_CfgProject``
  дали бы дубль; в CODESYS списки с ``qualified_only`` их различают.

Ключ ``--repo`` проверяет так же раскладку ``src/`` самого репозитория (пример КНС-1, сгенерированный в
``src/GVLs/Generated`` и ``src/POUs/Generated``, и ручной ``PRG_Main``) — без генерации.

Настоящая проверка — сборка в CODESYS 3.5.17 с библиотекой plc-process-lib: ``cds.py build`` и ``cds.py check``
(docs/MANUAL_STEPS.md, раздел 9).

Нужен Python 3.11+ (инструменты шаблона). Коды выхода: 0 — все проверки прошли (RuSTy без
компилятора с ``--optional`` — пропуск), 1 — ошибки.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "check")]

import assemble  # noqa: E402
import run_rusty  # noqa: E402
import st_lint  # noqa: E402
from iolistgen import __version__  # noqa: E402
from iolistgen.config import resolve_config  # noqa: E402
from iolistgen.generators import GeneratorContext, resolve_options  # noqa: E402
from iolistgen.generators.st_codesys import StCodesysGenerator  # noqa: E402
from iolistgen.validate import check_file  # noqa: E402

STUB_DIR = ROOT / "tests_support" / "pl_stub"
APP_STUB_DIR = ROOT / "tests_support" / "app_stub"
DEFAULT_OUT = ROOT / "build" / "st_check"
NAMESPACE = "PL"

_CONSTANT_INOUT_RE = re.compile(r"\bVAR_IN_OUT\s+CONSTANT\b")
_CFG_PROJECT_REF_RE = re.compile(r"\bGVL_CfgProject\.st([A-Za-z0-9_]+?)Cfg\b")
_CFG_PROJECT_DECL_RE = re.compile(r"^(\s*)st([A-Za-z0-9_]+?)Cfg(\s*:)", re.MULTILINE)


@dataclass(frozen=True)
class Case:
    """Случай проверки: перечень и опции генератора ``st-codesys``."""

    name: str
    list_file: Path
    options: dict[str, object] = field(default_factory=dict)


REPO_CASE = "repo_src"

CASES: tuple[Case, ...] = (
    Case("kns_mini", ROOT / "pytests" / "data" / "kns_mini.csv"),
    Case(
        "gen_fixture",
        ROOT / "pytests" / "data" / "gen_fixture.csv",
        {"time_source": "GVL_CheckApp.itfClock", "alarm_sink": "GVL_CheckApp.itfSink"},
    ),
    # примеры из README: перечень КНС-1 (с сигналами AUX) и синтетический на 300 сигналов
    Case("kns_example", ROOT / "examples" / "kns" / "io_list.csv"),
    Case("synthetic_300", ROOT / "examples" / "synthetic" / "io_list_300.csv"),
)


@dataclass
class CaseResult:
    """Итог случая: замечания st_lint и сборки, код RuSTy."""

    case: Case
    lint_errors: list[str] = field(default_factory=list)
    assemble_ok: bool = False
    rusty_code: int | None = None

    @property
    def ok(self) -> bool:
        return not self.lint_errors and self.assemble_ok and self.rusty_code in (0, None)


def generate(case: Case, target: Path) -> Path:
    """Сгенерировать ST случая в ``target`` (каталог раскладки — ``target/src``).

    Настройки — как у ``iolistgen``: ``iolistgen.toml`` рядом с перечнем или выше, иначе умолчания.
    """
    config = resolve_config(None, case.list_file)
    result = check_file(case.list_file, config)
    if result.model is None:
        messages = "; ".join(item.render() for item in result.errors)
        raise SystemExit(f"check_generated_st: в перечне {case.list_file} ошибки: {messages}")
    generator = StCodesysGenerator()
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    options = {"persist_check": False, **case.options}
    ctx = GeneratorContext(
        generator=generator.name,
        out_dir=target,
        options=resolve_options(
            generator,
            {**config.generators.get(generator.name, {}), **options},
            config_dir=Path(config.path).parent if config.path else None,
        ),
        config=config,
        source=result.model.source,
        version=__version__,
    )
    generator.generate(result.model, target, ctx)
    return target


def lint(root: Path) -> list[str]:
    """Замечания st_lint (ошибки и предупреждения) по ``root/src`` с настройками репозитория."""
    config = st_lint.load_config(st_lint.DEFAULT_CONFIG_PATH)
    findings, _ = st_lint.lint(str(root), config, ["src"])
    return [finding.format() for finding in findings]


def assemble_ok(root: Path, out: Path) -> bool:
    code, _ = assemble.run(str(root), "src", None, assemble.FLAVOR_IEC, str(out), [])
    return code == 0


def rusty_root(generated: Path, target: Path) -> Path:
    """Объединённая раскладка для RuSTy: заглушка библиотеки, заглушка приложения, сгенерированный код."""
    if target.exists():
        shutil.rmtree(target)
    for source in (STUB_DIR / "src", APP_STUB_DIR / "src", generated / "src"):
        shutil.copytree(source, target / "src", dirs_exist_ok=True)
    for path in sorted((target / "src").rglob("*.st")):
        text = path.read_text(encoding="utf-8")
        new = _CONSTANT_INOUT_RE.sub("VAR_IN_OUT", text)
        new = _CFG_PROJECT_REF_RE.sub(r"GVL_CfgProject.st\1CfgPrj", new)
        if path.name == "GVL_CfgProject.gvl.st":
            new = _CFG_PROJECT_DECL_RE.sub(r"\1st\2CfgPrj\3", new)
        if new != text:
            path.write_bytes(new.encode("utf-8"))
    return target


def rusty(root: Path, out: Path, *, optional: bool, plc: str | None, stdlib: str | None) -> int:
    argv = [
        "--root",
        str(root),
        "--no-tests",
        "--strip-namespace",
        NAMESPACE,
        "--out",
        str(out / "assembled"),
        "--log",
        str(out / "rusty.log"),
        "--json",
        str(out / "rusty.json"),
    ]
    if optional:
        argv.append("--optional")
    if plc:
        argv += ["--plc", plc]
    if stdlib:
        argv += ["--stdlib", stdlib]
    return run_rusty.main(argv)


def run_case(
    case: Case,
    out: Path,
    *,
    with_rusty: bool = True,
    optional: bool = False,
    plc: str | None = None,
    stdlib: str | None = None,
) -> CaseResult:
    base = out / case.name
    result = CaseResult(case)
    generated = ROOT if case.name == REPO_CASE else generate(case, base / "generated")
    result.lint_errors = lint(generated)
    result.assemble_ok = assemble_ok(generated, base / "assembled-iec")
    if with_rusty:
        root = rusty_root(generated, base / "rusty-root")
        result.rusty_code = rusty(root, base / "rusty", optional=optional, plc=plc, stdlib=stdlib)
    return result


def _shown(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_generated_st.py",
        description="Проверка сгенерированного ST без CODESYS: st_lint, assemble, RuSTy по заглушке plc-process-lib.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="каталог результатов (build/st_check)")
    parser.add_argument("--case", action="append", choices=[case.name for case in CASES], help="только этот случай")
    parser.add_argument(
        "--list",
        action="append",
        type=Path,
        metavar="ПЕРЕЧЕНЬ",
        help="проверить код по этому перечню (опции st-codesys — по умолчанию); можно повторять",
    )
    parser.add_argument(
        "--repo", action="store_true", help="проверить src/ репозитория (пример КНС-1 и PRG_Main) вместо генерации"
    )
    parser.add_argument("--no-rusty", action="store_true", help="без RuSTy: только st_lint и assemble")
    parser.add_argument("--optional", action="store_true", help="нет RuSTy — предупреждение, а не ошибка")
    parser.add_argument("--plc", help="путь к компилятору RuSTy plc")
    parser.add_argument("--stdlib", help="каталог объявлений stdlib RuSTy")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    assemble.configure_output()
    args = build_parser().parse_args(argv)
    if args.repo:
        selected = [Case(REPO_CASE, ROOT / "src")]
    elif args.list:
        selected = [Case(path.stem, path.resolve()) for path in args.list]
    else:
        selected = [case for case in CASES if not args.case or case.name in args.case]
    failed = 0
    for case in selected:
        print(f"== {case.name}: {_shown(case.list_file)} {case.options or ''}".rstrip())
        result = run_case(
            case, args.out, with_rusty=not args.no_rusty, optional=args.optional, plc=args.plc, stdlib=args.stdlib
        )
        for line in result.lint_errors:
            print(line)
        rusty_text = {None: "пропущен", 0: "без ошибок"}.get(result.rusty_code, "ОШИБКИ")
        print(
            f"   st_lint: {'без замечаний' if not result.lint_errors else f'замечаний {len(result.lint_errors)}'}; "
            f"assemble: {'ок' if result.assemble_ok else 'ОШИБКИ'}; RuSTy: {rusty_text}"
        )
        failed += not result.ok
    print(f"check_generated_st: случаев {len(selected)}, с ошибками {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
