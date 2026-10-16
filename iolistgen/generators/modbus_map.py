"""Встроенный генератор ``modbus-map``: карта обмена Modbus в CSV и Markdown.

Две части (контракт plc-process-lib, 20.3):

- **master** — сигналы перечня типа MB: ПЛК опрашивает слейвы (ПЧ, приборы). Адрес — адрес PDU с
  нуля, длина — с учётом типа данных, порядок слов, направление, переменная ``GVL_IO``,
  масштабирование;
- **slave** — ПЛК отдаёт SCADA блоки ``stSts`` устройств (раздел 4.6: регистр n блока — байты
  2n…2n+1 структуры, 32-битные поля выровнены по 4 байтам). Блоки идут по возрастанию dev_no:
  плотно (``packed``) или с шагом на номер устройства (``dev_no``). Порядок слов 32-битных
  полей задаёт адаптер обмена приложения — в карте он записан опцией ``slave_word_order``
  (открытый вопрос O5 контракта).

Команды SCADA по Modbus в карту не входят: они идут только через адаптер приложения (2.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from iolistgen.enums import Role
from iolistgen.fbapi import FlatField, flat_fields, struct_size
from iolistgen.generators import csvout
from iolistgen.generators.base import GenerationError, GeneratorContext, GeneratorOption
from iolistgen.generators.plc import GVL_DEVICES, DeviceBinding, PlcModel, build_plc, number_text
from iolistgen.generators.templating import environment
from iolistgen.modbus import ADDRESS_MAX, Access
from iolistgen.model import Device, IoList, Signal
from iolistgen.report.markdown import md_cell

MASTER_COLUMNS = (
    "link",
    "slave",
    "function",
    "function_name",
    "area",
    "address",
    "bit",
    "length",
    "data_type",
    "word_order",
    "direction",
    "tag",
    "description",
    "device",
    "role",
    "plc_variable",
    "eng_min",
    "eng_max",
    "units",
    "raw_min",
    "raw_max",
    "scaling",
)

SLAVE_COLUMNS = (
    "dev_no",
    "device",
    "device_type",
    "function",
    "area",
    "address",
    "offset",
    "length",
    "data_type",
    "word_order",
    "field",
    "description",
    "units",
    "plc_path",
)

_AREAS = {"holding": ("4x", 3, "Read Holding Registers"), "input": ("3x", 4, "Read Input Registers")}


@dataclass(frozen=True)
class SlaveBlock:
    """Блок ``stSts`` устройства в образе Modbus slave."""

    binding: DeviceBinding
    start: int
    registers: int

    @property
    def end(self) -> int:
        return self.start + self.registers - 1


def _scaling(signal: Signal, device: Device | None) -> tuple[str, float | None, float | None]:
    """Пояснение масштабирования и сырой диапазон (только для eInput = Raw)."""
    role = signal.role
    if role is Role.AUX or device is None:
        return "сигнал без ФБ — значение читает и пишет код приложения", None, None
    if role is Role.PV:
        if device.cfg.value("eInput") == "Raw":
            low = float(device.cfg.value("rRawLo_cnt"))
            high = float(device.cfg.value("rRawHi_cnt"))
            text = f"eInput = Raw: {number_text(low)}…{number_text(high)} → шкала прибора"
            return text, low, high
        return "eInput = Eng: значение в инженерных единицах", None, None
    if role in (Role.VFD_STW, Role.VFD_CTW):
        return "биты слова — разбирает и собирает адаптер ПЧ (код приложения)", None, None
    if role in (Role.SPEED_ACT, Role.SPEED_REF):
        return "шкала ↔ 0…100 % — пересчёт в адаптере ПЧ (код приложения)", None, None
    return "", None, None


def master_rows(model: IoList, plc: PlcModel) -> list[dict[str, csvout.CsvValue]]:
    """Строки карты master: сигналы MB по линии, слейву, области и адресу."""
    devices = {device.ident: device for device in model.devices}
    rows: list[dict[str, csvout.CsvValue]] = []
    for var in plc.section("mb_in") + plc.section("mb_out"):
        signal = var.signal
        assert signal is not None and signal.modbus is not None
        address = signal.modbus
        device = devices[signal.device] if signal.device is not None else None
        scaling, raw_min, raw_max = _scaling(signal, device)
        rows.append(
            {
                "link": address.link,
                "slave": address.slave,
                "function": address.function,
                "function_name": address.info.name,
                "area": address.space.prefix,
                "address": address.address,
                "bit": address.bit,
                "length": address.length,
                "data_type": address.data_type.value,
                "word_order": address.word_order.value if address.word_order is not None else None,
                "direction": "чтение" if address.access is Access.READ else "запись",
                "tag": signal.tag,
                "description": signal.description,
                "device": device.ident if device is not None else None,
                "role": signal.role.value,
                "plc_variable": var.path,
                "eng_min": signal.range_min,
                "eng_max": signal.range_max,
                "units": signal.units,
                "raw_min": raw_min,
                "raw_max": raw_max,
                "scaling": scaling,
            }
        )
    rows.sort(key=lambda r: (str(r["link"]), int(r["slave"] or 0), _area_rank(str(r["area"])), int(r["address"] or 0)))
    return rows


def _area_rank(prefix: str) -> int:
    return ("0x", "1x", "3x", "4x").index(prefix)


def slave_blocks(plc: PlcModel, *, base: int, layout: str, stride: int) -> list[SlaveBlock]:
    """Блоки устройств по возрастанию dev_no; ``GenerationError`` — вышли за 65535 или шаг мал."""
    blocks: list[SlaveBlock] = []
    cursor = base
    for binding in plc.by_dev_no():
        registers = struct_size(binding.device.spec.sts) // 2
        if layout == "dev_no":
            if stride < registers:
                raise GenerationError(
                    f"modbus-map: slave_stride = {stride} меньше блока {binding.device.spec.sts} "
                    f"({registers} регистров)"
                )
            start = base + binding.device.dev_no * stride
        else:
            start = cursor
            cursor += registers
        block = SlaveBlock(binding, start, registers)
        if block.end > ADDRESS_MAX:
            raise GenerationError(
                f"modbus-map: блок {binding.device.ident} (dev_no {binding.device.dev_no}) заканчивается на адресе "
                f"{block.end} > {ADDRESS_MAX}; уменьшите slave_base или slave_stride "
                "или выберите slave_layout = packed"
            )
        blocks.append(block)
    return blocks


def _field_word_order(field: FlatField, order: str) -> str | None:
    return order if field.size == 4 else None


def slave_rows(
    blocks: Sequence[SlaveBlock], *, area: str, word_order: str, application: str
) -> list[dict[str, csvout.CsvValue]]:
    prefix, function, _ = _AREAS[area]
    rows: list[dict[str, csvout.CsvValue]] = []
    for block in blocks:
        binding = block.binding
        device = binding.device
        for field in flat_fields(device.spec.sts):
            rows.append(
                {
                    "dev_no": device.dev_no,
                    "device": device.ident,
                    "device_type": device.device_type.value,
                    "function": function,
                    "area": prefix,
                    "address": block.start + field.register,
                    "offset": field.register,
                    "length": field.registers,
                    "data_type": field.field.scalar_type,
                    "word_order": _field_word_order(field, word_order),
                    "field": f"stSts.{field.path}",
                    "description": field.field.description,
                    "units": field.field.units or None,
                    "plc_path": f"{application}.{GVL_DEVICES}.{binding.instance}.stSts.{field.path}",
                }
            )
    return rows


class ModbusMapGenerator:
    """Карта обмена Modbus: master (сигналы MB перечня) и slave (блоки stSts для SCADA)."""

    name = "modbus-map"
    description = "карта обмена Modbus: CSV (master и slave) и Markdown"
    options = (
        GeneratorOption("dir", "каталог файлов относительно --out", "str", "docs"),
        GeneratorOption("master_csv", "файл карты master (сигналы MB перечня)", "str", "modbus_master_map.csv"),
        GeneratorOption("slave_csv", "файл карты slave (блоки stSts для SCADA)", "str", "modbus_slave_map.csv"),
        GeneratorOption("markdown", "файл Markdown с обеими картами", "str", "modbus_map.md"),
        csvout.DELIMITER_OPTION,
        csvout.COMMENT_OPTION,
        GeneratorOption("slave", "карта slave: ПЛК отдаёт SCADA блоки stSts", "bool", True),
        GeneratorOption(
            "slave_area",
            "область slave: holding (4x, FC3) или input (3x, FC4)",
            "choice",
            "holding",
            ("holding", "input"),
        ),
        GeneratorOption("slave_base", "адрес первого блока (PDU, с нуля)", "int", 0),
        GeneratorOption(
            "slave_layout",
            "packed — блоки подряд по dev_no; dev_no — адрес = slave_base + dev_no · slave_stride",
            "choice",
            "packed",
            ("packed", "dev_no"),
        ),
        GeneratorOption("slave_stride", "шаг блоков при slave_layout = dev_no, регистров", "int", 40),
        GeneratorOption(
            "slave_word_order",
            "порядок слов 32-битных полей в образе slave (LH — копия памяти на ПЛК с прямым порядком байт)",
            "choice",
            "LH",
            ("LH", "HL"),
        ),
        GeneratorOption("application", "имя приложения CODESYS в путях переменных", "str", "Application"),
        GeneratorOption("template_dir", "каталог своих шаблонов Jinja2 (перекрывают шаблоны пакета)", "str", ""),
    )

    def generate(self, model: IoList, out_dir: Path, ctx: GeneratorContext) -> list[Path]:
        plc = build_plc(model)
        directory = PurePosixPath(ctx.str_option("dir").strip().strip("/") or ".")
        master = master_rows(model, plc)
        written = [
            ctx.write_text(
                str(directory / ctx.str_option("master_csv")),
                csvout.render_csv(
                    ctx,
                    MASTER_COLUMNS,
                    master,
                    notes=["Карта Modbus, ПЛК — master: адрес — адрес PDU с нуля, length — регистров или катушек"],
                ),
            )
        ]
        blocks: list[SlaveBlock] = []
        slave: list[dict[str, csvout.CsvValue]] = []
        area = ctx.str_option("slave_area")
        if ctx.bool_option("slave"):
            blocks = slave_blocks(
                plc,
                base=ctx.int_option("slave_base"),
                layout=ctx.str_option("slave_layout"),
                stride=ctx.int_option("slave_stride"),
            )
            slave = slave_rows(
                blocks,
                area=area,
                word_order=ctx.str_option("slave_word_order"),
                application=ctx.str_option("application"),
            )
            written.append(
                ctx.write_text(
                    str(directory / ctx.str_option("slave_csv")),
                    csvout.render_csv(
                        ctx,
                        SLAVE_COLUMNS,
                        slave,
                        notes=[
                            "Карта Modbus, ПЛК — slave для SCADA: блок устройства — stSts целиком "
                            "(контракт plc-process-lib 4.6); адрес — PDU с нуля"
                        ],
                    ),
                )
            )
        text = self.render_markdown(model, ctx, master, blocks, area)
        written.append(ctx.write_text(str(directory / ctx.str_option("markdown")), text))
        return written

    def render_markdown(
        self,
        model: IoList,
        ctx: GeneratorContext,
        master: Sequence[dict[str, csvout.CsvValue]],
        blocks: Sequence[SlaveBlock],
        area: str,
    ) -> str:
        env = environment(ctx.str_option("template_dir"))
        prefix, function, function_name = _AREAS[area]
        layouts = []
        seen: set[str] = set()
        for block in blocks:
            sts = block.binding.device.spec.sts
            if sts in seen:
                continue
            seen.add(sts)
            types = sorted({b.binding.device.device_type.value for b in blocks if b.binding.device.spec.sts == sts})
            layouts.append(
                {
                    "sts": sts,
                    "types": ", ".join(types),
                    "registers": struct_size(sts) // 2,
                    "fields": [
                        {
                            "offset": field.register,
                            "length": field.registers,
                            "type": field.field.scalar_type,
                            "path": field.path,
                            "description": md_cell(field.field.description),
                            "units": md_cell(field.field.units),
                        }
                        for field in flat_fields(sts)
                    ],
                }
            )
        return env.get_template("modbus_map.md.j2").render(
            header=ctx.comment_header("markdown").rstrip("\n"),
            source=model.source.name,
            master=[{key: md_cell(csvout.cell(value)) for key, value in row.items()} for row in master],
            blocks=[
                {
                    "dev_no": block.binding.device.dev_no,
                    "device": block.binding.device.ident,
                    "type": block.binding.device.device_type.value,
                    "description": md_cell(block.binding.device.description),
                    "start": block.start,
                    "end": block.end,
                    "registers": block.registers,
                    "sts": block.binding.device.spec.sts,
                }
                for block in blocks
            ],
            layouts=layouts,
            slave=ctx.bool_option("slave"),
            area=prefix,
            function=function,
            function_name=function_name,
            word_order=ctx.str_option("slave_word_order"),
            layout=ctx.str_option("slave_layout"),
            base=ctx.int_option("slave_base"),
            stride=ctx.int_option("slave_stride"),
        )
