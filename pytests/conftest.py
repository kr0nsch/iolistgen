"""Фикстуры тестов iolistgen."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from iolistgen.validate import CheckResult, check_file
from pytests.helpers import COLUMNS, Row, config_from, write_csv


@pytest.fixture
def check_rows(tmp_path: Path) -> Callable[..., CheckResult]:
    """Записать строки в CSV и проверить: ``check_rows(rows, config={...}, columns=...)``."""
    counter = iter(range(1_000_000))

    def run(
        rows: Sequence[Row],
        *,
        config: Mapping[str, object] | None = None,
        columns: Sequence[str] = COLUMNS,
    ) -> CheckResult:
        path = write_csv(tmp_path / f"list{next(counter)}.csv", rows, columns)
        return check_file(path, config_from(config))

    return run
