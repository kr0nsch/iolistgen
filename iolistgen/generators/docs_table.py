"""Встроенный генератор ``docs-table``: таблица «Перечень сигналов» для ``docs/`` в Markdown.

Образец генератора для плагинов: опции, заголовок AUTO-GENERATED, идемпотентная запись через
``ctx.write_text()``. Колонка «Переменная ПЛК» берётся из той же модели имён, что и ST
(``generators.plc``): имя в документе всегда совпадает с объявлением в ``GVL_IO``.
"""

from __future__ import annotations

from pathlib import Path

from iolistgen.catalog import LIBRARY_NAMESPACE
from iolistgen.generators.base import GeneratorContext, GeneratorOption
from iolistgen.generators.plc import PlcModel, build_plc
from iolistgen.model import Device, IoList, Signal
from iolistgen.report.markdown import md_cell
from iolistgen.stvalues import format_real, format_seconds


def _number(value: float) -> str:
    text = format_real(value)
    return text[:-2] if text.endswith(".0") else text


def signal_range(signal: Signal) -> str:
    if signal.range_min is None or signal.range_max is None:
        return ""
    return f"{_number(signal.range_min)}…{_number(signal.range_max)}"


def signal_address(signal: Signal) -> str:
    """Канал модуля или адрес Modbus одной строкой."""
    if signal.modbus is not None:
        address = signal.modbus
        place = f"{address.space.prefix} {address.address}"
        if address.bit is not None:
            place += f".{address.bit}"
        parts = [f"FC{address.function}", place, address.data_type.value]
        if address.word_order is not None:
            parts.append(address.word_order.value)
        parts.append(f"слейв {address.slave}")
        if address.link:
            parts.append(address.link)
        return " · ".join(parts)
    if signal.io_module is not None and signal.io_channel is not None:
        return f"{signal.io_module}.{signal.io_channel}"
    return ""


def device_summary(device: Device) -> str:
    """Строка под заголовком устройства: тип, номер, уставки, задержки."""
    parts = [f"{device.device_type.value}, № {device.dev_no}, `{LIBRARY_NAMESPACE}.{device.spec.fb}`"]
    if not device.spec.has_io:
        parts.append("сигналов ввода-вывода нет: вызов ФБ — в логике станции")
        if device.range_min is not None and device.range_max is not None:
            units = f" {device.units}" if device.units else ""
            parts.append(f"диапазон PV {_number(device.range_min)}…{_number(device.range_max)}{units}")
    defined = device.setpoints.defined()
    if defined:
        units = device.units or ""
        values = " · ".join(f"{name} {_number(value)}" for name, value in defined)
        parts.append(f"уставки: {values}{(' ' + units) if units else ''}")
    if device.delay_on_ms is not None:
        parts.append(f"задержка вкл. {format_seconds(device.delay_on_ms)} с")
    if device.delay_off_ms is not None:
        parts.append(f"задержка откл. {format_seconds(device.delay_off_ms)} с")
    if device.alarm_priority is not None:
        parts.append(f"приоритет тревог {device.alarm_priority.value}")
    return "; ".join(parts) + "."


class DocsTableGenerator:
    """Перечень сигналов в Markdown: сводка устройств и таблицы сигналов."""

    name = "docs-table"
    description = "таблица «Перечень сигналов» для docs/ (Markdown)"
    options = (
        GeneratorOption("filename", "имя файла относительно --out", "str", "docs/signal_list.md"),
        GeneratorOption("title", "заголовок документа", "str", "Перечень сигналов"),
        GeneratorOption("group_by_device", "таблица сигналов по разделам устройств", "bool", True),
        GeneratorOption("plc_variables", "колонка «Переменная ПЛК» (GVL_IO)", "bool", True),
    )

    def generate(self, model: IoList, out_dir: Path, ctx: GeneratorContext) -> list[Path]:
        text = self.render(model, ctx)
        return [ctx.write_text(ctx.str_option("filename"), text)]

    def render(self, model: IoList, ctx: GeneratorContext) -> str:
        plc = build_plc(model) if ctx.bool_option("plc_variables") else None
        lines: list[str] = [ctx.comment_header("markdown").rstrip("\n"), f"# {ctx.str_option('title')}", ""]
        lines += [
            f"Сигналов: {len(model.signals)}, устройств: {len(model.devices)}. "
            "Адреса Modbus — адреса PDU с нуля: функция, пространство (4x — регистры хранения, "
            "3x — входные, 1x — дискретные входы, 0x — катушки), тип данных и слейв.",
            "",
            "## Устройства",
            "",
            "| № | Устройство | Тип | ФБ | Описание | Сигналов | Группа HMI |",
            "|---:|---|---|---|---|---:|---|",
        ]
        for device in model.devices_by_dev_no():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(device.dev_no),
                        f"`{device.ident}`",
                        device.device_type.value,
                        f"`{LIBRARY_NAMESPACE}.{device.spec.fb}`",
                        md_cell(device.description),
                        str(len(device.signals)),
                        md_cell(device.hmi_group or ""),
                    ]
                )
                + " |"
            )
        lines += ["", "## Сигналы", ""]
        if ctx.bool_option("group_by_device"):
            for device in model.devices_by_dev_no():
                lines += [f"### `{device.ident}` — {md_cell(device.description)}", "", device_summary(device), ""]
                if device.signals:
                    lines += self._table(device.signals, with_device=False, plc=plc)
                    lines.append("")
            plain = model.plain_signals()
            if plain:
                lines += [
                    "## Сигналы без ФБ",
                    "",
                    "Роль AUX без устройства: лампы, сирены, реле и регистры, которые читает и пишет код "
                    "приложения. Экземпляра ФБ, команд, Cfg и тревог у них нет.",
                    "",
                ]
                lines += self._table(plain, with_device=False, plc=plc)
                lines.append("")
        else:
            lines += self._table(model.signals, with_device=True, plc=plc)
            lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n"

    @staticmethod
    def _table(signals: tuple[Signal, ...], *, with_device: bool, plc: PlcModel | None) -> list[str]:
        head = ["Тег", "Описание", "Сигнал", "Роль", "Шкала", "Ед.", "Канал / адрес Modbus", "Группа HMI"]
        if with_device:
            head.insert(2, "Устройство")
        if plc is not None:
            head.append("Переменная ПЛК")
        lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for signal in signals:
            cells = [
                f"`{signal.tag}`",
                md_cell(signal.description),
                signal.signal_type.value,
                signal.role.value,
                signal_range(signal),
                md_cell(signal.units or ""),
                md_cell(signal_address(signal)),
                md_cell(signal.hmi_group or ""),
            ]
            if with_device:
                cells.insert(2, f"`{signal.device}`" if signal.device is not None else "—")
            if plc is not None:
                cells.append(f"`{plc.signal_var(signal).path}`")
            lines.append("| " + " | ".join(cells) + " |")
        return lines
