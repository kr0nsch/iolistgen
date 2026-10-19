"""Колонки перечня: канонические имена, синонимы заголовков, уровень и формат.

Канонические имена — английские (``tag``, ``signal_type``): их понимают генераторы и плагины.
В файле заголовок может быть и русским («Тег», «Тип сигнала»): регистр, «ё», пробелы и знаки
препинания при сравнении не учитываются. Дополнительные синонимы задаются в ``iolistgen.toml``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

Level = Literal["signal", "device", "identity"]


@dataclass(frozen=True)
class ColumnSpec:
    """Колонка перечня.

    ``level``: ``signal`` — свойство строки; ``device`` — читается из главной строки устройства;
    ``identity`` — относится к устройству, но может повторяться в любой его строке (должно совпадать).
    """

    name: str
    title: str
    aliases: tuple[str, ...]
    level: Level
    required: str
    value: str
    description: str


COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec(
        "tag",
        "Тег",
        ("тег", "позиция", "обозначение", "tag name"),
        "signal",
        "да",
        "латиница, цифры, «_»",
        "тег сигнала; из него получается имя переменной GVL_IO",
    ),
    ColumnSpec(
        "description",
        "Описание",
        ("описание", "наименование", "наименование сигнала", "описание сигнала"),
        "signal",
        "да",
        "текст",
        "что за сигнал; идёт в документацию, SCADA и тексты тревог",
    ),
    ColumnSpec(
        "signal_type",
        "Тип сигнала",
        ("тип сигнала", "sig type", "вид сигнала"),
        "signal",
        "да (у строки устройства Pid — пусто)",
        "AI, DI, DO, AO, MB",
        "канал модуля ПЛК (AI, DI, DO, AO) или обмен Modbus (MB)",
    ),
    ColumnSpec(
        "device",
        "Устройство",
        ("устройство", "device tag", "позиция устройства"),
        "identity",
        "нет (= tag)",
        "латиница, цифры, «_»",
        "тег устройства: строки с одним device — один экземпляр ФБ fb<DEV>",
    ),
    ColumnSpec(
        "device_type",
        "Тип устройства",
        ("тип устройства", "тип фб", "фб"),
        "identity",
        "в главной строке",
        "AnalogInput, DigitalInput, Motor, MotorVfd, Valve, ControlValve, Pid",
        "функциональный блок библиотеки PL",
    ),
    ColumnSpec(
        "dev_no",
        "Номер устройства",
        ("номер устройства", "№ устройства", "dev no", "device no"),
        "identity",
        "в главной строке",
        "целое 1…9999",
        "стабильный номер: номера тревог dev_no·10 + слот, порядок GVL_Persist, GVL_DevIdx",
    ),
    ColumnSpec(
        "role",
        "Роль",
        ("роль", "роль сигнала"),
        "signal",
        "да (у AI и DI — по умолчанию PV и IN; у строки устройства Pid — пусто)",
        "PV, IN, CMD_RUN, … (таблица ролей)",
        "вход или выход ФБ, к которому привязан сигнал",
    ),
    ColumnSpec(
        "dev_desc",
        "Описание устройства",
        ("описание устройства", "наименование устройства"),
        "device",
        "нет (= описание главной строки)",
        "текст",
        "название устройства для HMI, SCADA и текстов тревог",
    ),
    ColumnSpec(
        "range_min",
        "Мин.",
        ("мин", "минимум", "диапазон мин", "шкала мин", "нижний предел шкалы", "range min", "min"),
        "signal",
        "у AnalogInput",
        "число",
        "нижняя граница шкалы, инж. ед.; у Pid — диапазона PV (rPvMin_eu)",
    ),
    ColumnSpec(
        "range_max",
        "Макс.",
        ("макс", "максимум", "диапазон макс", "шкала макс", "верхний предел шкалы", "range max", "max"),
        "signal",
        "у AnalogInput",
        "число",
        "верхняя граница шкалы, инж. ед.; у Pid — диапазона PV (rPvMax_eu)",
    ),
    ColumnSpec(
        "units",
        "Ед. изм.",
        ("ед изм", "единицы", "единицы измерения", "ед", "units"),
        "signal",
        "у AnalogInput",
        "текст",
        "единицы измерения (только SCADA и документация)",
    ),
    ColumnSpec("sp_hh", "HH", ("hh", "уставка hh"), "device", "нет", "число", "верхний аварийный предел"),
    ColumnSpec("sp_h", "H", ("h", "уставка h"), "device", "нет", "число", "верхний предупредительный предел"),
    ColumnSpec("sp_l", "L", ("l", "уставка l"), "device", "нет", "число", "нижний предупредительный предел"),
    ColumnSpec("sp_ll", "LL", ("ll", "уставка ll"), "device", "нет", "число", "нижний аварийный предел"),
    ColumnSpec(
        "delay_on_s",
        "Задержка вкл., с",
        ("задержка вкл", "задержка включения", "задержка срабатывания", "delay on"),
        "device",
        "нет",
        "секунды или T#…",
        "задержка включения; куда идёт — по типу устройства",
    ),
    ColumnSpec(
        "delay_off_s",
        "Задержка откл., с",
        ("задержка откл", "задержка отключения", "задержка снятия", "delay off"),
        "device",
        "нет",
        "секунды или T#…",
        "задержка отключения; куда идёт — по типу устройства",
    ),
    ColumnSpec(
        "alarm_priority",
        "Приоритет тревоги",
        ("приоритет", "приоритет тревоги", "priority"),
        "device",
        "нет",
        "None, Low, Medium, High, Critical или 0…4",
        "приоритет тревог устройства (правила — по типу устройства)",
    ),
    ColumnSpec(
        "hmi_group",
        "Группа HMI",
        ("группа hmi", "группа", "hmi group", "группа scada"),
        "signal",
        "нет",
        "текст",
        "группа экрана HMI или SCADA",
    ),
    ColumnSpec(
        "io_module",
        "Модуль",
        ("модуль", "модуль ввода вывода", "module"),
        "signal",
        "нет",
        "текст",
        "модуль ввода-вывода (для AI, DI, DO, AO)",
    ),
    ColumnSpec(
        "io_channel",
        "Канал",
        ("канал", "номер канала", "channel"),
        "signal",
        "нет",
        "целое от 0",
        "номер канала модуля",
    ),
    ColumnSpec(
        "mb_link",
        "Линия Modbus",
        ("линия", "линия modbus", "порт", "mb link"),
        "signal",
        "нет",
        "текст",
        "линия RS-485 или соединение TCP: адреса слейвов уникальны внутри линии",
    ),
    ColumnSpec(
        "mb_slave",
        "Слейв",
        ("слейв", "адрес слейва", "slave", "unit id", "адрес устройства modbus"),
        "signal",
        "для MB",
        "целое 1…255",
        "адрес слейва (Unit ID)",
    ),
    ColumnSpec(
        "mb_func",
        "Функция",
        ("функция", "функция modbus", "fc", "function"),
        "signal",
        "для MB",
        "1, 2, 3, 4, 5, 6, 15, 16",
        "функция Modbus: чтение 1–4, запись 5, 6, 15, 16",
    ),
    ColumnSpec(
        "mb_reg",
        "Регистр",
        ("регистр", "адрес регистра", "адрес modbus", "register"),
        "signal",
        "для MB",
        "целое 0…65535, 16#…, 0x…",
        "адрес PDU (с нуля; база — настройка modbus.address_base)",
    ),
    ColumnSpec(
        "mb_type",
        "Тип данных",
        ("тип данных", "data type", "тип данных modbus"),
        "signal",
        "для MB",
        "BOOL, INT, UINT, WORD, DINT, UDINT, DWORD, REAL, LINT, ULINT, LWORD, LREAL",
        "тип значения в памяти слейва; определяет длину",
    ),
    ColumnSpec(
        "mb_bit",
        "Бит",
        ("бит", "номер бита", "bit"),
        "signal",
        "для BOOL в регистре",
        "целое 0…15",
        "номер бита регистра для сигнала BOOL",
    ),
    ColumnSpec(
        "mb_order",
        "Порядок слов",
        ("порядок слов", "word order"),
        "signal",
        "для 32/64 бит",
        "HL или LH",
        "HL — старшее слово первым, LH — младшее первым",
    ),
    ColumnSpec(
        "link_power",
        "Питание",
        ("питание", "link power"),
        "device",
        "нет",
        "тег DI-устройства",
        "Motor, MotorVfd, Valve: xPowerOk := fb<LINK>.xValue",
    ),
    ColumnSpec(
        "link_fb",
        "ОС положения",
        ("ос положения", "link fb"),
        "device",
        "нет",
        "тег AI-устройства",
        "ControlValve: rPosFb_pct := fb<LINK>.rValue_pct, xPosFbValid := fb<LINK>.xValid",
    ),
    ColumnSpec(
        "params",
        "Параметры",
        ("параметры", "параметры cfg", "params"),
        "device",
        "нет",
        "<путь>=<литерал ST>; …",
        "любые поля Cfg: tMinStop=T#30S; stVfd.rSpeedMin_pct=30.0",
    ),
)

COLUMN_BY_NAME: dict[str, ColumnSpec] = {spec.name: spec for spec in COLUMNS}

# Колонки, без которых перечень не разобрать: их отсутствие — одна ошибка на файл
REQUIRED_COLUMNS: tuple[str, ...] = ("tag", "description", "signal_type", "device_type", "dev_no")
MODBUS_COLUMNS: tuple[str, ...] = ("mb_link", "mb_slave", "mb_func", "mb_reg", "mb_type", "mb_bit", "mb_order")
SETPOINT_COLUMNS: tuple[str, ...] = ("sp_hh", "sp_h", "sp_l", "sp_ll")

_NON_WORD = re.compile(r"[^0-9a-zа-я№]+")


def normalize_header(text: str) -> str:
    """Заголовок для сравнения: нижний регистр, «ё» → «е», знаки → пробел (``Ед. изм.`` → ``ед изм``)."""
    folded = text.casefold().replace("ё", "е")
    return " ".join(_NON_WORD.sub(" ", folded).split())


_UNIT_TOKENS = frozenset({"с", "сек", "s", "sec"})


def header_index(extra_aliases: Mapping[str, str] | None = None) -> dict[str, str]:
    """Нормализованный заголовок → каноническое имя колонки."""
    index: dict[str, str] = {}
    for spec in COLUMNS:
        index[normalize_header(spec.name)] = spec.name
        index[normalize_header(spec.title)] = spec.name
        for alias in spec.aliases:
            index[normalize_header(alias)] = spec.name
    for alias, name in (extra_aliases or {}).items():
        index[normalize_header(alias)] = name
    return index


def match_header(text: str, index: Mapping[str, str]) -> str | None:
    """Каноническое имя колонки по заголовку.

    Хвост с единицей не мешает: «Задержка вкл., с», «HH, м», «Уставка HH, ед. изм.», «Адрес
    регистра (PDU)» — сравнивается часть до первой запятой или скобки.
    """
    key = normalize_header(text)
    if not key:
        return None
    if key in index:
        return index[key]
    words = key.split()
    if len(words) > 1 and words[-1] in _UNIT_TOKENS:
        found = index.get(" ".join(words[:-1]))
        if found is not None:
            return found
    for separator in (",", "("):
        head, sep, _ = text.partition(separator)
        head_key = normalize_header(head)
        if sep and head_key and head_key in index:
            return index[head_key]
    return None


# Колонки с числами: ячейка из одних тире («—», «-») значит «нет значения», как пустая
NUMERIC_COLUMNS = frozenset(
    {
        "dev_no",
        "range_min",
        "range_max",
        "sp_hh",
        "sp_h",
        "sp_l",
        "sp_ll",
        "delay_on_s",
        "delay_off_s",
        "io_channel",
        "mb_slave",
        "mb_func",
        "mb_reg",
        "mb_bit",
    }
)
