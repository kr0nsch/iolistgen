"""Имена и привязки ПЛК: переменные ``GVL_IO``, экземпляры ФБ, Cmd/Cfg/Retain, параметры вызовов.

Одна модель на все генераторы: ST (``st-codesys``), карту Modbus, импорт SCADA и таблицу
документации. Поэтому имя переменной сигнала в карте обмена и в перечне для ``docs/`` всегда
совпадает с объявлением в ``GVL_IO``.

Правила (контракт plc-process-lib, разделы 1, 20.1–20.6):

- переменная сигнала — префикс типа и идентификатор тега: ``xLS101``, ``rLT101_mA`` (AI 4–20 мА),
  ``iP101_ACT`` (Modbus INT), ``wP101_STW`` (слово состояния ПЧ);
- каналы модулей — обычные переменные без ``AT %I…``: их привязывают в дереве устройств
  (I/O Mapping → «Map to existing variable»), адреса каналов в коде не появляются;
- значения Modbus (ПЛК — master) — переменные, которые пишет и читает слой Modbus
  (конфигуратор Modbus или код приложения); его состояние по слейвам — ``xMbOk_<линия>_S<слейв>``;
- ПЧ: адаптер приложения (``FB_VfdAdapter_<Model>``) разбирает слово состояния и пишет
  ``x<DEV>_CommOk``, ``x<DEV>_VfdRun``, ``x<DEV>_VfdReady``, ``x<DEV>_VfdFault``,
  ``r<DEV>_SpeedAct_pct``; читает ``r<DEV>_SpeedRef_pct`` (и ``x<DEV>_VfdQRun``,
  ``x<DEV>_VfdQReset`` при пуске по Modbus);
- экземпляр ``GVL_Devices.fb<DEV>``, команды ``GVL_Hmi.st<DEV>Cmd``, конфигурация
  ``GVL_Persist.st<DEV>Cfg``, энергонезависимые данные ``GVL_Persist.st<DEV>Retain``;
- сигнал ``AUX`` (без входа и выхода ФБ) — только переменная ``GVL_IO``: её читает и пишет код
  приложения; в вызове устройства она упомянута комментарием.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from iolistgen.catalog import LIBRARY_NAMESPACE
from iolistgen.enums import DeviceType, Direction, Role, SignalType
from iolistgen.fbapi import fb_inputs
from iolistgen.generators.base import GenerationError
from iolistgen.identifiers import to_identifier
from iolistgen.modbus import Access, ModbusSpace, ModbusType
from iolistgen.model import Device, IoList, Signal
from iolistgen.stvalues import format_real

GVL_IO = "GVL_IO"
GVL_DEVICES = "GVL_Devices"
GVL_HMI = "GVL_Hmi"
GVL_PERSIST = "GVL_Persist"
GVL_CFG_PROJECT = "GVL_CfgProject"
GVL_DEV_IDX = "GVL_DevIdx"
PRG_DEVICES = "PRG_Devices"
PRG_APPLY_CFG = "PRG_ApplyProjectCfg"
APPLY_CFG_CMD = "xApplyProjectCfg"
LAYOUT_VERSION_VAR = "uiLayoutVersion"

IoSection = Literal["hw_in", "hw_out", "mb_in", "mb_out", "mb_status", "vfd_in", "vfd_out"]

SECTION_ORDER: tuple[IoSection, ...] = ("hw_in", "hw_out", "mb_in", "mb_out", "mb_status", "vfd_in", "vfd_out")
SECTION_TITLES: dict[IoSection, str] = {
    "hw_in": "Входы модулей ввода-вывода (DI, AI): дерево устройств, I/O Mapping → Map to existing variable",
    "hw_out": "Выходы модулей ввода-вывода (DO, AO): дерево устройств, I/O Mapping → Map to existing variable",
    "mb_in": "Modbus, ПЛК — master, чтение: значения пишет слой Modbus",
    "mb_out": "Modbus, ПЛК — master, запись: значения читает слой Modbus",
    "mb_status": "Состояние обмена со слейвами: пишет слой Modbus (TRUE — обмен исправен)",
    "vfd_in": "Адаптеры ПЧ (код приложения) → ФБ: разобранное слово состояния и фактическая скорость",
    "vfd_out": "ФБ → адаптеры ПЧ: задание скорости и команды для слова управления",
}

_MB_PREFIX: dict[ModbusType, str] = {
    ModbusType.BOOL: "x",
    ModbusType.INT: "i",
    ModbusType.UINT: "ui",
    ModbusType.WORD: "w",
    ModbusType.DINT: "di",
    ModbusType.UDINT: "udi",
    ModbusType.DWORD: "dw",
    ModbusType.REAL: "r",
    ModbusType.LINT: "li",
    ModbusType.ULINT: "uli",
    ModbusType.LWORD: "lw",
    ModbusType.LREAL: "lr",
}

_SPACE_ORDER = {
    ModbusSpace.COILS: 0,
    ModbusSpace.DISCRETE_INPUTS: 1,
    ModbusSpace.INPUT_REGISTERS: 2,
    ModbusSpace.HOLDING_REGISTERS: 3,
}

# Слова, которые нельзя брать именем константы GVL_DevIdx: операторы IL (контракт 2.7, L8) и
# ключевые слова ST. Имена устройств по правилу по умолчанию содержат цифры и с ними не совпадают.
RESERVED_WORDS = frozenset(
    [
        "ABS",
        "ADD",
        "AND",
        "ANDN",
        "ARRAY",
        "AT",
        "BOOL",
        "BY",
        "BYTE",
        "CAL",
        "CALC",
        "CALCN",
        "CASE",
        "CONSTANT",
        "DATE",
        "DINT",
        "DIV",
        "DO",
        "DT",
        "DWORD",
        "ELSE",
        "ELSIF",
        "END_CASE",
        "END_FOR",
        "END_IF",
        "END_REPEAT",
        "END_VAR",
        "END_WHILE",
        "EQ",
        "EXIT",
        "FALSE",
        "FOR",
        "FUNCTION",
        "GE",
        "GT",
        "IF",
        "INT",
        "JMP",
        "JMPC",
        "JMPCN",
        "LD",
        "LDN",
        "LE",
        "LINT",
        "LREAL",
        "LT",
        "LTIME",
        "LWORD",
        "MOD",
        "MUL",
        "NE",
        "NOT",
        "OF",
        "OR",
        "ORN",
        "R",
        "REAL",
        "REPEAT",
        "RET",
        "RETC",
        "RETCN",
        "RETURN",
        "S",
        "SINT",
        "ST",
        "STN",
        "STRING",
        "STRUCT",
        "SUB",
        "THEN",
        "TIME",
        "TO",
        "TOD",
        "TRUE",
        "TYPE",
        "UDINT",
        "UINT",
        "ULINT",
        "UNTIL",
        "USINT",
        "VAR",
        "WHILE",
        "WORD",
        "WSTRING",
        "XOR",
        "XORN",
    ]
)


@dataclass(frozen=True)
class IoVar:
    """Переменная ``GVL_IO``: имя, тип, раздел, комментарий привязки и откуда она взялась."""

    name: str
    st_type: str
    section: IoSection
    comment: str
    signal: Signal | None = None
    device: Device | None = None

    @property
    def path(self) -> str:
        return f"{GVL_IO}.{self.name}"


@dataclass(frozen=True)
class Pin:
    """Параметр вызова экземпляра: вход ФБ, выражение и пояснение."""

    pin: str
    expr: str
    note: str = ""


@dataclass(frozen=True)
class OutAssign:
    """Присваивание после вызова: переменная ``GVL_IO`` ← выход ФБ."""

    target: str
    pin: str
    note: str = ""


@dataclass(frozen=True)
class DeviceBinding:
    """Экземпляр устройства: имена в GVL и параметры вызова."""

    device: Device
    namespace: str
    instance: str
    cmd: str
    cfg: str
    retain: str | None
    inputs: tuple[Pin, ...]
    outputs: tuple[OutAssign, ...]
    notes: tuple[str, ...] = ()
    called: bool = True
    """Вызов в ``PRG_Devices``; ``False`` — устройство без сигналов (Pid): его вызывает логика станции."""

    @property
    def fb_type(self) -> str:
        return _qualified(self.namespace, self.device.spec.fb)

    @property
    def cmd_type(self) -> str:
        return _qualified(self.namespace, self.device.spec.cmd)

    @property
    def cfg_type(self) -> str:
        return _qualified(self.namespace, self.device.spec.cfg)

    @property
    def retain_type(self) -> str:
        return _qualified(self.namespace, "ST_DeviceRetain")

    @property
    def instance_path(self) -> str:
        return f"{GVL_DEVICES}.{self.instance}"

    @property
    def cmd_path(self) -> str:
        return f"{GVL_HMI}.{self.cmd}"

    @property
    def cfg_path(self) -> str:
        return f"{GVL_PERSIST}.{self.cfg}"

    @property
    def retain_path(self) -> str | None:
        return f"{GVL_PERSIST}.{self.retain}" if self.retain else None

    @property
    def index_constant(self) -> str:
        """Имя константы ``GVL_DevIdx``: идентификатор устройства в верхнем регистре."""
        return self.device.ident.upper()


@dataclass(frozen=True)
class PlcModel:
    """Все имена ПЛК перечня."""

    namespace: str
    io_vars: tuple[IoVar, ...]
    devices: tuple[DeviceBinding, ...]
    """Порядок вызова: сначала устройства, на которые ссылаются ``link_*``, затем остальные."""

    def by_dev_no(self) -> tuple[DeviceBinding, ...]:
        """Устройства по возрастанию ``dev_no`` (порядок ``GVL_Persist``, контракт 18.3)."""
        return tuple(sorted(self.devices, key=lambda b: b.device.dev_no))

    def binding(self, device: Device) -> DeviceBinding:
        for item in self.devices:
            if item.device.ident == device.ident:
                return item
        raise KeyError(device.ident)

    def signal_var(self, signal: Signal) -> IoVar:
        """Переменная ``GVL_IO`` сигнала перечня."""
        for var in self.io_vars:
            if var.signal is not None and var.signal.tag == signal.tag:
                return var
        raise KeyError(signal.tag)

    def section(self, section: IoSection) -> tuple[IoVar, ...]:
        return tuple(var for var in self.io_vars if var.section == section)


def _qualified(namespace: str, name: str) -> str:
    return f"{namespace}.{name}" if namespace else name


def _natural_key(text: str) -> tuple[tuple[int, int | str], ...]:
    """«A10» после «A2»: числа сравниваются как числа."""
    parts = re.split(r"(\d+)", text)
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts if part)


def number_text(value: float) -> str:
    """Число для комментариев и таблиц: ``5`` вместо ``5.0``."""
    text = format_real(value)
    return text[:-2] if text.endswith(".0") else text


def scale_text(signal: Signal) -> str:
    """«0…5 м» — шкала и единицы сигнала."""
    if signal.range_min is None or signal.range_max is None:
        return ""
    text = f"{number_text(signal.range_min)}…{number_text(signal.range_max)}"
    return f"{text} {signal.units}" if signal.units else text


def modbus_place(signal: Signal) -> str:
    """«RS485-1 · слейв 1 · FC3 4x 3 WORD» — адрес Modbus одной строкой."""
    address = signal.modbus
    assert address is not None
    place = f"{address.space.prefix} {address.address}"
    if address.bit is not None:
        place += f".{address.bit}"
    text = f"FC{address.function} {place} {address.data_type.value}"
    if address.word_order is not None:
        text += f" {address.word_order.value}"
    head = f"{address.link} · " if address.link else ""
    return f"{head}слейв {address.slave} · {text}"


def channel_place(signal: Signal) -> str:
    """«A1.1» — модуль и канал, или «канал не назначен»."""
    if signal.io_module is not None and signal.io_channel is not None:
        return f"{signal.io_module}.{signal.io_channel}"
    if signal.io_module is not None:
        return f"{signal.io_module}, канал не назначен"
    return "канал не назначен"


def _ai_suffix(signal: Signal, device: Device | None) -> str:
    """Суффикс единиц сырого аналогового канала: ``_mA`` только там, где значение — ток."""
    if signal.signal_type is SignalType.AO and signal.role is Role.POS_OUT:
        return "_mA"
    if (
        device is not None
        and signal.signal_type is SignalType.AI
        and signal.role is Role.PV
        and device.cfg.value("eInput") == "MilliAmp"
    ):
        return "_mA"
    return ""


def signal_variable(signal: Signal, device: Device | None) -> tuple[str, str]:
    """Имя и тип переменной ``GVL_IO`` сигнала."""
    if signal.modbus is not None:
        data_type = signal.modbus.data_type
        return f"{_MB_PREFIX[data_type]}{signal.ident}", data_type.value
    if signal.signal_type in (SignalType.DI, SignalType.DO):
        return f"x{signal.ident}", "BOOL"
    return f"r{signal.ident}{_ai_suffix(signal, device)}", "REAL"


def _signal_comment(signal: Signal) -> str:
    place = modbus_place(signal) if signal.modbus is not None else channel_place(signal)
    parts = [place, signal.tag, signal.description]
    scale = scale_text(signal)
    if scale:
        parts.append(scale)
    if signal.is_aux:
        parts.append("без ФБ — код приложения")
    elif signal.role in _ADAPTER_ROLES:
        parts.append("адаптер ПЧ")
    return " · ".join(parts)


def _section_of(signal: Signal) -> IoSection:
    if signal.modbus is not None:
        return "mb_in" if signal.modbus.access is Access.READ else "mb_out"
    if signal.signal_type in (SignalType.DI, SignalType.AI):
        return "hw_in"
    return "hw_out"


def _hw_key(var: IoVar, position: int) -> tuple[int, tuple[tuple[int, int | str], ...], int, int]:
    signal = var.signal
    assert signal is not None
    if signal.io_module is None or signal.io_channel is None:
        return (1, (), 0, position)
    return (0, _natural_key(signal.io_module), signal.io_channel, position)


def _mb_key(var: IoVar, position: int) -> tuple[str, int, int, int, int, int]:
    signal = var.signal
    assert signal is not None and signal.modbus is not None
    address = signal.modbus
    bit = address.bit if address.bit is not None else -1
    return (address.link, address.slave, _SPACE_ORDER[address.space], address.address, bit, position)


@dataclass(frozen=True)
class _Slave:
    link: str
    slave: int


# Сигналы ПЧ, которые разбирает и собирает адаптер приложения (не входы и выходы ФБ напрямую)
_ADAPTER_ROLES = frozenset({Role.VFD_STW, Role.VFD_CTW, Role.SPEED_ACT, Role.SPEED_REF})


class _Builder:
    def __init__(self, model: IoList, namespace: str, time_source: str) -> None:
        self.model = model
        self.namespace = namespace
        self.time_source = time_source.strip()
        self.vars: list[IoVar] = []
        self.signal_vars: dict[str, IoVar] = {}
        self.slave_vars: dict[_Slave, IoVar] = {}
        self.link_names = self._link_names()

    # --- переменные GVL_IO -----------------------------------------------------------------------

    def _link_names(self) -> dict[str, str]:
        """Линия Modbus → часть идентификатора (``RS485-1`` → ``RS485_1``; не ASCII — ``L1``, ``L2``)."""
        links = sorted({s.modbus.link for s in self.model.signals if s.modbus is not None and s.modbus.link})
        names: dict[str, str] = {}
        for number, link in enumerate(links, 1):
            ident = to_identifier(link)
            valid = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*", ident))
            names[link] = ident if valid else f"L{number}"
        return names

    def slave_var(self, link: str, slave: int) -> IoVar:
        key = _Slave(link, slave)
        found = self.slave_vars.get(key)
        if found is not None:
            return found
        link_part = f"{self.link_names[link]}_" if link else ""
        where = f"линия {link}, " if link else ""
        var = IoVar(
            name=f"xMbOk_{link_part}S{slave}",
            st_type="BOOL",
            section="mb_status",
            comment=f"{where}слейв {slave}: обмен исправен",
        )
        self.slave_vars[key] = var
        return var

    def collect_vars(self) -> None:
        hw_in: list[tuple[object, IoVar]] = []
        hw_out: list[tuple[object, IoVar]] = []
        mb_in: list[tuple[object, IoVar]] = []
        mb_out: list[tuple[object, IoVar]] = []
        devices = {device.ident: device for device in self.model.devices}
        for position, signal in enumerate(self.model.signals):
            device = devices[signal.device] if signal.device is not None else None
            name, st_type = signal_variable(signal, device)
            section = _section_of(signal)
            var = IoVar(name, st_type, section, _signal_comment(signal), signal, device)
            self.signal_vars[signal.tag] = var
            if section in ("hw_in", "hw_out"):
                (hw_in if section == "hw_in" else hw_out).append((_hw_key(var, position), var))
            else:
                (mb_in if section == "mb_in" else mb_out).append((_mb_key(var, position), var))
        for group in (hw_in, hw_out, mb_in, mb_out):
            group.sort(key=lambda item: item[0])  # type: ignore[arg-type,return-value]
            self.vars.extend(var for _, var in group)
        for signal in self.model.signals:
            if signal.modbus is not None:
                self.slave_var(signal.modbus.link, signal.modbus.slave)
        self.vars.extend(var for _, var in sorted(self.slave_vars.items(), key=lambda kv: (kv[0].link, kv[0].slave)))
        adapter = [
            var
            for device in self.model.devices_by_dev_no()
            if device.device_type is DeviceType.MOTOR_VFD
            for var in self._vfd_vars(device)
        ]
        self.vars.extend(var for var in adapter if var.section == "vfd_in")
        self.vars.extend(var for var in adapter if var.section == "vfd_out")

    def _vfd_vars(self, device: Device) -> list[IoVar]:
        d = device.ident
        tag = device.name
        inputs = [
            ("CommOk", "BOOL", "обмен с ПЧ исправен → xCommOk"),
            ("VfdRun", "BOOL", "ПЧ в работе (слово состояния) → xVfdRunning"),
            ("VfdReady", "BOOL", "ПЧ готов к пуску (слово состояния) → xVfdReady"),
            ("VfdFault", "BOOL", "авария ПЧ (слово состояния) → xVfdFault"),
            ("SpeedAct_pct", "REAL", "фактическая скорость, % → rSpeedAct_pct"),
        ]
        result = [
            IoVar(f"{_prefix(st_type)}{d}_{suffix}", st_type, "vfd_in", f"{tag}: {text}", device=device)
            for suffix, st_type, text in inputs
        ]
        outputs = [("SpeedRef_pct", "REAL", "задание на ПЧ, % ← rSpeedRef_pct")]
        if device.signal(Role.VFD_CTW) is not None:
            outputs += [
                ("VfdQRun", "BOOL", "команда «работа» для слова управления ← xQRun"),
                ("VfdQReset", "BOOL", "импульс сброса аварии ПЧ для слова управления ← xQReset"),
            ]
        result += [
            IoVar(f"{_prefix(st_type)}{d}_{suffix}", st_type, "vfd_out", f"{tag}: {text}", device=device)
            for suffix, st_type, text in outputs
        ]
        return result

    def check_unique(self) -> None:
        seen: dict[str, IoVar] = {}
        for var in self.vars:
            key = var.name.casefold()
            if key in seen:
                first = seen[key]
                raise GenerationError(
                    f"{GVL_IO}: имена «{first.name}» ({_origin(first)}) и «{var.name}» ({_origin(var)}) "
                    "совпадают без учёта регистра — CODESYS их не различает; переименуйте тег"
                )
            seen[key] = var

    # --- устройства -------------------------------------------------------------------------------

    def call_order(self) -> list[Device]:
        targets = {d.link_power for d in self.model.devices if d.link_power} | {
            d.link_fb for d in self.model.devices if d.link_fb
        }
        ordered = self.model.devices_by_dev_no()
        first = [d for d in ordered if d.ident in targets]
        rest = [d for d in ordered if d.ident not in targets]
        return first + rest

    def binding(self, device: Device) -> DeviceBinding:
        d = device.ident
        pins: dict[str, Pin] = {}
        outputs: list[OutAssign] = []
        notes: list[str] = []
        aux_notes: list[str] = []
        for signal in device.signals:
            var = self.signal_vars[signal.tag]
            if signal.is_aux:
                aux_notes.append(f"без входа ФБ (AUX, код приложения): {var.path} — {signal.description}")
                continue
            role_spec = device.spec.role(signal.role)
            assert role_spec is not None
            if signal.role in _ADAPTER_ROLES:
                continue  # через адаптер ПЧ
            if role_spec.direction is Direction.IN:
                pins[role_spec.pin] = Pin(role_spec.pin, self._input_expr(var, role_spec.pin))
            else:
                outputs.append(OutAssign(var.path, role_spec.pin))
        if device.device_type in (DeviceType.ANALOG_INPUT, DeviceType.DIGITAL_INPUT):
            if "xChannelFault" not in pins:
                pins["xChannelFault"] = self._channel_fault_fallback(device)
            elif device.main.modbus is not None:
                # значение по Modbus: при потере связи и оно, и бит CHF замирают — обмен тоже отказ канала
                status = self.slave_var(device.main.modbus.link, device.main.modbus.slave)
                expr = f"{pins['xChannelFault'].expr} OR NOT {status.path}"
                pins["xChannelFault"] = Pin("xChannelFault", expr, "CHF или нет обмена со слейвом")
        if device.link_power:
            pins["xPowerOk"] = Pin("xPowerOk", f"{GVL_DEVICES}.fb{device.link_power}.xValue", "link_power")
        if device.link_fb:
            target = f"{GVL_DEVICES}.fb{device.link_fb}"
            pins["rPosFb_pct"] = Pin("rPosFb_pct", f"{target}.rValue_pct", "link_fb")
            pins["xPosFbValid"] = Pin("xPosFbValid", f"{target}.xValid", "link_fb")
        if device.device_type is DeviceType.MOTOR_VFD:
            adapter = {
                "xCommOk": f"x{d}_CommOk",
                "xVfdRunning": f"x{d}_VfdRun",
                "xVfdReady": f"x{d}_VfdReady",
                "xVfdFault": f"x{d}_VfdFault",
                "rSpeedAct_pct": f"r{d}_SpeedAct_pct",
            }
            for pin, name in adapter.items():
                pins[pin] = Pin(pin, f"{GVL_IO}.{name}")
            outputs.append(OutAssign(f"{GVL_IO}.r{d}_SpeedRef_pct", "rSpeedRef_pct"))
            if device.signal(Role.VFD_CTW) is not None:
                outputs.append(OutAssign(f"{GVL_IO}.x{d}_VfdQRun", "xQRun"))
                outputs.append(OutAssign(f"{GVL_IO}.x{d}_VfdQReset", "xQReset"))
            notes.append(
                f"ПЧ: xCommOk, xVfd*, rSpeedAct_pct и rSpeedRef_pct — через адаптер приложения ({GVL_IO}.x{d}_…)"
            )
        if not device.spec.has_io:
            return self._station_binding(device, aux_notes)
        notes += aux_notes
        ordered = [pins[spec.name] for spec in fb_inputs(device.device_type) if spec.name in pins]
        unknown = sorted(set(pins) - {spec.name for spec in fb_inputs(device.device_type)})
        if unknown:  # каталог ролей и интерфейс ФБ разошлись — ошибка пакета, а не перечня
            raise GenerationError(f"{device.name}: входов {', '.join(unknown)} нет у {device.spec.fb}")
        if self.time_source:
            ordered.append(Pin("itfTime", self.time_source, "источник времени"))
        instance = f"fb{d}"
        retain = f"st{d}Retain" if device.spec.has_retain else None
        in_out = [
            Pin("stCmd", f"{GVL_HMI}.st{d}Cmd"),
            Pin("stCfg", f"{GVL_PERSIST}.st{d}Cfg"),
        ]
        if retain is not None:
            in_out.append(Pin("stRetain", f"{GVL_PERSIST}.{retain}"))
        outputs.sort(key=lambda item: _output_rank(item.pin))
        return DeviceBinding(
            device=device,
            namespace=self.namespace,
            instance=instance,
            cmd=f"st{d}Cmd",
            cfg=f"st{d}Cfg",
            retain=retain,
            inputs=tuple(ordered + in_out),
            outputs=tuple(outputs),
            notes=tuple(notes),
        )

    def _station_binding(self, device: Device, aux_notes: list[str]) -> DeviceBinding:
        """Устройство без сигналов (Pid): имена есть, вызова в PRG_Devices нет — его пишет логика станции."""
        d = device.ident
        retain = f"st{d}Retain" if device.spec.has_retain else None
        in_out = [Pin("stCmd", f"{GVL_HMI}.st{d}Cmd"), Pin("stCfg", f"{GVL_PERSIST}.st{d}Cfg")]
        if retain is not None:
            in_out.append(Pin("stRetain", f"{GVL_PERSIST}.{retain}"))
        if self.time_source:
            in_out.append(Pin("itfTime", self.time_source, "источник времени"))
        notes = [
            f"вызов {device.spec.fb} пишет логика станции до {PRG_DEVICES} (контракт plc-process-lib 17.3): "
            "входы rPv_eu, xPvValid, xTrack, rOutAct_pct и параметры ниже",
            *aux_notes,
        ]
        return DeviceBinding(
            device=device,
            namespace=self.namespace,
            instance=f"fb{d}",
            cmd=f"st{d}Cmd",
            cfg=f"st{d}Cfg",
            retain=retain,
            inputs=tuple(in_out),
            outputs=(),
            notes=tuple(notes),
            called=False,
        )

    def _input_expr(self, var: IoVar, pin: str) -> str:
        signal = var.signal
        assert signal is not None
        if pin == "rIn" and signal.modbus is not None and signal.modbus.data_type is not ModbusType.REAL:
            return f"{signal.modbus.data_type.value}_TO_REAL({var.path})"
        return var.path

    def _channel_fault_fallback(self, device: Device) -> Pin:
        main = device.main
        if main.modbus is not None:
            status = self.slave_var(main.modbus.link, main.modbus.slave)
            return Pin("xChannelFault", f"NOT {status.path}", "нет строки CHF: обмен со слейвом")
        return Pin("xChannelFault", "FALSE", "нет строки CHF")

    def check_constants(self, bindings: Sequence[DeviceBinding]) -> None:
        for binding in bindings:
            if binding.index_constant in RESERVED_WORDS:
                raise GenerationError(
                    f"{GVL_DEV_IDX}: имя устройства {binding.device.name} совпадает с ключевым словом "
                    f"или оператором IL ({binding.index_constant}); переименуйте устройство"
                )


def _prefix(st_type: str) -> str:
    return "x" if st_type == "BOOL" else "r"


def _origin(var: IoVar) -> str:
    if var.signal is not None:
        return f"сигнал {var.signal.tag}, строка {var.signal.source.row}"
    if var.device is not None:
        return f"адаптер ПЧ {var.device.name}"
    return "состояние обмена Modbus"


_OUTPUT_ORDER = ("xQRun", "xQReset", "xQOpen", "xQClose", "xQCoil", "rOut_mA", "rSpeedRef_pct")


def _output_rank(pin: str) -> int:
    return _OUTPUT_ORDER.index(pin) if pin in _OUTPUT_ORDER else len(_OUTPUT_ORDER)


def build_plc(model: IoList, *, namespace: str = LIBRARY_NAMESPACE, time_source: str = "") -> PlcModel:
    """Имена и привязки ПЛК перечня; ``GenerationError`` — имена конфликтуют."""
    builder = _Builder(model, namespace, time_source)
    builder.collect_vars()
    bindings = [builder.binding(device) for device in builder.call_order()]
    # переменные состояния слейвов, добавленные при привязке CHF, уже учтены в collect_vars
    builder.check_unique()
    builder.check_constants(bindings)
    return PlcModel(namespace=namespace, io_vars=tuple(builder.vars), devices=tuple(bindings))
