"""Проверки строк перечня: теги, атрибуты сигналов, адреса Modbus, каналы модулей."""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence

from iolistgen.build import DeviceDraft
from iolistgen.config import ModbusConfig, NamingConfig
from iolistgen.diagnostics import DiagnosticBag
from iolistgen.enums import DeviceType, Direction, Role, SignalType
from iolistgen.identifiers import check_identifier, identifier_key
from iolistgen.modbus import ADDRESS_MAX, FUNCTIONS, Access, ModbusType, Span, WordOrder, find_overlaps, span_length
from iolistgen.model import ModbusAddress
from iolistgen.parse import SignalDraft
from iolistgen.stvalues import format_real

_SETPOINT_ORDER = ("ll", "l", "h", "hh")
_SETPOINT_COLUMNS = {"ll": "sp_ll", "l": "sp_l", "h": "sp_h", "hh": "sp_hh"}


def _num(value: float) -> str:
    return format_real(value).removesuffix(".0") if value == int(value) else format_real(value)


# --- теги и имена ------------------------------------------------------------------------------


def check_tags(drafts: Sequence[SignalDraft], bag: DiagnosticBag, naming: NamingConfig, *, has_tag: bool) -> None:
    """Пустые теги, идентификаторы ST, дубли без учёта регистра, правило именования."""
    pattern = re.compile(naming.tag_regex)
    seen: dict[str, SignalDraft] = {}
    for draft in drafts:
        if draft.tag is None:
            if has_tag:
                bag.add(
                    "IOL101",
                    "у сигнала нет тега",
                    "задайте тег (LT101, P101_RUN); резервный канал закомментируйте символом # в первой ячейке "
                    "или запишите сигналом без ФБ с тегом: role = AUX, tag = RES_D1_16",
                    source=draft.cell("tag"),
                )
            continue
        problem = check_identifier(draft.tag)
        if problem is not None:
            draft.invalid.add("tag")
            hint = problem.hint
            if len(draft.row.cells) == 1 and not draft.row.extra:
                hint += (
                    "; если это заголовок раздела, а не сигнал, — начните ячейку с # (комментарий) или "
                    "объедините ячейки строки через всю таблицу (XLSX)"
                )
            bag.add("IOL102", problem.message, hint, source=draft.cell("tag"), tag=draft.tag)
            continue
        assert draft.ident is not None
        key = identifier_key(draft.ident)
        first = seen.get(key)
        if first is not None:
            draft.duplicate = True
            if first.tag == draft.tag:
                what = f"тег {draft.tag} уже есть"
            else:
                what = f"теги «{draft.tag}» и «{first.tag}» дают один идентификатор {draft.ident}"
            bag.add(
                "IOL103",
                what,
                "теги уникальны без учёта регистра; «-», «.» и пробел считаются «_»",
                source=draft.cell("tag"),
                related=[first.cell("tag")],
                tag=draft.tag,
            )
        else:
            seen[key] = draft
        if not pattern.fullmatch(draft.tag):
            bag.add(
                "IOL104",
                f"тег «{draft.tag}» не соответствует правилу именования {naming.tag_regex}",
                "переименуйте по проектному правилу (по умолчанию — буквенный код и номер: LT101, P101_RUN) "
                "или задайте своё правило в iolistgen.toml: [naming] tag_regex",
                source=draft.cell("tag"),
                tag=draft.tag,
            )


def check_device_names(devices: Sequence[DeviceDraft], bag: DiagnosticBag, naming: NamingConfig) -> None:
    """Имена устройств: идентификатор, правило ``device_regex``, длина."""
    pattern = re.compile(naming.device_regex)
    for device in devices:
        if device.plain:
            continue  # простой сигнал AUX — не устройство: кодов тревог и тегов устройства у него нет
        explicit = next((draft for draft in device.signals if draft.device_explicit), None)
        if explicit is not None:
            problem = check_identifier(device.name)
            if problem is not None:
                bag.add(
                    "IOL105",
                    f"устройство «{device.name}»: {problem.message}",
                    problem.hint,
                    source=explicit.cell("device"),
                    tag=explicit.tag,
                    device=device.name,
                )
                continue
            if not pattern.fullmatch(device.name):
                bag.add(
                    "IOL106",
                    f"устройство «{device.name}» не соответствует правилу именования {naming.device_regex}",
                    "переименуйте устройство (позиция по схеме: P101, LT101) или задайте правило "
                    "в iolistgen.toml: [naming] device_regex",
                    source=explicit.cell("device"),
                    tag=explicit.tag,
                    device=device.name,
                )
        elif check_identifier(device.name) is not None:
            continue
        if len(device.ident) > naming.max_device_length:
            column = "device" if explicit is not None else "tag"
            row = explicit if explicit is not None else device.signals[0]
            bag.add(
                "IOL107",
                f"имя устройства {device.ident} длиннее {naming.max_device_length} символов",
                "имя устройства входит в коды тревог и теги SCADA: сократите его или увеличьте "
                "[naming] max_device_length",
                source=row.cell(column),
                tag=row.tag,
                device=device.name,
            )


# --- атрибуты сигналов -------------------------------------------------------------------------


def check_attributes(devices: Sequence[DeviceDraft], bag: DiagnosticBag) -> None:
    """Описание, диапазон, единицы, уставки и задержки."""
    for device in devices:
        for draft in device.signals:
            _check_description(draft, bag)
            _check_range(device, draft, bag)
            _check_units(device, draft, bag)
        _check_setpoints(device, bag)
        _check_delays(device, bag)


def _check_description(draft: SignalDraft, bag: DiagnosticBag) -> None:
    if draft.description is None and "description" in draft.columns:
        bag.add(
            "IOL201",
            f"у сигнала {draft.label} нет описания",
            "опишите сигнал: оно идёт в документацию, SCADA и тексты тревог",
            source=draft.cell("description"),
            tag=draft.tag,
        )


def _is_pv(device: DeviceDraft, draft: SignalDraft) -> bool:
    return device.device_type is DeviceType.ANALOG_INPUT and draft.role is Role.PV


def _is_analog(draft: SignalDraft) -> bool:
    if draft.signal_type in (SignalType.AI, SignalType.AO):
        return True
    data_type = draft.modbus.data_type
    # регистр AUX может быть кодом или счётчиком — единицы у него не обязательны
    return (
        draft.signal_type is SignalType.MB
        and data_type is not None
        and data_type.is_numeric
        and draft.role not in (Role.VFD_CTW, Role.VFD_STW, Role.AUX)
    )


def _check_range(device: DeviceDraft, draft: SignalDraft, bag: DiagnosticBag) -> None:
    low, high = draft.range_min, draft.range_max
    if "range_min" in draft.invalid or "range_max" in draft.invalid:
        return
    if low is not None and high is not None:
        if low >= high:
            bit = "PID_CFG_PV_RANGE" if draft.device_row else "AI_CFG_RANGE"
            bag.add(
                "IOL204",
                f"диапазон {_num(low)}…{_num(high)}: минимум не меньше максимума",
                f"задайте range_min меньше range_max (иначе ФБ отклонит Cfg: {bit})",
                source=draft.cell("range_min"),
                related=[draft.cell("range_max")],
                tag=draft.tag,
                device=device.name,
            )
        return
    if low is not None or high is not None:
        missing = "range_max" if low is not None else "range_min"
        bag.add(
            "IOL205",
            f"задана только одна граница диапазона, нет {missing}",
            "укажите обе границы шкалы: range_min и range_max",
            source=draft.cell(missing),
            tag=draft.tag,
            device=device.name,
        )
        return
    if _is_pv(device, draft):
        bag.add(
            "IOL203",
            f"у аналогового входа {device.name} нет диапазона шкалы",
            "укажите range_min и range_max в инженерных единицах (значения при 4 и 20 мА)",
            source=draft.cell("range_min"),
            tag=draft.tag,
            device=device.name,
        )


def _check_units(device: DeviceDraft, draft: SignalDraft, bag: DiagnosticBag) -> None:
    if draft.units is not None or "signal_type" in draft.invalid:
        return
    if _is_pv(device, draft):
        bag.add(
            "IOL206",
            f"у аналогового входа {device.name} не указаны единицы измерения",
            "укажите единицы (м, бар, м3/ч, °C): они нужны SCADA и документации",
            source=draft.cell("units"),
            tag=draft.tag,
            device=device.name,
        )
    elif _is_analog(draft):
        bag.add(
            "IOL207",
            f"у аналогового сигнала {draft.label} не указаны единицы измерения",
            "укажите единицы (%, Гц, мА)",
            source=draft.cell("units"),
            tag=draft.tag,
            device=device.name,
        )


def _check_setpoints(device: DeviceDraft, bag: DiagnosticBag) -> None:
    head = device.head
    if not head.setpoints:
        return
    first_cell = head.cell(next(_SETPOINT_COLUMNS[name] for name in _SETPOINT_ORDER[::-1] if name in head.setpoints))
    if device.device_type is not DeviceType.ANALOG_INPUT:
        if device.device_type is not None:
            bag.add(
                "IOL210",
                f"уставки заданы у {device.device_type.value} {device.name} — они есть только у AnalogInput",
                "очистите колонки sp_hh, sp_h, sp_l, sp_ll или смените тип устройства",
                source=first_cell,
                tag=head.tag,
                device=device.name,
            )
        return
    defined = [(name, head.setpoints[name]) for name in _SETPOINT_ORDER if name in head.setpoints]
    for (low_name, low), (high_name, high) in itertools.pairwise(defined):
        if low >= high:
            bag.add(
                "IOL208",
                f"уставка {high_name.upper()} ({_num(high)}) не больше {low_name.upper()} ({_num(low)})",
                "уставки идут строго по возрастанию: LL < L < H < HH (иначе ФБ отклонит Cfg: AI_CFG_LIMIT_ORDER)",
                source=head.cell(_SETPOINT_COLUMNS[high_name]),
                related=[head.cell(_SETPOINT_COLUMNS[low_name])],
                tag=head.tag,
                device=device.name,
            )
    low_range, high_range = head.range_min, head.range_max
    if low_range is None or high_range is None or low_range >= high_range:
        return
    for name, value in defined:
        if not low_range <= value <= high_range:
            bag.add(
                "IOL209",
                f"уставка {name.upper()} = {_num(value)} вне шкалы {_num(low_range)}…{_num(high_range)}",
                "уставка лежит внутри диапазона (иначе ФБ отклонит Cfg: AI_CFG_LIMIT_OUT_OF_RANGE)",
                source=head.cell(_SETPOINT_COLUMNS[name]),
                tag=head.tag,
                device=device.name,
            )


def _check_delays(device: DeviceDraft, bag: DiagnosticBag) -> None:
    head = device.head
    spec = device.spec
    if spec is None:
        return
    if spec.device_type is DeviceType.ANALOG_INPUT and not head.setpoints:
        for column in ("delay_on_s", "delay_off_s"):
            if head.has(column) and column not in head.invalid:
                bag.add(
                    "IOL211",
                    f"задержка {column} у {device.name} без уставок не действует",
                    "у AnalogInput задержки относятся к включённым уставкам HH/H/L/LL; задайте уставки или "
                    "очистите ячейку",
                    source=head.cell(column),
                    tag=head.tag,
                    device=device.name,
                )
    if spec.delay_on is None and head.has("delay_on_s") and "delay_on_s" not in head.invalid:
        bag.add(
            "IOL211",
            f"у {spec.device_type.value} нет задержек",
            "задержки перечня этому типу устройства не применяются; очистите колонки delay_on_s и delay_off_s",
            source=head.cell("delay_on_s"),
            tag=head.tag,
            device=device.name,
        )
    if spec.delay_off is None and head.has("delay_off_s") and "delay_off_s" not in head.invalid:
        no_delays = spec.delay_on is None
        bag.add(
            "IOL211",
            f"у {spec.device_type.value} нет задержки отключения"
            if not no_delays
            else f"у {spec.device_type.value} нет задержек",
            f"задержка включения задаёт {spec.delay_on}; очистите колонку delay_off_s"
            if not no_delays
            else "задержки перечня этому типу устройства не применяются; очистите колонку delay_off_s",
            source=head.cell("delay_off_s"),
            tag=head.tag,
            device=device.name,
        )


# --- Modbus ------------------------------------------------------------------------------------

_REQUIRED_MB = ("mb_slave", "mb_func", "mb_reg", "mb_type")
_MB_FIELDS = ("mb_link", "mb_slave", "mb_func", "mb_reg", "mb_type", "mb_bit", "mb_order")


def check_modbus(
    devices: Sequence[DeviceDraft],
    bag: DiagnosticBag,
    config: ModbusConfig,
) -> dict[int, ModbusAddress]:
    """Адреса Modbus всех строк; результат — корректные адреса по ``id(draft)``."""
    addresses: dict[int, ModbusAddress] = {}
    ordered: list[tuple[SignalDraft, ModbusAddress]] = []
    for device in devices:
        for draft in device.signals:
            address = _check_modbus_row(device, draft, bag, config)
            if address is not None:
                addresses[id(draft)] = address
                ordered.append((draft, address))
    ordered.sort(key=lambda item: item[0].line)
    _check_overlaps(ordered, bag)
    _check_device_slaves(devices, addresses, bag)
    _check_link_names(ordered, bag)
    return addresses


def _check_link_names(ordered: list[tuple[SignalDraft, ModbusAddress]], bag: DiagnosticBag) -> None:
    """Имя линии входит в имена переменных ``xMbOk_<линия>_S<слейв>``: нужна латиница."""
    reported: set[str] = set()
    for draft, address in ordered:
        link = address.link
        if not link or link.casefold() in reported:
            continue
        reported.add(link.casefold())
        if check_identifier(link) is None:
            continue
        bag.add(
            "IOL417",
            f"имя линии Modbus «{link}» не даёт идентификатор ST: переменные состояния обмена получат "
            "имена L1, L2… по алфавиту линий, и новая линия сдвинет их",
            "назовите линию латиницей и цифрами (RS485-1, TCP-1): имя входит в GVL_IO.xMbOk_<линия>_S<слейв>",
            source=draft.cell("mb_link"),
            tag=draft.tag,
        )


def _check_modbus_row(
    device: DeviceDraft,
    draft: SignalDraft,
    bag: DiagnosticBag,
    config: ModbusConfig,
) -> ModbusAddress | None:
    mb = draft.modbus
    if draft.signal_type is not SignalType.MB:
        if mb.present and (draft.signal_type is not None or draft.device_row):
            name = next(name for name in _MB_FIELDS if name in mb.present)
            what = f"сигнала {draft.signal_type.value}" if draft.signal_type is not None else "строки устройства"
            bag.add(
                "IOL402",
                f"у {what} {draft.label} заполнен адрес Modbus — он не используется",
                "адрес Modbus задаётся только у сигналов MB: очистите колонки mb_* или смените тип сигнала",
                source=draft.cell(name),
                tag=draft.tag,
                device=device.name,
            )
        return None
    missing = [name for name in _REQUIRED_MB if name not in mb.present]
    if missing:
        bag.add(
            "IOL401",
            f"у сигнала MB {draft.label} не задан адрес: нет {', '.join(missing)}",
            "заполните слейв, функцию, регистр и тип данных (mb_slave, mb_func, mb_reg, mb_type)",
            source=draft.cell(missing[0]),
            tag=draft.tag,
            device=device.name,
        )
        return None
    if any(name in draft.invalid for name in _MB_FIELDS):
        return None
    assert mb.slave is not None and mb.function is not None and mb.register is not None
    assert mb.data_type is not None
    if not 0 <= mb.slave <= 255:
        bag.add(
            "IOL413",
            f"адрес слейва {mb.slave} вне 0…255",
            "адрес слейва (Unit ID) — один байт: Modbus RTU — 1…247, Modbus TCP — 0…255",
            source=draft.cell("mb_slave"),
            tag=draft.tag,
            device=device.name,
        )
        return None
    if mb.slave == 0:
        bag.add(
            "IOL416",
            "адрес слейва 0 — широковещательный в Modbus RTU: на чтение ответа нет",
            "для Modbus RTU укажите 1…247; если это Unit ID 0 устройства Modbus TCP — ослабьте правило: "
            '[severity] IOL416 = "warning" или "off" в iolistgen.toml',
            source=draft.cell("mb_slave"),
            tag=draft.tag,
            device=device.name,
        )
    if mb.slave >= 248:
        bag.add(
            "IOL414",
            f"адрес слейва {mb.slave} зарезервирован в Modbus RTU (248…255)",
            "для Modbus RTU укажите 1…247; для Modbus TCP предупреждение можно отключить",
            source=draft.cell("mb_slave"),
            tag=draft.tag,
            device=device.name,
        )
    info = FUNCTIONS[mb.function]
    data_type = mb.data_type
    space = info.space
    if space.is_bits:
        if data_type is not ModbusType.BOOL:
            bag.add(
                "IOL405",
                f"{info.label} работает с битами ({space.label}), а тип данных {data_type.value}",
                "для значения в регистрах используйте FC3/FC4 (чтение) или FC6/FC16 (запись); для бита — тип BOOL",
                source=draft.cell("mb_type"),
                related=[draft.cell("mb_func")],
                tag=draft.tag,
                device=device.name,
            )
            return None
        if mb.bit is not None:
            bag.add(
                "IOL407",
                f"у {space.label} нет битов внутри адреса, а указан бит {mb.bit}",
                "очистите mb_bit: катушка или дискретный вход и есть один бит",
                source=draft.cell("mb_bit"),
                tag=draft.tag,
                device=device.name,
            )
            return None
    else:
        if data_type is ModbusType.BOOL and mb.bit is None:
            bag.add(
                "IOL407",
                "сигнал BOOL в регистре: не указан номер бита",
                "укажите mb_bit 0…15 или используйте функцию для битов (FC1, FC2, FC5, FC15)",
                source=draft.cell("mb_bit"),
                tag=draft.tag,
                device=device.name,
            )
            return None
        if data_type is not ModbusType.BOOL and mb.bit is not None:
            bag.add(
                "IOL407",
                f"номер бита указан у значения {data_type.value}",
                "бит указывается только у сигналов BOOL; очистите mb_bit или смените тип данных на BOOL",
                source=draft.cell("mb_bit"),
                tag=draft.tag,
                device=device.name,
            )
            return None
        if mb.bit is not None and not 0 <= mb.bit <= 15:
            bag.add(
                "IOL407",
                f"номер бита {mb.bit} вне 0…15",
                "регистр Modbus — 16 бит: укажите бит 0…15",
                source=draft.cell("mb_bit"),
                tag=draft.tag,
                device=device.name,
            )
            return None
        if info.single and data_type.words > 1:
            bag.add(
                "IOL405",
                f"{info.label} пишет один регистр, а {data_type.value} занимает {data_type.words}",
                "для многорегистровых значений используйте FC16 (Write Multiple Registers)",
                source=draft.cell("mb_func"),
                related=[draft.cell("mb_type")],
                tag=draft.tag,
                device=device.name,
            )
            return None
    register = mb.register - config.address_base
    if register < 0:
        bag.add(
            "IOL406",
            f"адрес {mb.register} меньше базы адресации {config.address_base}",
            "при [modbus] address_base = 1 адреса в перечне начинаются с 1; иначе адрес PDU — с 0",
            source=draft.cell("mb_reg"),
            tag=draft.tag,
            device=device.name,
        )
        return None
    length = span_length(space, data_type)
    if register + length - 1 > ADDRESS_MAX:
        bag.add(
            "IOL406",
            f"адрес {mb.register} + {length} выходит за предел {ADDRESS_MAX + config.address_base}",
            f"адрес PDU — 0…{ADDRESS_MAX}; {data_type.value} занимает {length} адр.",
            source=draft.cell("mb_reg"),
            tag=draft.tag,
            device=device.name,
        )
        return None
    order = mb.word_order
    if data_type.words > 1 and not space.is_bits:
        if order is None:
            order = config.default_word_order
            if order is None:
                order = WordOrder.HL
                bag.add(
                    "IOL408",
                    f"не указан порядок слов {data_type.value} — принят HL (старшее слово первым)",
                    "укажите mb_order: HL или LH (по документации прибора) или задайте [modbus] default_word_order",
                    source=draft.cell("mb_order"),
                    tag=draft.tag,
                    device=device.name,
                )
    elif order is not None:
        bag.add(
            "IOL409",
            f"порядок слов указан у 16-битного значения {data_type.value}",
            "порядок слов нужен только 32- и 64-битным типам: очистите mb_order",
            source=draft.cell("mb_order"),
            tag=draft.tag,
            device=device.name,
        )
        order = None
    _check_role_access(device, draft, info.access, data_type, bag)
    return ModbusAddress(
        link=mb.link,
        slave=mb.slave,
        function=mb.function,
        address=register,
        data_type=data_type,
        bit=mb.bit,
        word_order=order,
    )


def _check_role_access(
    device: DeviceDraft,
    draft: SignalDraft,
    access: Access,
    data_type: ModbusType,
    bag: DiagnosticBag,
) -> None:
    spec = device.spec
    if spec is None or draft.role is None:
        return
    role_spec = spec.role(draft.role)
    if role_spec is None:
        return
    reading = access is Access.READ
    if role_spec.direction is Direction.IN and not reading:
        fix = "FC1 или FC2" if data_type is ModbusType.BOOL else "FC3 или FC4"
        bag.add(
            "IOL410",
            f"роль {draft.role.value} — вход ФБ, ПЛК её читает, а функция записывает",
            f"для чтения используйте {fix}",
            source=draft.cell("mb_func"),
            tag=draft.tag,
            device=device.name,
        )
    elif role_spec.direction is Direction.OUT and reading:
        fix = "FC5 или FC15" if data_type is ModbusType.BOOL else "FC6 или FC16"
        bag.add(
            "IOL410",
            f"роль {draft.role.value} — выход ФБ, ПЛК её пишет, а функция читает",
            f"для записи используйте {fix}",
            source=draft.cell("mb_func"),
            tag=draft.tag,
            device=device.name,
        )
    if role_spec.mb_types and data_type not in role_spec.mb_types:
        allowed = ", ".join(t.value for t in ModbusType if t in role_spec.mb_types)
        bag.add(
            "IOL411",
            f"тип данных {data_type.value} не подходит к роли {draft.role.value} ({role_spec.title})",
            f"для роли {draft.role.value} допустимы: {allowed}",
            source=draft.cell("mb_type"),
            tag=draft.tag,
            device=device.name,
        )


def _check_overlaps(ordered: list[tuple[SignalDraft, ModbusAddress]], bag: DiagnosticBag) -> None:
    spans = [
        Span(
            key=(address.link.casefold(), address.slave, address.space),
            start=address.address,
            end=address.end,
            mask=address.mask,
        )
        for _, address in ordered
    ]
    for first_index, second_index in find_overlaps(spans):
        first, first_address = ordered[first_index]
        second, second_address = ordered[second_index]
        same_bit = first_address.data_type is ModbusType.BOOL and second_address.data_type is ModbusType.BOOL
        hint = (
            "у двух сигналов один и тот же бит: проверьте mb_bit и mb_reg"
            if same_bit and not first_address.space.is_bits
            else "проверьте адрес и длину типа данных: 32-битные типы занимают 2 регистра, 64-битные — 4"
        )
        bag.add(
            "IOL412",
            f"адрес пересекается с сигналом {first.label}: {second_address.describe()} и {first_address.describe()}",
            hint,
            source=second.cell("mb_reg"),
            related=[first.cell("mb_reg")],
            tag=second.tag,
        )


def _check_device_slaves(
    devices: Sequence[DeviceDraft],
    addresses: dict[int, ModbusAddress],
    bag: DiagnosticBag,
) -> None:
    for device in devices:
        first: tuple[SignalDraft, ModbusAddress] | None = None
        for draft in device.signals:
            address = addresses.get(id(draft))
            if address is None:
                continue
            if first is None:
                first = (draft, address)
                continue
            base_draft, base = first
            if (address.link.casefold(), address.slave) != (base.link.casefold(), base.slave):
                bag.add(
                    "IOL415",
                    f"сигнал {draft.label} на слейве {address.slave}, а {base_draft.label} устройства "
                    f"{device.name} — на слейве {base.slave}",
                    "адаптер устройства опрашивает один слейв: проверьте mb_slave и mb_link",
                    source=draft.cell("mb_slave"),
                    related=[base_draft.cell("mb_slave")],
                    tag=draft.tag,
                    device=device.name,
                )


# --- каналы модулей ----------------------------------------------------------------------------


def check_channels(drafts: Sequence[SignalDraft], bag: DiagnosticBag) -> None:
    """Повторы «модуль + канал», неполные привязки, канал у сигнала MB."""
    seen: dict[tuple[str, SignalType, int], SignalDraft] = {}
    for draft in drafts:
        has_module, has_channel = draft.has("io_module"), draft.has("io_channel")
        if not (has_module or has_channel):
            continue
        if draft.device_row:
            bag.add(
                "IOL603",
                f"у строки устройства {draft.label} заполнены модуль или канал — они не используются",
                "у устройства без сигналов ввода-вывода (Pid) каналов нет: очистите io_module и io_channel",
                source=draft.cell("io_module" if has_module else "io_channel"),
                tag=draft.tag,
            )
            continue
        if draft.signal_type is None:
            continue
        if draft.signal_type is SignalType.MB:
            bag.add(
                "IOL603",
                f"у сигнала MB {draft.label} заполнены модуль или канал — они не используются",
                "канал модуля задаётся у AI, DI, DO, AO; у MB — адрес Modbus",
                source=draft.cell("io_module" if has_module else "io_channel"),
                tag=draft.tag,
            )
            continue
        if has_module != has_channel:
            missing = "io_channel" if has_module else "io_module"
            bag.add(
                "IOL602",
                f"у сигнала {draft.label} задан {'модуль' if has_module else 'канал'}, но нет {missing}",
                "укажите и модуль, и номер канала — или очистите обе ячейки",
                source=draft.cell(missing),
                tag=draft.tag,
            )
            continue
        if draft.io_module is None or draft.io_channel is None:
            continue
        key = (draft.io_module.casefold(), draft.signal_type, draft.io_channel)
        first = seen.get(key)
        if first is not None:
            bag.add(
                "IOL601",
                f"канал {draft.signal_type.value} {draft.io_channel} модуля {draft.io_module} уже занят сигналом "
                f"{first.label}",
                "у каждого физического канала один сигнал: проверьте io_module и io_channel",
                source=draft.cell("io_channel"),
                related=[first.cell("io_channel")],
                tag=draft.tag,
            )
        else:
            seen[key] = draft
