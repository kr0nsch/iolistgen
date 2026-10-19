"""Интерфейс ФБ библиотеки plc-process-lib: входы и выходы, структуры Cmd, Sts и Retain.

Источник — выпуск plc-process-lib 1.0.0 (контракт ``API.md`` 1.0.0): разделы 4.1–4.3, 4.6
(раскладка Sts для обмена), 9.1, 11.1–17.2. Здесь только то, что нужно генераторам: имена и типы
входов и выходов экземпляров (вызовы в ``PRG_Devices``), поля команд (теги SCADA), поля состояния
с их смещениями (карта Modbus slave и теги SCADA), энергонезависимые данные. Поля Cfg — в
``catalog.py``. Изменение библиотеки — изменение этого модуля и заглушки ``tests_support/pl_stub/``:
заглушку с каталогом сверяет тест ``pytests/test_pl_stub.py``, каталог и заглушку с исходниками
библиотеки — скрипт ``tests_support/check_library.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from iolistgen.catalog import DEVICE_TYPES
from iolistgen.enums import DeviceType

REGISTER_BYTES = 2

# Размер типов ST в байтах для раскладки Sts. В Sts по контракту (4.6) только 16- и 32-битные
# поля; перечисления библиотеки — на INT.
_SCALAR_BYTES = {
    "BOOL": 1,
    "WORD": 2,
    "INT": 2,
    "UINT": 2,
    "REAL": 4,
    "UDINT": 4,
    "DWORD": 4,
    "TIME": 4,
}

# Перечисления библиотеки с явными значениями (раздел 4.1 и разделы ФБ)
ENUMS: dict[str, tuple[tuple[str, int], ...]] = {
    "E_DeviceMode": (("Auto", 1), ("Manual", 2), ("Local", 3), ("OutOfService", 4)),
    "E_DeviceType": (
        ("None", 0),
        ("AnalogInput", 1),
        ("DigitalInput", 2),
        ("Motor", 3),
        ("MotorVfd", 4),
        ("Valve", 5),
        ("ControlValve", 6),
        ("Pid", 7),
    ),
    "E_Ne107Status": (
        ("Good", 0),
        ("MaintenanceRequired", 1),
        ("OutOfSpecification", 2),
        ("CheckFunction", 3),
        ("Failure", 4),
    ),
    "E_CmdResult": (
        ("None", 0),
        ("Accepted", 1),
        ("RejectedMode", 2),
        ("RejectedInterlock", 3),
        ("RejectedPermit", 4),
        ("RejectedInhibit", 5),
        ("RejectedFault", 6),
        ("RejectedState", 7),
        ("RejectedNotSupported", 8),
        ("RejectedCfg", 9),
        ("SubstExpired", 10),
    ),
    "E_AlarmPriority": (("None", 0), ("Low", 1), ("Medium", 2), ("High", 3), ("Critical", 4)),
    # причина перехода тревоги в событии ST_AlarmEvent (журнал I_AlarmSink, раздел 10.2)
    "E_AlarmEventReason": (
        ("None", 0),
        ("Activated", 1),
        ("Cleared", 2),
        ("Acked", 3),
        ("Shelved", 4),
        ("Unshelved", 5),
        ("ShelveExpired", 6),
        ("Suppressed", 7),
        ("Unsuppressed", 8),
        ("OosOn", 9),
        ("OosOff", 10),
        ("Disabled", 11),
    ),
    "E_AiSignalState": (
        ("Good", 0),
        ("UnderRange", 1),
        ("OverRange", 2),
        ("FailLow", 3),
        ("FailHigh", 4),
        ("ChannelFault", 5),
        ("NotFinite", 6),
    ),
    "E_MotorState": (("Stopped", 0), ("Starting", 1), ("Running", 2), ("Stopping", 3), ("Fault", 4)),
    "E_ValveState": (
        ("Unknown", 0),
        ("Closed", 1),
        ("Opening", 2),
        ("Open", 3),
        ("Closing", 4),
        ("Intermediate", 5),
        ("Reversing", 6),
        ("Fault", 7),
    ),
}


@dataclass(frozen=True)
class StructField:
    """Поле структуры или вход/выход ФБ: имя, тип ST, начальное значение, смысл."""

    name: str
    st_type: str
    description: str
    default: str = ""
    units: str = ""

    @property
    def is_struct(self) -> bool:
        return self.st_type in STRUCTS

    @property
    def is_enum(self) -> bool:
        return self.st_type in ENUMS

    @property
    def scalar_type(self) -> str:
        """Тип значения для SCADA и карты обмена: перечисления — INT (базовый тип, 2.7)."""
        return "INT" if self.is_enum else self.st_type


def _f(name: str, st_type: str, description: str, default: str = "", units: str = "") -> StructField:
    return StructField(name, st_type, description, default, units)


STRUCTS: dict[str, tuple[StructField, ...]] = {
    "ST_DeviceCmd": (
        _f("xSetAuto", "BOOL", "импульс: в Auto (AI/DI: измерение; выход из OOS)"),
        _f("xSetManual", "BOOL", "импульс: в Manual (AI/DI: подмена; выход из OOS)"),
        _f("xSetOos", "BOOL", "импульс: вывести из работы"),
        _f("xReset", "BOOL", "импульс: сброс зафиксированных отказов и квитирование всех тревог"),
        _f("xAck", "BOOL", "импульс: квитировать все тревоги"),
        _f("wAckReq", "WORD", "маска: квитировать тревоги слотов (бит i — слот i)"),
        _f("wShelveReq", "WORD", "маска: отложить тревоги слотов"),
        _f("wUnshelveReq", "WORD", "маска: вернуть отложенные тревоги"),
    ),
    "ST_DeviceSts": (
        _f("wStatus", "WORD", "слово состояния: биты 0–7 по типу, 8–15 общие"),
        _f("wFault", "WORD", "причины отказа (карта по типу)"),
        _f("wWarning", "WORD", "предупреждения (карта по типу)"),
        _f("wCfgErr", "WORD", "непройденные проверки Cfg"),
        _f("eMode", "E_DeviceMode", "режим: 1 Auto, 2 Manual, 3 Local, 4 OutOfService", "E_DeviceMode.Manual"),
        _f("eNe107", "E_Ne107Status", "статус NE 107: 0 Good, 1 M, 2 S, 3 C, 4 F", "E_Ne107Status.CheckFunction"),
        _f("eCmdResult", "E_CmdResult", "результат последней команды", "E_CmdResult.None"),
        _f("uiCmdSeq", "UINT", "счётчик обработанных команд (по кругу)"),
        _f("wAlmActive", "WORD", "бит i: условие тревоги слота i активно"),
        _f("wAlmUnack", "WORD", "бит i: тревога слота i не квитирована"),
        _f("wAlmShelved", "WORD", "бит i: слот отложен оператором (Shelved)"),
        _f("ePrioUnack", "E_AlarmPriority", "наивысший приоритет неквитированных тревог", "E_AlarmPriority.None"),
        _f("eDevType", "E_DeviceType", "тип устройства (проверка адресации блока)", "E_DeviceType.None"),
        _f("wAlmSuppressed", "WORD", "бит i: слот подавлен логикой (SuppressedByDesign)"),
    ),
    "ST_DeviceRetain": (
        _f("eRemoteMode", "E_DeviceMode", "последний дистанционный режим (Auto/Manual)", "E_DeviceMode.Manual"),
        _f("xOutOfService", "BOOL", "выведено из работы оператором"),
        _f("udiOpTime_s", "UDINT", "наработка всего", units="с"),
        _f("udiOpCount", "UDINT", "операций всего"),
        _f("udiOpTimeMaint_s", "UDINT", "наработка с последнего ТО", units="с"),
        _f("udiOpCountMaint", "UDINT", "операций с последнего ТО"),
        _f("audiReserve", "ARRAY[0..3] OF UDINT", "резерв"),
    ),
    "ST_AnalogInputCmd": (
        _f("stCommon", "ST_DeviceCmd", "общие команды"),
        _f("rSubstValue_eu", "REAL", "значение подмены; в Auto ФБ пишет сюда текущее значение"),
    ),
    "ST_AnalogInputSts": (
        _f("stCommon", "ST_DeviceSts", "общий заголовок"),
        _f("rValue_eu", "REAL", "итоговое значение"),
        _f("rValue_pct", "REAL", "значение, % шкалы", units="%"),
        _f("rIn", "REAL", "сырое значение входа"),
        _f("eSignal", "E_AiSignalState", "классификация сигнала (NE 43)"),
        _f("uiSubstRemain_s", "UINT", "до автоматического снятия подмены", units="с"),
    ),
    "ST_DigitalInputCmd": (
        _f("stCommon", "ST_DeviceCmd", "общие команды"),
        _f("xSubstValue", "BOOL", "значение подмены; в Auto ФБ пишет сюда текущее значение"),
    ),
    "ST_DigitalInputSts": (
        _f("stCommon", "ST_DeviceSts", "общий заголовок"),
        _f("uiSubstRemain_s", "UINT", "до автоматического снятия подмены", units="с"),
    ),
    "ST_MotorCmd": (
        _f("stCommon", "ST_DeviceCmd", "общие команды"),
        _f("xStart", "BOOL", "импульс: пуск (Manual)"),
        _f("xStop", "BOOL", "импульс: стоп (в Auto — переход в Manual и стоп)"),
        _f("xResetMaint", "BOOL", "импульс: обнулить счётчики «с последнего ТО»"),
        _f("rSpeedSp_pct", "REAL", "ПЧ: задание скорости в Manual", units="%"),
    ),
    "ST_MotorSts": (
        _f("stCommon", "ST_DeviceSts", "общий заголовок"),
        _f("eState", "E_MotorState", "состояние: 0 стоп, 1 пуск, 2 работа, 3 останов, 4 отказ"),
        _f("wInterlock", "WORD", "действующие блокировки"),
        _f("wPermitMissing", "WORD", "недостающие разрешения"),
        _f("uiFirstOut", "UINT", "первая сработавшая блокировка (бит); 65535 — нет"),
        _f("uiInhibitRemain_s", "UINT", "до снятия запрета пуска", units="с"),
        _f("uiStartsLastHour", "UINT", "пусков за скользящий час"),
        _f("rRunTime_h", "REAL", "наработка всего", units="ч"),
        _f("udiStarts", "UDINT", "пусков всего"),
        _f("rRunTimeMaint_h", "REAL", "наработка с последнего ТО", units="ч"),
        _f("udiStartsMaint", "UDINT", "пусков с последнего ТО"),
        _f("rSpeedRef_pct", "REAL", "задание на ПЧ после ограничений и рампы", units="%"),
        _f("rSpeedAct_pct", "REAL", "фактическая скорость", units="%"),
        _f("udiRunCurrent_s", "UDINT", "текущая непрерывная работа", units="с"),
    ),
    "ST_ValveCmd": (
        _f("stCommon", "ST_DeviceCmd", "общие команды"),
        _f("xOpen", "BOOL", "импульс: открыть"),
        _f("xClose", "BOOL", "импульс: закрыть"),
        _f("xStop", "BOOL", "импульс: стоп (только задвижка с приводом)"),
        _f("xResetMaint", "BOOL", "импульс: обнулить счётчики «с последнего ТО»"),
    ),
    "ST_ValveSts": (
        _f("stCommon", "ST_DeviceSts", "общий заголовок"),
        _f("eState", "E_ValveState", "состояние: 1 закрыта, 2 открывается, 3 открыта, 4 закрывается, 7 отказ"),
        _f("wInterlock", "WORD", "действующие блокировки"),
        _f("wPermitMissing", "WORD", "недостающие разрешения для текущего направления"),
        _f("uiFirstOut", "UINT", "первопричина блокировки; 65535 — нет"),
        _f("uiTravelRemain_s", "UINT", "до таймаута хода", units="с"),
        _f("wReserve", "WORD", "выравнивание следующего 32-битного поля"),
        _f("udiCycles", "UDINT", "циклов «открыто» всего"),
        _f("udiCyclesMaint", "UDINT", "циклов с последнего ТО"),
        _f("rActTime_h", "REAL", "время работы привода", units="ч"),
    ),
    "ST_ControlValveCmd": (
        _f("stCommon", "ST_DeviceCmd", "общие команды"),
        _f("rPosSpMan_pct", "REAL", "задание положения в Manual", units="%"),
    ),
    "ST_ControlValveSts": (
        _f("stCommon", "ST_DeviceSts", "общий заголовок"),
        _f("rPosSp_pct", "REAL", "задание после пределов, до рампы", units="%"),
        _f("rOut_pct", "REAL", "выход", units="%"),
        _f("rOut_mA", "REAL", "выход на AO", units="мА"),
        _f("rPosFb_pct", "REAL", "ОС положения", units="%"),
        _f("rDeviation_pct", "REAL", "рассогласование выход − ОС", units="%"),
        _f("wInterlock", "WORD", "действующие блокировки"),
        _f("uiFirstOut", "UINT", "первопричина блокировки; 65535 — нет"),
    ),
    "ST_PidCmd": (
        _f("stCommon", "ST_DeviceCmd", "общие команды"),
        _f("rSp_eu", "REAL", "задание оператора; при внешнем задании ФБ пишет сюда внешнее"),
        _f("rManualOut_pct", "REAL", "выход в Manual; в Auto, слежении и OOS ФБ пишет сюда текущий выход", units="%"),
    ),
    "ST_PidSts": (
        _f("stCommon", "ST_DeviceSts", "общий заголовок"),
        _f("rSpTarget_eu", "REAL", "задание после пределов, до рампы"),
        _f("rSp_eu", "REAL", "действующее задание (после рампы)"),
        _f("rPv_eu", "REAL", "регулируемая величина"),
        _f("rErr_pct", "REAL", "ошибка, % диапазона PV, со знаком действия", units="%"),
        _f("rOut_pct", "REAL", "выход", units="%"),
        _f("rP_pct", "REAL", "пропорциональная составляющая", units="%"),
        _f("rI_pct", "REAL", "интегральная составляющая", units="%"),
        _f("rD_pct", "REAL", "дифференциальная составляющая", units="%"),
        _f("rDt_ms", "REAL", "последний шаг расчёта", units="мс"),
    ),
}


@dataclass(frozen=True)
class FbInterface:
    """Входы и выходы ФБ устройства (без ``VAR_IN_OUT``: они одинаковы по шаблону вызова)."""

    fb: str
    extends: str
    inputs: tuple[StructField, ...]
    outputs: tuple[StructField, ...]
    implements: str = ""


BASE_INPUTS = (_f("itfTime", "I_TimeSource", "источник времени; 0 — встроенный системный"),)

_MOTOR_INPUTS = (
    _f("xAutoRun", "BOOL", "запрос автоматики «работать»"),
    _f("xFbRun", "BOOL", "ОС «в работе»"),
    _f("xExtFault", "BOOL", "внешняя авария"),
    _f("xLocal", "BOOL", "переключатель «Местное»"),
    _f("xPowerOk", "BOOL", "напряжение на секции шин есть", "TRUE"),
    _f("wInterlock", "WORD", "защитные блокировки", "16#0000"),
    _f("wPermit", "WORD", "разрешения на пуск", "16#FFFF"),
)
_MOTOR_OUTPUTS = (
    _f("xQRun", "BOOL", "команда «работа» на КМ, УПП или ПЧ"),
    _f("xQReset", "BOOL", "импульс сброса аварии УПП или ПЧ"),
    _f("xRunning", "BOOL", "работает"),
    _f("stSts", "ST_MotorSts", "состояние для HMI и SCADA"),
)

FB_INTERFACES: dict[DeviceType, FbInterface] = {
    DeviceType.ANALOG_INPUT: FbInterface(
        fb="FB_AnalogInput",
        extends="FB_DeviceBase",
        inputs=(
            _f("rIn", "REAL", "значение канала; смысл — по stCfg.eInput"),
            _f("xChannelFault", "BOOL", "отказ канала или ошибка обмена"),
            _f("xSuppressLimitAlarms", "BOOL", "подавить тревоги уставок по условию"),
        ),
        outputs=(
            _f("rValue_eu", "REAL", "значение для логики"),
            _f("rValue_pct", "REAL", "значение, % шкалы", units="%"),
            _f("xValid", "BOOL", "значение пригодно для управления"),
            _f("xHH", "BOOL", "уставка HH"),
            _f("xH", "BOOL", "уставка H"),
            _f("xL", "BOOL", "уставка L"),
            _f("xLL", "BOOL", "уставка LL"),
            _f("stSts", "ST_AnalogInputSts", "состояние для HMI и SCADA"),
        ),
    ),
    DeviceType.DIGITAL_INPUT: FbInterface(
        fb="FB_DigitalInput",
        extends="FB_DeviceBase",
        inputs=(
            _f("xIn", "BOOL", "сигнал канала"),
            _f("xChannelFault", "BOOL", "отказ канала или ошибка обмена"),
        ),
        outputs=(
            _f("xValue", "BOOL", "значение для логики"),
            _f("xValid", "BOOL", "значение достоверно"),
            _f("stSts", "ST_DigitalInputSts", "состояние для HMI и SCADA"),
        ),
    ),
    DeviceType.MOTOR: FbInterface(
        fb="FB_Motor",
        extends="FB_DeviceBase",
        inputs=_MOTOR_INPUTS,
        outputs=_MOTOR_OUTPUTS,
        implements="I_Motor",
    ),
    DeviceType.MOTOR_VFD: FbInterface(
        fb="FB_MotorVfd",
        extends="FB_Motor",
        inputs=(
            _f("rSpeedSpAuto_pct", "REAL", "задание скорости от автоматики", units="%"),
            _f("xCommOk", "BOOL", "обмен с ПЧ исправен", "TRUE"),
            _f("xVfdRunning", "BOOL", "ПЧ в работе (слово состояния)"),
            _f("xVfdReady", "BOOL", "ПЧ готов к пуску (слово состояния)", "TRUE"),
            _f("xVfdFault", "BOOL", "авария ПЧ (слово состояния)"),
            _f("rSpeedAct_pct", "REAL", "фактическая скорость", units="%"),
        ),
        outputs=(
            _f("rSpeedRef_pct", "REAL", "задание на ПЧ", units="%"),
            _f("xSpeedAutoActive", "BOOL", "Auto, работа, отказов нет"),
        ),
        implements="I_MotorVfd",
    ),
    DeviceType.VALVE: FbInterface(
        fb="FB_Valve",
        extends="FB_DeviceBase",
        inputs=(
            _f("xAutoOpen", "BOOL", "запрос автоматики: TRUE — открыть, FALSE — закрыть"),
            _f("xZso", "BOOL", "концевик «открыто»"),
            _f("xZsc", "BOOL", "концевик «закрыто»"),
            _f("xTorqueOpen", "BOOL", "муфта в сторону открытия"),
            _f("xTorqueClose", "BOOL", "муфта в сторону закрытия"),
            _f("xExtFault", "BOOL", "авария привода"),
            _f("xLocal", "BOOL", "«Местное» на приводе или шкафу"),
            _f("xPowerOk", "BOOL", "напряжение питания привода", "TRUE"),
            _f("wInterlock", "WORD", "блокировки: вести в eSafePos", "16#0000"),
            _f("wPermitOpen", "WORD", "разрешения на открытие", "16#FFFF"),
            _f("wPermitClose", "WORD", "разрешения на закрытие", "16#FFFF"),
        ),
        outputs=(
            _f("xQOpen", "BOOL", "контактор «открывать»"),
            _f("xQClose", "BOOL", "контактор «закрывать»"),
            _f("xQCoil", "BOOL", "катушка соленоида"),
            _f("xOpened", "BOOL", "положение «открыто»"),
            _f("xClosed", "BOOL", "положение «закрыто»"),
            _f("stSts", "ST_ValveSts", "состояние для HMI и SCADA"),
        ),
    ),
    DeviceType.CONTROL_VALVE: FbInterface(
        fb="FB_ControlValve",
        extends="FB_DeviceBase",
        inputs=(
            _f("rPosSpAuto_pct", "REAL", "задание от автоматики", units="%"),
            _f("rPosFb_pct", "REAL", "ОС положения", units="%"),
            _f("xPosFbValid", "BOOL", "ОС положения достоверна"),
            _f("xLocal", "BOOL", "позиционер в местном"),
            _f("wInterlock", "WORD", "блокировки: в rSafePos_pct", "16#0000"),
            _f("xPositionerFault", "BOOL", "авария позиционера или канала AO"),
        ),
        outputs=(
            _f("rOut_pct", "REAL", "задание положения", units="%"),
            _f("rOut_mA", "REAL", "выход на AO", "4.0", units="мА"),
            _f("xAutoActive", "BOOL", "клапан следует заданию автоматики"),
            _f("stSts", "ST_ControlValveSts", "состояние для HMI и SCADA"),
        ),
    ),
    # вызов ПИД пишет логика станции (контракт 17.3): генератор входы не привязывает
    DeviceType.PID: FbInterface(
        fb="FB_PID",
        extends="FB_DeviceBase",
        inputs=(
            _f("rPv_eu", "REAL", "регулируемая величина"),
            _f("xPvValid", "BOOL", "PV достоверна; по умолчанию FALSE — забытая привязка видна сразу"),
            _f("xSpExt", "BOOL", "задание от логики (каскад, график), а не от оператора"),
            _f("rSpExt_eu", "REAL", "внешнее задание"),
            _f("xTrack", "BOOL", "слежение: выход := rTrack_pct"),
            _f("rTrack_pct", "REAL", "значение для слежения", units="%"),
            _f("rOutAct_pct", "REAL", "фактический выход механизма (при stCfg.xUseOutAct)", units="%"),
        ),
        outputs=(
            _f("rOut_pct", "REAL", "выход", units="%"),
            _f("xSatHigh", "BOOL", "выход на верхнем пределе rOutMax_pct"),
            _f("xSatLow", "BOOL", "выход на нижнем пределе rOutMin_pct"),
            _f("stSts", "ST_PidSts", "состояние для HMI и SCADA"),
        ),
    ),
}


def fb_inputs(device_type: DeviceType) -> tuple[StructField, ...]:
    """Все входы экземпляра в порядке объявления: от базы к наследнику (без ``itfTime``)."""
    api = FB_INTERFACES[device_type]
    if device_type is DeviceType.MOTOR_VFD:
        return FB_INTERFACES[DeviceType.MOTOR].inputs + api.inputs
    return api.inputs


def fb_outputs(device_type: DeviceType) -> tuple[StructField, ...]:
    """Все выходы экземпляра в порядке объявления (у MotorVfd — выходы FB_Motor и свои)."""
    api = FB_INTERFACES[device_type]
    if device_type is DeviceType.MOTOR_VFD:
        return FB_INTERFACES[DeviceType.MOTOR].outputs + api.outputs
    return api.outputs


@dataclass(frozen=True)
class FlatField:
    """Скалярное поле структуры с полным путём и смещением от начала структуры, байт."""

    path: str
    field: StructField
    offset: int
    size: int

    @property
    def register(self) -> int:
        """Номер регистра Modbus от начала блока (контракт 4.6: регистр n — байты 2n…2n+1)."""
        return self.offset // REGISTER_BYTES

    @property
    def registers(self) -> int:
        return max(self.size // REGISTER_BYTES, 1)


def _type_size(st_type: str) -> int:
    if st_type in ENUMS:
        return 2
    if st_type in STRUCTS:
        return struct_size(st_type)
    return _SCALAR_BYTES[st_type]


@cache
def struct_size(name: str) -> int:
    """Размер структуры Sts по правилу 4.6 (без скрытого выравнивания), байт."""
    return sum(_type_size(field.st_type) for field in STRUCTS[name])


@cache
def flat_fields(name: str, prefix: str = "") -> tuple[FlatField, ...]:
    """Скалярные поля структуры по порядку со смещениями (вложенные структуры развёрнуты)."""
    result: list[FlatField] = []
    offset = 0
    for field in STRUCTS[name]:
        path = f"{prefix}{field.name}"
        if field.is_struct:
            for inner in flat_fields(field.st_type, f"{path}."):
                result.append(FlatField(inner.path, inner.field, offset + inner.offset, inner.size))
            offset += struct_size(field.st_type)
            continue
        size = _type_size(field.st_type)
        result.append(FlatField(path, field, offset, size))
        offset += size
    return tuple(result)


def cmd_struct(device_type: DeviceType) -> str:
    return DEVICE_TYPES[device_type].cmd


def sts_struct(device_type: DeviceType) -> str:
    return DEVICE_TYPES[device_type].sts
