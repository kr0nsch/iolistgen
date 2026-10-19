"""Каталог библиотеки plc-process-lib 1.0.0: ФБ, роли сигналов, структуры Cfg, слоты тревог.

Источник — выпуск библиотеки 1.0.0 (контракт ``API.md`` 1.0.0, разделы 4, 5.1, 11–17, 19, 20).
Генератор знает о библиотеке только то, что записано здесь: имена ФБ и DUT, входы и выходы, поля
Cfg с типами и значениями по умолчанию, константы ``GVL_Const``. Изменение библиотеки — изменение
этого модуля; сверка с исходниками библиотеки — ``tests_support/check_library.py``.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache

from iolistgen.enums import AlarmPriority, DeviceType, Direction, Role, SignalType
from iolistgen.modbus import ModbusType
from iolistgen.stvalues import BOOL, REAL, TIME, UDINT, UINT, WORD, StScalar, StType, enum_type

LIBRARY_NAMESPACE = "PL"
LIBRARY_TITLE = "plc-process-lib"
LIBRARY_COMPANY = "plc-portfolio"
LIBRARY_VERSION = "1.0.0"
# Версия ссылки в Library Manager CODESYS (Project Information библиотеки): четыре числа
LIBRARY_REF_VERSION = "1.0.0.0"
ALARM_ID_STEP = 10
DEV_NO_MIN = 1
DEV_NO_MAX = 9999


@dataclass(frozen=True)
class LibraryConstant:
    """Константа ``GVL_Const`` библиотеки (таблица 5.1 контракта): имя, тип и литерал ST."""

    name: str
    st_type: str
    value: str
    description: str


# Таблица 5.1: константы GVL_Const без масок битов (маски — карты битов устройств, генератору не нужны)
GVL_CONST: tuple[LibraryConstant, ...] = (
    LibraryConstant("NE43_FAIL_LOW_MA", "REAL", "3.6", "NE 43: I <= — отказ, мА"),
    LibraryConstant("NE43_MEAS_LOW_MA", "REAL", "3.8", "NE 43: I < — вне диапазона снизу, мА"),
    LibraryConstant("NE43_MEAS_HIGH_MA", "REAL", "20.5", "NE 43: I > — вне диапазона сверху, мА"),
    LibraryConstant("NE43_FAIL_HIGH_MA", "REAL", "21.0", "NE 43: I >= — отказ, мА"),
    LibraryConstant("MA_ZERO", "REAL", "4.0", "ток нуля шкалы, мА"),
    LibraryConstant("MA_SPAN", "REAL", "16.0", "диапазон тока, мА"),
    LibraryConstant("PCT_FULL", "REAL", "100.0", "100 %"),
    LibraryConstant("REAL_SANE_MAX", "REAL", "1.0E30", "|x| больше — мусор (перепутан порядок слов Modbus)"),
    LibraryConstant("AI_LOWCUT_MAX_PCT", "REAL", "20.0", "предел rLowCut_pct, %"),
    LibraryConstant("REAL_EXP_MASK", "DWORD", "16#7F800000", "биты экспоненты REAL (F_IsFinite)"),
    LibraryConstant("WORD_ALL", "WORD", "16#FFFF", "все биты слова"),
    LibraryConstant("WORD_LOW_BYTE", "WORD", "16#00FF", "младший байт wStatus"),
    LibraryConstant("UINT_MAX", "UINT", "65535", "предел счётчиков-секунд в Sts"),
    LibraryConstant("NS_PER_S", "LREAL", "1.0E9", "нс в секунде"),
    LibraryConstant("MS_PER_S", "LREAL", "1000.0", "мс в секунде"),
    LibraryConstant("S_PER_H", "UDINT", "3600", "с в часе"),
    LibraryConstant("DT_ACCUM_MAX", "LTIME", "LTIME#10S", "больший шаг времени не идёт в счётчики наработки"),
    LibraryConstant("DEV_ALARMS_MAX", "UINT", "8", "слотов тревог в устройстве"),
    LibraryConstant("NO_FIRST_OUT", "UINT", "16#FFFF", "первопричины нет (uiFirstOut)"),
    LibraryConstant("STARTS_WINDOW_MAX", "UINT", "30", "ёмкость окна пусков = максимум uiMaxStartsPerHour"),
    LibraryConstant("STARTS_WINDOW", "LTIME", "LTIME#1H", "длина окна пусков"),
    LibraryConstant("PID_DFILTER_N_MIN", "REAL", "2.0", "допустимый rDFilterN, нижняя граница"),
    LibraryConstant("PID_DFILTER_N_MAX", "REAL", "50.0", "допустимый rDFilterN, верхняя граница"),
    LibraryConstant("PID_DEADBAND_MAX_PCT", "REAL", "10.0", "предел зоны нечувствительности, %"),
    LibraryConstant("VLV_UNSEAT_BYPASS", "TIME", "T#2S", "FB_Valve: страгивание с седла без контроля муфты"),
    LibraryConstant("CV_TIGHT_HYST_PCT", "REAL", "1.0", "FB_ControlValve: гистерезис снятия плотного закрытия, %"),
    LibraryConstant("VFD_POWER_UP_DELAY", "TIME", "T#10S", "FB_MotorVfd: готовность ПЧ к обмену после питания"),
    LibraryConstant("AI_ALARM_COUNT", "UINT", "6", "FB_AnalogInput: используемых слотов тревог"),
    LibraryConstant("DI_ALARM_COUNT", "UINT", "2", "FB_DigitalInput: используемых слотов тревог"),
    LibraryConstant("MOT_ALARM_COUNT", "UINT", "8", "FB_Motor: слотов тревог (6–7 формирует только FB_MotorVfd)"),
    LibraryConstant("VLV_ALARM_COUNT", "UINT", "7", "FB_Valve: используемых слотов тревог"),
    LibraryConstant("CV_ALARM_COUNT", "UINT", "4", "FB_ControlValve: используемых слотов тревог"),
    LibraryConstant("PID_ALARM_COUNT", "UINT", "1", "FB_PID: используемых слотов тревог"),
)
GVL_CONST_BY_NAME: dict[str, LibraryConstant] = {constant.name: constant for constant in GVL_CONST}


def _const_float(name: str) -> float:
    return float(GVL_CONST_BY_NAME[name].value)


def _const_int(name: str) -> int:
    text = GVL_CONST_BY_NAME[name].value
    return int(text[3:], 16) if text.startswith("16#") else int(text)


ALARM_SLOTS = _const_int("DEV_ALARMS_MAX")
AI_LOWCUT_MAX_PCT = _const_float("AI_LOWCUT_MAX_PCT")
STARTS_WINDOW_MAX = _const_int("STARTS_WINDOW_MAX")
PCT_FULL = _const_float("PCT_FULL")
PID_DFILTER_N_MIN = _const_float("PID_DFILTER_N_MIN")
PID_DFILTER_N_MAX = _const_float("PID_DFILTER_N_MAX")
PID_DEADBAND_MAX_PCT = _const_float("PID_DEADBAND_MAX_PCT")

E_AI_INPUT_TYPE = enum_type("E_AiInputType", [("MilliAmp", 0), ("Norm420", 1), ("Norm01", 2), ("Eng", 3), ("Raw", 4)])
E_AI_FAIL_VALUE = enum_type("E_AiFailValue", [("HoldLast", 0), ("Substitute", 1)])
E_DI_FAIL_VALUE = enum_type("E_DiFailValue", [("HoldLast", 0), ("ForceFalse", 1), ("ForceTrue", 2)])
E_VALVE_TYPE = enum_type("E_ValveType", [("SolenoidEto", 0), ("SolenoidEtc", 1), ("Motorized", 2)])
E_VALVE_SAFE_POS = enum_type("E_ValveSafePos", [("Closed", 0), ("Open", 1), ("Stay", 2)])
E_CV_FAULT_ACTION = enum_type("E_CvFaultAction", [("Hold", 0), ("SafePos", 1)])
E_ALARM_PRIORITY = enum_type("E_AlarmPriority", [(p.value, p.level) for p in AlarmPriority])

E_AI_ALARM = enum_type("E_AiAlarm", [("HH", 0), ("H", 1), ("L", 2), ("LL", 3), ("Failure", 4), ("OutOfRange", 5)])
E_DI_ALARM = enum_type("E_DiAlarm", [("State", 0), ("Failure", 1)])
E_MOTOR_ALARM = enum_type(
    "E_MotorAlarm",
    [
        ("FailToStart", 0),
        ("FeedbackLost", 1),
        ("FailToStop", 2),
        ("UncommandedRun", 3),
        ("ExtFault", 4),
        ("InterlockTrip", 5),
        ("CommLoss", 6),
        ("SpeedDeviation", 7),
    ],
)
E_VALVE_ALARM = enum_type(
    "E_ValveAlarm",
    [
        ("FailToOpen", 0),
        ("FailToClose", 1),
        ("BothLimits", 2),
        ("PositionLost", 3),
        ("TorqueTrip", 4),
        ("ExtFault", 5),
        ("InterlockAct", 6),
    ],
)
E_CV_ALARM = enum_type("E_CvAlarm", [("Deviation", 0), ("FbFailure", 1), ("PositionerFault", 2), ("InterlockAct", 3)])
E_PID_ACTION = enum_type("E_PidAction", [("Reverse", 0), ("Direct", 1)])
E_PID_PV_FAIL_ACTION = enum_type("E_PidPvFailAction", [("Hold", 0), ("SafeOut", 1), ("ShedToManual", 2)])
E_PID_ALARM = enum_type("E_PidAlarm", [("PvInvalid", 0)])

ST_TYPES: dict[str, StType] = {
    t.name: t
    for t in (
        BOOL,
        REAL,
        TIME,
        UINT,
        UDINT,
        WORD,
        E_AI_INPUT_TYPE,
        E_AI_FAIL_VALUE,
        E_DI_FAIL_VALUE,
        E_VALVE_TYPE,
        E_VALVE_SAFE_POS,
        E_CV_FAULT_ACTION,
        E_PID_ACTION,
        E_PID_PV_FAIL_ACTION,
        E_ALARM_PRIORITY,
    )
}

HOUR_MS = 3_600_000


@dataclass(frozen=True)
class FieldSpec:
    """Поле структуры Cfg: скаляр, вложенная структура или массив структур."""

    name: str
    description: str
    st_type: StType | None = None
    default: StScalar | None = None
    struct: str | None = None
    array: tuple[int, int] | None = None
    index_enum: StType | None = None
    element_defaults: tuple[Mapping[str, StScalar], ...] = ()


def _scalar(name: str, st_type: StType, default: StScalar, description: str) -> FieldSpec:
    return FieldSpec(name=name, st_type=st_type, default=default, description=description)


def _alarm_array(index_enum: StType, priorities: tuple[AlarmPriority, ...]) -> FieldSpec:
    return FieldSpec(
        name="astAlarm",
        description="настройки тревог по слотам",
        struct="ST_AlarmCfg",
        array=(0, ALARM_SLOTS - 1),
        index_enum=index_enum,
        element_defaults=tuple({"ePriority": p.value} for p in priorities),
    )


_ALARM_ID_BASE = _scalar("udiAlarmIdBase", UDINT, 0, "номер первой тревоги устройства (dev_no · 10)")

STRUCTS: dict[str, tuple[FieldSpec, ...]] = {
    "ST_AlarmCfg": (
        _scalar("ePriority", E_ALARM_PRIORITY, AlarmPriority.MEDIUM.value, "приоритет тревоги"),
        _scalar("tOnDelay", TIME, 0, "задержка появления тревоги"),
        _scalar("tOffDelay", TIME, 0, "задержка снятия тревоги"),
        _scalar("tShelveMax", TIME, 8 * HOUR_MS, "максимальный срок shelve; T#0S — откладывать запрещено"),
    ),
    "ST_AiLimitCfg": (
        _scalar("xEnable", BOOL, False, "уставка включена"),
        _scalar("rSetpoint_eu", REAL, 0.0, "уставка, инж. ед."),
        _scalar("rHyst_eu", REAL, 0.0, "гистерезис, инж. ед., не меньше 0"),
        _scalar("tOnDelay", TIME, 0, "задержка срабатывания флага"),
        _scalar("tOffDelay", TIME, 0, "задержка снятия флага"),
    ),
    "ST_AnalogInputCfg": (
        _scalar("eInput", E_AI_INPUT_TYPE, "MilliAmp", "тип входа: мА, нормированный, инж. ед., отсчёты"),
        _scalar("rRangeLo_eu", REAL, 0.0, "значение при 4 мА / 0.0"),
        _scalar("rRangeHi_eu", REAL, 100.0, "значение при 20 мА / 1.0"),
        _scalar("rRawLo_cnt", REAL, 0.0, "только Raw: значение канала при rRangeLo_eu"),
        _scalar("rRawHi_cnt", REAL, 0.0, "только Raw: значение канала при rRangeHi_eu"),
        _scalar("xSqrt", BOOL, False, "корень (расход по перепаду давления)"),
        _scalar("rLowCut_pct", REAL, 0.0, "отсечка малых значений, % шкалы; 0 — нет"),
        _scalar("tFilter", TIME, 0, "постоянная времени фильтра; T#0S — без фильтра"),
        _scalar("tFailDelay", TIME, 2000, "подтверждение отказа и возврата"),
        _scalar("eFailValue", E_AI_FAIL_VALUE, "HoldLast", "значение при отказе"),
        _scalar("rFailValue_eu", REAL, 0.0, "значение при Substitute"),
        _scalar("xLimitsOnFail", BOOL, False, "уставки при отказе считаются по значению отказа"),
        _scalar("xClamp", BOOL, False, "ограничить значение шкалой"),
        FieldSpec(
            name="astLimit",
            description="уставки HH, H, L, LL",
            struct="ST_AiLimitCfg",
            array=(0, 3),
            index_enum=E_AI_ALARM,
        ),
        _scalar("tSubstMax", TIME, 8 * HOUR_MS, "максимальная длительность подмены; T#0S — без ограничения"),
        _ALARM_ID_BASE,
        _alarm_array(
            E_AI_ALARM,
            (
                AlarmPriority.HIGH,
                AlarmPriority.LOW,
                AlarmPriority.LOW,
                AlarmPriority.HIGH,
                AlarmPriority.MEDIUM,
                AlarmPriority.LOW,
                AlarmPriority.NONE,
                AlarmPriority.NONE,
            ),
        ),
    ),
    "ST_DigitalInputCfg": (
        _scalar("xInvert", BOOL, False, "инверсия до задержек (НЗ-контакт)"),
        _scalar("tOnDelay", TIME, 0, "задержка включения"),
        _scalar("tOffDelay", TIME, 0, "задержка отключения"),
        _scalar("eFailValue", E_DI_FAIL_VALUE, "HoldLast", "значение при отказе канала"),
        _scalar("xAlarmOnTrue", BOOL, True, "тревога State при TRUE (FALSE — при FALSE)"),
        _scalar("tSubstMax", TIME, 8 * HOUR_MS, "максимальная длительность подмены"),
        _ALARM_ID_BASE,
        _alarm_array(
            E_DI_ALARM,
            (AlarmPriority.NONE, AlarmPriority.MEDIUM) + (AlarmPriority.NONE,) * 6,
        ),
    ),
    "ST_VfdCfg": (
        _scalar("rSpeedMin_pct", REAL, 0.0, "минимальное задание в работе, %"),
        _scalar("rSpeedMax_pct", REAL, 100.0, "максимальное задание, %"),
        _scalar("rRampUp_pctps", REAL, 0.0, "ограничение роста задания, %/с; 0 — нет"),
        _scalar("rRampDown_pctps", REAL, 0.0, "ограничение спада задания, %/с; 0 — нет"),
        _scalar("xFbFromComm", BOOL, True, "ОС «в работе» из слова состояния ПЧ; FALSE — DI xFbRun"),
        _scalar("xCommLossIsFault", BOOL, True, "потеря связи — отказ; FALSE — только предупреждение"),
        _scalar("tCommLoss", TIME, 3000, "фильтр потери связи"),
        _scalar("rSpeedDev_pct", REAL, 10.0, "допустимое рассогласование задание/факт, %; 0 — без контроля"),
        _scalar("tSpeedDev", TIME, 10_000, "задержка рассогласования"),
    ),
    "ST_MotorCfg": (
        _scalar("xFbUsed", BOOL, True, "ОС «в работе» подключена"),
        _scalar("tFbStart", TIME, 5000, "ожидание ОС при пуске"),
        _scalar("tFbStop", TIME, 5000, "ожидание пропадания ОС при останове"),
        _scalar("tFbLossFilter", TIME, 500, "фильтр пропадания ОС в работе"),
        _scalar("tExtFaultFilter", TIME, 200, "фильтр внешней аварии"),
        _scalar("tMinRun", TIME, 0, "минимальное время работы (остановы от автоматики)"),
        _scalar("tMinStop", TIME, 0, "минимальная пауза перед пуском"),
        _scalar("uiMaxStartsPerHour", UINT, 0, "пусков в час; 0 — без ограничения, не больше 30"),
        _scalar("tResetWindow", TIME, 3000, "окно снятия причин после Reset"),
        _scalar("tResetPulse", TIME, 1000, "длительность импульса xQReset"),
        _scalar("wInterlockMask", WORD, 0xFFFF, "действующие биты wInterlock"),
        _scalar("wPermitMask", WORD, 0xFFFF, "обязательные биты wPermit"),
        _scalar("udiMaintInterval_h", UDINT, 0, "ТО по наработке, ч; 0 — нет"),
        _scalar("udiMaintStarts", UDINT, 0, "ТО по числу пусков; 0 — нет"),
        FieldSpec(name="stVfd", description="параметры ПЧ (только MotorVfd)", struct="ST_VfdCfg"),
        _ALARM_ID_BASE,
        _alarm_array(
            E_MOTOR_ALARM,
            (
                AlarmPriority.MEDIUM,
                AlarmPriority.MEDIUM,
                AlarmPriority.HIGH,
                AlarmPriority.HIGH,
                AlarmPriority.MEDIUM,
                AlarmPriority.NONE,
                AlarmPriority.MEDIUM,
                AlarmPriority.LOW,
            ),
        ),
    ),
    "ST_ValveCfg": (
        _scalar("eType", E_VALVE_TYPE, "Motorized", "тип арматуры"),
        _scalar("xZsoUsed", BOOL, True, "концевик «открыто» подключён"),
        _scalar("xZscUsed", BOOL, True, "концевик «закрыто» подключён"),
        _scalar("tTravel", TIME, 60_000, "максимальное время хода"),
        _scalar("tLimitFilter", TIME, 500, "фильтр «оба концевика» и ухода с концевика"),
        _scalar("tReverse", TIME, 1000, "пауза перед реверсом (Motorized)"),
        _scalar("xTorqueUsed", BOOL, False, "муфта подключена (Motorized)"),
        _scalar("xCloseOnTorque", BOOL, False, "закрытие «по моменту»"),
        _scalar("eSafePos", E_VALVE_SAFE_POS, "Closed", "положение по блокировке"),
        _scalar("wInterlockMask", WORD, 0xFFFF, "действующие биты wInterlock"),
        _scalar("wPermitOpenMask", WORD, 0xFFFF, "обязательные биты wPermitOpen"),
        _scalar("wPermitCloseMask", WORD, 0xFFFF, "обязательные биты wPermitClose"),
        _scalar("tResetWindow", TIME, 3000, "окно снятия причин после Reset"),
        _scalar("udiMaintCycles", UDINT, 0, "ТО по числу циклов; 0 — нет"),
        _ALARM_ID_BASE,
        _alarm_array(
            E_VALVE_ALARM,
            (AlarmPriority.MEDIUM,) * 6 + (AlarmPriority.NONE, AlarmPriority.NONE),
        ),
    ),
    "ST_ControlValveCfg": (
        _scalar("rOutMin_pct", REAL, 0.0, "нижний предел выхода, %"),
        _scalar("rOutMax_pct", REAL, 100.0, "верхний предел выхода, %"),
        _scalar("rRateUp_pctps", REAL, 0.0, "скорость открытия, %/с; 0 — без ограничения"),
        _scalar("rRateDown_pctps", REAL, 0.0, "скорость закрытия, %/с; 0 — без ограничения"),
        _scalar("rTightShut_pct", REAL, 0.0, "плотное закрытие ниже порога; 0 — выключено"),
        _scalar("xOutInvert", BOOL, False, "TRUE: 100 % хода = 4 мА"),
        _scalar("rSafePos_pct", REAL, 0.0, "положение по блокировке и отказу, %"),
        _scalar("eFaultAction", E_CV_FAULT_ACTION, "Hold", "реакция на отказ"),
        _scalar("xFbUsed", BOOL, False, "ОС положения подключена"),
        _scalar("rDevMax_pct", REAL, 5.0, "допуск рассогласования, %"),
        _scalar("tDev", TIME, 30_000, "задержка рассогласования"),
        _scalar("xDevIsFault", BOOL, False, "рассогласование — отказ; FALSE — предупреждение"),
        _scalar("wInterlockMask", WORD, 0xFFFF, "действующие биты wInterlock"),
        _ALARM_ID_BASE,
        _alarm_array(
            E_CV_ALARM,
            (AlarmPriority.LOW, AlarmPriority.LOW, AlarmPriority.MEDIUM) + (AlarmPriority.NONE,) * 5,
        ),
    ),
    "ST_PidCfg": (
        _scalar("eAction", E_PID_ACTION, "Reverse", "действие: Reverse (e = SP − PV) или Direct (e = PV − SP)"),
        _scalar("rKp", REAL, 1.0, "коэффициент усиления, %/%; знак — только через eAction"),
        _scalar("rTi_s", REAL, 30.0, "время интегрирования, с; 0 — без И"),
        _scalar("rTd_s", REAL, 0.0, "время дифференцирования, с; 0 — без Д"),
        _scalar("rDFilterN", REAL, 10.0, "фильтр Д: Tf = Td / N"),
        _scalar("rTt_s", REAL, 0.0, "постоянная слежения anti-windup, с; 0 — авто"),
        _scalar("rPvMin_eu", REAL, 0.0, "нижняя граница диапазона PV для нормировки, инж. ед."),
        _scalar("rPvMax_eu", REAL, 100.0, "верхняя граница диапазона PV, инж. ед."),
        _scalar("rSpMin_eu", REAL, 0.0, "нижний предел задания, инж. ед."),
        _scalar("rSpMax_eu", REAL, 100.0, "верхний предел задания, инж. ед."),
        _scalar("rSpRate_ups", REAL, 0.0, "рампа задания, инж. ед./с; 0 — нет"),
        _scalar("rOutMin_pct", REAL, 0.0, "нижний предел выхода, %"),
        _scalar("rOutMax_pct", REAL, 100.0, "верхний предел выхода, %"),
        _scalar("rOutRate_pctps", REAL, 0.0, "ограничение скорости выхода, %/с; 0 — нет"),
        _scalar("rDeadband_pct", REAL, 0.0, "зона нечувствительности по ошибке, % диапазона PV"),
        _scalar("tSample", TIME, 0, "период расчёта; T#0S — каждый вызов"),
        _scalar("tDtMax", TIME, 2000, "больший шаг времени — разрыв: шаг пропускается"),
        _scalar("ePvFailAction", E_PID_PV_FAIL_ACTION, "Hold", "реакция на недостоверную PV в Auto"),
        _scalar("rSafeOut_pct", REAL, 0.0, "выход при ePvFailAction = SafeOut, %"),
        _scalar("xSpTrackPv", BOOL, False, "в Manual задание следует за PV"),
        _scalar("xUseOutAct", BOOL, False, "обратный расчёт по rOutAct_pct (внешнее насыщение)"),
        _ALARM_ID_BASE,
        _alarm_array(E_PID_ALARM, (AlarmPriority.MEDIUM,) + (AlarmPriority.NONE,) * 7),
    ),
}


@dataclass(frozen=True)
class LeafField:
    """Скалярное поле Cfg с полным путём (``stVfd.rSpeedMin_pct``, ``astLimit[1].rHyst_eu``)."""

    path: str
    st_type: StType
    default: StScalar
    description: str


@cache
def leaf_fields(struct_name: str) -> tuple[LeafField, ...]:
    """Все скалярные поля структуры в порядке объявления, массивы развёрнуты по элементам."""
    result: list[LeafField] = []
    for spec in STRUCTS[struct_name]:
        if spec.st_type is not None:
            default = spec.default if spec.default is not None else False
            result.append(LeafField(spec.name, spec.st_type, default, spec.description))
            continue
        assert spec.struct is not None
        inner = leaf_fields(spec.struct)
        if spec.array is None:
            result.extend(
                LeafField(f"{spec.name}.{leaf.path}", leaf.st_type, leaf.default, leaf.description) for leaf in inner
            )
            continue
        low, high = spec.array
        for index in range(low, high + 1):
            overrides: Mapping[str, StScalar] = spec.element_defaults[index - low] if spec.element_defaults else {}
            for leaf in inner:
                result.append(
                    LeafField(
                        f"{spec.name}[{index}].{leaf.path}",
                        leaf.st_type,
                        overrides.get(leaf.path, leaf.default),
                        leaf.description,
                    )
                )
    return tuple(result)


@cache
def plain_defaults(struct_name: str) -> dict[str, StScalar]:
    """Умолчания полей по их типам — без умолчаний элементов массивов из DUT устройства.

    Нужны для инициализатора массива: элемент, записанный не полностью, получает недостающие
    поля по умолчаниям типа элемента (``ST_AlarmCfg``), а не DUT устройства.
    """
    result: dict[str, StScalar] = {}
    for spec in STRUCTS[struct_name]:
        if spec.st_type is not None:
            result[spec.name] = spec.default if spec.default is not None else False
            continue
        assert spec.struct is not None
        inner = plain_defaults(spec.struct)
        if spec.array is None:
            result.update({f"{spec.name}.{path}": value for path, value in inner.items()})
            continue
        for index in range(spec.array[0], spec.array[1] + 1):
            result.update({f"{spec.name}[{index}].{path}": value for path, value in inner.items()})
    return result


@cache
def _leaf_index(struct_name: str) -> dict[str, LeafField]:
    return {leaf.path.casefold(): leaf for leaf in leaf_fields(struct_name)}


class PathError(ValueError):
    """Путь параметра не найден в структуре Cfg."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[\s*([^\]]+?)\s*\])?$")


def resolve_path(struct_name: str, text: str) -> LeafField:
    """Путь из колонки ``params`` → поле Cfg. Регистр букв не важен (ST).

    Индекс массива — число или имя значения перечисления-индекса:
    ``astLimit[HH]``, ``astAlarm[PL.E_MotorAlarm.FailToStart]``.
    """
    segments = _split_path(text)
    canonical: list[str] = []
    current = struct_name
    specs = STRUCTS[current]
    joined = ""
    for position, segment in enumerate(segments):
        match = _SEGMENT_RE.match(segment)
        if match is None:
            raise PathError(f"«{text}» — неверный путь параметра", "пример пути: astLimit[1].rHyst_eu")
        name, index_text = match.group(1), match.group(2)
        spec = next((s for s in specs if s.name.casefold() == name.casefold()), None)
        if spec is None:
            raise PathError(f"нет поля «{name}» в {current}", _suggest(name, [s.name for s in specs]))
        part = spec.name
        if spec.array is not None:
            if index_text is None:
                raise PathError(
                    f"«{spec.name}» — массив, нужен индекс",
                    f"укажите элемент: {spec.name}[{spec.array[0]}]",
                )
            index = _resolve_index(spec, index_text)
            part = f"{spec.name}[{index}]"
        elif index_text is not None:
            raise PathError(f"«{spec.name}» — не массив", f"уберите индекс: {spec.name}")
        canonical.append(part)
        joined = ".".join(canonical)
        if spec.st_type is not None:
            if position != len(segments) - 1:
                raise PathError(f"«{spec.name}» — скалярное поле, у него нет вложенных полей", f"путь: {joined}")
            return _leaf_index(struct_name)[joined.casefold()]
        assert spec.struct is not None
        current = spec.struct
        specs = STRUCTS[current]
    fields = ", ".join(s.name for s in specs)
    raise PathError(
        f"«{joined}» — структура {current}, задайте её поля по отдельности",
        f"например {joined}.{specs[0].name}; поля: {fields}",
    )


def _split_path(text: str) -> list[str]:
    """Разбить путь по точкам вне квадратных скобок: индекс может быть ``PL.E_AiAlarm.HH``."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text.strip():
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        if char == "." and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return parts


def _resolve_index(spec: FieldSpec, text: str) -> int:
    assert spec.array is not None
    low, high = spec.array
    number: int | None = int(text) if text.isdigit() else None
    if number is None and spec.index_enum is not None:
        name = text.rsplit(".", 1)[-1]
        for member, value in zip(spec.index_enum.members, spec.index_enum.values, strict=True):
            if member.casefold() == name.casefold():
                number = value
                break
    if number is None:
        names = ", ".join(spec.index_enum.members) if spec.index_enum else ""
        raise PathError(
            f"«{text}» — неверный индекс массива {spec.name}",
            f"индекс — число {low}…{high}" + (f" или имя: {names}" if names else ""),
        )
    if not low <= number <= high:
        raise PathError(f"индекс {number} вне границ {spec.name}[{low}..{high}]", f"укажите индекс от {low} до {high}")
    return number


def _suggest(name: str, choices: list[str]) -> str:
    close = difflib.get_close_matches(name, choices, n=1, cutoff=0.6)
    if not close:
        close = [c for c in choices if c.casefold() == name.casefold()]
    return f"возможно, {close[0]}" if close else ""


# --- типы устройств и роли -------------------------------------------------------------------


@dataclass(frozen=True)
class RoleSpec:
    """Роль сигнала: допустимые типы сигнала, вход или выход ФБ (контракт 20.2)."""

    role: Role
    title: str
    signal_types: frozenset[SignalType]
    direction: Direction
    pin: str
    mb_types: frozenset[ModbusType] = frozenset()
    required: bool = False
    main: bool = False
    note: str = ""


@dataclass(frozen=True)
class AlarmSlot:
    """Слот тревоги устройства: индекс, значение перечисления-индекса, суффикс кода (раздел 19)."""

    index: int
    member: str
    suffix: str
    title: str


@dataclass(frozen=True)
class LinkSpec:
    """Колонка ``link_*``: ссылка на другое устройство перечня."""

    column: str
    target: DeviceType
    pins: tuple[str, ...]
    title: str


@dataclass(frozen=True)
class DeviceTypeSpec:
    """Тип устройства перечня и его ФБ в библиотеке."""

    device_type: DeviceType
    title: str
    fb: str
    cmd: str
    cfg: str
    sts: str
    has_retain: bool
    sts_registers: int
    roles: tuple[RoleSpec, ...]
    main_roles: tuple[Role, ...]
    alarm_slots: tuple[AlarmSlot, ...]
    delay_on: str | None
    delay_off: str | None
    links: tuple[LinkSpec, ...] = ()
    notes: tuple[str, ...] = field(default=())
    has_io: bool = True
    """Есть сигналы ввода-вывода и вызов в ``PRG_Devices``; ``False`` — строка устройства без
    сигнала (Pid): экземпляр, Cmd, Cfg, Retain, Sts и тревоги есть, вызов пишет логика станции."""

    def role(self, role: Role) -> RoleSpec | None:
        return next((spec for spec in self.roles if spec.role is role), None)

    @property
    def single_signal_default(self) -> Role | None:
        """Роль по умолчанию для строки без роли (AnalogInput — PV, DigitalInput — IN)."""
        if self.device_type in (DeviceType.ANALOG_INPUT, DeviceType.DIGITAL_INPUT):
            return self.main_roles[0]
        return None

    def qualified(self, name: str, namespace: str = LIBRARY_NAMESPACE) -> str:
        return f"{namespace}.{name}" if namespace else name


_NUMERIC_MB = frozenset(t for t in ModbusType if t.is_numeric)
_BOOL_MB = frozenset({ModbusType.BOOL})
_WORD_MB = frozenset(t for t in ModbusType if t.is_bitstring)
_HW_IN = frozenset({SignalType.DI})
_HW_OUT = frozenset({SignalType.DO})

_LINK_POWER = LinkSpec(
    column="link_power",
    target=DeviceType.DIGITAL_INPUT,
    pins=("xPowerOk",),
    title="DI-устройство «напряжение»: xPowerOk := fb<LINK>.xValue",
)
_LINK_FB = LinkSpec(
    column="link_fb",
    target=DeviceType.ANALOG_INPUT,
    pins=("rPosFb_pct", "xPosFbValid"),
    title="AI-устройство ОС положения: rPosFb_pct := fb<LINK>.rValue_pct, xPosFbValid := fb<LINK>.xValid",
)


def _motor_roles(*, vfd: bool) -> tuple[RoleSpec, ...]:
    roles = [
        RoleSpec(
            Role.CMD_RUN,
            "команда «Работа» (удерживаемая)",
            _HW_OUT,
            Direction.OUT,
            "xQRun",
            required=not vfd,
            main=True,
        ),
        RoleSpec(
            Role.RUN_FB,
            "ОС «в работе»",
            _HW_IN,
            Direction.IN,
            "xFbRun",
            note=(
                "по умолчанию ОС — из слова состояния ПЧ (stVfd.xFbFromComm = TRUE); без строки и при "
                "xFbFromComm = FALSE — xFbUsed := FALSE"
                if vfd
                else "без строки — xFbUsed := FALSE"
            ),
        ),
        RoleSpec(Role.FAULT, "внешняя авария (тепловое реле, автомат, УПП)", _HW_IN, Direction.IN, "xExtFault"),
        RoleSpec(Role.LOCAL, "переключатель «Местное»", _HW_IN, Direction.IN, "xLocal"),
        RoleSpec(Role.CMD_RESET, "импульс сброса аварии УПП или ПЧ", _HW_OUT, Direction.OUT, "xQReset"),
    ]
    if vfd:
        roles += [
            RoleSpec(
                Role.VFD_CTW,
                "слово управления ПЧ",
                frozenset({SignalType.MB}),
                Direction.OUT,
                "адаптер ПЧ ← xQRun, xQReset",
                mb_types=_WORD_MB,
                main=True,
                note="при пуске по Modbus",
            ),
            RoleSpec(
                Role.VFD_STW,
                "слово состояния ПЧ",
                frozenset({SignalType.MB}),
                Direction.IN,
                "адаптер ПЧ → xVfdRunning, xVfdReady, xVfdFault",
                mb_types=_WORD_MB,
                required=True,
            ),
            RoleSpec(
                Role.SPEED_REF,
                "задание скорости (частоты) ПЧ",
                frozenset({SignalType.MB, SignalType.AO}),
                Direction.OUT,
                "rSpeedRef_pct (через адаптер)",
                mb_types=_NUMERIC_MB,
                required=True,
            ),
            RoleSpec(
                Role.SPEED_ACT,
                "фактическая скорость (частота) ПЧ",
                frozenset({SignalType.MB, SignalType.AI}),
                Direction.IN,
                "rSpeedAct_pct (через адаптер)",
                mb_types=_NUMERIC_MB,
                required=True,
            ),
        ]
    return tuple(roles)


_MOTOR_SLOTS = (
    AlarmSlot(0, "FailToStart", "FTS", "нет подтверждения пуска"),
    AlarmSlot(1, "FeedbackLost", "FBL", "пропала ОС в работе"),
    AlarmSlot(2, "FailToStop", "FTP", "не остановился"),
    AlarmSlot(3, "UncommandedRun", "UCR", "самопроизвольный пуск"),
    AlarmSlot(4, "ExtFault", "EXT", "внешняя авария"),
    AlarmSlot(5, "InterlockTrip", "ILK", "останов блокировкой"),
)
_VFD_SLOTS = (
    AlarmSlot(6, "CommLoss", "COM", "потеря связи с ПЧ"),
    AlarmSlot(7, "SpeedDeviation", "SPD", "рассогласование скорости"),
)

DEVICE_TYPES: dict[DeviceType, DeviceTypeSpec] = {
    spec.device_type: spec
    for spec in (
        DeviceTypeSpec(
            device_type=DeviceType.ANALOG_INPUT,
            title="аналоговый вход: масштабирование, NE 43, уставки HH/H/L/LL",
            fb="FB_AnalogInput",
            cmd="ST_AnalogInputCmd",
            cfg="ST_AnalogInputCfg",
            sts="ST_AnalogInputSts",
            has_retain=False,
            sts_registers=22,
            roles=(
                RoleSpec(
                    Role.PV,
                    "измеряемое значение",
                    frozenset({SignalType.AI, SignalType.MB}),
                    Direction.IN,
                    "rIn",
                    mb_types=_NUMERIC_MB,
                    required=True,
                    main=True,
                ),
                RoleSpec(
                    Role.CHF,
                    "отказ канала (диагностика модуля)",
                    frozenset({SignalType.DI, SignalType.MB}),
                    Direction.IN,
                    "xChannelFault",
                    mb_types=_BOOL_MB,
                    note=(
                        "без строки — FALSE, у PV по Modbus — нет обмена со слейвом; со строкой у PV по Modbus — "
                        "CHF OR нет обмена"
                    ),
                ),
            ),
            main_roles=(Role.PV,),
            alarm_slots=(
                AlarmSlot(0, "HH", "HH", "верхний аварийный предел"),
                AlarmSlot(1, "H", "H", "верхний предупредительный предел"),
                AlarmSlot(2, "L", "L", "нижний предупредительный предел"),
                AlarmSlot(3, "LL", "LL", "нижний аварийный предел"),
                AlarmSlot(4, "Failure", "FAIL", "отказ сигнала"),
                AlarmSlot(5, "OutOfRange", "OOR", "выход за диапазон"),
            ),
            delay_on="astLimit[i].tOnDelay",
            delay_off="astLimit[i].tOffDelay",
        ),
        DeviceTypeSpec(
            device_type=DeviceType.DIGITAL_INPUT,
            title="дискретный вход: инверсия, задержки, подмена, тревога по состоянию",
            fb="FB_DigitalInput",
            cmd="ST_DigitalInputCmd",
            cfg="ST_DigitalInputCfg",
            sts="ST_DigitalInputSts",
            has_retain=False,
            sts_registers=15,
            roles=(
                RoleSpec(
                    Role.IN,
                    "дискретный сигнал",
                    frozenset({SignalType.DI, SignalType.MB}),
                    Direction.IN,
                    "xIn",
                    mb_types=_BOOL_MB,
                    required=True,
                    main=True,
                ),
                RoleSpec(
                    Role.CHF,
                    "отказ канала (обрыв, КЗ, модуль)",
                    frozenset({SignalType.DI, SignalType.MB}),
                    Direction.IN,
                    "xChannelFault",
                    mb_types=_BOOL_MB,
                    note=(
                        "без строки — FALSE, у IN по Modbus — нет обмена со слейвом; со строкой у IN по Modbus — "
                        "CHF OR нет обмена"
                    ),
                ),
            ),
            main_roles=(Role.IN,),
            alarm_slots=(
                AlarmSlot(0, "State", "ALM", "тревожное состояние"),
                AlarmSlot(1, "Failure", "FAIL", "отказ канала"),
            ),
            delay_on="tOnDelay",
            delay_off="tOffDelay",
        ),
        DeviceTypeSpec(
            device_type=DeviceType.MOTOR,
            title="двигатель прямого пуска или с УПП",
            fb="FB_Motor",
            cmd="ST_MotorCmd",
            cfg="ST_MotorCfg",
            sts="ST_MotorSts",
            has_retain=True,
            sts_registers=34,
            roles=_motor_roles(vfd=False),
            main_roles=(Role.CMD_RUN,),
            alarm_slots=_MOTOR_SLOTS,
            delay_on="tFbStart",
            delay_off="tFbStop",
            links=(_LINK_POWER,),
        ),
        DeviceTypeSpec(
            device_type=DeviceType.MOTOR_VFD,
            title="двигатель с ПЧ (адаптер Modbus — код приложения)",
            fb="FB_MotorVfd",
            cmd="ST_MotorCmd",
            cfg="ST_MotorCfg",
            sts="ST_MotorSts",
            has_retain=True,
            sts_registers=34,
            roles=_motor_roles(vfd=True),
            main_roles=(Role.CMD_RUN, Role.VFD_CTW),
            alarm_slots=_MOTOR_SLOTS + _VFD_SLOTS,
            delay_on="tFbStart",
            delay_off="tFbStop",
            links=(_LINK_POWER,),
            notes=("главная строка — CMD_RUN (DO) или VFD_CTW (MB), одна из двух обязательна",),
        ),
        DeviceTypeSpec(
            device_type=DeviceType.VALVE,
            title="запорная арматура: задвижка с электроприводом или клапан с соленоидом",
            fb="FB_Valve",
            cmd="ST_ValveCmd",
            cfg="ST_ValveCfg",
            sts="ST_ValveSts",
            has_retain=True,
            sts_registers=26,
            roles=(
                RoleSpec(Role.CMD_OPEN, "команда «Открывать»", _HW_OUT, Direction.OUT, "xQOpen", main=True),
                RoleSpec(Role.CMD_CLOSE, "команда «Закрывать»", _HW_OUT, Direction.OUT, "xQClose"),
                RoleSpec(Role.CMD_COIL, "катушка соленоида", _HW_OUT, Direction.OUT, "xQCoil", main=True),
                RoleSpec(
                    Role.ZSO, "концевик «Открыто»", _HW_IN, Direction.IN, "xZso", note="без строки — xZsoUsed := FALSE"
                ),
                RoleSpec(
                    Role.ZSC, "концевик «Закрыто»", _HW_IN, Direction.IN, "xZsc", note="без строки — xZscUsed := FALSE"
                ),
                RoleSpec(Role.TQO, "муфта в сторону открытия", _HW_IN, Direction.IN, "xTorqueOpen"),
                RoleSpec(Role.TQC, "муфта в сторону закрытия", _HW_IN, Direction.IN, "xTorqueClose"),
                RoleSpec(Role.FAULT, "авария привода", _HW_IN, Direction.IN, "xExtFault"),
                RoleSpec(Role.LOCAL, "«Местное» на приводе или шкафу", _HW_IN, Direction.IN, "xLocal"),
            ),
            main_roles=(Role.CMD_OPEN, Role.CMD_COIL),
            alarm_slots=(
                AlarmSlot(0, "FailToOpen", "FTO", "не открылась"),
                AlarmSlot(1, "FailToClose", "FTC", "не закрылась"),
                AlarmSlot(2, "BothLimits", "BLS", "оба концевика"),
                AlarmSlot(3, "PositionLost", "PLS", "уход с концевика"),
                AlarmSlot(4, "TorqueTrip", "TRQ", "муфта в ходе"),
                AlarmSlot(5, "ExtFault", "EXT", "авария привода"),
                AlarmSlot(6, "InterlockAct", "ILK", "действует блокировка"),
            ),
            delay_on="tTravel",
            delay_off=None,
            links=(_LINK_POWER,),
            notes=(
                "формы управления: CMD_OPEN + CMD_CLOSE (eType := Motorized) или CMD_COIL "
                "(eType := SolenoidEto или SolenoidEtc через params)",
            ),
        ),
        DeviceTypeSpec(
            device_type=DeviceType.CONTROL_VALVE,
            title="регулирующий клапан с позиционером 4–20 мА",
            fb="FB_ControlValve",
            cmd="ST_ControlValveCmd",
            cfg="ST_ControlValveCfg",
            sts="ST_ControlValveSts",
            has_retain=True,
            sts_registers=26,
            roles=(
                RoleSpec(
                    Role.POS_OUT,
                    "задание положения на позиционер",
                    frozenset({SignalType.AO}),
                    Direction.OUT,
                    "rOut_mA",
                    required=True,
                    main=True,
                ),
                RoleSpec(Role.POS_FAULT, "авария позиционера", _HW_IN, Direction.IN, "xPositionerFault"),
                RoleSpec(Role.LOCAL, "позиционер в местном (байпас, маховик)", _HW_IN, Direction.IN, "xLocal"),
            ),
            main_roles=(Role.POS_OUT,),
            alarm_slots=(
                AlarmSlot(0, "Deviation", "DEV", "рассогласование положения"),
                AlarmSlot(1, "FbFailure", "FBF", "отказ ОС положения"),
                AlarmSlot(2, "PositionerFault", "POS", "авария позиционера"),
                AlarmSlot(3, "InterlockAct", "ILK", "действует блокировка"),
            ),
            delay_on="tDev",
            delay_off=None,
            links=(_LINK_FB,),
        ),
        DeviceTypeSpec(
            device_type=DeviceType.PID,
            title="ПИД-регулятор: строка устройства без сигналов, вызов ФБ — в логике станции",
            fb="FB_PID",
            cmd="ST_PidCmd",
            cfg="ST_PidCfg",
            sts="ST_PidSts",
            has_retain=True,
            sts_registers=32,
            roles=(),
            main_roles=(),
            alarm_slots=(AlarmSlot(0, "PvInvalid", "PVF", "недостоверная регулируемая величина"),),
            delay_on=None,
            delay_off=None,
            notes=(
                "строка устройства — без signal_type и role: device_type = Pid, dev_no, диапазон PV, params; "
                "привязки rPv_eu, xPvValid, xTrack, rOutAct_pct пишет логика станции (контракт 17.3)",
            ),
            has_io=False,
        ),
    )
}

# Роль AUX (расширение схемы iolistgen): сигнал без входа и выхода ФБ — в устройстве (сколько угодно
# строк) или отдельной строкой без device и device_type. Тип сигнала — любой.
AUX_TITLE = "сигнал без входа и выхода ФБ: переменная GVL_IO, карта Modbus, SCADA, документация"
AUX_SIGNAL_TYPES = frozenset(SignalType)

LINK_COLUMNS: dict[str, LinkSpec] = {_LINK_POWER.column: _LINK_POWER, _LINK_FB.column: _LINK_FB}
ROLE_DIRECTIONS: dict[Role, Direction] = {
    spec.role: spec.direction for device in DEVICE_TYPES.values() for spec in device.roles
}


def link_owners(column: str) -> tuple[DeviceType, ...]:
    """Типы устройств, у которых допустима колонка ``link_*``."""
    return tuple(t for t, spec in DEVICE_TYPES.items() if any(link.column == column for link in spec.links))
