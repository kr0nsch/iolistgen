"""Встроенный генератор ``scada-csv``: универсальный импорт тегов SCADA (CSV) и список тревог для SCADA.

SCADA читает состояние устройства из ``stSts`` экземпляра и пишет команды в ``GVL_Hmi.st<DEV>Cmd``
(контракт plc-process-lib, раздел 1, R2: ``VAR_IN_OUT`` экземпляра снаружи недоступен). Каждая
строка ``scada_tags.csv`` — тег SCADA: имя, описание, тип IEC, доступ, единицы, шкала, пределы
тревог (у значения AI), путь переменной ПЛК и идентификатор узла OPC UA сервера CODESYS
(``ns=<n>;s=|var|<устройство>.<путь>``; номер пространства имён и имя устройства — сверить по
обзору сервера, например в UaExpert).

Сигнал без ФБ (роль ``AUX``) — один тег: переменная ``GVL_IO`` (только чтение), с единицами и
шкалой из перечня; тег идёт после тегов своего устройства, простые сигналы — в конце.

``scada_alarms.csv`` — тревоги устройств для SCADA: номер, код, приоритет, текст и где их видно —
бит ``AlmActive``/``AlmUnack`` и маска квитирования ``Cmd.AckReq``.

Форматы конкретных SCADA здесь не выдумываются: для MasterSCADA 4D документированного формата
импорта тегов не найдено (``docs/GENERATORS.md``, раздел «SCADA»), переменные CODESYS она берёт
обзором сервера OPC UA.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from iolistgen.enums import DeviceType
from iolistgen.fbapi import STRUCTS, StructField, fb_outputs
from iolistgen.generators import csvout
from iolistgen.generators.alarms import AlarmTemplate, alarm_rows, load_templates
from iolistgen.generators.base import GeneratorContext, GeneratorOption
from iolistgen.generators.plc import GVL_DEVICES, GVL_HMI, DeviceBinding, IoVar, PlcModel, build_plc
from iolistgen.generators.stfmt import one_line
from iolistgen.model import Device, IoList, Signal

TAG_COLUMNS = (
    "tag",
    "description",
    "device",
    "dev_no",
    "device_type",
    "hmi_group",
    "data_type",
    "access",
    "units",
    "eng_min",
    "eng_max",
    "alarm_hh",
    "alarm_h",
    "alarm_l",
    "alarm_ll",
    "alarm_priority",
    "plc_path",
    "opcua_node_id",
)

ALARM_COLUMNS = (
    "id",
    "code",
    "device",
    "slot",
    "priority",
    "text",
    "active_tag",
    "unack_tag",
    "ack_tag",
    "bit",
    "setpoint",
    "delay_s",
)

Source = Literal["sts", "out", "cmd"]


@dataclass(frozen=True)
class Point:
    """Тег устройства: имя в SCADA, откуда значение, описание."""

    name: str
    source: Source
    path: str
    description: str = ""


# Общий заголовок состояния и команды — у всех типов (ST_DeviceSts, ST_DeviceCmd)
_COMMON_STS = (
    Point("Mode", "sts", "stCommon.eMode"),
    Point("Ne107", "sts", "stCommon.eNe107"),
    Point("Status", "sts", "stCommon.wStatus"),
    Point("Fault", "sts", "stCommon.wFault"),
    Point("Warning", "sts", "stCommon.wWarning"),
    Point("CfgErr", "sts", "stCommon.wCfgErr"),
    Point("AlmActive", "sts", "stCommon.wAlmActive"),
    Point("AlmUnack", "sts", "stCommon.wAlmUnack"),
    Point("AlmShelved", "sts", "stCommon.wAlmShelved"),
    Point("AlmSuppressed", "sts", "stCommon.wAlmSuppressed"),
    Point("PrioUnack", "sts", "stCommon.ePrioUnack"),
    Point("CmdResult", "sts", "stCommon.eCmdResult"),
    Point("CmdSeq", "sts", "stCommon.uiCmdSeq"),
    Point("DevType", "sts", "stCommon.eDevType"),
)
_COMMON_CMD = (
    Point("Cmd.SetAuto", "cmd", "stCommon.xSetAuto"),
    Point("Cmd.SetManual", "cmd", "stCommon.xSetManual"),
    Point("Cmd.SetOos", "cmd", "stCommon.xSetOos"),
    Point("Cmd.Reset", "cmd", "stCommon.xReset"),
    Point("Cmd.Ack", "cmd", "stCommon.xAck"),
    Point("Cmd.AckReq", "cmd", "stCommon.wAckReq"),
    Point("Cmd.ShelveReq", "cmd", "stCommon.wShelveReq"),
    Point("Cmd.UnshelveReq", "cmd", "stCommon.wUnshelveReq"),
)
_MOTOR = (
    Point("Running", "out", "xRunning"),
    Point("State", "sts", "eState"),
    Point("Interlock", "sts", "wInterlock"),
    Point("PermitMissing", "sts", "wPermitMissing"),
    Point("FirstOut", "sts", "uiFirstOut"),
    Point("InhibitRemain", "sts", "uiInhibitRemain_s"),
    Point("StartsLastHour", "sts", "uiStartsLastHour"),
    Point("RunTime", "sts", "rRunTime_h"),
    Point("Starts", "sts", "udiStarts"),
    Point("RunTimeMaint", "sts", "rRunTimeMaint_h"),
    Point("StartsMaint", "sts", "udiStartsMaint"),
    Point("RunCurrent", "sts", "udiRunCurrent_s"),
)
_MOTOR_CMD = (
    Point("Cmd.Start", "cmd", "xStart"),
    Point("Cmd.Stop", "cmd", "xStop"),
    Point("Cmd.ResetMaint", "cmd", "xResetMaint"),
)
POINTS: dict[DeviceType, tuple[Point, ...]] = {
    DeviceType.ANALOG_INPUT: (
        Point("Value", "sts", "rValue_eu"),
        Point("ValuePct", "sts", "rValue_pct"),
        Point("Valid", "out", "xValid"),
        Point("Raw", "sts", "rIn"),
        Point("Signal", "sts", "eSignal"),
        Point("SubstRemain", "sts", "uiSubstRemain_s"),
        Point("Cmd.SubstValue", "cmd", "rSubstValue_eu"),
    ),
    DeviceType.DIGITAL_INPUT: (
        Point("Value", "out", "xValue"),
        Point("Valid", "out", "xValid"),
        Point("SubstRemain", "sts", "uiSubstRemain_s"),
        Point("Cmd.SubstValue", "cmd", "xSubstValue"),
    ),
    DeviceType.MOTOR: _MOTOR + _MOTOR_CMD,
    DeviceType.MOTOR_VFD: (
        *_MOTOR,
        Point("SpeedRef", "sts", "rSpeedRef_pct"),
        Point("SpeedAct", "sts", "rSpeedAct_pct"),
        Point("SpeedAutoActive", "out", "xSpeedAutoActive"),
        *_MOTOR_CMD,
        Point("Cmd.SpeedSp", "cmd", "rSpeedSp_pct"),
    ),
    DeviceType.VALVE: (
        Point("Opened", "out", "xOpened"),
        Point("Closed", "out", "xClosed"),
        Point("State", "sts", "eState"),
        Point("Interlock", "sts", "wInterlock"),
        Point("PermitMissing", "sts", "wPermitMissing"),
        Point("FirstOut", "sts", "uiFirstOut"),
        Point("TravelRemain", "sts", "uiTravelRemain_s"),
        Point("Cycles", "sts", "udiCycles"),
        Point("CyclesMaint", "sts", "udiCyclesMaint"),
        Point("ActTime", "sts", "rActTime_h"),
        Point("Cmd.Open", "cmd", "xOpen"),
        Point("Cmd.Close", "cmd", "xClose"),
        Point("Cmd.Stop", "cmd", "xStop"),
        Point("Cmd.ResetMaint", "cmd", "xResetMaint"),
    ),
    DeviceType.CONTROL_VALVE: (
        Point("Out", "sts", "rOut_pct"),
        Point("OutmA", "sts", "rOut_mA"),
        Point("PosSp", "sts", "rPosSp_pct"),
        Point("PosFb", "sts", "rPosFb_pct"),
        Point("Deviation", "sts", "rDeviation_pct"),
        Point("Interlock", "sts", "wInterlock"),
        Point("FirstOut", "sts", "uiFirstOut"),
        Point("AutoActive", "out", "xAutoActive"),
        Point("Cmd.PosSpMan", "cmd", "rPosSpMan_pct"),
    ),
}


def _struct_field(struct: str, path: str) -> StructField:
    """Поле структуры по пути ``stCommon.eMode``."""
    current = struct
    field: StructField | None = None
    for part in path.split("."):
        field = next(item for item in STRUCTS[current] if item.name == part)
        current = field.st_type
    assert field is not None
    return field


def _output_field(device_type: DeviceType, name: str) -> StructField:
    return next(item for item in fb_outputs(device_type) if item.name == name)


class ScadaCsvGenerator:
    """Импорт тегов SCADA: универсальный CSV с путями переменных ПЛК и узлами OPC UA."""

    name = "scada-csv"
    description = "импорт тегов SCADA: универсальный CSV (теги, пути ПЛК, узлы OPC UA, тревоги)"
    options = (
        GeneratorOption("dir", "каталог файлов относительно --out", "str", "scada"),
        GeneratorOption("tags_csv", "файл тегов", "str", "scada_tags.csv"),
        GeneratorOption("alarms_csv", "файл тревог (пусто — не писать)", "str", "scada_alarms.csv"),
        csvout.DELIMITER_OPTION,
        csvout.COMMENT_OPTION,
        GeneratorOption(
            "separator", "разделитель частей имени тега: P101.Cmd.Start или P101_Cmd_Start", "choice", ".", (".", "_")
        ),
        GeneratorOption("commands", "теги команд GVL_Hmi.st<DEV>Cmd (запись)", "bool", True),
        GeneratorOption("aux_signals", "теги сигналов без ФБ (роль AUX): переменные GVL_IO, чтение", "bool", True),
        GeneratorOption(
            "diagnostics", "теги общего заголовка stCommon (режим, NE 107, тревоги, команды)", "bool", True
        ),
        GeneratorOption("application", "имя приложения CODESYS в путях переменных", "str", "Application"),
        GeneratorOption("opcua_namespace", "номер пространства имён переменных OPC UA сервера CODESYS", "int", 4),
        GeneratorOption(
            "opcua_device",
            "имя устройства в идентификаторе узла OPC UA (пусто — колонка не заполняется)",
            "str",
            "CODESYS Control Win V3",
        ),
        GeneratorOption("templates", "шаблоны текстов тревог библиотеки (docs/alarm_templates.csv)", "str", ""),
    )

    def generate(self, model: IoList, out_dir: Path, ctx: GeneratorContext) -> list[Path]:
        plc = build_plc(model)
        directory = PurePosixPath(ctx.str_option("dir").strip().strip("/") or ".")
        rows: list[dict[str, csvout.CsvValue]] = []
        aux = ctx.bool_option("aux_signals")
        for binding in plc.by_dev_no():
            rows += self.device_rows(binding, ctx)
            if aux:
                rows += [
                    self.aux_row(signal, binding.device, plc, ctx) for signal in binding.device.signals if signal.is_aux
                ]
        if aux:
            rows += [self.aux_row(signal, None, plc, ctx) for signal in model.plain_signals()]
        notes = [
            "Теги SCADA: состояние — stSts экземпляра GVL_Devices.fb<DEV>, команды — GVL_Hmi.st<DEV>Cmd "
            "(импульсные биты сбрасывает ПЛК), сигналы без ФБ (AUX) — переменные GVL_IO; access R — чтение, "
            "RW — запись",
            "opcua_node_id — узел OPC UA сервера CODESYS (символьная конфигурация: GVL_Devices, GVL_Hmi и для "
            "сигналов AUX — GVL_IO); номер пространства имён и имя устройства сверить по обзору сервера",
        ]
        written = [
            ctx.write_text(
                str(directory / ctx.str_option("tags_csv")), csvout.render_csv(ctx, TAG_COLUMNS, rows, notes=notes)
            )
        ]
        alarms_file = ctx.str_option("alarms_csv").strip()
        if alarms_file:
            templates: dict[tuple[str, int], AlarmTemplate] | None = None
            if ctx.str_option("templates"):
                templates = load_templates(Path(ctx.str_option("templates")))
            sep = ctx.str_option("separator")
            alarm_dicts: list[dict[str, csvout.CsvValue]] = []
            for alarm in alarm_rows(model, templates):
                prefix = alarm.device.ident
                alarm_dicts.append(
                    {
                        "id": alarm.alarm_id,
                        "code": alarm.code,
                        "device": prefix,
                        "slot": alarm.slot.index,
                        "priority": alarm.priority.value,
                        "text": alarm.text,
                        "active_tag": f"{prefix}{sep}AlmActive",
                        "unack_tag": f"{prefix}{sep}AlmUnack",
                        "ack_tag": f"{prefix}{sep}Cmd{sep}AckReq",
                        "bit": alarm.slot.index,
                        "setpoint": alarm.setpoint,
                        "delay_s": alarm.as_dict()["delay_s"],
                    }
                )
            alarm_notes = [
                "Тревоги для SCADA: состояние — бит slot в словах <DEV>.AlmActive и <DEV>.AlmUnack, квитирование — "
                "бит slot в <DEV>.Cmd.AckReq; id = dev_no · 10 + слот"
            ]
            written.append(
                ctx.write_text(
                    str(directory / alarms_file),
                    csvout.render_csv(ctx, ALARM_COLUMNS, alarm_dicts, notes=alarm_notes),
                )
            )
        return written

    def device_rows(self, binding: DeviceBinding, ctx: GeneratorContext) -> list[dict[str, csvout.CsvValue]]:
        device = binding.device
        sep = ctx.str_option("separator")
        points: list[Point] = []
        if ctx.bool_option("diagnostics"):
            points += _COMMON_STS
        points += POINTS[device.device_type]
        if ctx.bool_option("diagnostics"):
            points += _COMMON_CMD
        if not ctx.bool_option("commands"):
            points = [point for point in points if point.source != "cmd"]
        if device.device_type is DeviceType.VALVE and device.cfg.value("eType") != "Motorized":
            points = [point for point in points if point.name != "Cmd.Stop"]  # у соленоида стопа нет
        return [self._row(binding, point, sep, ctx) for point in points]

    def aux_row(
        self, signal: Signal, device: Device | None, plc: PlcModel, ctx: GeneratorContext
    ) -> dict[str, csvout.CsvValue]:
        """Тег сигнала без ФБ: переменная ``GVL_IO``, только чтение (выход пишет код приложения)."""
        var: IoVar = plc.signal_var(signal)
        plc_path = self._plc_path(var.path, ctx)
        return {
            "tag": signal.ident,
            "description": one_line(signal.description),
            "device": device.ident if device is not None else None,
            "dev_no": device.dev_no if device is not None else None,
            "device_type": device.device_type.value if device is not None else None,
            "hmi_group": signal.hmi_group or (device.hmi_group if device is not None else None),
            "data_type": var.st_type,
            "access": "R",
            "units": signal.units,
            "eng_min": signal.range_min,
            "eng_max": signal.range_max,
            "plc_path": plc_path,
            "opcua_node_id": self._node(plc_path, ctx),
        }

    @staticmethod
    def _plc_path(relative: str, ctx: GeneratorContext) -> str:
        application = ctx.str_option("application")
        return f"{application}.{relative}" if application else relative

    @staticmethod
    def _node(plc_path: str, ctx: GeneratorContext) -> str | None:
        opcua_device = ctx.str_option("opcua_device").strip()
        return f"ns={ctx.int_option('opcua_namespace')};s=|var|{opcua_device}.{plc_path}" if opcua_device else None

    def _row(self, binding: DeviceBinding, point: Point, sep: str, ctx: GeneratorContext) -> dict[str, csvout.CsvValue]:
        device = binding.device
        if point.source == "sts":
            field = _struct_field(device.spec.sts, point.path)
            relative = f"{GVL_DEVICES}.{binding.instance}.stSts.{point.path}"
        elif point.source == "out":
            field = _output_field(device.device_type, point.path)
            relative = f"{GVL_DEVICES}.{binding.instance}.{point.path}"
        else:
            field = _struct_field(device.spec.cmd, point.path)
            relative = f"{GVL_HMI}.{binding.cmd}.{point.path}"
        plc_path = self._plc_path(relative, ctx)
        node = self._node(plc_path, ctx)
        units = field.units
        row: dict[str, csvout.CsvValue] = {
            "tag": sep.join([device.ident, *point.name.split(".")]),
            "description": f"{one_line(device.description)}: {point.description or field.description}",
            "device": device.ident,
            "dev_no": device.dev_no,
            "device_type": device.device_type.value,
            "hmi_group": device.hmi_group,
            "data_type": field.scalar_type,
            "access": "RW" if point.source == "cmd" else "R",
            "units": units or None,
            "plc_path": plc_path,
            "opcua_node_id": node,
        }
        if device.device_type is DeviceType.ANALOG_INPUT and point.name in ("Value", "Cmd.SubstValue"):
            main = device.main
            row["units"] = main.units
            row["eng_min"] = main.range_min
            row["eng_max"] = main.range_max
            if point.name == "Value":
                row["alarm_hh"] = device.setpoints.hh
                row["alarm_h"] = device.setpoints.h
                row["alarm_l"] = device.setpoints.l
                row["alarm_ll"] = device.setpoints.ll
                row["alarm_priority"] = device.alarm_priority.value if device.alarm_priority is not None else None
        return row
