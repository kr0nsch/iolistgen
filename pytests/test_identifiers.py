"""Тег → идентификатор ST (контракт plc-process-lib, 20.4)."""

from __future__ import annotations

import pytest

from iolistgen.identifiers import check_identifier, identifier_key, to_identifier


@pytest.mark.parametrize(
    ("tag", "identifier"),
    [
        ("LT101", "LT101"),
        ("P-101.RUN", "P_101_RUN"),
        ("P101  RUN", "P101_RUN"),
        ("P101__RUN", "P101_RUN"),
        ("P101-_RUN", "P101_RUN"),
        (" LT101 ", "LT101"),
        ("P101-", "P101"),
    ],
)
def test_to_identifier(tag: str, identifier: str) -> None:
    assert to_identifier(tag) == identifier
    assert check_identifier(tag) is None


def test_identifier_key_ignores_case() -> None:
    assert identifier_key(to_identifier("LT101a")) == identifier_key(to_identifier("lt101A"))


def test_cyrillic_lookalikes_get_latin_suggestion() -> None:
    problem = check_identifier("Р101_RUN")
    assert problem is not None
    assert "«Р»" in problem.message
    assert "P101_RUN" in problem.hint


def test_other_cyrillic_letters() -> None:
    problem = check_identifier("НАСОС1")
    assert problem is not None
    assert "не ASCII" in problem.message or "кириллические" in problem.message
    problem = check_identifier("Насос1")
    assert problem is not None
    assert "не ASCII" in problem.message


@pytest.mark.parametrize(("tag", "fragment"), [("101LT", "не с буквы"), ("LT#101", "недопустимые"), ("---", "букв")])
def test_invalid_identifiers(tag: str, fragment: str) -> None:
    problem = check_identifier(tag)
    assert problem is not None
    assert fragment in problem.message
