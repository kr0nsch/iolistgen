"""Каталог и заглушка совпадают с исходниками выпущенной библиотеки plc-process-lib 1.0.0.

Проверки — ``tests_support/check_library.py``: версия и закрепление, перечисления, Cfg с
умолчаниями, Cmd/Sts/Retain, входы и выходы ФБ, константы ``GVL_Const``, полнота каталога,
заглушка, шаблоны текстов тревог. Нужны исходники библиотеки (``PL_REPO`` или соседний каталог
``../plc-process-lib``); без них тест пропускается — в CI каталог с заглушкой сверяет
``test_pl_stub.py``.
"""

from __future__ import annotations

import pytest

from tests_support import check_library

LIBRARY = check_library.find_library()

pytestmark = pytest.mark.skipif(
    LIBRARY is None, reason="нет исходников plc-process-lib (PL_REPO или ../plc-process-lib)"
)


@pytest.fixture(scope="module")
def library() -> check_library.Library:
    assert LIBRARY is not None
    return check_library.load_library(LIBRARY)


@pytest.mark.parametrize("check", list(check_library.CHECKS))
def test_matches_library(library: check_library.Library, check: str) -> None:
    problems = check_library.run_checks(library, [check])[check]
    assert problems == []


def test_library_is_released_version(library: check_library.Library) -> None:
    assert library.version == "1.0.0.0"


def test_eval_bound_with_constants() -> None:
    assert check_library.eval_bound("GVL_Const.DEV_ALARMS_MAX - 1", {"DEV_ALARMS_MAX": 8}) == 7
    assert check_library.eval_bound("3", {}) == 3


def test_element_assignments() -> None:
    items = check_library.element_assignments("[(ePriority:=E_AlarmPriority.High),(ePriority:=X,tOnDelay:=T#1S)]")
    assert items == [{"ePriority": "E_AlarmPriority.High"}, {"ePriority": "X", "tOnDelay": "T#1S"}]
