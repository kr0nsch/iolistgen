"""Отчёты Markdown и HTML: содержание, экранирование, детерминированность, самодостаточность."""

from __future__ import annotations

import re
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path

import pytest

from iolistgen import __version__
from iolistgen.config import resolve_config
from iolistgen.report import count_text, plural, render_html, render_markdown, summary_line
from iolistgen.report.markdown import md_cell
from iolistgen.validate import CheckResult, check_file
from pytests.helpers import DATA, ai

Check = Callable[..., CheckResult]


@pytest.mark.parametrize(
    ("count", "word"),
    [(1, "ошибка"), (2, "ошибки"), (5, "ошибок"), (11, "ошибок"), (21, "ошибка"), (104, "ошибки"), (112, "ошибок")],
)
def test_plural(count: int, word: str) -> None:
    assert plural(count, "ошибка", "ошибки", "ошибок") == word


def test_summary_line() -> None:
    assert count_text(3, "сигнал", "сигнала", "сигналов") == "3 сигнала"
    good = check_file(DATA / "kns_mini.csv")
    assert summary_line(good) == "ошибок нет"
    bad = check_file(DATA / "kns_errors.csv")
    assert re.fullmatch(r"\d+ ошиб\w+, \d+ предупрежден\w+", summary_line(bad))


def test_md_cell_escaping() -> None:
    assert md_cell("a | b") == "a \\| b"
    assert md_cell("<путь>=<литерал>") == "&lt;путь&gt;=&lt;литерал&gt;"
    assert md_cell("строка 1\nстрока 2") == "строка 1<br>строка 2"


def test_markdown_report_for_errors() -> None:
    result = check_file(DATA / "kns_errors.csv")
    text = render_markdown(result, __version__)
    assert text.startswith("# Проверка перечня сигналов\n")
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert "Генерация невозможна" in text
    assert "| ошибка | IOL204 | 2 | H «range_min» | `LT101` |" in text
    assert "## Сработавшие правила" in text
    assert result.source.sha256 in text
    table_rows = [
        line for line in text.splitlines() if line.startswith("| ошибка |") or line.startswith("| предупреждение |")
    ]
    assert len(table_rows) == len(result.diagnostics)
    for line in table_rows:
        assert line.count(" | ") == 6


def test_markdown_report_without_messages() -> None:
    text = render_markdown(check_file(DATA / "kns_mini.csv"), __version__)
    assert "Перечень готов к генерации" in text
    assert "Сообщений нет." in text
    assert "Типы устройств: AnalogInput 5" in text


def test_reports_are_deterministic() -> None:
    first = check_file(DATA / "kns_errors.csv")
    second = check_file(DATA / "kns_errors.csv")
    assert render_markdown(first, "0.1.0") == render_markdown(second, "0.1.0")
    assert render_html(first, "0.1.0") == render_html(second, "0.1.0")


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.links: list[str] = []
        self.rows = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        values = dict(attrs)
        for name in ("src", "href"):
            if values.get(name):
                self.links.append(str(values[name]))
        if tag == "tr" and "data-severity" in values:
            self.rows += 1


def test_html_report_is_self_contained() -> None:
    result = check_file(DATA / "kns_errors.csv")
    html = render_html(result, __version__)
    parser = _Collector()
    parser.feed(html)
    assert html.startswith("<!doctype html>")
    assert parser.links == []
    assert "http://" not in html and "https://" not in html
    assert "<style>" in html and "prefers-color-scheme: dark" in html
    assert parser.rows == len(result.diagnostics)
    assert f"Найдено: {summary_line(result)}" in html
    assert 'lang="ru"' in html


def test_html_escapes_cell_values(check_rows: Check) -> None:
    result = check_rows([ai(tag="LT<b>101")])
    assert result.diagnostics[0].code == "IOL102"
    html = render_html(result, __version__)
    assert "LT<b>101" not in html
    assert "LT&lt;b&gt;101" in html


def test_html_report_ok_state() -> None:
    html = render_html(check_file(DATA / "kns_mini.csv"), __version__)
    assert "Перечень прошёл проверку" in html
    assert "Сообщений нет" in html
    assert "<script>" not in html  # без сообщений сценарий фильтров не нужен


def test_report_shows_found_config_relative_to_list(tmp_path: Path) -> None:
    """Регрессия: найденный iolistgen.toml попадал в отчёт абсолютным путём машины автора."""
    (tmp_path / ".git").mkdir()  # корень репозитория: поиск настроек дальше не идёт
    (tmp_path / "iolistgen.toml").write_text("[naming]\nmax_device_length = 20\n", encoding="utf-8")
    lists = tmp_path / "docs"
    lists.mkdir()
    target = lists / "io_list.csv"
    target.write_bytes((DATA / "kns_mini.csv").read_bytes())
    result = check_file(target, resolve_config(None, target))
    assert result.config.path is not None and Path(result.config.path).is_absolute()
    for text in (render_markdown(result, __version__), render_html(result, __version__)):
        assert "../iolistgen.toml" in text
        assert str(tmp_path) not in text and tmp_path.as_posix() not in text
