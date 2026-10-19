"""Перечисления схемы перечня: типы сигналов и устройств, роли, приоритеты тревог."""

from __future__ import annotations

from enum import Enum


class SignalType(str, Enum):
    """Тип сигнала перечня."""

    AI = "AI"
    DI = "DI"
    DO = "DO"
    AO = "AO"
    MB = "MB"

    @property
    def label(self) -> str:
        return _SIGNAL_TITLES[self]

    @property
    def is_hardwired(self) -> bool:
        """Канал модуля ввода-вывода ПЛК (не обмен)."""
        return self is not SignalType.MB

    @property
    def is_analog(self) -> bool:
        return self in (SignalType.AI, SignalType.AO)


_SIGNAL_TITLES = {
    SignalType.AI: "аналоговый вход",
    SignalType.DI: "дискретный вход",
    SignalType.DO: "дискретный выход",
    SignalType.AO: "аналоговый выход",
    SignalType.MB: "обмен Modbus",
}


class DeviceType(str, Enum):
    """Тип устройства — функциональный блок библиотеки plc-process-lib (namespace ``PL``).

    ``PID`` — регулятор без сигналов ввода-вывода: в перечне это строка устройства без типа
    сигнала и роли, привязки ФБ пишет логика станции (контракт 17.3, 18.3, правило 9).
    """

    ANALOG_INPUT = "AnalogInput"
    DIGITAL_INPUT = "DigitalInput"
    MOTOR = "Motor"
    MOTOR_VFD = "MotorVfd"
    VALVE = "Valve"
    CONTROL_VALVE = "ControlValve"
    PID = "Pid"


class Role(str, Enum):
    """Роль сигнала в устройстве: вход или выход ФБ (контракт plc-process-lib, 20.2).

    ``AUX`` — расширение схемы iolistgen: сигнал без входа и выхода ФБ (лампа, сирена, регистр,
    который читает адаптер). У него есть переменная ``GVL_IO``, адрес в карте обмена, тег SCADA и
    строка документации; читает и пишет его код приложения.
    """

    PV = "PV"
    CHF = "CHF"
    IN = "IN"
    CMD_RUN = "CMD_RUN"
    RUN_FB = "RUN_FB"
    FAULT = "FAULT"
    LOCAL = "LOCAL"
    CMD_RESET = "CMD_RESET"
    VFD_CTW = "VFD_CTW"
    VFD_STW = "VFD_STW"
    SPEED_REF = "SPEED_REF"
    SPEED_ACT = "SPEED_ACT"
    CMD_OPEN = "CMD_OPEN"
    CMD_CLOSE = "CMD_CLOSE"
    CMD_COIL = "CMD_COIL"
    ZSO = "ZSO"
    ZSC = "ZSC"
    TQO = "TQO"
    TQC = "TQC"
    POS_OUT = "POS_OUT"
    POS_FAULT = "POS_FAULT"
    AUX = "AUX"


class Direction(str, Enum):
    """Направление сигнала относительно ПЛК."""

    IN = "in"
    OUT = "out"

    @property
    def label(self) -> str:
        return "вход ФБ" if self is Direction.IN else "выход ФБ"


class AlarmPriority(str, Enum):
    """Приоритет тревоги — значения ``PL.E_AlarmPriority``."""

    NONE = "None"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

    @property
    def level(self) -> int:
        return _PRIORITY_ORDER.index(self)

    @property
    def label(self) -> str:
        return _PRIORITY_TITLES[self]

    def step_down(self) -> AlarmPriority:
        """На ступень ниже, но не ниже Low; ``None`` остаётся ``None``."""
        if self is AlarmPriority.NONE:
            return self
        return _PRIORITY_ORDER[max(self.level - 1, AlarmPriority.LOW.level)]


_PRIORITY_ORDER = (
    AlarmPriority.NONE,
    AlarmPriority.LOW,
    AlarmPriority.MEDIUM,
    AlarmPriority.HIGH,
    AlarmPriority.CRITICAL,
)
_PRIORITY_TITLES = {
    AlarmPriority.NONE: "нет (тревога выключена)",
    AlarmPriority.LOW: "низкий",
    AlarmPriority.MEDIUM: "средний",
    AlarmPriority.HIGH: "высокий",
    AlarmPriority.CRITICAL: "критический",
}
