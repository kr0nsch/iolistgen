"""Группировка строк в устройства: тип, номер, роли, главная строка, ссылки ``link_*``.

Устройство — строки с одинаковым ``device`` (без учёта регистра, после нормализации тега,
контракт plc-process-lib, 20.4). Главная строка — строка главной роли типа устройства: из неё
читаются уставки, задержки, приоритет, ``params`` и ссылки (20.2).

Строка с ролью ``AUX`` — сигнал без входа и выхода ФБ: в устройстве (сколько угодно строк) или
отдельно, без ``device`` и ``device_type`` («простой» сигнал: лампа, сирена, реле). Простой
сигнал устройством не считается: экземпляра ФБ, Cmd, Cfg и тревог у него нет.

У типа без сигналов ввода-вывода (``Pid``) главная строка — строка устройства: без ``signal_type`` и
``role``, с ``device_type``, ``dev_no``, диапазоном PV и ``params``. Других строк, кроме ``AUX``, у
такого устройства нет: привязки ФБ пишет логика станции (контракт plc-process-lib 17.3).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from iolistgen.catalog import (
    AUX_TITLE,
    DEV_NO_MAX,
    DEV_NO_MIN,
    DEVICE_TYPES,
    LINK_COLUMNS,
    DeviceTypeSpec,
    link_owners,
)
from iolistgen.columns import COLUMNS
from iolistgen.diagnostics import DiagnosticBag
from iolistgen.enums import DeviceType, Role
from iolistgen.identifiers import identifier_key, to_identifier
from iolistgen.model import DeviceCfg, ParamAssignment, SourceRef
from iolistgen.parse import SignalDraft

DEVICE_LEVEL_COLUMNS: tuple[str, ...] = tuple(spec.name for spec in COLUMNS if spec.level == "device")
# Колонки, которые у простого сигнала (AUX без устройства) ничего не задают
PLAIN_UNUSED_COLUMNS: tuple[str, ...] = tuple(
    spec.name for spec in COLUMNS if spec.level == "device" or spec.name == "dev_no"
)

_VFD_ONLY_ROLES = frozenset({Role.VFD_CTW, Role.VFD_STW, Role.SPEED_REF, Role.SPEED_ACT})


@dataclass
class DeviceDraft:
    """Устройство перечня во время проверки."""

    key: str
    name: str
    signals: list[SignalDraft]
    device_type: DeviceType | None = None
    dev_no: int | None = None
    main: SignalDraft | None = None
    has_main_role: bool = False
    roles: dict[Role, SignalDraft] = field(default_factory=dict)
    link_targets: dict[str, DeviceDraft] = field(default_factory=dict)
    params: list[ParamAssignment] = field(default_factory=list)
    cfg: DeviceCfg | None = None
    plain: bool = False
    """Простой сигнал: одна строка AUX без device и device_type — не экземпляр ФБ."""

    @property
    def ident(self) -> str:
        return to_identifier(self.name)

    @property
    def spec(self) -> DeviceTypeSpec | None:
        return DEVICE_TYPES[self.device_type] if self.device_type is not None else None

    @property
    def head(self) -> SignalDraft:
        """Строка, из которой читаются атрибуты устройства: главная или первая."""
        return self.main if self.main is not None else self.signals[0]

    @property
    def source(self) -> SourceRef:
        return self.head.source

    def has(self, role: Role) -> bool:
        return role in self.roles


def group_devices(drafts: list[SignalDraft], bag: DiagnosticBag) -> list[DeviceDraft]:
    """Сгруппировать строки по ``device`` и проверить состав каждого устройства."""
    groups: dict[str, DeviceDraft] = {}
    for draft in drafts:
        key = draft.device_key
        if key is None or draft.duplicate:
            # строка с дублем тега в устройства не входит: иначе один дубль дал бы цепочку
            # сообщений о ролях и номерах устройства
            continue
        device = groups.get(key)
        if device is None:
            groups[key] = DeviceDraft(key=key, name=draft.device_name or "", signals=[draft])
        else:
            device.signals.append(draft)
    devices = list(groups.values())
    for device in devices:
        _check_names(device, bag)
        _resolve_type(device, bag, groups)
        _resolve_dev_no(device, bag)
        _resolve_roles(device, bag)
        _check_device_columns(device, bag)
    _check_dev_no_unique(devices, bag)
    _resolve_links(devices, bag)
    for device in devices:
        if device.plain:
            _check_plain(device, bag)
    _check_signal_types(drafts, bag)
    return devices


def _check_signal_types(drafts: list[SignalDraft], bag: DiagnosticBag) -> None:
    """Тип сигнала есть у каждой строки, кроме строки устройства без сигналов (Pid)."""
    for draft in drafts:
        if draft.device_row or draft.signal_type is not None or "signal_type" in draft.invalid:
            continue
        if "signal_type" not in draft.columns:
            continue  # колонки нет в файле: одна ошибка IOL003 на весь файл
        bag.add(
            "IOL202",
            f"у сигнала {draft.label} не задан тип сигнала",
            "укажите AI, DI, DO, AO или MB; строка ПИД-регулятора (device_type = Pid) — без типа сигнала и роли",
            source=draft.cell("signal_type"),
            tag=draft.tag,
        )


def _check_plain(device: DeviceDraft, bag: DiagnosticBag) -> None:
    """Колонки устройства у простого сигнала ничего не задают — предупредить."""
    draft = device.signals[0]
    for name in PLAIN_UNUSED_COLUMNS:
        if draft.has(name):
            bag.add(
                "IOL317",
                f"колонка {name} у сигнала без ФБ {draft.label} не используется",
                f"роль AUX — {AUX_TITLE}; очистите ячейку или укажите device_type и роль сигнала ФБ",
                source=draft.cell(name),
                tag=draft.tag,
            )


def _check_names(device: DeviceDraft, bag: DiagnosticBag) -> None:
    reported: set[str] = set()
    for draft in device.signals:
        name = (draft.device_name or "").strip()
        if name != device.name and name not in reported:
            reported.add(name)
            column = "device" if draft.device_explicit else "tag"
            bag.add(
                "IOL108",
                f"устройство «{name}» и «{device.name}» (строка {device.signals[0].line}) дают один "
                f"идентификатор {device.ident}",
                f"запишите имя устройства одинаково во всех строках: {device.name}",
                source=draft.cell(column),
                tag=draft.tag,
                device=device.name,
            )


# Роли, которые бывают только у сигнала в составе устройства (не одиночная строка AI или DI)
_MEMBER_ROLES = frozenset(Role) - {Role.PV, Role.IN}


def _guess_device(draft: SignalDraft, groups: dict[str, DeviceDraft]) -> DeviceDraft | None:
    """Устройство, к которому, судя по тегу, относится строка: ``P101_FB`` → ``P101``."""
    ident = draft.ident or ""
    best: DeviceDraft | None = None
    for key, candidate in groups.items():
        if candidate.device_type is None and not any(d.device_type is not None for d in candidate.signals):
            continue
        if identifier_key(ident).startswith(key + "_") and (best is None or len(key) > len(best.key)):
            best = candidate
    return best


def _is_plain(device: DeviceDraft) -> bool:
    """Одна строка AUX, device пуст или равен тегу."""
    if len(device.signals) != 1:
        return False
    draft = device.signals[0]
    return draft.role is Role.AUX and (not draft.device_explicit or device.key == identifier_key(draft.ident or ""))


def _resolve_type(device: DeviceDraft, bag: DiagnosticBag, groups: dict[str, DeviceDraft]) -> None:
    typed = [draft for draft in device.signals if draft.device_type is not None]
    if not typed:
        if _is_plain(device):
            device.plain = True
            return
        if not any("device_type" in draft.invalid for draft in device.signals) and _column_exists(
            device, "device_type"
        ):
            first = device.signals[0]
            if all(draft.role is Role.AUX for draft in device.signals):
                typed_names = [
                    group.name for group in groups.values() if any(d.device_type is not None for d in group.signals)
                ]
                close = difflib.get_close_matches(device.name, typed_names, n=1, cutoff=0.6)
                bag.add(
                    "IOL302",
                    f"у устройства {device.name} не задан тип, а все его строки — AUX",
                    (f"возможно, device = {close[0]}; " if close else "")
                    + "сигнал без ФБ (AUX) записывается отдельной строкой без device; если это сигналы "
                    "устройства — укажите device_type и главную строку",
                    source=first.cell("device"),
                    tag=first.tag,
                    device=device.name,
                )
                return
            if len(device.signals) == 1 and not first.device_explicit and first.role in _MEMBER_ROLES:
                assert first.role is not None
                owners = ", ".join(t.value for t, spec in DEVICE_TYPES.items() if spec.role(first.role) is not None)
                guess = _guess_device(first, groups)
                hint = f"укажите в колонке device тег устройства ({owners}), к которому относится сигнал"
                if guess is not None:
                    hint += f": похоже, {guess.name}"
                bag.add(
                    "IOL302",
                    f"у сигнала {first.label} с ролью {first.role.value} не указано устройство (device)",
                    hint,
                    source=first.cell("device"),
                    tag=first.tag,
                    device=device.name,
                )
                return
            types = ", ".join(t.value for t in DEVICE_TYPES)
            bag.add(
                "IOL302",
                f"у устройства {device.name} не задан тип",
                f"укажите device_type в главной строке: {types}",
                source=first.cell("device_type"),
                tag=first.tag,
                device=device.name,
            )
        return
    device.device_type = typed[0].device_type
    for draft in typed[1:]:
        if draft.device_type is not device.device_type:
            assert draft.device_type is not None and device.device_type is not None
            bag.add(
                "IOL303",
                f"тип устройства {draft.device_type.value} не совпадает с {device.device_type.value}",
                "у всех строк одного устройства тип одинаковый; оставьте его только в главной строке",
                source=draft.cell("device_type"),
                related=[typed[0].cell("device_type")],
                tag=draft.tag,
                device=device.name,
            )


def _resolve_dev_no(device: DeviceDraft, bag: DiagnosticBag) -> None:
    numbered = [draft for draft in device.signals if draft.dev_no is not None]
    if not numbered:
        return
    first = numbered[0]
    device.dev_no = first.dev_no
    for draft in numbered[1:]:
        if draft.dev_no != device.dev_no:
            bag.add(
                "IOL303",
                f"номер устройства {draft.dev_no} не совпадает с {device.dev_no}",
                "у устройства один dev_no; оставьте его только в главной строке",
                source=draft.cell("dev_no"),
                related=[first.cell("dev_no")],
                tag=draft.tag,
                device=device.name,
            )
    assert device.dev_no is not None
    if not DEV_NO_MIN <= device.dev_no <= DEV_NO_MAX:
        bag.add(
            "IOL310",
            f"номер устройства {device.dev_no} вне {DEV_NO_MIN}…{DEV_NO_MAX}",
            "dev_no — стабильный номер 1…9999: номера тревог устройства — dev_no·10 + слот",
            source=first.cell("dev_no"),
            tag=first.tag,
            device=device.name,
        )
        first.invalid.add("dev_no")
        device.dev_no = None


def _column_exists(device: DeviceDraft, name: str) -> bool:
    return name in device.signals[0].columns


def _resolve_roles(device: DeviceDraft, bag: DiagnosticBag) -> None:
    spec = device.spec
    if spec is None:
        return
    if not spec.has_io:
        _resolve_device_row(device, spec, bag)
        return
    explicit = {draft.role for draft in device.signals if draft.role is not None}
    default = spec.single_signal_default
    for draft in device.signals:
        if draft.role is Role.AUX:
            continue  # без входа ФБ: подходит любой тип сигнала, строк AUX может быть сколько угодно
        if draft.role is None:
            if "role" in draft.invalid:
                continue
            if default is not None and default not in explicit and not device.roles.get(default):
                draft.role = default
                draft.role_default = True
            else:
                allowed = ", ".join(role.role.value for role in spec.roles) + ", AUX (сигнал без входа ФБ)"
                bag.add(
                    "IOL304",
                    f"у сигнала {draft.label} устройства {device.name} не задана роль",
                    f"укажите роль сигнала в {spec.device_type.value}: {allowed}",
                    source=draft.cell("role"),
                    tag=draft.tag,
                    device=device.name,
                )
                continue
        role_spec = spec.role(draft.role)
        if role_spec is None:
            allowed = ", ".join(role.role.value for role in spec.roles)
            hint = f"роли {spec.device_type.value}: {allowed}"
            if draft.role in _VFD_ONLY_ROLES and spec.device_type is DeviceType.MOTOR:
                hint = "роль только у MotorVfd: смените тип устройства на MotorVfd"
            bag.add(
                "IOL305",
                f"роль {draft.role.value} недопустима для {spec.device_type.value}",
                hint,
                source=draft.cell("role"),
                tag=draft.tag,
                device=device.name,
            )
            continue
        if draft.signal_type is not None and draft.signal_type not in role_spec.signal_types:
            draft.invalid.add("signal_type")
            allowed = ", ".join(sorted(t.value for t in role_spec.signal_types))
            bag.add(
                "IOL306",
                f"роль {draft.role.value} ({role_spec.title}) не может быть сигналом {draft.signal_type.value}",
                f"для роли {draft.role.value} допустимы: {allowed}",
                source=draft.cell("signal_type"),
                tag=draft.tag,
                device=device.name,
            )
        if draft.role in device.roles:
            first = device.roles[draft.role]
            bag.add(
                "IOL307",
                f"роль {draft.role.value} уже есть у сигнала {first.label}",
                "у устройства каждая роль — один сигнал; проверьте device и role",
                source=draft.cell("role"),
                related=[first.cell("role")],
                tag=draft.tag,
                device=device.name,
            )
            continue
        device.roles[draft.role] = draft
    _resolve_main(device, spec, bag)
    _check_required_roles(device, spec, bag)


def _resolve_device_row(device: DeviceDraft, spec: DeviceTypeSpec, bag: DiagnosticBag) -> None:
    """Устройство без сигналов (Pid): одна строка устройства без signal_type и role, остальные — AUX."""
    kind = spec.device_type.value
    for draft in device.signals:
        if draft.role is Role.AUX:
            continue
        if draft.role is None and "role" in draft.invalid:
            continue
        if draft.role is not None:
            bag.add(
                "IOL305",
                f"роль {draft.role.value} недопустима для {kind}: у него нет сигналов ввода-вывода",
                "привязки ФБ (rPv_eu, xPvValid, xTrack, rOutAct_pct) пишет логика станции (контракт 17.3); "
                "строку устройства оставьте без role, сигнал без ФБ запишите с ролью AUX",
                source=draft.cell("role"),
                tag=draft.tag,
                device=device.name,
            )
            continue
        if draft.signal_type is not None or "signal_type" in draft.invalid:
            bag.add(
                "IOL304",
                f"у сигнала {draft.label} устройства {device.name} ({kind}) не задана роль",
                f"у {kind} нет сигналов ввода-вывода: строка устройства — без signal_type и role, "
                "сигнал без ФБ — с ролью AUX",
                source=draft.cell("role"),
                tag=draft.tag,
                device=device.name,
            )
            continue
        if device.main is None:
            device.main = draft
            device.has_main_role = True
            draft.device_row = True
            continue
        bag.add(
            "IOL307",
            f"у {kind} {device.name} уже есть строка устройства {device.main.label} (строка {device.main.line})",
            f"у {kind} одна строка устройства без signal_type и role; другие строки — сигналы с ролью AUX",
            source=draft.cell("signal_type"),
            related=[device.main.source],
            tag=draft.tag,
            device=device.name,
        )
    if device.main is not None:
        return
    device.main = next((draft for draft in device.signals if draft.device_type is not None), device.signals[0])
    bag.add(
        "IOL308",
        f"у {kind} {device.name} нет строки устройства",
        f"добавьте строку без signal_type и role: device = {device.name}, device_type = {kind}, dev_no, params",
        source=device.main.cell("role"),
        tag=device.main.tag,
        device=device.name,
    )


def _resolve_main(device: DeviceDraft, spec: DeviceTypeSpec, bag: DiagnosticBag) -> None:
    for role in spec.main_roles:
        if role in device.roles:
            device.main = device.roles[role]
            device.has_main_role = True
            return
    if spec.device_type is DeviceType.VALVE and Role.CMD_CLOSE in device.roles:
        # задвижка без CMD_OPEN: об этом сообщит проверка формы управления (IOL312)
        device.main = device.roles[Role.CMD_CLOSE]
        device.has_main_role = True
        return
    device.main = next((draft for draft in device.signals if draft.device_type is not None), device.signals[0])
    names = " или ".join(role.value for role in spec.main_roles)
    if spec.device_type is DeviceType.VALVE:
        names = "CMD_OPEN + CMD_CLOSE (задвижка) или CMD_COIL (соленоид)"
    bag.add(
        "IOL308",
        f"у {spec.device_type.value} {device.name} нет главной строки: роль {names}",
        "главная строка несёт тип устройства, dev_no, уставки, задержки и params — добавьте её",
        source=device.main.cell("role"),
        tag=device.main.tag,
        device=device.name,
    )


def _check_required_roles(device: DeviceDraft, spec: DeviceTypeSpec, bag: DiagnosticBag) -> None:
    for role_spec in spec.roles:
        if not role_spec.required or role_spec.role in device.roles or role_spec.role in spec.main_roles:
            continue
        types = ", ".join(sorted(t.value for t in role_spec.signal_types))
        bag.add(
            "IOL308",
            f"у {spec.device_type.value} {device.name} нет сигнала {role_spec.role.value} ({role_spec.title})",
            f"добавьте строку с device = {device.name}, role = {role_spec.role.value}, тип сигнала {types}",
            source=device.head.source,
            tag=device.head.tag,
            device=device.name,
        )
    if spec.device_type is DeviceType.VALVE:
        _check_valve_form(device, bag)


def _check_valve_form(device: DeviceDraft, bag: DiagnosticBag) -> None:
    has_open, has_close, has_coil = (device.has(r) for r in (Role.CMD_OPEN, Role.CMD_CLOSE, Role.CMD_COIL))
    if has_coil and (has_open or has_close):
        other = device.roles[Role.CMD_OPEN] if has_open else device.roles[Role.CMD_CLOSE]
        bag.add(
            "IOL312",
            f"у арматуры {device.name} одновременно CMD_COIL и {other.role.value if other.role else ''}",
            "задвижка с приводом — CMD_OPEN + CMD_CLOSE, клапан с соленоидом — только CMD_COIL",
            source=other.cell("role"),
            related=[device.roles[Role.CMD_COIL].cell("role")],
            tag=other.tag,
            device=device.name,
        )
    elif has_open != has_close:
        present, missing = (Role.CMD_OPEN, Role.CMD_CLOSE) if has_open else (Role.CMD_CLOSE, Role.CMD_OPEN)
        row = device.roles[present]
        bag.add(
            "IOL312",
            f"у задвижки {device.name} есть {present.value}, но нет {missing.value}",
            f"добавьте строку {missing.value} (DO) или, если это соленоид, оставьте одну роль CMD_COIL",
            source=row.cell("role"),
            tag=row.tag,
            device=device.name,
        )


def _check_device_columns(device: DeviceDraft, bag: DiagnosticBag) -> None:
    if device.main is None or not device.has_main_role:
        return
    for draft in device.signals:
        if draft is device.main:
            continue
        for name in DEVICE_LEVEL_COLUMNS:
            if draft.has(name):
                bag.add(
                    "IOL212",
                    f"колонка {name} заполнена в строке {draft.label}, а читается из главной строки "
                    f"{device.main.label}",
                    f"перенесите значение в главную строку (строка {device.main.line})",
                    source=draft.cell(name),
                    tag=draft.tag,
                    device=device.name,
                )


def _check_dev_no_unique(devices: list[DeviceDraft], bag: DiagnosticBag) -> None:
    seen: dict[int, DeviceDraft] = {}
    for device in devices:
        if device.dev_no is None:
            if (
                device.device_type is not None
                and not any("dev_no" in draft.invalid for draft in device.signals)
                and _column_exists(device, "dev_no")
            ):
                bag.add(
                    "IOL309",
                    f"у устройства {device.name} не задан номер dev_no",
                    "укажите стабильный номер 1…9999 в главной строке; номера не переиспользуйте",
                    source=device.head.cell("dev_no"),
                    tag=device.head.tag,
                    device=device.name,
                )
            continue
        if device.dev_no in seen:
            first = seen[device.dev_no]
            source = next(draft for draft in device.signals if draft.dev_no is not None).cell("dev_no")
            bag.add(
                "IOL311",
                f"номер {device.dev_no} уже у устройства {first.name}",
                "номера устройств уникальны: от них считаются номера тревог (dev_no·10 + слот)",
                source=source,
                related=[first.head.cell("dev_no")],
                tag=device.head.tag,
                device=device.name,
            )
        else:
            seen[device.dev_no] = device


def _resolve_links(devices: list[DeviceDraft], bag: DiagnosticBag) -> None:
    by_key = {device.key: device for device in devices}
    names = [device.name for device in devices]
    for device in devices:
        spec = device.spec
        head = device.head
        for column, link in LINK_COLUMNS.items():
            value: str | None = head.link_power if column == "link_power" else head.link_fb
            if value is None:
                continue
            source = head.cell(column)
            if spec is None:
                continue
            if all(item.column != column for item in spec.links):
                owners = ", ".join(t.value for t in link_owners(column))
                bag.add(
                    "IOL314",
                    f"колонка {column} недопустима для {spec.device_type.value}",
                    f"{column} задаётся только у {owners}; очистите ячейку",
                    source=source,
                    tag=head.tag,
                    device=device.name,
                )
                continue
            target = by_key.get(identifier_key(to_identifier(value)))
            if target is None:
                close = difflib.get_close_matches(value, names, n=1, cutoff=0.6)
                hint = f"возможно, {close[0]}" if close else f"добавьте устройство {link.target.value} {value}"
                bag.add(
                    "IOL313",
                    f"{column}: устройства «{value}» нет в перечне",
                    hint,
                    source=source,
                    tag=head.tag,
                    device=device.name,
                )
                continue
            if target is device:
                bag.add(
                    "IOL314",
                    f"{column}: устройство ссылается само на себя",
                    f"укажите тег устройства {link.target.value}",
                    source=source,
                    tag=head.tag,
                    device=device.name,
                )
                continue
            if target.device_type is not None and target.device_type is not link.target:
                bag.add(
                    "IOL314",
                    f"{column}: {target.name} — {target.device_type.value}, а нужен {link.target.value}",
                    f"{link.title}",
                    source=source,
                    related=[target.head.source],
                    tag=head.tag,
                    device=device.name,
                )
                continue
            device.link_targets[column] = target
