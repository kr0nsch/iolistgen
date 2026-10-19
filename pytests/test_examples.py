"""Примеры из ``examples/``: КНС, синтетический перечень, витрина ошибок, замер времени.

Примеры — часть документации, поэтому тесты держат их в согласии с валидатором: перечень КНС
и синтетический проходят проверку без сообщений, XLSX КНС даёт ту же модель, что CSV, у каждой
строки витрины ошибок есть ожидаемое сообщение, а отчёт в ``docs/`` совпадает с текущим выводом.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from pathlib import Path

import pytest
from openpyxl import load_workbook

import benchmark
import csv_to_xlsx
import make_synthetic
from iolistgen import __version__
from iolistgen.config import Config
from iolistgen.enums import DeviceType, Role, SignalType
from iolistgen.model import IoList
from iolistgen.report import render_markdown
from iolistgen.validate import CheckResult, check_file

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
KNS_CSV = EXAMPLES / "kns" / "io_list.csv"
KNS_XLSX = EXAMPLES / "kns" / "io_list.xlsx"
SYNTHETIC = EXAMPLES / "synthetic" / "io_list_300.csv"
BROKEN = EXAMPLES / "broken" / "io_list_broken.csv"
BROKEN_REPORT = ROOT / "docs" / "io_list_broken.validation.md"
NOTE_COLUMN = "Пояснение"


def _check(path: Path) -> CheckResult:
    return check_file(path, Config())


def _model(path: Path) -> IoList:
    result = _check(path)
    assert result.model is not None, [item.render() for item in result.diagnostics]
    return result.model


def _signature(model: IoList) -> tuple[object, ...]:
    """Содержимое модели без мест в файле: устройства с Cfg и сигналы с адресами."""
    devices = tuple(
        (d.ident, d.device_type, d.dev_no, d.link_power, d.link_fb, d.cfg.initializer()) for d in model.devices
    )
    signals = tuple(
        (
            s.tag,
            s.description,
            s.signal_type,
            s.device,
            s.role,
            s.range_min,
            s.range_max,
            s.units,
            s.hmi_group,
            s.io_module,
            s.io_channel,
            s.modbus.model_dump() if s.modbus is not None else None,
        )
        for s in model.signals
    )
    return devices, signals


# --- КНС ------------------------------------------------------------------------------------------


def test_kns_list_is_clean() -> None:
    result = _check(KNS_CSV)
    assert [item.render() for item in result.diagnostics] == []
    stats = result.stats
    assert (stats.signals, stats.devices, stats.modbus) == (58, 30, 19)
    assert stats.by_signal_type == {"AI": 5, "DI": 27, "DO": 7, "MB": 19}
    assert stats.by_device_type == {"AnalogInput": 9, "DigitalInput": 16, "Motor": 1, "MotorVfd": 3, "Pid": 1}


def test_kns_level_controller_and_application_data(tmp_path: Path) -> None:
    """Регулятор уровня LIC101 (Pid) и данные приложения examples/kns/persist_extra.txt (iolistgen.toml рядом)."""
    from iolistgen.config import resolve_config
    from iolistgen.generators import GeneratorContext, resolve_options
    from iolistgen.generators.st_codesys import StCodesysGenerator

    model = _model(KNS_CSV)
    loop = model.device("LIC101")
    assert loop.device_type is DeviceType.PID and loop.signals == ()
    assert loop.cfg.value("eAction") == "Direct" and loop.cfg.value("xUseOutAct") is True
    assert (loop.cfg.value("rPvMin_eu"), loop.cfg.value("rPvMax_eu")) == (0.0, 5.0)
    assert loop.cfg.value("astAlarm[0].ePriority") == "None"  # дублирует LT101.FAIL (рационализация тревог)
    config = resolve_config(None, KNS_CSV)
    generator = StCodesysGenerator()
    options = resolve_options(
        generator, config.generators.get(generator.name), config_dir=Path(str(config.path)).parent
    )
    assert Path(str(options["persist_extra"])) == EXAMPLES / "kns" / "persist_extra.txt"
    ctx = GeneratorContext(generator.name, tmp_path, options, config, model.source, "test")
    generator.generate(model, tmp_path, ctx)
    persist = (tmp_path / "src/GVLs/Generated/GVL_Persist.pvl.st").read_text(encoding="utf-8")
    assert persist.index("stHS502Cfg") < persist.index("rLIC101SpOper_m : REAL := 2.0;")


def test_kns_pumps_follow_station_conventions() -> None:
    """Насосы Н1–Н3: пуск проводом, ОС и авария проводом, ПЧ — слейв n линии RS485-1 (README примера)."""
    model = _model(KNS_CSV)
    registers = {"VFD_CTW": (16, 0), "SPEED_REF": (16, 1), "VFD_STW": (3, 100), "SPEED_ACT": (3, 101)}
    for n in (1, 2, 3):
        pump = model.device(f"P10{n}")
        assert pump.device_type is DeviceType.MOTOR_VFD
        assert pump.link_power == "ES301"
        assert {s.role for s in pump.signals} == {
            Role.CMD_RUN,
            Role.RUN_FB,
            Role.FAULT,
            Role.LOCAL,
            Role.VFD_CTW,
            Role.SPEED_REF,
            Role.VFD_STW,
            Role.SPEED_ACT,
            Role.AUX,
        }
        for role, (function, address) in registers.items():
            signal = pump.signal(Role(role))
            assert signal is not None and signal.modbus is not None
            assert (signal.modbus.link, signal.modbus.slave) == ("RS485-1", n)
            assert (signal.modbus.function, signal.modbus.address) == (function, address)
        current = model.device(f"IT1{n}1")
        assert current.main.modbus is not None
        assert (current.main.modbus.slave, current.main.modbus.address) == (n, 102)
        code = next(s for s in pump.signals if s.role is Role.AUX)
        assert code.tag == f"P10{n}_FCODE" and code.modbus is not None
        assert (code.modbus.slave, code.modbus.function, code.modbus.address) == (n, 3, 103)
        cfg = pump.cfg.initializer()
        assert "xFbFromComm := FALSE" in cfg and "xCommLossIsFault := FALSE" in cfg


def test_kns_signals_without_fb_are_aux() -> None:
    """Сирена, лампа, реле общей аварии — простые сигналы AUX; коды аварий ПЧ — AUX в составе насоса."""
    lines = KNS_CSV.read_text(encoding="utf-8").splitlines()
    assert not [line for line in lines if line.startswith("#")]
    model = _model(KNS_CSV)
    assert [s.tag for s in model.plain_signals()] == ["HA1", "HL1", "K1"]
    assert all(s.signal_type is SignalType.DO and s.io_module == "Q1" for s in model.plain_signals())
    aux = [s.tag for s in model.signals if s.role is Role.AUX and s.device is not None]
    assert aux == ["P101_FCODE", "P102_FCODE", "P103_FCODE"]


def test_readme_list_to_code_snippet_is_generated_code(tmp_path: Path) -> None:
    """Фрагмент ST в README (раздел «Перечень → код») — дословно из вывода st-codesys по КНС-1."""
    from iolistgen.generators.st_codesys import StCodesysGenerator
    from pytests.genhelp import run

    run(StCodesysGenerator(), _model(KNS_CSV), tmp_path, {"persist_check": False})
    impl = (tmp_path / "src/POUs/Generated/PRG_Devices/PRG_Devices.impl.st").read_text(encoding="utf-8")
    persist = (tmp_path / "src/GVLs/Generated/GVL_Persist.pvl.st").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Перечень → код", 1)[1]
    block = section.split("```st\n", 1)[1].split("```", 1)[0]
    call, marker, declarations = block.partition("// GVL_Persist.pvl.st")
    assert marker, "в README нет фрагмента GVL_Persist"
    assert call.rstrip("\n") in impl, "обновите фрагмент PRG_Devices в README"
    assert declarations.split("\n", 1)[1].rstrip("\n") in persist, "обновите фрагмент GVL_Persist в README"


def test_kns_xlsx_gives_the_same_model_as_csv() -> None:
    assert _signature(_model(KNS_XLSX)) == _signature(_model(KNS_CSV))


def test_kns_xlsx_is_rebuilt_from_csv(tmp_path: Path) -> None:
    """Книга в репозитории собрана из CSV текущим скриптом (сравнивается содержимое архива)."""
    target = tmp_path / "io_list.xlsx"
    assert csv_to_xlsx.main([str(KNS_CSV), str(target), "--title", "КНС-1. Перечень сигналов"]) == 0

    def entries(data: bytes) -> dict[str, bytes]:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    assert entries(target.read_bytes()) == entries(KNS_XLSX.read_bytes()), (
        "пересоберите: python examples/csv_to_xlsx.py examples/kns/io_list.csv examples/kns/io_list.xlsx "
        '--title "КНС-1. Перечень сигналов"'
    )


def test_csv_to_xlsx_writes_title_russian_headers_and_numbers(tmp_path: Path) -> None:
    target = tmp_path / "list.xlsx"
    csv_to_xlsx.main([str(KNS_CSV), str(target)])
    sheet = load_workbook(target).active
    assert sheet is not None and sheet.title == "Перечень"
    header = [cell.value for cell in sheet[3]]
    assert header[:4] == ["Тег", "Описание", "Тип сигнала", "Устройство"]
    first = {header[i]: cell.value for i, cell in enumerate(sheet[4])}
    assert first["Тег"] == "LT101"
    assert first["Номер устройства"] == 101
    assert first["Макс."] == 5
    assert first["H"] == 3.5
    assert isinstance(first["Канал"], int)
    assert sheet.freeze_panes == "B4"


def test_csv_to_xlsx_keeps_non_numeric_text() -> None:
    assert csv_to_xlsx._number("delay_on_s", "5 с") == "5 с"
    assert csv_to_xlsx._number("sp_h", "0,8") == 0.8
    assert csv_to_xlsx._number("mb_reg", "100") == 100
    assert csv_to_xlsx._number("tag", "LT101") == "LT101"
    assert csv_to_xlsx._number("units", "") is None


# --- синтетический перечень ------------------------------------------------------------------------


def test_synthetic_list_is_reproducible() -> None:
    text = make_synthetic.render_csv(make_synthetic.generate(make_synthetic.SEED, make_synthetic.COUNT))
    assert text == SYNTHETIC.read_text(encoding="utf-8"), "пересоберите: python examples/synthetic/make_synthetic.py"


def test_synthetic_list_is_clean_and_covers_the_schema() -> None:
    result = _check(SYNTHETIC)
    assert [item.render() for item in result.diagnostics] == []
    assert result.stats.signals == 300
    assert result.model is not None
    signals = result.model.signals
    assert {s.signal_type for s in signals} == set(SignalType)
    assert {d.device_type for d in result.model.devices} == set(DeviceType)
    assert {s.role for s in signals} == set(Role)
    modbus = Counter(s.modbus.data_type.value for s in signals if s.modbus is not None)
    assert {"BOOL", "WORD", "UINT", "REAL"} <= set(modbus)
    assert {s.modbus.function for s in signals if s.modbus is not None} >= {1, 2, 3, 4, 16}
    assert any(s.modbus is not None and s.modbus.bit is not None for s in signals)


@pytest.mark.parametrize(("seed", "count"), [(1, 150), (7, 300), (42, 600), (2026, 1000)])
def test_synthetic_generator_other_seeds_and_sizes(tmp_path: Path, seed: int, count: int) -> None:
    path = tmp_path / "list.csv"
    assert make_synthetic.main(["--seed", str(seed), "--count", str(count), "--out", str(path)]) == 0
    result = _check(path)
    assert [item.render() for item in result.diagnostics] == []
    assert result.stats.signals == count


def test_synthetic_generator_rejects_too_small_count() -> None:
    with pytest.raises(ValueError, match="минимум сигналов"):
        make_synthetic.generate(make_synthetic.SEED, 20)


# --- витрина ошибок ----------------------------------------------------------------------------------


def _broken_rows() -> dict[int, str]:
    """Номер строки файла → пояснение; пустое пояснение или «без ошибки: …» — строка без ошибок."""
    with BROKEN.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        return {index: row[NOTE_COLUMN] for index, row in enumerate(reader, start=2)}


def _expects_error(note: str) -> bool:
    return bool(note) and not note.startswith("без ошибки")


def test_broken_list_every_annotated_row_is_reported() -> None:
    """Строка с пояснением ошибки получает сообщение, строка без пояснения — нет."""
    result = _check(BROKEN)
    rows = Counter(item.source.row for item in result.diagnostics if item.source is not None)
    notes = _broken_rows()
    missing = [f"строка {line}: {note}" for line, note in notes.items() if _expects_error(note) and not rows[line]]
    unexpected = [
        item.render()
        for item in result.diagnostics
        if item.source is not None and item.source.row in notes and not _expects_error(notes[item.source.row])
    ]
    assert missing == []
    assert unexpected == []
    assert result.model is None and result.exit_code() == 1


def test_broken_list_shows_each_kind_of_error() -> None:
    result = _check(BROKEN)
    codes = Counter(item.code for item in result.diagnostics)
    # дубли (точный и без учёта регистра), плохие теги, шкала, уставки, единицы, Modbus, состав, Cfg
    for code in ("IOL102", "IOL103", "IOL104", "IOL204", "IOL206", "IOL208", "IOL209", "IOL308", "IOL412", "IOL507"):
        assert codes[code] >= 1, code
    assert codes["IOL103"] >= 2 and codes["IOL412"] >= 3
    overlaps = [item.message for item in result.diagnostics if item.code == "IOL412"]
    assert any("REAL" in message for message in overlaps), "нужно пересечение 32-битного значения"
    assert any("бит" in message for message in overlaps), "нужно пересечение битов одного регистра"


def test_broken_report_in_docs_matches_validator() -> None:
    expected = render_markdown(_check(BROKEN), __version__)
    assert BROKEN_REPORT.read_text(encoding="utf-8") == expected, (
        "обновите отчёт: iolistgen validate examples/broken/io_list_broken.csv --report md --out docs"
    )


# --- замер времени --------------------------------------------------------------------------------------


def test_benchmark_writes_report_and_readme_block(tmp_path: Path) -> None:
    out = tmp_path / "benchmark.md"
    readme = tmp_path / "README.md"
    readme.write_text("# Проект\n\n<!-- BEGIN benchmark -->\nстарое\n<!-- END benchmark -->\n\nдальше\n", "utf-8")
    args = ["--list", str(KNS_CSV), "--repeat", "1", "--cli-repeat", "0", "--only", "docs-table"]
    assert benchmark.main([*args, "--out", str(out), "--readme", str(readme)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "# Замер времени iolistgen" in text
    assert "`examples/kns/io_list.csv` | 58 | 30 |" in text
    assert "проверка + генерация" in text
    assert "процесс целиком" not in text  # --cli-repeat 0: без запусков отдельного процесса
    block = readme.read_text(encoding="utf-8")
    assert "старое" not in block and block.endswith("<!-- END benchmark -->\n\nдальше\n")
    assert "| `io_list.csv` | 58 |" in block and "[benchmark.md](docs/benchmark.md)" in block


def test_benchmark_leaves_readme_without_markers(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Проект\n", encoding="utf-8")
    assert benchmark.update_readme(readme, "итог") is False
    assert benchmark.update_readme(tmp_path / "нет.md", "итог") is False
    assert readme.read_text(encoding="utf-8") == "# Проект\n"


def test_benchmark_timing_statistics() -> None:
    timing = benchmark.Timing((3.0, 1.0, 2.0, 10.0))
    assert (timing.median, timing.minimum, timing.maximum) == (2.5, 1.0, 10.0)
    assert benchmark.cpu_name()
