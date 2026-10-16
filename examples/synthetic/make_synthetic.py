"""Синтетический перечень сигналов для замера и нагрузочных тестов: детерминированный, с зерном.

Объект вымышленный — условная водоочистная станция, разбитая на участки (насосные, фильтры,
реагенты…). Перечень корректен по схеме iolistgen (ошибок и предупреждений нет) и покрывает
все типы устройств и сигналов:

- AnalogInput: 4–20 мА, Modbus ``REAL`` (инженерные единицы), Modbus ``UINT``/``INT``
  (отсчёты прибора и шкала в ``params``), строки отказа канала ``CHF`` (DI и Modbus);
- DigitalInput: DI, Modbus — дискретный вход (функция 2), катушка (1), бит регистра (3 + бит);
- Motor: команда, ОС, авария, «Местное», сброс;
- MotorVfd: пуск проводом и Modbus для задания и состояния; пуск словом управления;
  аналоговое задание (AO) и фактическая частота (AI);
- Valve: задвижка (открыть/закрыть, концевики, муфты) и клапан с соленоидом;
- ControlValve: выход 4–20 мА и ОС положения отдельным AnalogInput (``link_fb``);
- сигналы без ФБ (роль AUX): лампа на щите отдельной строкой и регистр кода аварии ПЧ в
  составе насоса.

Первый участок собран по фиксированному рецепту — в нём есть каждый вариант; остальные
участки — случайные (``random.Random(seed)``). Последние строки добирают точное число сигналов
одиночными входами. Один и тот же ``--seed`` и ``--count`` дают побайтно тот же файл.

Запуск из корня репозитория::

    python examples/synthetic/make_synthetic.py                 # 300 сигналов, зерно 2026
    python examples/synthetic/make_synthetic.py --count 1000 --out build/io_list_1000.csv
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

SEED = 2026
COUNT = 300
DEFAULT_OUT = Path(__file__).resolve().parent / "io_list_300.csv"

COLUMNS: tuple[str, ...] = (
    "tag",
    "description",
    "signal_type",
    "device",
    "device_type",
    "dev_no",
    "role",
    "dev_desc",
    "range_min",
    "range_max",
    "units",
    "sp_hh",
    "sp_h",
    "sp_l",
    "sp_ll",
    "delay_on_s",
    "delay_off_s",
    "alarm_priority",
    "hmi_group",
    "io_module",
    "io_channel",
    "mb_link",
    "mb_slave",
    "mb_func",
    "mb_reg",
    "mb_type",
    "mb_bit",
    "mb_order",
    "link_power",
    "link_fb",
    "params",
)

AREAS: tuple[str, ...] = (
    "Насосная 1-го подъёма",
    "Смеситель и реагенты",
    "Блок фильтров",
    "Резервуары чистой воды",
    "Насосная 2-го подъёма",
    "Воздуходувная",
    "Обработка осадка",
    "Промывные воды",
    "Сооружения повторного использования",
)

# Каналы модулей ввода-вывода: префикс имени модуля и число каналов
MODULES: dict[str, tuple[str, int]] = {"AI": ("A", 8), "DI": ("D", 16), "DO": ("Q", 16), "AO": ("Y", 4)}

Row = dict[str, str]


@dataclass(frozen=True)
class AnalogKind:
    """Вид аналогового измерения: буквенный код, описание, единицы, варианты шкалы."""

    code: str
    title: str
    units: str
    ranges: tuple[tuple[float, float], ...]


ANALOG_KINDS: tuple[AnalogKind, ...] = (
    AnalogKind("LT", "Уровень", "м", ((0, 3), (0, 4), (0, 5), (0, 6))),
    AnalogKind("PT", "Давление", "бар", ((0, 6), (0, 10), (0, 16))),
    AnalogKind("FT", "Расход", "м³/ч", ((0, 100), (0, 250), (0, 500), (0, 1000))),
    AnalogKind("TT", "Температура", "°C", ((0, 100), (-40, 60), (0, 150))),
    AnalogKind("PDT", "Перепад давления", "кПа", ((0, 50), (0, 100))),
    AnalogKind("AT", "Остаточный хлор", "мг/л", ((0, 2), (0, 5))),
    AnalogKind("QT", "Мутность", "ЕМФ", ((0, 10), (0, 50))),
)

OBJECTS: tuple[str, ...] = (
    "в резервуаре",
    "в камере переключений",
    "в напорном коллекторе",
    "на входе участка",
    "на выходе участка",
    "в сборном лотке",
    "в приёмной камере",
    "в баке реагента",
)

DIGITAL_KINDS: tuple[tuple[str, str], ...] = (
    ("LS", "Сигнализатор уровня"),
    ("PS", "Реле давления"),
    ("ZS", "Концевой выключатель люка"),
    ("YS", "Состояние шкафа"),
    ("TS", "Термореле"),
)

# Наборы уставок: доли шкалы, всегда по возрастанию LL < L < H < HH
SETPOINT_SETS: tuple[dict[str, float], ...] = (
    {"sp_ll": 0.1, "sp_l": 0.2, "sp_h": 0.8, "sp_hh": 0.9},
    {"sp_l": 0.15, "sp_h": 0.85},
    {"sp_h": 0.75, "sp_hh": 0.9},
    {"sp_ll": 0.05, "sp_l": 0.15},
    {"sp_h": 0.8},
    {"sp_l": 0.1},
    {},
)


def number(value: float) -> str:
    """Число для CSV с десятичной запятой (как у Excel в русской локали)."""
    text = f"{round(value, 3):g}"
    return text.replace(".", ",")


@dataclass
class Plant:
    """Состояние генерации: строки, счётчики номеров, каналы модулей и адреса Modbus."""

    rng: random.Random
    rows: list[Row] = field(default_factory=list)
    dev_no: int = 0
    channels: dict[str, int] = field(default_factory=dict)
    next_vfd_slave: int = 1
    next_sensor_slave: int = 10
    gateway_regs: dict[str, int] = field(default_factory=dict)
    gateway_bit: tuple[int, int] = (-1, 16)
    full: bool = False  # участок покрытия: все необязательные строки устройств включены

    # --- служебное ------------------------------------------------------------------------------

    def new_dev_no(self) -> str:
        self.dev_no += 1
        return str(self.dev_no)

    def channel(self, signal_type: str) -> dict[str, str]:
        """Следующий свободный канал модуля этого типа сигнала."""
        prefix, size = MODULES[signal_type]
        used = self.channels.get(signal_type, 0)
        self.channels[signal_type] = used + 1
        return {"io_module": f"{prefix}{used // size + 1}", "io_channel": str(used % size + 1)}

    def gateway(self, space: str, length: int = 1) -> int:
        """Адрес в шлюзе удалённого ввода-вывода (TCP-1, слейв 1): пространства — отдельно."""
        address = self.gateway_regs.get(space, 0)
        self.gateway_regs[space] = address + length
        return address

    def gateway_bit_slot(self) -> tuple[int, int]:
        """Следующий бит в регистрах состояния шлюза (функция 3, адреса с 1000)."""
        register, bit = self.gateway_bit
        if bit >= 15:
            register, bit = self.gateway("bits") + 1000, 0
        else:
            bit += 1
        self.gateway_bit = (register, bit)
        return register, bit

    def add(self, **cells: str) -> Row:
        unknown = set(cells) - set(COLUMNS)
        if unknown:
            raise ValueError(f"нет колонок {sorted(unknown)}")
        row = {name: cells.get(name, "") for name in COLUMNS}
        self.rows.append(row)
        return row

    def chance(self, probability: float) -> bool:
        return self.rng.random() < probability

    def option(self, probability: float) -> bool:
        """Необязательная строка устройства: на участке покрытия есть всегда."""
        return self.full or self.chance(probability)

    # --- одиночные входы -----------------------------------------------------------------------

    def analog(self, tag: str, area: str, *, modbus: str = "", chf: str = "") -> int:
        """Аналоговый вход: 4–20 мА или Modbus (``real``, ``raw``); ``chf`` — ``di`` или ``mb``."""
        kind = self.rng.choice(ANALOG_KINDS)
        lo, hi = self.rng.choice(kind.ranges)
        tag = f"{kind.code}{tag}"
        setpoints = self.rng.choice(SETPOINT_SETS)
        cells: Row = {
            "tag": tag,
            "description": f"{kind.title} {self.rng.choice(OBJECTS)}",
            "device_type": "AnalogInput",
            "dev_no": self.new_dev_no(),
            "role": "PV",
            "range_min": number(lo),
            "range_max": number(hi),
            "units": kind.units,
            "hmi_group": area,
        }
        for column, share in setpoints.items():
            cells[column] = number(lo + share * (hi - lo))
        params = []
        if setpoints:
            cells["delay_on_s"] = str(self.rng.choice((1, 2, 3, 5, 10)))
            cells["alarm_priority"] = self.rng.choice(("High", "Medium", "Low", ""))
            if self.chance(0.4):
                column = next(iter(setpoints))
                index = {"sp_hh": "HH", "sp_h": "H", "sp_l": "L", "sp_ll": "LL"}[column]
                params.append(f"astLimit[{index}].rHyst_eu={(hi - lo) * 0.01:.2f}")
        if self.chance(0.5):
            params.append(f"tFilter=T#{self.rng.choice((1, 2, 3, 5))}S")
        if modbus == "real":
            slave = self.next_sensor_slave
            self.next_sensor_slave += 1
            cells.update(
                signal_type="MB",
                mb_link="RS485-2",
                mb_slave=str(slave),
                mb_func="4",
                mb_reg="0",
                mb_type="REAL",
                mb_order=self.rng.choice(("HL", "LH")),
            )
        elif modbus == "raw":
            data_type = "INT" if lo < 0 else "UINT"
            scale = self.rng.choice((10, 100))
            register = self.gateway("input")
            cells.update(
                signal_type="MB", mb_link="TCP-1", mb_slave="1", mb_func="4", mb_reg=str(register), mb_type=data_type
            )
            params.append(f"rRawLo_cnt={lo * scale:.1f}; rRawHi_cnt={hi * scale:.1f}")
        else:
            cells.update(signal_type="AI", **self.channel("AI"))
        cells["params"] = "; ".join(params)
        self.add(**cells)
        count = 1
        if chf == "di":
            self.add(
                tag=f"{tag}_CHF",
                description=f"{cells['description']}: отказ канала (диагностика модуля)",
                signal_type="DI",
                device=tag,
                role="CHF",
                hmi_group=area,
                **self.channel("DI"),
            )
            count += 1
        elif chf == "mb":
            register, bit = self.gateway_bit_slot()
            self.add(
                tag=f"{tag}_CHF",
                description=f"{cells['description']}: отказ канала (бит состояния шлюза)",
                signal_type="MB",
                device=tag,
                role="CHF",
                hmi_group=area,
                mb_link="TCP-1",
                mb_slave="1",
                mb_func="3",
                mb_reg=str(register),
                mb_type="BOOL",
                mb_bit=str(bit),
            )
            count += 1
        return count

    def digital(self, tag: str, area: str, *, modbus: str = "") -> int:
        """Дискретный вход: DI или Modbus (``di`` — функция 2, ``coil`` — 1, ``bit`` — бит регистра)."""
        code, title = self.rng.choice(DIGITAL_KINDS)
        cells: Row = {
            "tag": f"{code}{tag}",
            "description": f"{title} {self.rng.choice(OBJECTS)}",
            "device_type": "DigitalInput",
            "dev_no": self.new_dev_no(),
            "role": "IN",
            "hmi_group": area,
            "alarm_priority": self.rng.choice(("High", "Medium", "Low", "")),
        }
        if cells["alarm_priority"]:
            cells["delay_on_s"] = str(self.rng.choice((1, 2, 5)))
        params = []
        if self.chance(0.3):
            params.append("xInvert=TRUE")
        if modbus == "di":
            cells.update(
                signal_type="MB",
                mb_link="TCP-1",
                mb_slave="1",
                mb_func="2",
                mb_reg=str(self.gateway("discrete")),
                mb_type="BOOL",
            )
        elif modbus == "coil":
            cells.update(
                signal_type="MB",
                mb_link="TCP-1",
                mb_slave="1",
                mb_func="1",
                mb_reg=str(self.gateway("coils")),
                mb_type="BOOL",
            )
        elif modbus == "bit":
            register, bit = self.gateway_bit_slot()
            cells.update(
                signal_type="MB",
                mb_link="TCP-1",
                mb_slave="1",
                mb_func="3",
                mb_reg=str(register),
                mb_type="BOOL",
                mb_bit=str(bit),
            )
        else:
            cells.update(signal_type="DI", **self.channel("DI"))
        cells["params"] = "; ".join(params)
        self.add(**cells)
        return 1

    def power(self, tag: str, area: str) -> tuple[str, int]:
        """DI «напряжение в норме» участка: на него ссылаются link_power двигателей и задвижек."""
        name = f"ES{tag}"
        self.add(
            tag=name,
            description=f"Напряжение на вводе щита участка «{area}» в норме",
            signal_type="DI",
            device_type="DigitalInput",
            dev_no=self.new_dev_no(),
            role="IN",
            delay_on_s="3",
            alarm_priority="High",
            hmi_group=area,
            params="xAlarmOnTrue=FALSE",
            **self.channel("DI"),
        )
        return name, 1

    # --- устройства из нескольких строк -------------------------------------------------------

    def motor(self, tag: str, area: str, power: str) -> int:
        dev = f"M{tag}"
        title = f"Мешалка {dev}"
        self.add(
            tag=f"{dev}_RUN",
            description=f"{title}: команда «Работа»",
            signal_type="DO",
            device=dev,
            device_type="Motor",
            dev_no=self.new_dev_no(),
            role="CMD_RUN",
            dev_desc=title,
            delay_on_s=str(self.rng.choice((3, 5))),
            delay_off_s=str(self.rng.choice((3, 5))),
            alarm_priority=self.rng.choice(("", "Low", "High")),
            hmi_group=area,
            link_power=power,
            params=f"tMinStop=T#{self.rng.choice((10, 30))}S; uiMaxStartsPerHour={self.rng.choice((6, 10, 20))}",
            **self.channel("DO"),
        )
        count = 1
        for suffix, role, text in (
            ("RFB", "RUN_FB", "в работе (блок-контакт пускателя)"),
            ("FLT", "FAULT", "авария (автомат защиты двигателя)"),
            ("LOC", "LOCAL", "режим «Местное»"),
        ):
            self.add(
                tag=f"{dev}_{suffix}",
                description=f"{title}: {text}",
                signal_type="DI",
                device=dev,
                role=role,
                hmi_group=area,
                **self.channel("DI"),
            )
            count += 1
        if self.option(0.3):
            self.add(
                tag=f"{dev}_RST",
                description=f"{title}: сброс аварии УПП",
                signal_type="DO",
                device=dev,
                role="CMD_RESET",
                hmi_group=area,
                **self.channel("DO"),
            )
            count += 1
        return count

    def pump(self, tag: str, area: str, power: str, variant: str) -> int:
        """Насос с ПЧ: ``wired`` — пуск проводом; ``modbus`` — слово управления; ``analog`` — AO/AI."""
        dev = f"P{tag}"
        title = f"Насос {dev}"
        slave = str(self.next_vfd_slave)
        self.next_vfd_slave += 1
        link = {"mb_link": "RS485-1", "mb_slave": slave}
        main: Row = {
            "device": dev,
            "device_type": "MotorVfd",
            "dev_no": self.new_dev_no(),
            "dev_desc": title,
            "delay_on_s": "10",
            "delay_off_s": "15",
            "hmi_group": area,
            "link_power": power,
        }
        params = [f"stVfd.rSpeedMin_pct={self.rng.choice((30, 40, 50))}.0", "tMinStop=T#30S"]
        rows: list[Row] = []
        if variant == "modbus":
            rows.append(
                main
                | {"tag": f"{dev}_CTW", "description": f"{title}: слово управления ПЧ", "signal_type": "MB"}
                | {"role": "VFD_CTW", "mb_func": "16", "mb_reg": "0", "mb_type": "WORD"}
                | link
            )
        else:
            rows.append(
                main
                | {"tag": f"{dev}_RUN", "description": f"{title}: команда «Работа» на ПЧ", "signal_type": "DO"}
                | {"role": "CMD_RUN"}
                | self.channel("DO")
            )
        common = {"device": dev, "hmi_group": area}
        if variant == "wired":
            params += ["stVfd.xFbFromComm=FALSE", "stVfd.xCommLossIsFault=FALSE"]
            rows.append(
                common
                | {"tag": f"{dev}_RFB", "description": f"{title}: ПЧ в работе", "signal_type": "DI", "role": "RUN_FB"}
                | self.channel("DI")
            )
        if variant != "modbus" or self.option(0.5):
            rows.append(
                common
                | {"tag": f"{dev}_FLT", "description": f"{title}: авария ПЧ", "signal_type": "DI", "role": "FAULT"}
                | self.channel("DI")
            )
        if self.option(0.7):
            rows.append(
                common
                | {"tag": f"{dev}_LOC", "description": f"{title}: режим «Местное»", "signal_type": "DI"}
                | {"role": "LOCAL"}
                | self.channel("DI")
            )
        rows.append(
            common
            | {"tag": f"{dev}_STW", "description": f"{title}: слово состояния ПЧ", "signal_type": "MB"}
            | {"role": "VFD_STW", "mb_func": "3", "mb_reg": "100", "mb_type": "WORD"}
            | link
        )
        if self.full and variant == "wired":
            rows.append(
                common
                | {"tag": f"{dev}_FCODE", "description": f"{title}: код аварии ПЧ (читает адаптер)"}
                | {"signal_type": "MB", "role": "AUX", "mb_func": "3", "mb_reg": "102", "mb_type": "UINT"}
                | link
            )
        if variant == "analog":
            rows.append(
                common
                | {"tag": f"{dev}_FREF", "description": f"{title}: задание частоты (4–20 мА)", "signal_type": "AO"}
                | {"role": "SPEED_REF", "range_min": "0", "range_max": "100", "units": "%"}
                | self.channel("AO")
            )
            rows.append(
                common
                | {"tag": f"{dev}_FACT", "description": f"{title}: фактическая частота (4–20 мА)", "signal_type": "AI"}
                | {"role": "SPEED_ACT", "range_min": "0", "range_max": "50", "units": "Гц"}
                | self.channel("AI")
            )
        else:
            rows.append(
                common
                | {"tag": f"{dev}_FREF", "description": f"{title}: задание частоты ПЧ", "signal_type": "MB"}
                | {"role": "SPEED_REF", "range_min": "0", "range_max": "50", "units": "Гц"}
                | {"mb_func": "16", "mb_reg": "1", "mb_type": "UINT"}
                | link
            )
            rows.append(
                common
                | {"tag": f"{dev}_FACT", "description": f"{title}: фактическая частота ПЧ", "signal_type": "MB"}
                | {"role": "SPEED_ACT", "range_min": "0", "range_max": "50", "units": "Гц"}
                | {"mb_func": "3", "mb_reg": "101", "mb_type": "UINT"}
                | link
            )
        rows[0]["params"] = "; ".join(params)
        for row in rows:
            self.add(**row)
        return len(rows)

    def lamp(self, tag: str, area: str) -> int:
        """Лампа на двери щита — дискретный выход без ФБ библиотеки (роль AUX)."""
        self.add(
            tag=f"HL{tag}",
            description=f"Лампа «Авария участка» на двери щита участка «{area}»",
            signal_type="DO",
            role="AUX",
            hmi_group=area,
            **self.channel("DO"),
        )
        return 1

    def gate_valve(self, tag: str, area: str, power: str, *, torque: bool) -> int:
        dev = f"MV{tag}"
        title = f"Задвижка {dev}"
        self.add(
            tag=f"{dev}_OPN",
            description=f"{title}: открыть",
            signal_type="DO",
            device=dev,
            device_type="Valve",
            dev_no=self.new_dev_no(),
            role="CMD_OPEN",
            dev_desc=title,
            delay_on_s=str(self.rng.choice((30, 60, 90, 120))),
            alarm_priority=self.rng.choice(("", "Low", "High")),
            hmi_group=area,
            link_power=power if self.option(0.6) else "",
            params="xCloseOnTorque=TRUE" if torque and self.option(0.5) else "",
            **self.channel("DO"),
        )
        self.add(
            tag=f"{dev}_CLS",
            description=f"{title}: закрыть",
            signal_type="DO",
            device=dev,
            role="CMD_CLOSE",
            hmi_group=area,
            **self.channel("DO"),
        )
        inputs = [("ZSO", "ZSO", "открыта"), ("ZSC", "ZSC", "закрыта")]
        if torque:
            inputs += [("TQO", "TQO", "муфта на открытие"), ("TQC", "TQC", "муфта на закрытие")]
        if self.option(0.6):
            inputs.append(("FLT", "FAULT", "авария привода"))
        if self.option(0.5):
            inputs.append(("LOC", "LOCAL", "режим «Местное»"))
        for suffix, role, text in inputs:
            self.add(
                tag=f"{dev}_{suffix}",
                description=f"{title}: {text}",
                signal_type="DI",
                device=dev,
                role=role,
                hmi_group=area,
                **self.channel("DI"),
            )
        return 2 + len(inputs)

    def solenoid_valve(self, tag: str, area: str) -> int:
        dev = f"XV{tag}"
        title = f"Клапан {dev}"
        normally = self.rng.choice((("SolenoidEto", "нормально закрытый"), ("SolenoidEtc", "нормально открытый")))
        self.add(
            tag=f"{dev}_COIL",
            description=f"{title} ({normally[1]}): катушка",
            signal_type="DO",
            device=dev,
            device_type="Valve",
            dev_no=self.new_dev_no(),
            role="CMD_COIL",
            dev_desc=f"Клапан {dev} с соленоидом",
            delay_on_s=str(self.rng.choice((5, 10))),
            hmi_group=area,
            params=f"eType={normally[0]}",
            **self.channel("DO"),
        )
        count = 1
        for suffix, text in (("ZSO", "открыт"), ("ZSC", "закрыт")):
            if self.option(0.5):
                self.add(
                    tag=f"{dev}_{suffix}",
                    description=f"{title}: {text}",
                    signal_type="DI",
                    device=dev,
                    role=suffix,
                    hmi_group=area,
                    **self.channel("DI"),
                )
                count += 1
        return count

    def control_valve(self, tag: str, area: str) -> int:
        code = self.rng.choice(("FCV", "LCV", "PCV", "TCV"))
        dev = f"{code}{tag}"
        feedback = f"ZT{tag}"
        title = f"Регулирующий клапан {dev}"
        self.add(
            tag=f"{dev}_OUT",
            description=f"{title}: задание положения",
            signal_type="AO",
            device=dev,
            device_type="ControlValve",
            dev_no=self.new_dev_no(),
            role="POS_OUT",
            dev_desc=title,
            range_min="0",
            range_max="100",
            units="%",
            delay_on_s=str(self.rng.choice((30, 60))),
            hmi_group=area,
            link_fb=feedback,
            params=f"rRateUp_pctps={self.rng.choice((1, 2, 5))}.0; rRateDown_pctps={self.rng.choice((1, 2, 5))}.0",
            **self.channel("AO"),
        )
        count = 1
        if self.option(0.5):
            self.add(
                tag=f"{dev}_FLT",
                description=f"{title}: авария позиционера",
                signal_type="DI",
                device=dev,
                role="POS_FAULT",
                hmi_group=area,
                **self.channel("DI"),
            )
            count += 1
        if self.option(0.3):
            self.add(
                tag=f"{dev}_LOC",
                description=f"{title}: позиционер в местном режиме",
                signal_type="DI",
                device=dev,
                role="LOCAL",
                hmi_group=area,
                **self.channel("DI"),
            )
            count += 1
        self.add(
            tag=feedback,
            description=f"{title}: положение (ОС)",
            signal_type="AI",
            device_type="AnalogInput",
            dev_no=self.new_dev_no(),
            role="PV",
            range_min="0",
            range_max="100",
            units="%",
            hmi_group=area,
            **self.channel("AI"),
        )
        return count + 1


# Позиция — номер участка · 100 + порядковый номер: не больше 4 цифр (правило тегов по умолчанию)
MAX_BASE = 9800

# Наибольшее число строк каждого вида устройства: рецепт участка не превышает остаток бюджета
MAX_ROWS = {"analog": 2, "digital": 1, "motor": 5, "pump": 7, "gate": 8, "solenoid": 3, "cv": 4}


def coverage_area(plant: Plant, area: str, base: int) -> int:
    """Первый участок: каждый вариант устройства и сигнала хотя бы по разу."""
    seq = iter(range(base + 1, base + 100))
    plant.full = True
    power, count = plant.power(str(next(seq)), area)
    count += plant.analog(str(next(seq)), area)
    count += plant.analog(str(next(seq)), area, chf="di")
    count += plant.analog(str(next(seq)), area, modbus="real")
    count += plant.analog(str(next(seq)), area, modbus="raw", chf="mb")
    count += plant.digital(str(next(seq)), area)
    count += plant.digital(str(next(seq)), area, modbus="di")
    count += plant.digital(str(next(seq)), area, modbus="coil")
    count += plant.digital(str(next(seq)), area, modbus="bit")
    count += plant.motor(str(next(seq)), area, power)
    count += plant.pump(str(next(seq)), area, power, "wired")
    count += plant.pump(str(next(seq)), area, power, "modbus")
    count += plant.pump(str(next(seq)), area, power, "analog")
    count += plant.gate_valve(str(next(seq)), area, power, torque=True)
    count += plant.gate_valve(str(next(seq)), area, power, torque=False)
    count += plant.solenoid_valve(str(next(seq)), area)
    count += plant.control_valve(str(next(seq)), area)
    count += plant.lamp(str(next(seq)), area)
    plant.full = False
    return count


def _pump(plant: Plant, seq: Iterator[int], area: str, power: str, variant: str) -> int:
    return plant.pump(str(next(seq)), area, power, variant)


def random_area(plant: Plant, area: str, base: int, budget: int) -> int:
    """Случайный участок в пределах бюджета строк."""
    rng = plant.rng
    seq = iter(range(base + 1, base + 100))
    if budget < 2:
        return 0
    power, count = plant.power(str(next(seq)), area)
    makers: list[tuple[str, Callable[[], int]]] = []
    for _ in range(rng.randint(2, 4)):
        makers.append(("analog", lambda: plant.analog(str(next(seq)), area, chf="di" if rng.random() < 0.15 else "")))
    makers.append(("analog", lambda: plant.analog(str(next(seq)), area, modbus=rng.choice(("real", "raw")))))
    for _ in range(rng.randint(2, 3)):
        makers.append(
            ("digital", lambda: plant.digital(str(next(seq)), area, modbus=rng.choice(("", "", "di", "bit"))))
        )
    for _ in range(rng.randint(1, 2)):
        variant = rng.choice(("wired", "wired", "modbus", "analog"))
        makers.append(("pump", partial(_pump, plant, seq, area, power, variant)))
    if rng.random() < 0.5:
        makers.append(("motor", lambda: plant.motor(str(next(seq)), area, power)))
    for _ in range(rng.randint(1, 2)):
        makers.append(("gate", lambda: plant.gate_valve(str(next(seq)), area, power, torque=rng.random() < 0.3)))
    if rng.random() < 0.6:
        makers.append(("solenoid", lambda: plant.solenoid_valve(str(next(seq)), area)))
    if rng.random() < 0.5:
        makers.append(("cv", lambda: plant.control_valve(str(next(seq)), area)))
    rng.shuffle(makers)
    for kind, make in makers:
        if count + MAX_ROWS[kind] > budget:
            continue
        count += make()
    return count


def generate(seed: int = SEED, count: int = COUNT) -> list[Row]:
    """Строки перечня: ровно ``count`` сигналов (не меньше, чем строк в участке покрытия)."""
    plant = Plant(random.Random(seed))
    total = coverage_area(plant, AREAS[0], 100)
    if total > count:
        raise ValueError(f"минимум сигналов — {total} (участок покрытия)")
    area_no, name, base = 1, AREAS[0], 100
    while count - total >= 12:
        name = AREAS[area_no % len(AREAS)] + (f" {area_no // len(AREAS) + 1}" if area_no >= len(AREAS) else "")
        base = (area_no + 1) * 100
        if base > MAX_BASE:
            raise ValueError(f"слишком много участков для позиций из 4 цифр: уменьшите --count (сейчас {count})")
        total += random_area(plant, name, base, count - total)
        area_no += 1
    # добор точного числа одиночными входами на последнем участке (позиции …91 и дальше)
    seq = 90
    while total < count:
        seq += 1
        tag = str(base + seq)
        total += plant.analog(tag, name) if seq % 2 else plant.digital(tag, name)
    return plant.rows


def render_csv(rows: Sequence[Row]) -> str:
    """CSV с разделителем «;»: ячейки с «;» или кавычками — в кавычках, как у Excel."""
    lines = [";".join(COLUMNS)]
    for row in rows:
        cells = []
        for name in COLUMNS:
            value = row.get(name, "")
            if ";" in value or '"' in value:
                value = '"' + value.replace('"', '""') + '"'
            cells.append(value)
        lines.append(";".join(cells))
    return "\n".join(lines) + "\n"


def _configure_streams() -> None:
    """Вывод в файл или канал — UTF-8 (в Windows по умолчанию кодировка консоли)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None and not stream.isatty():
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_streams()
    parser = argparse.ArgumentParser(description="Синтетический перечень сигналов (детерминированный).")
    parser.add_argument("--seed", type=int, default=SEED, help=f"зерно генератора (по умолчанию {SEED})")
    parser.add_argument("--count", type=int, default=COUNT, help=f"число сигналов (по умолчанию {COUNT})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="файл CSV (по умолчанию io_list_300.csv рядом)")
    args = parser.parse_args(argv)
    rows = generate(args.seed, args.count)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(render_csv(rows).encode("utf-8"))
    sys.stdout.write(f"{args.out}: {len(rows)} сигналов, зерно {args.seed}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
