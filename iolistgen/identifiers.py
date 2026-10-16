"""Тег перечня → идентификатор ST (контракт plc-process-lib, 20.4).

Правило: ASCII, первая — буква, дальше буквы, цифры и одиночные ``_``. Символы ``-``, ``.`` и
пробел заменяются на ``_``, два ``_`` подряд схлопываются (CODESYS запрещает ``__``).
Регистр в ST не различается, поэтому дубли ищутся по ``casefold()`` нормализованного имени.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_REPLACED = re.compile(r"[-. ]+")
_MULTI_UNDERSCORE = re.compile(r"_{2,}")
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*$")

# Кириллические буквы, которые выглядят как латинские: частая ошибка в тегах («Р» вместо «P»)
HOMOGLYPHS = {
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "Х": "X",
    "У": "Y",
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "у": "y",
    "х": "x",
}


@dataclass(frozen=True)
class IdentifierProblem:
    """Почему тег нельзя превратить в идентификатор и как это исправить."""

    message: str
    hint: str


def to_identifier(text: str) -> str:
    """Нормализовать тег: ``P-101.RUN`` → ``P_101_RUN``. Проверку делает ``check_identifier``."""
    value = _REPLACED.sub("_", text.strip())
    value = _MULTI_UNDERSCORE.sub("_", value)
    return value.strip("_")


def identifier_key(identifier: str) -> str:
    """Ключ сравнения: CODESYS не различает регистр."""
    return identifier.casefold()


def check_identifier(text: str) -> IdentifierProblem | None:
    """Проблема тега или ``None``, если из него получается идентификатор ST."""
    identifier = to_identifier(text)
    foreign = sorted({char for char in identifier if not char.isascii()})
    if foreign:
        lookalikes = [char for char in foreign if char in HOMOGLYPHS]
        foreign_count = sum(1 for char in identifier if not char.isascii())
        has_latin = any(char.isascii() and char.isalpha() for char in identifier)
        # «Р101_RUN», «Р101» — опечатка раскладки; «Насос1» — русское слово, замену не предлагаем
        typo = has_latin or foreign_count <= 2
        if lookalikes and len(lookalikes) == len(foreign) and typo:
            fixed = "".join(HOMOGLYPHS.get(char, char) for char in identifier)
            letters = ", ".join(f"«{char}»" for char in lookalikes)
            return IdentifierProblem(
                f"в теге кириллические буквы {letters}, похожие на латинские",
                f"замените их латинскими: {fixed}",
            )
        letters = ", ".join(f"«{char}»" for char in foreign)
        return IdentifierProblem(
            f"в теге символы не ASCII: {letters}",
            "тег пишется латиницей, цифрами и «_» (позиции по ГОСТ 21.208 — латинскими буквами)",
        )
    if not identifier:
        return IdentifierProblem("тег не содержит букв и цифр", "задайте тег вида LT101 или P101_RUN")
    if not identifier[0].isalpha():
        return IdentifierProblem(
            f"тег «{text}» начинается не с буквы",
            "идентификатор ST начинается с буквы: добавьте буквенный код (например, LT101)",
        )
    if not _IDENTIFIER.match(identifier):
        bad = sorted({char for char in identifier if not (char.isalnum() or char == "_")})
        letters = " ".join(bad)
        return IdentifierProblem(
            f"в теге недопустимые символы: {letters}",
            "оставьте латинские буквы, цифры и «_»; «-», «.» и пробел заменяются на «_» автоматически",
        )
    return None
