"""Общий контекст отчётов: строки сообщений, сводка по правилам, формы слов после чисел."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from iolistgen.diagnostics import RULES, Diagnostic, Severity
from iolistgen.validate import CheckResult


def plural(count: int, one: str, few: str, many: str) -> str:
    """Форма слова после числа: 1 ошибка, 2 ошибки, 5 ошибок."""
    tens, hundreds = count % 10, count % 100
    if tens == 1 and hundreds != 11:
        return one
    if 2 <= tens <= 4 and not 12 <= hundreds <= 14:
        return few
    return many


def count_text(count: int, one: str, few: str, many: str) -> str:
    return f"{count} {plural(count, one, few, many)}"


def summary_line(result: CheckResult) -> str:
    """«3 ошибки, 2 предупреждения» или «ошибок нет»."""
    errors, warnings = len(result.errors), len(result.warnings)
    parts = []
    parts.append(count_text(errors, "ошибка", "ошибки", "ошибок") if errors else "ошибок нет")
    if warnings:
        parts.append(count_text(warnings, "предупреждение", "предупреждения", "предупреждений"))
    return ", ".join(parts)


@dataclass(frozen=True)
class ReportRow:
    """Строка таблицы сообщений."""

    severity: str
    severity_title: str
    code: str
    rule_title: str
    row: int | None
    column: str | None
    header: str | None
    location: str
    tag: str
    device: str
    message: str
    hint: str
    related: str


@dataclass(frozen=True)
class RuleCount:
    """Сколько раз сработало правило."""

    code: str
    severity: str
    severity_title: str
    group: str
    title: str
    count: int


def report_rows(diagnostics: list[Diagnostic]) -> list[ReportRow]:
    rows: list[ReportRow] = []
    for item in diagnostics:
        source = item.source
        rows.append(
            ReportRow(
                severity=item.severity.value,
                severity_title=item.severity.label,
                code=item.code,
                rule_title=RULES[item.code].title,
                row=source.row if source is not None else None,
                column=source.column_letter if source is not None else None,
                header=source.header if source is not None else None,
                location=source.location() if source is not None else "файл",
                tag=item.tag or "",
                device=item.device or "",
                message=item.message,
                hint=item.hint,
                related=item.related_text,
            )
        )
    return rows


def rule_counts(diagnostics: list[Diagnostic]) -> list[RuleCount]:
    counter = Counter((item.code, item.severity) for item in diagnostics)
    result = [
        RuleCount(
            code=code,
            severity=severity.value,
            severity_title=severity.label,
            group=RULES[code].group,
            title=RULES[code].title,
            count=count,
        )
        for (code, severity), count in counter.items()
    ]
    result.sort(key=lambda item: (item.severity != Severity.ERROR.value, item.code))
    return result


@dataclass(frozen=True)
class ReportContext:
    """Данные отчёта для шаблонов Markdown и HTML."""

    title: str
    file_name: str
    file_path: str
    sheet: str | None
    format: str
    sha256: str
    sha_short: str
    version: str
    config: str
    ok: bool
    errors: int
    warnings: int
    errors_text: str
    warnings_text: str
    summary: str
    signals: int
    devices: int
    modbus: int
    by_signal_type: dict[str, int]
    by_device_type: dict[str, int]
    rows: list[ReportRow]
    rules: list[RuleCount]


def config_display(result: CheckResult) -> str:
    """Файл настроек для отчёта: путь относительно каталога перечня, без абсолютных путей машины.

    Найденный ``iolistgen.toml`` хранится абсолютным путём; в отчёт, который коммитят в ``docs/``,
    попадает ``iolistgen.toml`` или ``../iolistgen.toml`` — отчёт одинаков на любой машине и не
    раскрывает структуру каталогов автора.
    """
    if not result.config.path:
        return "по умолчанию"
    config = Path(result.config.path)
    if not config.is_absolute():
        return config.as_posix()
    base = Path(os.path.abspath(result.source.path)).parent
    try:
        return Path(os.path.relpath(config, base)).as_posix()
    except ValueError:  # другой диск Windows: относительного пути нет
        return config.name


def build_context(result: CheckResult, version: str) -> ReportContext:
    """Собрать данные отчёта."""
    source = result.source
    stats = result.stats
    errors, warnings = len(result.errors), len(result.warnings)
    return ReportContext(
        title="Проверка перечня сигналов",
        file_name=source.name,
        file_path=source.path,
        sheet=source.sheet,
        format=source.format.upper(),
        sha256=source.sha256,
        sha_short=source.short_hash,
        version=version,
        config=config_display(result),
        ok=result.ok,
        errors=errors,
        warnings=warnings,
        errors_text=count_text(errors, "ошибка", "ошибки", "ошибок"),
        warnings_text=count_text(warnings, "предупреждение", "предупреждения", "предупреждений"),
        summary=summary_line(result),
        signals=stats.signals,
        devices=stats.devices,
        modbus=stats.modbus,
        by_signal_type=stats.by_signal_type,
        by_device_type=stats.by_device_type,
        rows=report_rows(result.diagnostics),
        rules=rule_counts(result.diagnostics),
    )
