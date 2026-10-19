"""Сообщения проверки: правила с кодами, уровни, сбор и сортировка.

Каждое сообщение отвечает на три вопроса: где (файл, лист, строка, колонка), что не так
и как исправить. Уровень правила по умолчанию задан здесь, проект переопределяет его в
``iolistgen.toml`` (``[severity] IOL104 = "warning"`` или ``"off"``).

Структурные правила (``Rule.adjustable = False``) не ослабляются: сработав, они отбрасывают
данные, без которых модель перечня не строится, — тег, тип сигнала, роль, тип и номер
устройства, адрес Modbus. Отключи такое правило — и перечень «без ошибок» дошёл бы до генераторов
с дырами.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict

from iolistgen.model import SourceRef


class Severity(str, Enum):
    """Уровень сообщения."""

    ERROR = "error"
    WARNING = "warning"

    @property
    def label(self) -> str:
        return "ошибка" if self is Severity.ERROR else "предупреждение"


SEVERITY_OFF = "off"


@dataclass(frozen=True)
class Rule:
    """Правило проверки перечня; ``adjustable`` — уровень можно понизить в ``iolistgen.toml``."""

    code: str
    severity: Severity
    group: str
    title: str
    adjustable: bool = True


GROUPS = {
    "0": "Структура файла",
    "1": "Теги и имена",
    "2": "Атрибуты сигналов",
    "3": "Устройства и роли",
    "4": "Modbus",
    "5": "Параметры Cfg (params)",
    "6": "Каналы модулей ввода-вывода",
}

_E = Severity.ERROR
_W = Severity.WARNING
# Структурные правила: данные строки после них не попадают в модель (см. docstring модуля)
STRUCTURAL_RULES = frozenset(
    {
        "IOL001",
        "IOL002",
        "IOL003",
        "IOL007",
        "IOL101",
        "IOL102",
        "IOL103",
        "IOL105",
        "IOL201",
        "IOL202",
        "IOL301",
        "IOL302",
        "IOL303",
        "IOL304",
        "IOL305",
        "IOL306",
        "IOL307",
        "IOL308",
        "IOL309",
        "IOL310",
        "IOL311",
        "IOL312",
        "IOL401",
        "IOL403",
        "IOL404",
        "IOL405",
        "IOL406",
        "IOL407",
        "IOL411",
        "IOL413",
    }
)
_RULE_TABLE: tuple[tuple[str, Severity, str], ...] = (
    ("IOL001", _E, "файл не читается: кодировка, повреждённый XLSX, пустой файл"),
    ("IOL002", _E, "нет строки заголовка с колонкой tag"),
    ("IOL003", _E, "нет обязательной колонки"),
    ("IOL004", _E, "колонка повторяется"),
    ("IOL005", _W, "неизвестная колонка (игнорируется)"),
    ("IOL006", _W, "значения за последней колонкой заголовка (игнорируются)"),
    ("IOL007", _E, "значение ячейки не разобрано: число, целое, длительность, перечисление"),
    ("IOL101", _E, "пустой тег"),
    ("IOL102", _E, "тег нельзя превратить в идентификатор ST"),
    ("IOL103", _E, "дубль тега (без учёта регистра, после замены «-», «.», пробела на «_»)"),
    ("IOL104", _E, "тег не по правилу именования (naming.tag_regex)"),
    ("IOL105", _E, "имя устройства нельзя превратить в идентификатор ST"),
    ("IOL106", _E, "имя устройства не по правилу именования (naming.device_regex)"),
    ("IOL107", _E, "имя устройства длиннее naming.max_device_length"),
    ("IOL108", _E, "разные имена устройств дают один идентификатор"),
    ("IOL201", _E, "нет описания"),
    ("IOL202", _E, "тип сигнала не задан или неизвестен"),
    ("IOL203", _E, "у AnalogInput нет диапазона шкалы"),
    ("IOL204", _E, "минимум диапазона не меньше максимума (AI_CFG_RANGE)"),
    ("IOL205", _E, "задана только одна граница диапазона"),
    ("IOL206", _E, "у AnalogInput нет единиц измерения"),
    ("IOL207", _W, "у аналогового сигнала нет единиц измерения"),
    ("IOL208", _E, "нарушен порядок уставок LL < L < H < HH (AI_CFG_LIMIT_ORDER)"),
    ("IOL209", _E, "уставка вне диапазона шкалы (AI_CFG_LIMIT_OUT_OF_RANGE)"),
    ("IOL210", _W, "уставки у устройства не AnalogInput (игнорируются)"),
    ("IOL211", _W, "задержка не применяется (тип устройства, нет уставок)"),
    ("IOL212", _W, "колонка устройства заполнена не в главной строке (игнорируется)"),
    ("IOL213", _W, "у ПИД-регулятора не задан диапазон PV (нормировка ошибки по умолчанию 0…100)"),
    ("IOL301", _E, "неизвестный тип устройства"),
    ("IOL302", _E, "не задан тип устройства"),
    ("IOL303", _E, "в строках устройства разные device_type или dev_no"),
    ("IOL304", _E, "роль не задана или неизвестна"),
    ("IOL305", _E, "роль недопустима для типа устройства"),
    ("IOL306", _E, "тип сигнала недопустим для роли"),
    ("IOL307", _E, "роль повторяется в устройстве"),
    ("IOL308", _E, "нет обязательной роли"),
    ("IOL309", _E, "не задан номер устройства dev_no"),
    ("IOL310", _E, "номер устройства вне 1…9999"),
    ("IOL311", _E, "номер устройства повторяется"),
    ("IOL312", _E, "несовместимые роли: формы управления арматурой, роли ПЧ у Motor"),
    ("IOL313", _E, "link_* ссылается на несуществующее устройство"),
    ("IOL314", _E, "link_* недопустим для типа устройства или ведёт к устройству не того типа"),
    ("IOL315", _W, "сигнал не используется ФБ при заданных параметрах"),
    ("IOL316", _W, "неполный или рискованный набор сигналов устройства"),
    ("IOL317", _W, "колонка устройства у сигнала без ФБ (AUX) не используется"),
    ("IOL401", _E, "у сигнала MB не задан адрес Modbus"),
    ("IOL402", _W, "адрес Modbus у сигнала не MB или у строки устройства (игнорируется)"),
    ("IOL403", _E, "неизвестная функция Modbus"),
    ("IOL404", _E, "неизвестный тип данных Modbus"),
    ("IOL405", _E, "тип данных не подходит к функции"),
    ("IOL406", _E, "адрес вне 0…65535 с учётом длины типа"),
    ("IOL407", _E, "номер бита задан неверно"),
    ("IOL408", _W, "не указан порядок слов 32/64-битного значения"),
    ("IOL409", _W, "порядок слов у 16-битного значения не нужен"),
    ("IOL410", _E, "направление функции Modbus не совпадает с ролью"),
    ("IOL411", _E, "тип данных не подходит к роли"),
    ("IOL412", _E, "адреса Modbus пересекаются (с учётом длины типа и битов)"),
    ("IOL413", _E, "адрес слейва вне 0…255"),
    ("IOL414", _W, "адрес слейва 248…255 зарезервирован в Modbus RTU"),
    ("IOL415", _W, "сигналы MB одного устройства на разных слейвах"),
    ("IOL416", _E, "адрес слейва 0 — широковещательный в Modbus RTU (для Unit ID 0 Modbus TCP — ослабить)"),
    ("IOL417", _W, "имя линии Modbus не даёт идентификатор ST (имена переменных состояния обмена)"),
    ("IOL501", _E, "синтаксис params: ожидается <путь>=<литерал ST>; …"),
    ("IOL502", _E, "неизвестный параметр Cfg"),
    ("IOL503", _E, "значение параметра не подходит к его типу"),
    ("IOL504", _E, "параметр задаётся колонкой перечня или генератором"),
    ("IOL505", _E, "параметр задан и колонкой, и в params"),
    ("IOL506", _E, "параметр повторяется в params"),
    ("IOL507", _E, "конфигурация не пройдёт CheckConfig ФБ (бит wCfgErr)"),
    ("IOL508", _W, "параметр не используется этим типом устройства"),
    ("IOL509", _E, "параметр противоречит составу устройства"),
    ("IOL601", _E, "два сигнала на одном канале модуля"),
    ("IOL602", _W, "задан модуль без канала или канал без модуля"),
    ("IOL603", _W, "модуль и канал у сигнала MB или у строки устройства (игнорируются)"),
)

RULES: dict[str, Rule] = {
    code: Rule(
        code=code, severity=severity, group=GROUPS[code[3]], title=title, adjustable=code not in STRUCTURAL_RULES
    )
    for code, severity, title in _RULE_TABLE
}


def lowering_error(code: str, level: str) -> str | None:
    """Почему уровень ``level`` нельзя назначить правилу ``code`` (``None`` — можно)."""
    rule = RULES[code]
    if rule.adjustable or level == rule.severity.value:
        return None
    return (
        f"правило {code} нельзя ослабить: оно структурное — без данных, которые оно отбрасывает, "
        "модель перечня не строится; исправьте перечень"
    )


class Diagnostic(BaseModel):
    """Сообщение проверки."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: Severity
    message: str
    hint: str = ""
    source: SourceRef | None = None
    related: tuple[SourceRef, ...] = ()
    tag: str | None = None
    device: str | None = None

    @property
    def rule(self) -> Rule:
        return RULES[self.code]

    @property
    def related_text(self) -> str:
        return describe_related(self.source, self.related)

    def render(self) -> str:
        """Одна-две строки для консоли: ``kns.csv:12: IOL204 [ошибка] колонка F «Макс.»: …``."""
        where = self.source.short() if self.source is not None else "?"
        place = ""
        if self.source is not None and self.source.col is not None:
            place = f"колонка {self.source.column_letter}"
            if self.source.header:
                place += f" «{self.source.header}»"
            place += ": "
        sheet = f"лист «{self.source.sheet}», " if self.source is not None and self.source.sheet else ""
        text = f"{where}: {self.code} [{self.severity.label}] {sheet}{place}{self.message}"
        if self.related:
            text += f" (см. {self.related_text})"
        if self.hint:
            text += f"\n    как исправить: {self.hint}"
        return text


def describe_related(source: SourceRef | None, refs: Sequence[SourceRef]) -> str:
    """Связанные места для «см. …»: «строку 5», а в той же строке — «колонку I «Макс.»»."""
    parts: list[str] = []
    for ref in refs:
        same_row = source is not None and ref.row is not None and ref.row == source.row
        if same_row and ref.col is not None:
            column = f"колонку {ref.column_letter}"
            parts.append(f"{column} «{ref.header}»" if ref.header else column)
        elif ref.row is not None:
            parts.append(f"строку {ref.row}")
        else:
            parts.append(ref.file)
    return ", ".join(parts)


class DiagnosticBag:
    """Накопитель сообщений одной проверки."""

    def __init__(self) -> None:
        self._items: list[Diagnostic] = []

    def add(
        self,
        code: str,
        message: str,
        hint: str = "",
        *,
        source: SourceRef | None = None,
        related: Sequence[SourceRef] = (),
        tag: str | None = None,
        device: str | None = None,
    ) -> None:
        rule = RULES[code]
        self._items.append(
            Diagnostic(
                code=code,
                severity=rule.severity,
                message=message,
                hint=hint,
                source=source,
                related=tuple(related),
                tag=tag,
                device=device,
            )
        )

    def extend(self, items: Iterable[Diagnostic]) -> None:
        self._items.extend(items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def finalize(self, overrides: Mapping[str, str] | None = None) -> list[Diagnostic]:
        """Уровни из настроек проекта (``off`` — убрать), сортировка по месту в файле."""
        result: list[Diagnostic] = []
        for item in self._items:
            level = (overrides or {}).get(item.code)
            if level is not None and lowering_error(item.code, level) is not None:
                level = None  # структурное правило: уровень не понижается (настройки это уже отвергли)
            if level == SEVERITY_OFF:
                continue
            if level is not None and level != item.severity.value:
                item = item.model_copy(update={"severity": Severity(level)})
            result.append(item)
        result.sort(key=sort_key)
        return result


def sort_key(item: Diagnostic) -> tuple[str, str, int, int, str]:
    source = item.source
    if source is None:
        return ("", "", -1, -1, item.code)
    return (source.file, source.sheet or "", source.row or 0, source.col or 0, item.code)
