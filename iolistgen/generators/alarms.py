"""Тревоги устройств и встроенный генератор ``alarm-list`` (контракт plc-process-lib, 10.4, 19, 20.5).

Номер тревоги — ``dev_no · 10 + слот``, код — ``<DEV>.<SUFFIX>`` (``LT101.HH``, ``P101.FTS``).
Приоритет — из итоговой Cfg устройства (``astAlarm[слот].ePriority``): умолчание библиотеки,
колонка ``alarm_priority`` или ``params``. Слоты с приоритетом ``None`` выключены и в список не
входят (опция ``include_disabled``). Не входят и слоты, условие которых при этом составе
устройства не возникает (опция ``only_possible``): контроль ОС двигателя без ОС, концевики
задвижки без концевиков, выход за диапазон у входа без NE 43 и т. п. (разделы 11–16 контракта).

Тексты: по умолчанию — «описание устройства: смысл слота» (смысл — из каталога библиотеки).
Опция ``templates`` подключает шаблоны текстов библиотеки ``docs/alarm_templates.csv``
(``type;slot;suffix;text_ru;operator_action``, раздел 19): текст и действие оператора берутся
оттуда. Причина и последствие заполняются по шаблонам ``cause`` и ``consequence``, если такие
колонки в файле шаблонов есть.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from iolistgen.catalog import AlarmSlot
from iolistgen.enums import AlarmPriority, DeviceType, Role, SignalType
from iolistgen.generators import csvout
from iolistgen.generators.base import GenerationError, GeneratorContext, GeneratorOption
from iolistgen.generators.stfmt import one_line
from iolistgen.model import Device, IoList
from iolistgen.stvalues import format_seconds

ALARM_COLUMNS = (
    "id",
    "code",
    "tag",
    "slot",
    "priority",
    "text_ru",
    "cause",
    "consequence",
    "operator_action",
    "setpoint",
    "delay_s",
)


@dataclass(frozen=True)
class AlarmTemplate:
    """Строка шаблонов текстов тревог библиотеки."""

    text: str
    operator_action: str = ""
    cause: str = ""
    consequence: str = ""


@dataclass(frozen=True)
class AlarmRow:
    """Тревога устройства."""

    device: Device
    slot: AlarmSlot
    priority: AlarmPriority
    text: str
    cause: str
    consequence: str
    operator_action: str
    setpoint: float | None
    delay_ms: int

    @property
    def alarm_id(self) -> int:
        return self.device.alarm_id_base + self.slot.index

    @property
    def code(self) -> str:
        return f"{self.device.ident}.{self.slot.suffix}"

    def as_dict(self) -> dict[str, csvout.CsvValue]:
        return {
            "id": self.alarm_id,
            "code": self.code,
            "tag": self.device.name,
            "slot": self.slot.index,
            "priority": self.priority.value,
            "text_ru": self.text,
            "cause": self.cause,
            "consequence": self.consequence,
            "operator_action": self.operator_action,
            "setpoint": self.setpoint,
            "delay_s": format_seconds(self.delay_ms),
        }


def load_templates(path: Path) -> dict[tuple[str, int], AlarmTemplate]:
    """Шаблоны ``type;slot;suffix;text_ru;operator_action[;cause;consequence]`` (UTF-8, ``;`` или ``,``)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise GenerationError(f"alarm templates: не удалось прочитать {path} ({exc.strerror})") from exc
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise GenerationError(f"alarm templates: {path} пуст")
    sep = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    reader = csv.DictReader(lines, delimiter=sep)
    required = {"type", "slot", "text_ru"}
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise GenerationError(f"alarm templates: в {path} нет колонок {', '.join(sorted(missing))}")
    result: dict[tuple[str, int], AlarmTemplate] = {}
    for number, row in enumerate(reader, 2):
        try:
            slot = int((row.get("slot") or "").strip())
        except ValueError:
            raise GenerationError(f"alarm templates: {path}, строка {number}: slot — не число") from None
        key = ((row.get("type") or "").strip().casefold(), slot)
        result[key] = AlarmTemplate(
            text=(row.get("text_ru") or "").strip(),
            operator_action=(row.get("operator_action") or "").strip(),
            cause=(row.get("cause") or "").strip(),
            consequence=(row.get("consequence") or "").strip(),
        )
    return result


def _template_type(device_type: DeviceType) -> tuple[str, ...]:
    """Ключи типа в шаблонах: у MotorVfd — свой, затем общий Motor (раздел 19: Motor / MotorVfd)."""
    if device_type is DeviceType.MOTOR_VFD:
        return ("motorvfd", "motor")
    return (device_type.value.casefold(),)


def _setpoint_and_delay(device: Device, slot: AlarmSlot) -> tuple[float | None, int]:
    cfg = device.cfg
    delay = int(cfg.value(f"astAlarm[{slot.index}].tOnDelay"))
    if device.device_type is DeviceType.ANALOG_INPUT and slot.index <= 3:
        enabled = bool(cfg.value(f"astLimit[{slot.index}].xEnable"))
        setpoint = float(cfg.value(f"astLimit[{slot.index}].rSetpoint_eu")) if enabled else None
        return setpoint, delay + int(cfg.value(f"astLimit[{slot.index}].tOnDelay"))
    if device.device_type is DeviceType.DIGITAL_INPUT and slot.index == 0:
        return None, delay + int(cfg.value("tOnDelay"))
    return None, delay


def _channel_fault_wired(device: Device) -> bool:
    """Отказ канала DI/AI приходит: есть строка CHF или главный сигнал идёт по Modbus (статус обмена)."""
    return device.signal(Role.CHF) is not None or device.main.signal_type is SignalType.MB


def slot_possible(device: Device, slot: AlarmSlot) -> bool:
    """Может ли условие слота возникнуть при составе устройства и его Cfg."""
    cfg = device.cfg
    kind = device.device_type
    suffix = slot.suffix
    if kind is DeviceType.ANALOG_INPUT:
        if slot.index <= 3:
            return bool(cfg.value(f"astLimit[{slot.index}].xEnable"))
        if suffix == "OOR":  # вне диапазона — только у входов 4–20 мА (11.3)
            return cfg.value("eInput") in ("MilliAmp", "Norm420")
        return True
    if kind is DeviceType.DIGITAL_INPUT:
        return suffix != "FAIL" or _channel_fault_wired(device)
    if kind in (DeviceType.MOTOR, DeviceType.MOTOR_VFD):
        if suffix in ("FTS", "FBL", "FTP", "UCR"):  # без ОС не формируются (13.6)
            return bool(cfg.value("xFbUsed"))
        if suffix == "EXT":
            return device.signal(Role.FAULT) is not None or kind is DeviceType.MOTOR_VFD
        if suffix == "SPD":
            return float(cfg.value("stVfd.rSpeedDev_pct")) > 0
        return True
    if kind is DeviceType.VALVE:
        zso, zsc = bool(cfg.value("xZsoUsed")), bool(cfg.value("xZscUsed"))
        rules = {
            "FTO": zso,
            "FTC": zsc or bool(cfg.value("xCloseOnTorque")),
            "BLS": zso and zsc,
            "PLS": zso or zsc,
            "TRQ": bool(cfg.value("xTorqueUsed")),
            "EXT": device.signal(Role.FAULT) is not None,
        }
        return rules.get(suffix, True)
    if kind is DeviceType.CONTROL_VALVE:
        if suffix in ("DEV", "FBF"):
            return bool(cfg.value("xFbUsed"))
        if suffix == "POS":
            return device.signal(Role.POS_FAULT) is not None
    return True


def alarm_rows(
    model: IoList,
    templates: dict[tuple[str, int], AlarmTemplate] | None = None,
    *,
    include_disabled: bool = False,
    only_possible: bool = True,
) -> list[AlarmRow]:
    """Тревоги всех устройств по номерам."""
    rows: list[AlarmRow] = []
    for device in model.devices_by_dev_no():
        for slot in device.spec.alarm_slots:
            if only_possible and not slot_possible(device, slot):
                continue
            priority = AlarmPriority(str(device.cfg.value(f"astAlarm[{slot.index}].ePriority")))
            if priority is AlarmPriority.NONE and not include_disabled:
                continue
            template = None
            for key in _template_type(device.device_type):
                template = (templates or {}).get((key, slot.index))
                if template is not None:
                    break
            title = template.text if template is not None and template.text else slot.title
            setpoint, delay = _setpoint_and_delay(device, slot)
            rows.append(
                AlarmRow(
                    device=device,
                    slot=slot,
                    priority=priority,
                    text=f"{one_line(device.description)}: {title}",
                    cause=template.cause if template is not None else "",
                    consequence=template.consequence if template is not None else "",
                    operator_action=template.operator_action if template is not None else "",
                    setpoint=setpoint,
                    delay_ms=delay,
                )
            )
    return rows


class AlarmListGenerator:
    """Список тревог проекта ``docs/alarms.csv`` (контракт plc-process-lib, раздел 19)."""

    name = "alarm-list"
    description = "список тревог устройств docs/alarms.csv: номер, код, приоритет, текст, уставка, задержка"
    options = (
        GeneratorOption("filename", "файл относительно --out", "str", "docs/alarms.csv"),
        csvout.DELIMITER_OPTION,
        csvout.COMMENT_OPTION,
        GeneratorOption(
            "templates", "шаблоны текстов тревог библиотеки (docs/alarm_templates.csv); пусто — встроенные", "str", ""
        ),
        GeneratorOption("include_disabled", "включить слоты с приоритетом None (выключенные)", "bool", False),
        GeneratorOption(
            "only_possible", "только тревоги, условие которых возникает при составе устройства", "bool", True
        ),
    )

    def generate(self, model: IoList, out_dir: Path, ctx: GeneratorContext) -> list[Path]:
        templates = load_templates(Path(ctx.str_option("templates"))) if ctx.str_option("templates") else None
        rows = alarm_rows(
            model,
            templates,
            include_disabled=ctx.bool_option("include_disabled"),
            only_possible=ctx.bool_option("only_possible"),
        )
        notes = [
            "Тревоги устройств: id = dev_no · 10 + слот, code = <DEV>.<SUFFIX>; приоритет — из Cfg устройства; "
            "delay_s — задержка появления (логическая плюс задержка тревоги)"
        ]
        text = csvout.render_csv(ctx, ALARM_COLUMNS, [row.as_dict() for row in rows], notes=notes)
        return [ctx.write_text(str(PurePosixPath(ctx.str_option("filename"))), text)]
