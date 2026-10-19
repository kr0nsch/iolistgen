"""Командная строка ``iolistgen``: ``validate``, ``generate``, ``schema``."""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from iolistgen import __version__
from iolistgen.config import Config, ConfigError, resolve_config
from iolistgen.diagnostics import Severity
from iolistgen.generators import (
    ENTRY_POINT_GROUP,
    GenerationError,
    Generator,
    GeneratorContext,
    GeneratorEntry,
    OptionError,
    discover,
    resolve_options,
)
from iolistgen.loaders import InputError
from iolistgen.report import count_text, render_html, render_markdown, summary_line
from iolistgen.schema_doc import SECTIONS, render_reference, schema_json
from iolistgen.validate import CheckResult, check_file

PROG = "iolistgen"
NOT_WRITTEN = "файлы не записаны: генерация выполняется целиком или не выполняется"

MAIN_DESCRIPTION = """\
Проверка перечня сигналов АСУ ТП (CSV или XLSX) и генерация по нему кода ПЛК, карт обмена
и документации. Перечень описан в docs/schema.md, краткий справочник — iolistgen schema."""

MAIN_EPILOG = """\
примеры:
  iolistgen validate docs/03_io_list.csv
  iolistgen validate kns.xlsx --sheet Перечень --report html --out build/reports
  iolistgen generate docs/03_io_list.csv --out .
  iolistgen generate docs/03_io_list.csv --out build/generated --only st-codesys,modbus-map
  iolistgen generate --list
  iolistgen schema --output build/schema.md

коды выхода:
  0  ошибок нет
  1  в перечне есть ошибки (с --strict — и предупреждения) или генератор завершился ошибкой
  2  неверные аргументы, ошибка в iolistgen.toml, файл перечня не найден или не того формата"""

VALIDATE_EPILOG = """\
примеры:
  iolistgen validate docs/03_io_list.csv
  iolistgen validate docs/03_io_list.csv --report both --out build/reports
  iolistgen validate kns.xlsx --sheet Перечень --strict
  iolistgen validate old_list.csv --encoding cp1251 --format json

Сообщение показывает файл и строку, правило (IOL...), уровень, колонку, что не так и как
исправить. Уровни правил меняются в iolistgen.toml: [severity] IOL104 = "warning" или "off"."""

GENERATE_EPILOG = f"""\
примеры:
  iolistgen generate docs/03_io_list.csv --out .
  iolistgen generate docs/03_io_list.csv --out build/generated --only st-codesys
  iolistgen generate kns.xlsx --out . --only docs-table --set docs-table.filename=docs/03_signal_list.md
  iolistgen generate docs/03_io_list.csv --out . --set modbus-map.slave_layout=dev_no
  iolistgen generate --list

С --out . (корень проекта) файлы ложатся по местам: ST — src/GVLs/Generated/ и
src/POUs/Generated/, карты Modbus, перечень сигналов и список тревог — docs/, импорт SCADA —
scada/. Перед генерацией перечень проверяется: при ошибках файлы не пишутся. Файлы пишутся,
только если все генераторы отработали без ошибок (с --strict — и без предупреждений), и
перезаписываются только при изменении содержимого; времени генерации в файлах нет (только с
--timestamp). Плагины подключаются точками входа {ENTRY_POINT_GROUP}."""

SCHEMA_EPILOG = """\
примеры:
  iolistgen schema
  iolistgen schema --section columns --section roles
  iolistgen schema --format json --output build/schema.json"""


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Справка по-русски: «использование:» вместо «usage:»."""

    def add_usage(
        self,
        usage: str | None,
        actions: Iterable[argparse.Action],
        groups: Iterable[Any],
        prefix: str | None = None,
    ) -> None:
        super().add_usage(usage, actions, groups, prefix if prefix is not None else "использование: ")


class _Parser(argparse.ArgumentParser):
    """Парсер с русскими заголовками разделов справки и сообщением об ошибке."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", _HelpFormatter)
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self._positionals.title = "аргументы"
        self._optionals.title = "параметры"
        self.add_argument("-h", "--help", action="help", help="показать эту справку и выйти")

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: ошибка: {message}\n")


def _add_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        metavar="ФАЙЛ",
        help="файл настроек (по умолчанию iolistgen.toml ищется рядом с перечнем и выше, до корня репозитория)",
    )
    parser.add_argument("--no-config", action="store_true", help="не искать iolistgen.toml: только умолчания")
    parser.add_argument("--sheet", metavar="ЛИСТ", help="лист книги XLSX (по умолчанию — первый со строкой заголовка)")
    parser.add_argument(
        "--encoding",
        metavar="КОДИРОВКА",
        help="кодировка CSV (по умолчанию utf-8; обычный CSV из Excel в русской Windows — cp1251)",
    )
    parser.add_argument("--strict", action="store_true", help="предупреждения тоже дают код выхода 1")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=PROG, description=MAIN_DESCRIPTION, epilog=MAIN_EPILOG)
    parser.add_argument("-V", "--version", action="version", version=f"{PROG} {__version__}", help="показать версию")
    commands = parser.add_subparsers(dest="command", metavar="команда", parser_class=_Parser)

    validate = commands.add_parser(
        "validate",
        help="проверить перечень сигналов",
        description="Проверить перечень сигналов и при необходимости записать отчёт Markdown или HTML.",
        epilog=VALIDATE_EPILOG,
    )
    validate.add_argument("list_file", type=Path, metavar="ПЕРЕЧЕНЬ", help="файл перечня: .csv или .xlsx")
    _add_input_options(validate)
    validate.add_argument(
        "--report",
        choices=("md", "html", "both"),
        help="записать отчёт: md — Markdown, html — HTML, both — оба",
    )
    validate.add_argument(
        "--out", type=Path, default=Path("."), metavar="КАТАЛОГ", help="каталог отчётов (по умолчанию текущий)"
    )
    validate.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="вывод в консоль: text (по умолчанию) или json",
    )
    validate.add_argument("-q", "--quiet", action="store_true", help="не печатать сообщения, только итог")
    validate.set_defaults(handler=_cmd_validate)

    generate = commands.add_parser(
        "generate",
        help="сгенерировать файлы по перечню",
        description="Проверить перечень и запустить генераторы (встроенные и плагины).",
        epilog=GENERATE_EPILOG,
    )
    generate.add_argument("list_file", type=Path, nargs="?", metavar="ПЕРЕЧЕНЬ", help="файл перечня: .csv или .xlsx")
    generate.add_argument("--out", type=Path, metavar="КАТАЛОГ", help="каталог для сгенерированных файлов")
    generate.add_argument("--only", metavar="ИМЕНА", help="только эти генераторы, через запятую")
    generate.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="ГЕНЕРАТОР.ОПЦИЯ=ЗНАЧЕНИЕ",
        help="опция генератора (перекрывает [generators.<имя>] в iolistgen.toml); можно повторять",
    )
    generate.add_argument("--list", action="store_true", help="показать генераторы и их опции и выйти")
    generate.add_argument(
        "--timestamp",
        action="store_true",
        help="добавить время генерации (UTC) в заголовки файлов; без ключа генерация идемпотентна",
    )
    _add_input_options(generate)
    generate.set_defaults(handler=_cmd_generate)

    schema = commands.add_parser(
        "schema",
        help="справочник схемы перечня",
        description="Справочник схемы перечня: колонки, типы устройств, роли, параметры Cfg, Modbus, правила.",
        epilog=SCHEMA_EPILOG,
    )
    schema.add_argument("--format", choices=("md", "json"), default="md", help="md (по умолчанию) или json")
    schema.add_argument(
        "--section",
        action="append",
        choices=tuple(SECTIONS),
        metavar="РАЗДЕЛ",
        help=f"только раздел справочника: {', '.join(SECTIONS)}; можно повторять",
    )
    schema.add_argument("--output", type=Path, metavar="ФАЙЛ", help="записать в файл (UTF-8) вместо консоли")
    schema.set_defaults(handler=_cmd_schema)
    return parser


# --- вывод -------------------------------------------------------------------------------------


def _configure_streams() -> None:
    """Вывод в файл или канал — UTF-8; в консоль — с заменой непредставимых символов."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if stream.isatty():
                reconfigure(errors="replace")
            else:
                reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def _out(text: str = "") -> None:
    print(text)


def _err(text: str) -> None:
    print(text, file=sys.stderr)


def _load_config(args: argparse.Namespace) -> Config:
    config = resolve_config(args.config, args.list_file, search=not args.no_config)
    if args.encoding:
        try:
            "".encode(args.encoding)
        except LookupError:
            raise ConfigError(f"--encoding: неизвестная кодировка «{args.encoding}»") from None
        config = config.model_copy(update={"input": config.input.model_copy(update={"encoding": args.encoding})})
    return config


def _summary(result: CheckResult) -> str:
    stats = result.stats
    return (
        f"{result.source.path}: {count_text(stats.signals, 'сигнал', 'сигнала', 'сигналов')}, "
        f"{count_text(stats.devices, 'устройство', 'устройства', 'устройств')} — {summary_line(result)}"
    )


def _result_json(result: CheckResult) -> dict[str, object]:
    return {
        "file": result.source.path,
        "sheet": result.source.sheet,
        "sha256": result.source.sha256,
        "config": result.config.path,
        "ok": result.ok,
        "errors": len(result.errors),
        "warnings": len(result.warnings),
        "stats": dataclasses.asdict(result.stats),
        "diagnostics": [item.model_dump(mode="json") for item in result.diagnostics],
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


# --- команды -----------------------------------------------------------------------------------


def _cmd_validate(args: argparse.Namespace) -> int:
    config = _load_config(args)
    result = check_file(args.list_file, config, sheet=args.sheet)
    reports: list[Path] = []
    if args.report:
        stem = args.list_file.stem
        if args.report in ("md", "both"):
            path = args.out / f"{stem}.validation.md"
            _write(path, render_markdown(result, __version__))
            reports.append(path)
        if args.report in ("html", "both"):
            path = args.out / f"{stem}.validation.html"
            _write(path, render_html(result, __version__))
            reports.append(path)
    if args.format == "json":
        payload = _result_json(result)
        payload["reports"] = [str(path) for path in reports]
        _out(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not args.quiet:
            for item in result.diagnostics:
                _out(item.render())
        _out(_summary(result))
        for path in reports:
            _out(f"отчёт: {path}")
    return result.exit_code(strict=args.strict)


def _print_generators(entries: dict[str, GeneratorEntry]) -> None:
    _out(f"Генераторы iolistgen (плагины — точки входа {ENTRY_POINT_GROUP}):")
    width = max((len(entry.name) for entry in entries.values()), default=0)
    for entry in entries.values():
        if entry.generator is None:
            _out(f"  {entry.name:<{width}}  {entry.origin} — НЕ ЗАГРУЖЕН: {entry.error}")
            continue
        _out(f"  {entry.name:<{width}}  {entry.origin} — {entry.generator.description}")
        for option in entry.generator.options:
            default = str(option.default).lower() if isinstance(option.default, bool) else option.default
            choices = f" ({', '.join(option.choices)})" if option.choices else ""
            _out(f"  {'':<{width}}    {option.name} = {default}{choices}: {option.help}")


def _parse_sets(values: Sequence[str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in values:
        key, sep, value = item.partition("=")
        name, dot, option = key.partition(".")
        if not sep or not dot or not name.strip() or not option.strip():
            raise OptionError(f"--set {item}: ожидается ГЕНЕРАТОР.ОПЦИЯ=ЗНАЧЕНИЕ")
        result.setdefault(name.strip(), {})[option.strip()] = value
    return result


def _cmd_generate(args: argparse.Namespace) -> int:
    entries = discover()
    if args.list:
        _print_generators(entries)
        return 0
    if args.list_file is None or args.out is None:
        _err(f"{PROG} generate: ошибка: укажите перечень и --out КАТАЛОГ (или --list)")
        return 2
    available: dict[str, Generator] = {
        entry.name: entry.generator for entry in entries.values() if entry.generator is not None
    }
    if args.only:
        names = list(dict.fromkeys(name.strip() for name in args.only.split(",") if name.strip()))
        for name in names:
            broken = next((e for e in entries.values() if e.name == name and e.generator is None), None)
            if name not in available:
                reason = f": {broken.error}" if broken is not None else ""
                _err(f"{PROG} generate: ошибка: генератор «{name}» недоступен{reason}; есть: {', '.join(available)}")
                return 2
    else:
        names = list(available)
        for entry in entries.values():
            if entry.generator is None:
                _err(f"предупреждение: плагин {entry.name} не загружен ({entry.error}) и пропущен")
    try:
        overrides = _parse_sets(args.set)
        unknown = sorted(set(overrides) - set(available))
        if unknown:
            raise OptionError(f"--set: нет генератора {', '.join(unknown)}")
        config = _load_config(args)
        config_dir = Path(config.path).parent if config.path else None
        options = {
            name: resolve_options(
                available[name], config.generators.get(name), overrides.get(name), config_dir=config_dir
            )
            for name in names
        }
    except OptionError as exc:
        _err(f"{PROG} generate: ошибка: {exc}")
        return 2
    result = check_file(args.list_file, config, sheet=args.sheet)
    for item in result.diagnostics:
        _out(item.render())
    if result.model is None:
        _out(_summary(result))
        _out(f"генерация отменена: в перечне {count_text(len(result.errors), 'ошибка', 'ошибки', 'ошибок')}")
        return 1
    if args.strict and result.warnings:
        _out(_summary(result))
        _out("генерация отменена: есть предупреждения, а задан --strict")
        return 1
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = None
    if args.timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # все генераторы работают в памяти; файлы пишутся, только если все отработали без ошибок
    contexts: list[GeneratorContext] = []
    owners: dict[Path, str] = {}
    for name in names:
        generator = available[name]
        ctx = GeneratorContext(
            generator=name,
            out_dir=out_dir,
            options=options[name],
            config=config,
            source=result.source,
            version=__version__,
            timestamp=timestamp,
            deferred=True,
        )
        try:
            generator.generate(result.model, out_dir, ctx)
        except GenerationError as exc:
            _err(f"{PROG} generate: генератор {name}: {exc}")
            _err(NOT_WRITTEN)
            return 1
        except Exception as exc:  # плагин может упасть: сообщить и вернуть 1
            _err(f"{PROG} generate: генератор {name} завершился ошибкой: {type(exc).__name__}: {exc}")
            _err(NOT_WRITTEN)
            return 1
        for output in ctx.outputs:
            owner = owners.setdefault(output.path, name)
            if owner != name:
                _err(
                    f"{PROG} generate: файл {_display(output.path, out_dir)} пишут два генератора: {owner} и {name}; "
                    "задайте другое имя файла опцией одного из них"
                )
                _err(NOT_WRITTEN)
                return 1
        contexts.append(ctx)
    for ctx in contexts:
        for message in ctx.warnings:
            _out(f"{ctx.generator}: предупреждение: {message}")
    if args.strict and any(ctx.warnings for ctx in contexts):
        _out("генерация отменена: генераторы выдали предупреждения, а задан --strict; файлы не записаны")
        return 1
    total = changed = 0
    for ctx in contexts:
        ctx.commit()
        for output in ctx.outputs:
            total += 1
            changed += output.changed
            status = "записан" if output.changed else "без изменений"
            _out(f"{ctx.generator}: {_display(output.path, out_dir)} — {status}")
    warnings = len([item for item in result.diagnostics if item.severity is Severity.WARNING])
    tail = f", предупреждений в перечне: {warnings}" if warnings else ""
    _out(f"файлов: {total}, изменено: {changed}{tail}")
    return 0


def _display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _cmd_schema(args: argparse.Namespace) -> int:
    if args.format == "json":
        text = json.dumps(schema_json(), ensure_ascii=False, indent=2) + "\n"
    else:
        text = render_reference(args.section)
    if args.output is not None:
        _write(args.output, text)
        _out(f"справочник: {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа консольной команды ``iolistgen``."""
    _configure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        code: int = args.handler(args)
    except (ConfigError, InputError) as exc:
        _err(f"{PROG}: ошибка: {exc}")
        return 2
    except OSError as exc:  # каталог вывода не создать, файл отчёта не записать
        _err(f"{PROG}: ошибка: {exc.strerror or exc}: {exc.filename or ''}".rstrip(": "))
        return 2
    return code


__all__ = ["build_parser", "main"]
