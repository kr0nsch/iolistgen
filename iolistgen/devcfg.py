"""Конфигурация устройства: умолчания DUT, колонки перечня, ``params``, выводы из состава.

Порядок расчёта Cfg (контракт plc-process-lib, 20.1–20.3):

1. значения по умолчанию DUT библиотеки;
2. колонки главной строки: диапазон, уставки, задержки, приоритет тревог, ``dev_no``;
3. ``params`` — любые поля Cfg литералами ST (кроме полей, которые задают колонки);
4. выводы из состава устройства для полей, не заданных в ``params``: нет строки ``RUN_FB`` —
   ``xFbUsed := FALSE``, нет ``ZSO`` — ``xZsoUsed := FALSE``, PV по Modbus ``REAL`` —
   ``eInput := Eng`` и т. д.;
5. зеркало ``CheckConfig`` ФБ: Cfg, которую ФБ отклонит (бит ``wCfgErr``), — ошибка перечня.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from iolistgen.build import DeviceDraft
from iolistgen.catalog import (
    AI_LOWCUT_MAX_PCT,
    ALARM_ID_STEP,
    PCT_FULL,
    PID_DEADBAND_MAX_PCT,
    PID_DFILTER_N_MAX,
    PID_DFILTER_N_MIN,
    STARTS_WINDOW_MAX,
    LeafField,
    PathError,
    leaf_fields,
    resolve_path,
)
from iolistgen.diagnostics import DiagnosticBag
from iolistgen.enums import AlarmPriority, DeviceType, Role, SignalType
from iolistgen.model import CfgOrigin, CfgValue, DeviceCfg, ModbusAddress, ParamAssignment, SourceRef
from iolistgen.stvalues import LiteralError, StScalar, format_real, format_time

_SOLENOIDS = ("SolenoidEto", "SolenoidEtc")
_LIMIT_INDEX = {"hh": 0, "h": 1, "l": 2, "ll": 3}
_LIMIT_COLUMN = {0: "sp_hh", 1: "sp_h", 2: "sp_l", 3: "sp_ll"}


@dataclass
class _Entry:
    value: StScalar
    origin: CfgOrigin
    note: str
    column: str | None = None


class CfgBuilder:
    """Расчёт Cfg одного устройства с сообщениями об ошибках ``params`` и CheckConfig."""

    def __init__(self, device: DeviceDraft, bag: DiagnosticBag, addresses: dict[int, ModbusAddress]) -> None:
        spec = device.spec
        assert spec is not None
        self.device = device
        self.spec = spec
        self.bag = bag
        self.addresses = addresses
        self.head = device.head
        self.leaves: dict[str, LeafField] = {leaf.path: leaf for leaf in leaf_fields(spec.cfg)}
        self.entries: dict[str, _Entry] = {
            path: _Entry(leaf.default, "default", "") for path, leaf in self.leaves.items()
        }
        self.params: list[ParamAssignment] = []

    # --- запись значений -----------------------------------------------------------------------

    def set_column(self, path: str, value: StScalar, column: str, note: str = "") -> None:
        self.entries[path] = _Entry(value, "column", note or f"колонка {column}", column)

    def set_inferred(self, path: str, value: StScalar, note: str) -> None:
        if self.entries[path].origin != "params":
            self.entries[path] = _Entry(value, "inferred", note)

    def value(self, path: str) -> StScalar:
        return self.entries[path].value

    def from_params(self, path: str) -> bool:
        return self.entries[path].origin == "params"

    def report(self, code: str, message: str, hint: str, *paths: str) -> None:
        """Сообщение с местом: ячейка ``params`` или колонки, которая задала поле."""
        self.bag.add(
            code,
            message,
            hint,
            source=self._source(paths),
            tag=self.head.tag,
            device=self.device.name,
        )

    def _source(self, paths: tuple[str, ...]) -> SourceRef:
        for path in paths:
            entry = self.entries.get(path)
            if entry is not None and entry.origin == "params":
                return self.head.cell("params")
        for path in paths:
            entry = self.entries.get(path)
            if entry is not None and entry.column is not None:
                return self.head.cell(entry.column)
        return self.head.source

    # --- шаги ----------------------------------------------------------------------------------

    def build(self) -> DeviceCfg:
        self.apply_columns()
        self.apply_params()
        self.apply_inferences()
        self.check_config()
        return DeviceCfg(
            type_name=self.spec.cfg,
            values=tuple(
                CfgValue(
                    path=path,
                    st_type=leaf.st_type.name,
                    value=self.entries[path].value,
                    default=leaf.default,
                    origin=self.entries[path].origin,
                    note=self.entries[path].note,
                )
                for path, leaf in self.leaves.items()
            ),
        )

    def apply_columns(self) -> None:
        head = self.head
        device_type = self.spec.device_type
        if self.device.dev_no is not None:
            self.set_column("udiAlarmIdBase", self.device.dev_no * ALARM_ID_STEP, "dev_no", note="dev_no · 10")
        delay_on, delay_off = head.delay_on_ms, head.delay_off_ms
        if device_type is DeviceType.ANALOG_INPUT:
            if head.range_min is not None and head.range_max is not None and head.range_min < head.range_max:
                self.set_column("rRangeLo_eu", head.range_min, "range_min")
                self.set_column("rRangeHi_eu", head.range_max, "range_max")
            for name, value in head.setpoints.items():
                index = _LIMIT_INDEX[name]
                column = _LIMIT_COLUMN[index]
                self.set_column(f"astLimit[{index}].xEnable", True, column)
                self.set_column(f"astLimit[{index}].rSetpoint_eu", value, column)
                if delay_on is not None:
                    self.set_column(f"astLimit[{index}].tOnDelay", delay_on, "delay_on_s")
                if delay_off is not None:
                    self.set_column(f"astLimit[{index}].tOffDelay", delay_off, "delay_off_s")
        elif device_type is DeviceType.DIGITAL_INPUT:
            if delay_on is not None:
                self.set_column("tOnDelay", delay_on, "delay_on_s")
            if delay_off is not None:
                self.set_column("tOffDelay", delay_off, "delay_off_s")
        elif device_type in (DeviceType.MOTOR, DeviceType.MOTOR_VFD):
            if delay_on is not None:
                self.set_column("tFbStart", delay_on, "delay_on_s")
            if delay_off is not None:
                self.set_column("tFbStop", delay_off, "delay_off_s")
        elif device_type is DeviceType.VALVE:
            if delay_on is not None:
                self.set_column("tTravel", delay_on, "delay_on_s")
        elif device_type is DeviceType.CONTROL_VALVE and delay_on is not None:
            self.set_column("tDev", delay_on, "delay_on_s")
        elif device_type is DeviceType.PID and _valid_range(head.range_min, head.range_max):
            assert head.range_min is not None and head.range_max is not None
            self.set_column("rPvMin_eu", head.range_min, "range_min")
            self.set_column("rPvMax_eu", head.range_max, "range_max")
        if head.alarm_priority is not None:
            self._apply_priority(head.alarm_priority)

    def _apply_priority(self, priority: AlarmPriority) -> None:
        device_type = self.spec.device_type
        note = "колонка alarm_priority"
        if device_type is DeviceType.ANALOG_INPUT:
            for slot in (0, 3):
                self.set_column(f"astAlarm[{slot}].ePriority", priority.value, "alarm_priority", note)
            for slot in (1, 2):
                self.set_column(
                    f"astAlarm[{slot}].ePriority",
                    priority.step_down().value,
                    "alarm_priority",
                    note + ", на ступень ниже",
                )
        elif device_type is DeviceType.DIGITAL_INPUT:
            self.set_column("astAlarm[0].ePriority", priority.value, "alarm_priority", note)
        else:
            # только слоты этого типа: у Motor (Cfg общая с MotorVfd) слоты 6–7 ПЧ не трогаются
            for alarm in self.spec.alarm_slots:
                path = f"astAlarm[{alarm.index}].ePriority"
                if self.leaves[path].default == AlarmPriority.MEDIUM.value:
                    self.set_column(path, priority.value, "alarm_priority", note)

    def apply_params(self) -> None:
        seen: dict[str, str] = {}
        for param in self.head.params:
            try:
                leaf = resolve_path(self.spec.cfg, param.path)
            except PathError as exc:
                self.bag.add(
                    "IOL502",
                    f"params: {exc.message}",
                    exc.hint or f"поля — в справочнике: iolistgen schema (раздел {self.spec.device_type.value})",
                    source=param.source,
                    tag=self.head.tag,
                    device=self.device.name,
                )
                continue
            if leaf.path in seen:
                self.bag.add(
                    "IOL506",
                    f"params: {leaf.path} задан дважды («{seen[leaf.path]}» и «{param.path}={param.value}»)",
                    "оставьте одно присваивание",
                    source=param.source,
                    tag=self.head.tag,
                    device=self.device.name,
                )
                continue
            seen[leaf.path] = f"{param.path}={param.value}"
            try:
                value = leaf.st_type.parse(param.value)
            except LiteralError as exc:
                self.bag.add(
                    "IOL503",
                    f"params: {leaf.path} ({leaf.st_type.name}) — {exc.message}",
                    exc.hint,
                    source=param.source,
                    tag=self.head.tag,
                    device=self.device.name,
                )
                continue
            reserved = self._reserved(leaf.path)
            if reserved is not None:
                self.bag.add(
                    "IOL504",
                    f"params: {leaf.path} {reserved}",
                    "уберите присваивание из params",
                    source=param.source,
                    tag=self.head.tag,
                    device=self.device.name,
                )
                continue
            entry = self.entries[leaf.path]
            if entry.origin == "column":
                self.bag.add(
                    "IOL505",
                    f"params: {leaf.path} уже задан колонкой {entry.column}",
                    f"оставьте значение в одном месте: в колонке {entry.column} или в params",
                    source=param.source,
                    related=[self.head.cell(entry.column or "params")],
                    tag=self.head.tag,
                    device=self.device.name,
                )
                continue
            if self.spec.device_type is DeviceType.MOTOR and leaf.path.startswith("stVfd."):
                self.bag.add(
                    "IOL508",
                    f"params: {leaf.path} — параметр ПЧ, а устройство Motor (без ПЧ)",
                    "stVfd.* читает только FB_MotorVfd: уберите параметр или смените тип на MotorVfd",
                    source=param.source,
                    tag=self.head.tag,
                    device=self.device.name,
                )
            self.entries[leaf.path] = _Entry(value, "params", "params")
            self.params.append(
                ParamAssignment(
                    path=leaf.path,
                    st_type=leaf.st_type.name,
                    value=value,
                    text=f"{param.path}={param.value}",
                    source=param.source,
                )
            )

    def _reserved(self, path: str) -> str | None:
        if path == "udiAlarmIdBase":
            return "генератор считает из dev_no (dev_no · 10)"
        if self.spec.device_type is DeviceType.ANALOG_INPUT:
            if path == "rRangeLo_eu":
                return "задаётся колонкой range_min"
            if path == "rRangeHi_eu":
                return "задаётся колонкой range_max"
            if path.startswith("astLimit[") and path.endswith((".xEnable", ".rSetpoint_eu")):
                index = int(path[len("astLimit[")])
                return f"задаётся колонкой {_LIMIT_COLUMN[index]}"
        return None

    # --- выводы из состава устройства ----------------------------------------------------------

    def apply_inferences(self) -> None:
        handlers: dict[DeviceType, Callable[[], None]] = {
            DeviceType.ANALOG_INPUT: self._infer_analog,
            DeviceType.MOTOR: self._infer_motor,
            DeviceType.MOTOR_VFD: self._infer_motor,
            DeviceType.VALVE: self._infer_valve,
            DeviceType.CONTROL_VALVE: self._infer_control_valve,
            DeviceType.PID: self._infer_pid,
        }
        handler = handlers.get(self.spec.device_type)
        if handler is not None:
            handler()

    def _infer_analog(self) -> None:
        pv = self.device.roles.get(Role.PV)
        if pv is None or pv.signal_type is not SignalType.MB:
            return
        address = self.addresses.get(id(pv))
        data_type = address.data_type if address is not None else pv.modbus.data_type
        if data_type is None:
            return
        if self.from_params("eInput"):
            if self.value("eInput") not in ("Eng", "Raw"):
                self.report(
                    "IOL509",
                    f"eInput = {self.value('eInput')} у значения по Modbus",
                    "для PV по Modbus допустимы Eng (значение в инж. ед.) и Raw (целое со шкалой rRawLo_cnt…"
                    "rRawHi_cnt)",
                    "eInput",
                )
            return
        if data_type.is_float:
            self.set_inferred("eInput", "Eng", f"PV по Modbus {data_type.value}")
        else:
            self.set_inferred("eInput", "Raw", f"PV по Modbus {data_type.value}")

    def _infer_motor(self) -> None:
        vfd = self.spec.device_type is DeviceType.MOTOR_VFD
        has_fb = self.device.has(Role.RUN_FB)
        fb_from_comm = bool(self.value("stVfd.xFbFromComm")) if vfd else False
        if not has_fb and not fb_from_comm:
            if self.from_params("xFbUsed") and self.value("xFbUsed") is True:
                self.report(
                    "IOL509",
                    "xFbUsed = TRUE, но нет сигнала RUN_FB (ОС «в работе»)",
                    "добавьте строку RUN_FB (DI) или уберите xFbUsed из params",
                    "xFbUsed",
                )
            else:
                self.set_inferred("xFbUsed", False, "нет строки RUN_FB")
        if vfd and has_fb and fb_from_comm and "signal_type" not in self.device.roles[Role.RUN_FB].invalid:
            run_fb = self.device.roles[Role.RUN_FB]
            self.bag.add(
                "IOL315",
                f"сигнал RUN_FB {run_fb.label} не используется: ОС «в работе» берётся из слова состояния ПЧ "
                "(stVfd.xFbFromComm = TRUE)",
                "если ОС заведена проводом, задайте в params stVfd.xFbFromComm=FALSE; иначе удалите строку",
                source=run_fb.cell("role"),
                tag=run_fb.tag,
                device=self.device.name,
            )
        modbus_start = vfd and not self.device.has(Role.CMD_RUN) and self.device.has(Role.VFD_CTW)
        if modbus_start and self.value("stVfd.xCommLossIsFault") is False:
            self.report(
                "IOL316",
                "пуск по Modbus (VFD_CTW), а потеря связи не считается отказом (xCommLossIsFault = FALSE)",
                "при пуске по Modbus ПЛК не остановит ПЧ без связи: оставьте xCommLossIsFault = TRUE и "
                "настройте сторожевой таймер связи в ПЧ",
                "stVfd.xCommLossIsFault",
            )

    def _infer_valve(self) -> None:
        coil = self.device.has(Role.CMD_COIL)
        motorized = self.device.has(Role.CMD_OPEN) or self.device.has(Role.CMD_CLOSE)
        valve_type = str(self.value("eType"))
        if coil and not motorized and valve_type not in _SOLENOIDS:
            self.report(
                "IOL509",
                f"клапан с катушкой (CMD_COIL), а eType = {valve_type}",
                "укажите в params eType=SolenoidEto (под током — открыт) или eType=SolenoidEtc (под током — закрыт)",
                "eType",
            )
        if motorized and not coil and valve_type in _SOLENOIDS:
            self.report(
                "IOL509",
                f"задвижка с CMD_OPEN/CMD_CLOSE, а eType = {valve_type}",
                "для привода «открыть/закрыть» eType = Motorized: уберите eType из params",
                "eType",
            )
        for role, path, title in ((Role.ZSO, "xZsoUsed", "«открыто»"), (Role.ZSC, "xZscUsed", "«закрыто»")):
            if self.device.has(role):
                continue
            if self.from_params(path) and self.value(path) is True:
                self.report(
                    "IOL509",
                    f"{path} = TRUE, но нет концевика {title} (роль {role.value})",
                    f"добавьте строку {role.value} (DI) или уберите {path} из params",
                    path,
                )
            else:
                self.set_inferred(path, False, f"нет строки {role.value}")
        has_tqo, has_tqc = self.device.has(Role.TQO), self.device.has(Role.TQC)
        if has_tqo or has_tqc:
            self.set_inferred("xTorqueUsed", True, "есть строки TQO/TQC")
            if has_tqo != has_tqc:
                present, missing = (Role.TQO, Role.TQC) if has_tqo else (Role.TQC, Role.TQO)
                row = self.device.roles[present]
                self.bag.add(
                    "IOL316",
                    f"у {self.device.name} есть муфта {present.value}, но нет {missing.value}",
                    f"добавьте строку {missing.value}: без неё муфта в этом направлении не контролируется",
                    source=row.cell("role"),
                    tag=row.tag,
                    device=self.device.name,
                )
        elif self.from_params("xTorqueUsed") and self.value("xTorqueUsed") is True:
            self.report(
                "IOL509",
                "xTorqueUsed = TRUE, но нет сигналов муфты TQO/TQC",
                "добавьте строки TQO и TQC (DI) или уберите xTorqueUsed из params",
                "xTorqueUsed",
            )

    def _infer_control_valve(self) -> None:
        has_link = "link_fb" in self.device.link_targets
        if has_link:
            if self.from_params("xFbUsed") and self.value("xFbUsed") is False:
                self.report(
                    "IOL315",
                    "задана ОС положения link_fb, но xFbUsed = FALSE — она не используется",
                    "уберите xFbUsed=FALSE из params или очистите link_fb",
                    "xFbUsed",
                )
            else:
                self.set_inferred("xFbUsed", True, "задана ссылка link_fb")
        elif self.from_params("xFbUsed") and self.value("xFbUsed") is True:
            self.report(
                "IOL509",
                "xFbUsed = TRUE, но не задана ОС положения link_fb",
                "укажите в link_fb тег AI-устройства ОС положения (ZT) или уберите xFbUsed из params",
                "xFbUsed",
            )

    def _infer_pid(self) -> None:
        pv_min, pv_max = self.entries["rPvMin_eu"], self.entries["rPvMax_eu"]
        if pv_min.origin == "column" and pv_max.origin == "column":
            # пределы задания по умолчанию — диапазон PV: задание вне шкалы датчика бессмысленно
            note = "пределы задания — диапазон PV (range_min…range_max)"
            self.set_inferred("rSpMin_eu", pv_min.value, note)
            self.set_inferred("rSpMax_eu", pv_max.value, note)
            return
        if pv_min.origin == "default" and pv_max.origin == "default":
            self.report(
                "IOL213",
                f"у {self.device.name} не задан диапазон PV: ошибка регулятора нормируется по 0…100",
                "укажите range_min и range_max — диапазон датчика PV в инженерных единицах (как у его "
                "AnalogInput) — или rPvMin_eu и rPvMax_eu в params",
                "rPvMin_eu",
            )

    # --- зеркало CheckConfig -------------------------------------------------------------------

    def check_config(self) -> None:
        checks: dict[DeviceType, Callable[[], None]] = {
            DeviceType.ANALOG_INPUT: self._check_analog,
            DeviceType.MOTOR: self._check_motor,
            DeviceType.MOTOR_VFD: self._check_motor,
            DeviceType.VALVE: self._check_valve,
            DeviceType.CONTROL_VALVE: self._check_control_valve,
            DeviceType.PID: self._check_pid,
        }
        check = checks.get(self.spec.device_type)
        if check is not None:
            check()

    def _fail(self, bit: str, message: str, hint: str, *paths: str) -> None:
        self.report("IOL507", f"{bit}: {message}", hint, *paths)

    def _real(self, path: str) -> float:
        return float(self.value(path))

    def _time(self, path: str) -> int:
        return int(self.value(path))

    def _check_analog(self) -> None:
        span = self._real("rRangeHi_eu") - self._real("rRangeLo_eu")
        for index in range(4):
            if self.value(f"astLimit[{index}].xEnable") is not True:
                continue
            path = f"astLimit[{index}].rHyst_eu"
            hyst = self._real(path)
            if hyst < 0 or (span > 0 and hyst >= span):
                name = ("HH", "H", "L", "LL")[index]
                self._fail(
                    "AI_CFG_HYST",
                    f"гистерезис уставки {name} = {format_real(hyst)} вне 0…{format_real(span)} (ширина шкалы)",
                    "гистерезис — не меньше 0 и меньше ширины шкалы range_max − range_min",
                    path,
                )
        low_cut = self._real("rLowCut_pct")
        if not 0 <= low_cut <= AI_LOWCUT_MAX_PCT:
            self._fail(
                "AI_CFG_LOW_CUT",
                f"отсечка rLowCut_pct = {format_real(low_cut)} вне 0…{format_real(AI_LOWCUT_MAX_PCT)} %",
                "укажите отсечку 0…20 % шкалы",
                "rLowCut_pct",
            )
        if self.value("eInput") == "Raw":
            raw_low, raw_high = self._real("rRawLo_cnt"), self._real("rRawHi_cnt")
            if raw_low >= raw_high:
                self._fail(
                    "AI_CFG_RAW_RANGE",
                    f"тип входа Raw, а шкала канала rRawLo_cnt…rRawHi_cnt = {format_real(raw_low)}…"
                    f"{format_real(raw_high)}",
                    "задайте в params шкалу целого значения прибора: rRawLo_cnt=0.0; rRawHi_cnt=10000.0 "
                    "(значения канала при range_min и range_max)",
                    "rRawLo_cnt",
                    "rRawHi_cnt",
                    "eInput",
                )

    def _check_motor(self) -> None:
        if self.value("xFbUsed") is True and (self._time("tFbStart") == 0 or self._time("tFbStop") == 0):
            self._fail(
                "MOT_CFG_FB_TIMES",
                f"ОС используется, а время контроля пуска/останова "
                f"{format_time(self._time('tFbStart'))}/{format_time(self._time('tFbStop'))}",
                "задайте tFbStart и tFbStop больше 0 (колонки delay_on_s и delay_off_s)",
                "tFbStart",
                "tFbStop",
            )
        starts = int(self.value("uiMaxStartsPerHour"))
        if starts > STARTS_WINDOW_MAX:
            self._fail(
                "MOT_CFG_STARTS_LIMIT",
                f"uiMaxStartsPerHour = {starts} больше {STARTS_WINDOW_MAX}",
                f"окно пусков вмещает {STARTS_WINDOW_MAX} отметок: укажите 0…{STARTS_WINDOW_MAX}",
                "uiMaxStartsPerHour",
            )
        window, pulse = self._time("tResetWindow"), self._time("tResetPulse")
        if window == 0 or pulse > window:
            self._fail(
                "MOT_CFG_RESET",
                f"окно сброса tResetWindow = {format_time(window)}, импульс tResetPulse = {format_time(pulse)}",
                "tResetWindow больше 0 и не меньше tResetPulse",
                "tResetWindow",
                "tResetPulse",
            )
        if self.spec.device_type is DeviceType.MOTOR_VFD:
            self._check_vfd()

    def _check_vfd(self) -> None:
        low, high = self._real("stVfd.rSpeedMin_pct"), self._real("stVfd.rSpeedMax_pct")
        if low < 0 or high > 100 or low >= high:
            self._fail(
                "MOT_CFG_VFD_SPEED_LIMITS",
                f"пределы задания {format_real(low)}…{format_real(high)} %",
                "нужно 0 <= rSpeedMin_pct < rSpeedMax_pct <= 100",
                "stVfd.rSpeedMin_pct",
                "stVfd.rSpeedMax_pct",
            )
        for path in ("stVfd.rRampUp_pctps", "stVfd.rRampDown_pctps"):
            if self._real(path) < 0:
                self._fail(
                    "MOT_CFG_VFD_RAMP",
                    f"{path} = {format_real(self._real(path))} < 0",
                    "ограничение скорости изменения задания — не меньше 0",
                    path,
                )
        if self._time("stVfd.tCommLoss") == 0:
            self._fail(
                "MOT_CFG_VFD_COMM",
                "фильтр потери связи tCommLoss = T#0S",
                "задайте tCommLoss больше 0 (по умолчанию T#3S)",
                "stVfd.tCommLoss",
            )
        deviation = self._real("stVfd.rSpeedDev_pct")
        if deviation < 0 or (deviation > 0 and self._time("stVfd.tSpeedDev") == 0):
            self._fail(
                "MOT_CFG_VFD_SPEED_DEV",
                f"рассогласование rSpeedDev_pct = {format_real(deviation)} при tSpeedDev = "
                f"{format_time(self._time('stVfd.tSpeedDev'))}",
                "rSpeedDev_pct не меньше 0; при rSpeedDev_pct > 0 задержка tSpeedDev больше 0",
                "stVfd.rSpeedDev_pct",
                "stVfd.tSpeedDev",
            )

    def _check_valve(self) -> None:
        valve_type = str(self.value("eType"))
        solenoid = valve_type in _SOLENOIDS
        if self._time("tTravel") == 0:
            self._fail(
                "VLV_CFG_TRAVEL",
                "время хода tTravel = T#0S",
                "укажите время хода по паспорту привода с запасом (колонка delay_on_s)",
                "tTravel",
            )
        if solenoid and self.value("eSafePos") == "Stay":
            self._fail(
                "VLV_CFG_SAFE_POS",
                "eSafePos = Stay у клапана с соленоидом",
                "соленоид не может остаться в промежутке: Closed или Open",
                "eSafePos",
            )
        torque_used = self.value("xTorqueUsed") is True
        if self.value("xCloseOnTorque") is True and not torque_used:
            self._fail(
                "VLV_CFG_TORQUE",
                "закрытие по моменту без муфты (xTorqueUsed = FALSE)",
                "добавьте сигналы муфты TQO/TQC или уберите xCloseOnTorque",
                "xCloseOnTorque",
            )
        if torque_used and solenoid:
            self._fail(
                "VLV_CFG_TORQUE",
                "муфта (xTorqueUsed) у клапана с соленоидом",
                "муфта бывает только у электропривода: уберите TQO/TQC",
                "xTorqueUsed",
            )
        if valve_type == "Motorized" and self._time("tReverse") == 0:
            self._fail(
                "VLV_CFG_REVERSE",
                "пауза перед реверсом tReverse = T#0S",
                "задайте паузу больше 0 (по умолчанию T#1S)",
                "tReverse",
            )
        if self._time("tResetWindow") == 0:
            self._fail("VLV_CFG_RESET", "окно сброса tResetWindow = T#0S", "задайте окно больше 0", "tResetWindow")

    def _check_control_valve(self) -> None:
        low, high = self._real("rOutMin_pct"), self._real("rOutMax_pct")
        if low < 0 or high > 100 or low >= high:
            self._fail(
                "CV_CFG_LIMITS",
                f"пределы выхода {format_real(low)}…{format_real(high)} %",
                "нужно 0 <= rOutMin_pct < rOutMax_pct <= 100",
                "rOutMin_pct",
                "rOutMax_pct",
            )
        for path in ("rRateUp_pctps", "rRateDown_pctps"):
            if self._real(path) < 0:
                self._fail(
                    "CV_CFG_RATE",
                    f"{path} = {format_real(self._real(path))} < 0",
                    "скорость изменения выхода — не меньше 0",
                    path,
                )
        safe = self._real("rSafePos_pct")
        if not 0 <= safe <= 100:
            self._fail("CV_CFG_SAFE_POS", f"rSafePos_pct = {format_real(safe)} вне 0…100 %", "0…100 %", "rSafePos_pct")
        if self.value("xFbUsed") is True and (self._real("rDevMax_pct") <= 0 or self._time("tDev") == 0):
            self._fail(
                "CV_CFG_DEVIATION",
                f"контроль рассогласования: rDevMax_pct = {format_real(self._real('rDevMax_pct'))}, "
                f"tDev = {format_time(self._time('tDev'))}",
                "при ОС положения rDevMax_pct > 0 и tDev > 0 (колонка delay_on_s)",
                "rDevMax_pct",
                "tDev",
            )
        tight = self._real("rTightShut_pct")
        if tight < 0 or tight >= high:
            self._fail(
                "CV_CFG_TIGHT_SHUT",
                f"порог плотного закрытия rTightShut_pct = {format_real(tight)} вне 0…{format_real(high)} %",
                "порог не меньше 0 и меньше rOutMax_pct",
                "rTightShut_pct",
            )

    def _check_pid(self) -> None:
        """Зеркало FB_PID.CheckConfig (контракт 17.6); перечисления проверяет разбор литералов."""
        if self._real("rKp") <= 0:
            self._fail("PID_CFG_KP", f"rKp = {format_real(self._real('rKp'))}", "коэффициент усиления больше 0", "rKp")
        for path in ("rTi_s", "rTd_s"):
            if self._real(path) < 0:
                self._fail("PID_CFG_TI_TD", f"{path} = {format_real(self._real(path))} < 0", "не меньше 0", path)
        n_filter = self._real("rDFilterN")
        if self._real("rTd_s") > 0 and not PID_DFILTER_N_MIN <= n_filter <= PID_DFILTER_N_MAX:
            self._fail(
                "PID_CFG_DFILTER",
                f"rDFilterN = {format_real(n_filter)} вне {format_real(PID_DFILTER_N_MIN)}…"
                f"{format_real(PID_DFILTER_N_MAX)} при rTd_s > 0",
                f"фильтр Д: N от {format_real(PID_DFILTER_N_MIN)} до {format_real(PID_DFILTER_N_MAX)}",
                "rDFilterN",
                "rTd_s",
            )
        if self._real("rTt_s") < 0:
            self._fail("PID_CFG_TT", f"rTt_s = {format_real(self._real('rTt_s'))} < 0", "0 — авто, иначе > 0", "rTt_s")
        pv_min, pv_max = self._real("rPvMin_eu"), self._real("rPvMax_eu")
        if pv_min >= pv_max:
            self._fail(
                "PID_CFG_PV_RANGE",
                f"диапазон PV {format_real(pv_min)}…{format_real(pv_max)}",
                "rPvMin_eu меньше rPvMax_eu (колонки range_min и range_max)",
                "rPvMin_eu",
                "rPvMax_eu",
            )
        sp_min, sp_max = self._real("rSpMin_eu"), self._real("rSpMax_eu")
        if sp_min > sp_max:
            self._fail(
                "PID_CFG_SP_RANGE",
                f"пределы задания {format_real(sp_min)}…{format_real(sp_max)}",
                "rSpMin_eu не больше rSpMax_eu (равные — фиксированное задание)",
                "rSpMin_eu",
                "rSpMax_eu",
            )
        out_min, out_max = self._real("rOutMin_pct"), self._real("rOutMax_pct")
        if out_min < 0 or out_max > PCT_FULL or out_min >= out_max:
            self._fail(
                "PID_CFG_OUT_RANGE",
                f"пределы выхода {format_real(out_min)}…{format_real(out_max)} %",
                "нужно 0 <= rOutMin_pct < rOutMax_pct <= 100",
                "rOutMin_pct",
                "rOutMax_pct",
            )
        deadband = self._real("rDeadband_pct")
        if not 0 <= deadband <= PID_DEADBAND_MAX_PCT:
            self._fail(
                "PID_CFG_DEADBAND",
                f"зона нечувствительности rDeadband_pct = {format_real(deadband)} вне "
                f"0…{format_real(PID_DEADBAND_MAX_PCT)} %",
                f"укажите 0…{format_real(PID_DEADBAND_MAX_PCT)} % диапазона PV",
                "rDeadband_pct",
            )
        for path in ("rSpRate_ups", "rOutRate_pctps"):
            if self._real(path) < 0:
                self._fail(
                    "PID_CFG_RATES", f"{path} = {format_real(self._real(path))} < 0", "0 — без ограничения", path
                )
        sample, dt_max = self._time("tSample"), self._time("tDtMax")
        if dt_max == 0 or sample >= dt_max:
            self._fail(
                "PID_CFG_SAMPLE",
                f"период расчёта tSample = {format_time(sample)}, предел шага tDtMax = {format_time(dt_max)}",
                "tDtMax больше 0 и больше tSample",
                "tSample",
                "tDtMax",
            )
        safe = self._real("rSafeOut_pct")
        if not out_min <= safe <= out_max:
            self._fail(
                "PID_CFG_PV_FAIL",
                f"безопасный выход rSafeOut_pct = {format_real(safe)} вне пределов выхода "
                f"{format_real(out_min)}…{format_real(out_max)} %",
                "rSafeOut_pct — внутри rOutMin_pct…rOutMax_pct (проверяется при любом ePvFailAction)",
                "rSafeOut_pct",
            )


def _valid_range(low: float | None, high: float | None) -> bool:
    return low is not None and high is not None and low < high


def build_device_cfg(
    device: DeviceDraft,
    bag: DiagnosticBag,
    addresses: dict[int, ModbusAddress],
) -> tuple[DeviceCfg | None, list[ParamAssignment]]:
    """Cfg устройства и разобранные ``params``; ``None`` — тип устройства неизвестен."""
    if device.spec is None:
        return None, []
    builder = CfgBuilder(device, bag, addresses)
    cfg = builder.build()
    return cfg, builder.params
