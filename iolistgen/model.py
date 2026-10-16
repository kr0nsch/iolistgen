"""Модель проверенного перечня: сигналы, устройства, адреса Modbus, конфигурация устройств.

Модель строится только из перечня без ошибок (``CheckResult.model``), поэтому обязательные по
схеме поля в ней всегда заполнены. Её получают генераторы: имена идентификаторов уже
нормализованы (контракт plc-process-lib, 20.4), Cfg каждого устройства рассчитана целиком —
значения по умолчанию библиотеки, колонки перечня, ``params`` и выводы из состава устройства.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from iolistgen.catalog import (
    DEVICE_TYPES,
    LIBRARY_NAMESPACE,
    ST_TYPES,
    STRUCTS,
    DeviceTypeSpec,
    FieldSpec,
    leaf_fields,
    plain_defaults,
)
from iolistgen.enums import AlarmPriority, DeviceType, Role, SignalType
from iolistgen.modbus import (
    FUNCTIONS,
    Access,
    FunctionInfo,
    ModbusSpace,
    ModbusType,
    WordOrder,
    describe_area,
    span_length,
    span_mask,
)
from iolistgen.stvalues import StScalar

CfgOrigin = Literal["default", "column", "params", "inferred"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def column_letter(index: int) -> str:
    """Номер колонки (с 1) → буквы Excel: 1 → A, 27 → AA."""
    letters = ""
    number = index
    while number > 0:
        number, rest = divmod(number - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


class SourceRef(_Frozen):
    """Место в перечне: файл, лист XLSX, строка, колонка (номер с 1 и заголовок)."""

    file: str
    sheet: str | None = None
    row: int | None = None
    col: int | None = None
    header: str | None = None

    @property
    def column_letter(self) -> str | None:
        return column_letter(self.col) if self.col else None

    def cell(self, col: int | None, header: str | None) -> SourceRef:
        """Та же строка, другая колонка."""
        return self.model_copy(update={"col": col, "header": header})

    def location(self) -> str:
        """«лист «Перечень», строка 12, колонка C «Тип сигнала»» — для сообщений."""
        parts: list[str] = []
        if self.sheet:
            parts.append(f"лист «{self.sheet}»")
        if self.row is not None:
            parts.append(f"строка {self.row}")
        if self.col is not None:
            column = f"колонка {self.column_letter}"
            if self.header:
                column += f" «{self.header}»"
            parts.append(column)
        return ", ".join(parts) if parts else "файл"

    def short(self) -> str:
        """``kns.csv:12`` — путь и строка (так их понимают редакторы и CI)."""
        return f"{self.file}:{self.row}" if self.row is not None else self.file


class ModbusAddress(_Frozen):
    """Адрес значения в памяти слейва (ПЛК — master). ``address`` — адрес PDU с нуля."""

    link: str = ""
    slave: int
    function: int
    address: int
    data_type: ModbusType
    bit: int | None = None
    word_order: WordOrder | None = None

    @property
    def info(self) -> FunctionInfo:
        return FUNCTIONS[self.function]

    @property
    def space(self) -> ModbusSpace:
        return self.info.space

    @property
    def access(self) -> Access:
        return self.info.access

    @property
    def length(self) -> int:
        """Число катушек или регистров."""
        return span_length(self.space, self.data_type)

    @property
    def end(self) -> int:
        """Последний занятый адрес (включительно)."""
        return self.address + self.length - 1

    @property
    def mask(self) -> int:
        return span_mask(self.space, self.data_type, self.bit)

    def describe(self) -> str:
        """«регистры хранения 100…101 (REAL), слейв 2, линия RS485-1»."""
        text = f"{describe_area(self.space, self.address, self.data_type, self.bit)}, слейв {self.slave}"
        return f"{text}, линия {self.link}" if self.link else text


class ParamAssignment(_Frozen):
    """Присваивание из колонки ``params``: путь поля Cfg и значение."""

    path: str
    st_type: str
    value: StScalar
    text: str
    source: SourceRef

    def literal(self, namespace: str = LIBRARY_NAMESPACE) -> str:
        return ST_TYPES[self.st_type].format(self.value, namespace)


class CfgValue(_Frozen):
    """Значение поля Cfg устройства и откуда оно взялось."""

    path: str
    st_type: str
    value: StScalar
    default: StScalar
    origin: CfgOrigin
    note: str = ""

    @property
    def changed(self) -> bool:
        """Отличается от значения по умолчанию DUT."""
        return self.value != self.default

    def literal(self, namespace: str = LIBRARY_NAMESPACE) -> str:
        return ST_TYPES[self.st_type].format(self.value, namespace)


class DeviceCfg(_Frozen):
    """Полная Cfg устройства: все скалярные поля DUT в порядке объявления."""

    type_name: str
    values: tuple[CfgValue, ...]

    def get(self, path: str) -> CfgValue:
        for item in self.values:
            if item.path == path:
                return item
        raise KeyError(path)

    def value(self, path: str) -> StScalar:
        return self.get(path).value

    def changed(self) -> tuple[CfgValue, ...]:
        """Поля, отличные от значений по умолчанию DUT."""
        return tuple(item for item in self.values if item.changed)

    def initializer(self, namespace: str = LIBRARY_NAMESPACE) -> str:
        """Инициализатор ST только с отличными от умолчаний полями: ``(tMinStop := T#30S, ...)``.

        Массив пишется целиком, если в нём изменилось хотя бы одно поле: частичный
        инициализатор массива заполнил бы остаток умолчаниями типа элемента, а не умолчаниями
        DUT устройства (контракт plc-process-lib, 18.3, правило 3). Пустая строка — все поля
        по умолчанию.
        """
        tree = self.initializer_tree(namespace)
        return tree.flat() if tree.items else ""

    def initializer_tree(self, namespace: str = LIBRARY_NAMESPACE) -> InitGroup:
        """Тот же инициализатор деревом: для записи в несколько строк (``generators.stfmt``)."""
        renderer = _Renderer(plain_defaults(self.type_name), namespace)
        items = renderer.struct(_build_tree(self.values), self.type_name, in_array=False)
        return InitGroup(open="(", close=")", items=tuple(items))


class InitItem(_Frozen):
    """Элемент инициализатора: ``name := value``, ``name := <группа>`` или элемент массива.

    У элемента массива имя пустое, а ``comment`` — индекс и имя слота (``0 HH``).
    """

    name: str = ""
    value: str | None = None
    group: InitGroup | None = None
    comment: str = ""

    def flat(self) -> str:
        body = self.value if self.group is None else self.group.flat()
        assert body is not None
        return f"{self.name} := {body}" if self.name else body


class InitGroup(_Frozen):
    """Скобки инициализатора: ``( ... )`` структуры или ``[ ... ]`` массива."""

    open: str
    close: str
    items: tuple[InitItem, ...]

    def flat(self) -> str:
        return f"{self.open}{', '.join(item.flat() for item in self.items)}{self.close}"


InitItem.model_rebuild()


class _Node:
    """Узел дерева полей для записи вложенного инициализатора."""

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.indices: dict[int, _Node] = {}
        self.value: CfgValue | None = None


def _build_tree(values: tuple[CfgValue, ...]) -> _Node:
    root = _Node()
    for item in values:
        node = root
        for segment in item.path.split("."):
            name, _, index_text = segment.partition("[")
            node = node.children.setdefault(name, _Node())
            if index_text:
                node = node.indices.setdefault(int(index_text.rstrip("]")), _Node())
        node.value = item
    return root


def _subtree_changed(node: _Node) -> bool:
    """Есть поле, отличное от умолчания DUT устройства."""
    if node.value is not None:
        return node.value.changed
    return any(_subtree_changed(child) for child in node.children.values()) or any(
        _subtree_changed(child) for child in node.indices.values()
    )


def _field_spec(struct_name: str, name: str) -> FieldSpec:
    return next(spec for spec in STRUCTS[struct_name] if spec.name == name)


def _slot_comment(spec: FieldSpec, index: int) -> str:
    """«0 HH» — индекс элемента и имя значения перечисления-индекса."""
    if spec.index_enum is not None and index in spec.index_enum.values:
        member = spec.index_enum.members[spec.index_enum.values.index(index)]
        return f"{index} {member}"
    return f"{index} (резерв)" if spec.index_enum is not None else str(index)


class _Renderer:
    """Запись дерева полей инициализатором ST.

    Вне массивов поле пишется, если отличается от умолчания DUT устройства. Внутри элемента
    массива — если отличается от умолчания типа элемента: недописанные поля элемента
    компилятор заполнит умолчаниями типа (``ST_AlarmCfg``), а не DUT устройства.
    """

    def __init__(self, plain: dict[str, StScalar], namespace: str) -> None:
        self.plain = plain
        self.namespace = namespace

    def struct(self, node: _Node, struct_name: str, *, in_array: bool) -> list[InitItem]:
        items: list[InitItem] = []
        for name, child in node.children.items():
            spec = _field_spec(struct_name, name)
            if child.value is not None:
                if self._include(child.value, in_array=in_array):
                    items.append(InitItem(name=name, value=child.value.literal(self.namespace)))
            elif child.indices:
                if in_array or _subtree_changed(child):
                    assert spec.struct is not None
                    elements = tuple(
                        self.element(element, spec.struct, _slot_comment(spec, index))
                        for index, element in sorted(child.indices.items())
                    )
                    items.append(InitItem(name=name, group=InitGroup(open="[", close="]", items=elements)))
            else:
                assert spec.struct is not None
                inner = self.struct(child, spec.struct, in_array=in_array)
                if inner:
                    items.append(InitItem(name=name, group=InitGroup(open="(", close=")", items=tuple(inner))))
        return items

    def element(self, node: _Node, struct_name: str, comment: str) -> InitItem:
        """Элемент массива; если писать нечего — первое поле явно (пустого ``()`` в ST нет)."""
        items = self.struct(node, struct_name, in_array=True)
        if not items:
            first_name, first = next(iter(node.children.items()))
            assert first.value is not None
            items = [InitItem(name=first_name, value=first.value.literal(self.namespace))]
        return InitItem(group=InitGroup(open="(", close=")", items=tuple(items)), comment=comment)

    def _include(self, item: CfgValue, *, in_array: bool) -> bool:
        if in_array:
            return item.value != self.plain[item.path]
        return item.changed


def default_cfg(struct_name: str) -> DeviceCfg:
    """Cfg со значениями по умолчанию DUT."""
    return DeviceCfg(
        type_name=struct_name,
        values=tuple(
            CfgValue(
                path=leaf.path,
                st_type=leaf.st_type.name,
                value=leaf.default,
                default=leaf.default,
                origin="default",
            )
            for leaf in leaf_fields(struct_name)
        ),
    )


class Setpoints(_Frozen):
    """Уставки аналогового входа, инж. ед."""

    hh: float | None = None
    h: float | None = None
    l: float | None = None  # noqa: E741 — имя уставки L по ISA-18.2
    ll: float | None = None

    def defined(self) -> list[tuple[str, float]]:
        """Заданные уставки в порядке LL, L, H, HH."""
        pairs = (("LL", self.ll), ("L", self.l), ("H", self.h), ("HH", self.hh))
        return [(name, value) for name, value in pairs if value is not None]


class Signal(_Frozen):
    """Строка перечня: физический или обменный сигнал.

    ``device`` — идентификатор устройства (экземпляра ФБ); ``None`` — простой сигнал без ФБ
    (роль ``AUX`` без устройства: лампа, сирена, реле).
    """

    tag: str
    ident: str
    description: str
    signal_type: SignalType
    device: str | None
    role: Role
    is_main: bool
    range_min: float | None = None
    range_max: float | None = None
    units: str | None = None
    hmi_group: str | None = None
    io_module: str | None = None
    io_channel: int | None = None
    modbus: ModbusAddress | None = None
    extra: dict[str, str] = {}
    source: SourceRef

    @property
    def is_aux(self) -> bool:
        """Сигнал без входа и выхода ФБ: переменную читает и пишет код приложения."""
        return self.role is Role.AUX


class Device(_Frozen):
    """Устройство — экземпляр ФБ библиотеки, группа строк с одним ``device``."""

    name: str
    ident: str
    device_type: DeviceType
    dev_no: int
    description: str
    main_role: Role
    signals: tuple[Signal, ...]
    setpoints: Setpoints = Setpoints()
    delay_on_ms: int | None = None
    delay_off_ms: int | None = None
    alarm_priority: AlarmPriority | None = None
    hmi_group: str | None = None
    link_power: str | None = None
    link_fb: str | None = None
    params: tuple[ParamAssignment, ...] = ()
    cfg: DeviceCfg
    source: SourceRef

    @property
    def spec(self) -> DeviceTypeSpec:
        return DEVICE_TYPES[self.device_type]

    @property
    def main(self) -> Signal:
        signal = self.signal(self.main_role)
        assert signal is not None
        return signal

    def signal(self, role: Role) -> Signal | None:
        return next((s for s in self.signals if s.role is role), None)

    @property
    def roles(self) -> tuple[Role, ...]:
        return tuple(s.role for s in self.signals)

    @property
    def alarm_id_base(self) -> int:
        return self.dev_no * 10

    @property
    def modbus_slave(self) -> tuple[str, int] | None:
        """Линия и адрес слейва строк MB устройства (``None`` — строк MB нет)."""
        for signal in self.signals:
            if signal.modbus is not None:
                return signal.modbus.link, signal.modbus.slave
        return None


class SourceInfo(_Frozen):
    """Файл перечня: путь, лист, формат и SHA-256 содержимого."""

    path: str
    name: str
    sheet: str | None = None
    format: Literal["csv", "xlsx"]
    sha256: str

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]


class IoList(_Frozen):
    """Проверенный перечень сигналов."""

    source: SourceInfo
    columns: tuple[str, ...]
    signals: tuple[Signal, ...]
    devices: tuple[Device, ...]

    def device(self, ident: str) -> Device:
        """Устройство по идентификатору (без учёта регистра, как в CODESYS)."""
        key = ident.casefold()
        for device in self.devices:
            if device.ident.casefold() == key:
                return device
        raise KeyError(ident)

    def devices_by_dev_no(self) -> tuple[Device, ...]:
        """Устройства по возрастанию ``dev_no`` — порядок ``GVL_Persist`` (контракт 20.6)."""
        return tuple(sorted(self.devices, key=lambda d: d.dev_no))

    def modbus_signals(self) -> tuple[Signal, ...]:
        return tuple(s for s in self.signals if s.modbus is not None)

    def plain_signals(self) -> tuple[Signal, ...]:
        """Простые сигналы — без устройства (роль ``AUX`` отдельной строкой)."""
        return tuple(s for s in self.signals if s.device is None)

    def signals_of_type(self, signal_type: SignalType) -> tuple[Signal, ...]:
        return tuple(s for s in self.signals if s.signal_type is signal_type)
