"""Чтение CSV: разделители, BOM, кодировка, заголовки по-русски, координаты ячеек."""

from __future__ import annotations

from pathlib import Path

import pytest

from iolistgen.config import InputConfig
from iolistgen.loaders import InputError, load_table
from iolistgen.loaders.csv_loader import detect_delimiter, read_records
from iolistgen.validate import check_file
from pytests.helpers import DATA, codes, config_from

HEADER = "tag;description;signal_type;device_type;dev_no;role;range_min;range_max;units"
ROW = "LT101;Уровень;AI;AnalogInput;1;PV;0;4,5;м"


def write(tmp_path: Path, text: str, *, encoding: str = "utf-8", name: str = "list.csv") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_semicolon_with_decimal_comma(tmp_path: Path) -> None:
    table = load_table(write(tmp_path, f"{HEADER}\n{ROW}\n"), InputConfig())
    assert table.header_row == 1
    assert table.rows[0].cells["range_max"].text == "4,5"
    result = check_file(write(tmp_path, f"{HEADER}\n{ROW}\n"))
    assert result.ok
    assert result.model is not None
    assert result.model.signals[0].range_max == 4.5


def test_comma_delimiter(tmp_path: Path) -> None:
    text = HEADER.replace(";", ",") + "\n" + 'LT101,Уровень,AI,AnalogInput,1,PV,0,"4,5",м\n'
    result = check_file(write(tmp_path, text))
    assert result.ok, [d.render() for d in result.diagnostics]
    assert result.model is not None and result.model.signals[0].range_max == 4.5


def test_tab_delimiter(tmp_path: Path) -> None:
    text = HEADER.replace(";", "\t") + "\n" + ROW.replace(";", "\t") + "\n"
    assert check_file(write(tmp_path, text)).ok


def test_detect_delimiter_prefers_header_match() -> None:
    assert detect_delimiter(f"{HEADER}\n{ROW}\n") == ";"
    assert detect_delimiter("a,b,c;d\n") == ","
    assert detect_delimiter("a,b;c\n") == ";"
    assert detect_delimiter("") == ";"


def test_bom_is_ignored(tmp_path: Path) -> None:
    result = check_file(write(tmp_path, f"﻿{HEADER}\r\n{ROW}\r\n"))
    assert result.ok
    assert result.model is not None and result.model.signals[0].tag == "LT101"


def test_cp1251_reports_encoding_with_position(tmp_path: Path) -> None:
    path = write(tmp_path, f"{HEADER}\n{ROW}\n", encoding="cp1251")
    result = check_file(path)
    assert codes(result) == ["IOL001"]
    diagnostic = result.diagnostics[0]
    assert diagnostic.source is not None and diagnostic.source.row == 2
    assert "cp1251" in diagnostic.hint


def test_cp1251_with_encoding_option(tmp_path: Path) -> None:
    path = write(tmp_path, f"{HEADER}\n{ROW}\n", encoding="cp1251")
    result = check_file(path, config_from({"input": {"encoding": "cp1251"}}))
    assert result.ok
    assert result.model is not None and result.model.signals[0].description == "Уровень"


def test_empty_file(tmp_path: Path) -> None:
    assert codes(check_file(write(tmp_path, "  \n"))) == ["IOL001"]


def test_multiline_cell_keeps_physical_row_numbers(tmp_path: Path) -> None:
    text = (
        f"{HEADER}\n"
        'LT101;"Уровень\nв резервуаре";AI;AnalogInput;1;PV;0;5;м\n'
        "LT102;Уровень 2;AI;AnalogInput;2;PV;5;0;м\n"
    )
    result = check_file(write(tmp_path, text))
    assert codes(result) == ["IOL204"]
    assert result.diagnostics[0].source is not None
    assert result.diagnostics[0].source.row == 4
    assert result.diagnostics[0].source.column_letter == "G"


def test_records_report_start_line() -> None:
    records = list(read_records('a;b\n"x\ny";z\nq;w\n', ";"))
    assert [line for line, _ in records] == [1, 2, 4]


def test_russian_headers_and_title_rows(tmp_path: Path) -> None:
    text = (
        "Перечень сигналов КНС-1;;;;;\n"
        "\n"
        "# служебная строка\n"
        "Тег;Описание;Тип сигнала;Тип устройства;Номер устройства;Роль;Мин.;Макс.;Ед. изм.;Задержка вкл., с\n"
        "LT101;Уровень;AI;AnalogInput;1;PV;0;5;м;\n"
        "# закомментированный резерв;;;;;\n"
        "LT102;Уровень 2;AI;AnalogInput;2;PV;0;5;м;\n"
    )
    table = load_table(write(tmp_path, text), InputConfig())
    assert table.header_row == 4
    assert [b.field for b in table.columns] == [
        "tag",
        "description",
        "signal_type",
        "device_type",
        "dev_no",
        "role",
        "range_min",
        "range_max",
        "units",
        "delay_on_s",
    ]
    assert [row.source.row for row in table.rows] == [5, 7]
    assert check_file(write(tmp_path, text, name="b.csv")).ok


def test_column_aliases_from_config(tmp_path: Path) -> None:
    text = "Позиция по схеме;description;signal_type;device_type;dev_no;role;range_min;range_max;units\n" + ROW + "\n"
    assert "IOL002" in codes(check_file(write(tmp_path, text)))
    result = check_file(write(tmp_path, text), config_from({"input": {"column_aliases": {"Позиция по схеме": "tag"}}}))
    assert result.ok


def test_missing_header(tmp_path: Path) -> None:
    result = check_file(write(tmp_path, "a;b\n1;2\n"))
    assert codes(result) == ["IOL002"]


def test_missing_required_columns_reported_once(tmp_path: Path) -> None:
    text = (
        "tag;description;signal_type;role;range_min;range_max;units\nLT101;Уровень;AI;PV;0;5;м\nLT102;x;AI;PV;0;5;м\n"
    )
    result = check_file(write(tmp_path, text))
    assert codes(result).count("IOL003") == 2
    assert "IOL302" not in codes(result)
    assert "IOL309" not in codes(result)


def test_unknown_column_kept_in_model(tmp_path: Path) -> None:
    text = f"{HEADER};Примечание\n{ROW};поверка 2026\n"
    result = check_file(write(tmp_path, text))
    assert codes(result) == ["IOL005"]
    assert result.model is not None
    assert result.model.signals[0].extra == {"Примечание": "поверка 2026"}


def test_unquoted_params_tail_is_merged(tmp_path: Path) -> None:
    text = f"{HEADER};params\n{ROW};tFilter=T#2S; xClamp=TRUE; tFailDelay=T#3S\n"
    result = check_file(write(tmp_path, text))
    assert result.ok, [d.render() for d in result.diagnostics]
    assert result.model is not None
    cfg = result.model.devices[0].cfg
    assert cfg.value("tFilter") == 2000
    assert cfg.value("xClamp") is True
    assert cfg.value("tFailDelay") == 3000


def test_values_without_header_warn(tmp_path: Path) -> None:
    text = f"{HEADER}\n{ROW};лишнее\n"
    result = check_file(write(tmp_path, text))
    assert codes(result) == ["IOL006"]


def test_explicit_delimiter_from_config(tmp_path: Path) -> None:
    text = HEADER.replace(";", ",") + "\n" + ROW.replace(";", ",").replace("4,5", "4.5") + "\n"
    assert check_file(write(tmp_path, text), config_from({"input": {"delimiter": ","}})).ok


def test_unsupported_extensions(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="не найден"):
        load_table(tmp_path / "missing.csv", InputConfig())
    old = tmp_path / "list.xls"
    old.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(InputError, match="xlsx"):
        load_table(old, InputConfig())
    other = tmp_path / "list.json"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(InputError, match="неподдерживаемый"):
        load_table(other, InputConfig())


def test_sample_lists() -> None:
    good = check_file(DATA / "kns_mini.csv")
    assert good.diagnostics == []
    bad = check_file(DATA / "kns_errors.csv")
    assert not bad.ok
    assert len(bad.errors) >= 10


def test_number_formats(tmp_path: Path) -> None:
    rows = "\n".join(
        [
            HEADER,
            "LT101;Уровень;AI;AnalogInput;1;PV;0;1 000;м",
            "LT102;Уровень;AI;AnalogInput;2;PV;-0,5;12 345,5;м",
            "LT103;Уровень;AI;AnalogInput;3;PV;0;4 20;м",
            "LT104;Уровень;AI;AnalogInput;4;PV;0;1e3;м",
        ]
    )
    result = check_file(write(tmp_path, rows + "\n"))
    assert codes(result) == ["IOL007"]
    assert result.diagnostics[0].tag == "LT103"


def test_unicode_minus_and_group_separators(tmp_path: Path) -> None:
    """«−40» из Word или PDF — знак минус U+2212, «1 000» с узким неразрывным пробелом U+202F."""
    rows = "\n".join(
        [
            HEADER,
            "TT101;Температура;AI;AnalogInput;1;PV;−40;60;°C",
            "TT102;Температура;AI;AnalogInput;2;PV;–50;1 000;°C",
            "TT103;Температура;AI;AnalogInput;3;PV;− 5;5;°C",
        ]
    )
    result = check_file(write(tmp_path, rows + "\n"))
    assert result.ok, [d.render() for d in result.diagnostics]
    assert result.model is not None
    assert [(s.range_min, s.range_max) for s in result.model.signals] == [(-40, 60), (-50, 1000), (-5, 5)]


def test_excel_error_value_named_in_message(tmp_path: Path) -> None:
    result = check_file(write(tmp_path, f"{HEADER}\nLT101;Уровень;AI;AnalogInput;1;PV;0;#ЗНАЧ!;м\n"))
    assert codes(result) == ["IOL007"]
    assert "ошибка формулы Excel" in result.diagnostics[0].message


@pytest.mark.parametrize(
    ("header", "column"),
    [
        ("HH, м", "sp_hh"),
        ("Уставка HH, ед. изм.", "sp_hh"),
        ("Мин., ед.", "range_min"),
        ("Шкала макс, бар", "range_max"),
        ("Задержка вкл., с", "delay_on_s"),
        ("Тег, позиция", "tag"),
    ],
)
def test_header_with_units_after_comma(header: str, column: str) -> None:
    from iolistgen.columns import header_index, match_header

    assert match_header(header, header_index()) == column


def test_directory_is_not_a_list(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="каталог"):
        load_table(tmp_path, InputConfig())


def test_content_hash_ignores_comments_and_blank_rows(tmp_path: Path) -> None:
    base = load_table(write(tmp_path, f"{HEADER}\n{ROW}\n", name="a.csv"), InputConfig())
    noisy = load_table(
        write(tmp_path, f"Перечень КНС-1\n\n{HEADER}\r\n# резерв D1.8\n\n{ROW}\r\n", name="b.csv"), InputConfig()
    )
    assert base.sha256 == noisy.sha256 and len(base.sha256) == 64
    other = load_table(write(tmp_path, f"{HEADER}\n{ROW.replace('4,5', '4,6')}\n", name="c.csv"), InputConfig())
    assert other.sha256 != base.sha256


def test_enum_cells_tolerate_cyrillic_lookalikes_and_tails(tmp_path: Path) -> None:
    """Русская раскладка («АI» — кириллическая А) и пояснение в ячейке типа («AI 4–20 мА»)."""
    header = HEADER + ";mb_slave;mb_func;mb_reg;mb_type"
    rows = [
        header,
        "LT101;Уровень;АI;AnalogInput;1;PV;0;5;м;;;;",
        "LT102;Уровень;AI 4–20 мА;AnalogInput;2;PV;0;5;м;;;;",
        "LS103;Поплавок;DI (сухой контакт);DigitalInput;3;IN;;;;;;;",
        "TT104;Температура;МB;AnalogInput;4;PV;0;100;°C;1;4;0;REAL",
    ]
    result = check_file(write(tmp_path, "\n".join(rows) + "\n"), config_from({"severity": {"IOL408": "off"}}))
    assert [d.render() for d in result.diagnostics] == []
    assert result.model is not None
    assert [s.signal_type.value for s in result.model.signals] == ["AI", "AI", "DI", "MB"]


def test_enum_cell_with_unknown_word_is_still_an_error(tmp_path: Path) -> None:
    result = check_file(write(tmp_path, f"{HEADER}\nLT101;Уровень;AIX;AnalogInput;1;PV;0;5;м\n"))
    assert codes(result) == ["IOL202"]


def test_missing_header_hint_mentions_column_aliases(tmp_path: Path) -> None:
    result = check_file(write(tmp_path, "Позиция по схеме;Наименование\nLT101;Уровень\n"))
    assert codes(result) == ["IOL002"]
    assert "column_aliases" in result.diagnostics[0].hint


def test_empty_tag_hint_mentions_aux_for_spare_channels(tmp_path: Path) -> None:
    result = check_file(write(tmp_path, f"{HEADER}\n{ROW}\n;Резерв;DI;;;;;;\n"))
    found = [d for d in result.diagnostics if d.code == "IOL101"]
    assert found and "AUX" in found[0].hint
