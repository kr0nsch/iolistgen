"""Запись текста ST по правилам раскладки шаблона (``docs/LAYOUT.md``, ``tools/check/st_lint.py``).

- отступ — 4 пробела, табов нет, строка не длиннее 120 символов (STL003);
- текст нормализован: без хвостовых пробелов, LF, ровно один перевод строки в конце (STL009);
- инициализатор Cfg, который не помещается в строку, пишется по полю на строку, элементы
  массивов — с комментарием «индекс и слот» (``// 0 HH``);
- параметры вызова выравниваются по ``:=``.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Iterable, Sequence

from iolistgen.generators.plc import OutAssign, Pin
from iolistgen.model import InitGroup, InitItem

INDENT = "    "
MAX_LINE = 120


def normalize(text: str) -> str:
    """Нормализация, как у ``stlayout.normalize_text``: хвостовые пробелы, CRLF, пустые строки в конце."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


_LINT_MARKERS = re.compile(r"\b(TODO|FIXME)\b|lint:allow")


def one_line(text: str) -> str:
    """Текст перечня для комментария: одна строка без повторных пробелов.

    Слова-метки линтера из перечня обезвреживаются: «TODO»/«FIXME» без номера задачи — ошибка
    STL004, «lint:allow» — подавление правила. В комментарий они попадают строчными буквами.
    """
    flat = " ".join(text.split())
    return _LINT_MARKERS.sub(lambda match: match.group(0).lower().replace(":", "-"), flat)


def comment_lines(text: str, indent: str = "", width: int = MAX_LINE, prefix: str = "// ") -> list[str]:
    """Комментарий ``//``, перенесённый по словам так, чтобы строки помещались в ``width``."""
    body = one_line(text)
    if not body:
        return []
    available = max(width - len(indent) - len(prefix), 20)
    wrapped = textwrap.wrap(body, available, break_long_words=True, break_on_hyphens=False)
    return [f"{indent}{prefix}{line}".rstrip() for line in wrapped]


def with_comment(code: str, comment: str, width: int = MAX_LINE) -> list[str]:
    """Строка кода с комментарием в конце; если не помещается — комментарий строкой выше."""
    if not comment:
        return [code]
    line = f"{code}  // {one_line(comment)}"
    if len(line) <= width:
        return [line]
    indent = code[: len(code) - len(code.lstrip())]
    return [*comment_lines(comment, indent, width), code]


def _render_items(items: Sequence[InitItem], indent: str, width: int) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(items):
        comma = "," if index < len(items) - 1 else ""
        lines.extend(_render_item(item, indent, width, comma))
    return lines


def _render_item(item: InitItem, indent: str, width: int, comma: str) -> list[str]:
    prefix = f"{item.name} := " if item.name else ""
    tail = f"  // {item.comment}" if item.comment else ""
    flat = f"{indent}{item.flat()}{comma}"
    if item.group is None or len(flat + tail) <= width:
        return [flat + tail]
    group = item.group
    head = f"{indent}{prefix}{group.open}{tail}"
    body = _render_items(group.items, indent + INDENT, width)
    return [head, *body, f"{indent}{group.close}{comma}"]


def declaration(
    name: str,
    type_text: str,
    init: InitGroup | None = None,
    *,
    indent: str = INDENT,
    width: int = MAX_LINE,
    comment: str = "",
) -> list[str]:
    """Объявление ``name : type := инициализатор;`` в одну или несколько строк."""
    head = f"{indent}{name} : {type_text}"
    if init is None or not init.items:
        return with_comment(f"{head};", comment, width)
    flat = f"{head} := {init.flat()};"
    if len(flat) <= width:
        return with_comment(flat, comment, width)
    lines = [f"{head} := {init.open}", *_render_items(init.items, indent + INDENT, width), f"{indent}{init.close};"]
    if comment:
        return [*comment_lines(comment, indent, width), *lines]
    return lines


def aligned(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Пары «имя, значение» с именами, дополненными пробелами до общей ширины."""
    items = list(pairs)
    width = max((len(name) for name, _ in items), default=0)
    return [(name.ljust(width), value) for name, value in items]


def call(instance: str, pins: Sequence[Pin], width: int = MAX_LINE) -> list[str]:
    """Вызов экземпляра с параметрами по одному на строку, выровненными по ``:=``."""
    if not pins:
        return [f"{instance}();"]
    lines = [f"{instance}("]
    names = aligned((pin.pin, pin.expr) for pin in pins)
    for index, ((name, expr), pin) in enumerate(zip(names, pins, strict=True)):
        end = ");" if index == len(pins) - 1 else ","
        lines.extend(with_comment(f"{INDENT}{name} := {expr}{end}", pin.note, width))
    return lines


def assignments(items: Sequence[OutAssign], source: str, width: int = MAX_LINE) -> list[str]:
    """Присваивания выходов экземпляра переменным ``GVL_IO`` (выравнивание по ``:=``)."""
    names = aligned((item.target, f"{source}.{item.pin}") for item in items)
    lines: list[str] = []
    for (target, expr), item in zip(names, items, strict=True):
        lines.extend(with_comment(f"{target} := {expr};", item.note, width))
    return lines
