"""Отчёт проверки в Markdown (GitHub Flavored Markdown): для pull request и ``docs/``."""

from __future__ import annotations

from iolistgen.report.context import ReportRow, build_context
from iolistgen.validate import CheckResult


def md_cell(text: str) -> str:
    """Текст для ячейки таблицы GFM: экранирование ``|``, ``<``, ``>``, переводы строк."""
    escaped = text.replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    return "<br>".join(line.strip() for line in escaped.splitlines())


def _code(text: str) -> str:
    """Тег моноширинным шрифтом; тег со спецсимволами Markdown (ошибка IOL102) — обычным текстом."""
    if not text:
        return ""
    if any(char in text for char in "`<>|\\\n"):
        return md_cell(text)
    return f"`{text}`"


def _column(row: ReportRow) -> str:
    if row.column is None:
        return ""
    return f"{row.column} «{row.header}»" if row.header else row.column


def render_markdown(result: CheckResult, version: str) -> str:
    """Отчёт целиком; строки заканчиваются ``\\n``, в конце — один перевод строки."""
    ctx = build_context(result, version)
    lines: list[str] = [f"# {ctx.title}", ""]
    file_text = f"`{ctx.file_name}`" + (f", лист «{ctx.sheet}»" if ctx.sheet else "")
    lines += [
        "| | |",
        "|---|---|",
        f"| Файл | {md_cell(file_text)} |",
        f"| Формат | {ctx.format} |",
        f"| SHA-256 | `{ctx.sha256}` |",
        f"| Настройки | {md_cell(ctx.config)} |",
        f"| iolistgen | {ctx.version} |",
        "",
    ]
    if ctx.ok:
        verdict = f"**Итог: {ctx.summary}.** Перечень готов к генерации."
    else:
        verdict = f"**Итог: {ctx.summary}.** Генерация невозможна, пока есть ошибки."
    lines += [verdict, "", "## Сводка", ""]
    lines += [
        "| Сигналов | Устройств | Сигналов Modbus | Ошибок | Предупреждений |",
        "|---:|---:|---:|---:|---:|",
        f"| {ctx.signals} | {ctx.devices} | {ctx.modbus} | {ctx.errors} | {ctx.warnings} |",
        "",
    ]
    if ctx.by_signal_type:
        lines.append("Типы сигналов: " + " · ".join(f"{name} {n}" for name, n in ctx.by_signal_type.items()) + ".")
    if ctx.by_device_type:
        lines.append("Типы устройств: " + " · ".join(f"{name} {n}" for name, n in ctx.by_device_type.items()) + ".")
    if ctx.by_signal_type or ctx.by_device_type:
        lines.append("")
    lines += ["## Сообщения", ""]
    if not ctx.rows:
        lines += ["Сообщений нет.", ""]
    else:
        lines += [
            "| Уровень | Код | Строка | Колонка | Тег | Что не так | Как исправить |",
            "|---|---|---:|---|---|---|---|",
        ]
        for row in ctx.rows:
            message = row.message + (f" (см. {row.related})" if row.related else "")
            cells = [
                row.severity_title,
                row.code,
                str(row.row) if row.row is not None else "",
                md_cell(_column(row)),
                _code(row.tag),
                md_cell(message),
                md_cell(row.hint),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        lines += ["## Сработавшие правила", "", "| Код | Уровень | Правило | Сообщений |", "|---|---|---|---:|"]
        for rule in ctx.rules:
            lines.append(f"| {rule.code} | {rule.severity_title} | {md_cell(rule.title)} | {rule.count} |")
        lines.append("")
    lines.append(
        f"<sub>iolistgen {ctx.version} · SHA-256 перечня `{ctx.sha_short}` · "
        "схема перечня и правила — `iolistgen schema`</sub>"
    )
    return "\n".join(lines) + "\n"
