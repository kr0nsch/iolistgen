"""Замер времени iolistgen: проверка и генерация по перечню, медиана нескольких повторов.

Что измеряется (на каждом перечне из ``--list``):

1. **Проверка** — ``check_file()``: чтение файла, разбор ячеек, все правила, полная Cfg
   устройств и модель ``IoList`` (то же, что делает ``iolistgen validate`` без вывода).
2. **Генерация** — все доступные генераторы (встроенные и плагины, как ``iolistgen generate``)
   в пустой каталог: файлы действительно записываются.
3. **Повторная генерация** — те же генераторы в каталог с уже записанными файлами: содержимое
   совпадает, файлы не перезаписываются (идемпотентность).
4. **Команда целиком** — ``python -m iolistgen validate`` и ``generate`` в отдельном процессе:
   со стартом интерпретатора и импортом пакета, как это видит инженер в консоли.

Шаги 1–3 выполняются в одном процессе после прогрева (первый прогон не учитывается), шаг 4 —
отдельными процессами. Результат — медиана, минимум и максимум; сведения о машине и версиях —
в шапке отчёта ``docs/benchmark.md``.

Запуск из корня репозитория::

    python examples/benchmark.py                       # 300 сигналов и КНС: docs/benchmark.md и итог в README
    python examples/benchmark.py --repeat 50 --cli-repeat 10
    python examples/benchmark.py --list build/io_list_1000.csv --out build/benchmark.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))  # запуск из клона без установки пакета

from iolistgen import __version__  # noqa: E402
from iolistgen.config import Config  # noqa: E402
from iolistgen.generators import Generator, GeneratorContext, discover, resolve_options  # noqa: E402
from iolistgen.model import IoList  # noqa: E402
from iolistgen.validate import CheckResult, check_file  # noqa: E402

DEFAULT_LISTS = (
    REPO_ROOT / "examples" / "synthetic" / "io_list_300.csv",
    REPO_ROOT / "examples" / "kns" / "io_list.csv",
)
DEFAULT_OUT = REPO_ROOT / "docs" / "benchmark.md"
DEFAULT_README = REPO_ROOT / "README.md"
README_BEGIN = "<!-- BEGIN benchmark -->"
README_END = "<!-- END benchmark -->"


@dataclass(frozen=True)
class Timing:
    """Ряд замеров одного шага, мс."""

    samples: tuple[float, ...]

    @property
    def median(self) -> float:
        return statistics.median(self.samples)

    @property
    def minimum(self) -> float:
        return min(self.samples)

    @property
    def maximum(self) -> float:
        return max(self.samples)


@dataclass(frozen=True)
class ListResult:
    """Замеры одного перечня."""

    path: Path
    result: CheckResult
    files: int
    validate: Timing
    generate: Timing
    regenerate: Timing
    cli_validate: Timing | None
    cli_generate: Timing | None

    @property
    def total(self) -> float:
        return self.validate.median + self.generate.median


def _measure(action: Callable[[], object], repeat: int, *, warmup: int = 1) -> Timing:
    for _ in range(warmup):
        action()
    samples = []
    for _ in range(repeat):
        start = time.perf_counter_ns()
        action()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return Timing(tuple(samples))


def _generators(only: Sequence[str] | None) -> dict[str, Generator]:
    available = {entry.name: entry.generator for entry in discover().values() if entry.generator is not None}
    if only:
        missing = [name for name in only if name not in available]
        if missing:
            raise SystemExit(f"генераторы недоступны: {', '.join(missing)}; есть: {', '.join(available)}")
        return {name: available[name] for name in only}
    return available


def _run_generators(model: IoList, generators: dict[str, Generator], out_dir: Path, config: Config) -> int:
    """Запустить генераторы так же, как ``iolistgen generate``; вернуть число записанных файлов."""
    changed = 0
    for name, generator in generators.items():
        ctx = GeneratorContext(
            generator=name,
            out_dir=out_dir,
            options=resolve_options(generator, config.generators.get(name)),
            config=config,
            source=model.source,
            version=__version__,
        )
        generator.generate(model, out_dir, ctx)
        changed += sum(output.changed for output in ctx.outputs)
    return changed


def _cli(args: Sequence[str], repeat: int) -> Timing:
    """Команда ``python -m iolistgen …`` отдельным процессом: медиана по ``repeat`` запускам."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(REPO_ROOT), env.get("PYTHONPATH"))))
    command = [sys.executable, "-m", "iolistgen", *args]

    def run() -> None:
        completed = subprocess.run(command, env=env, capture_output=True, check=False)
        if completed.returncode != 0:
            raise SystemExit(f"{' '.join(command)}: код выхода {completed.returncode}\n{completed.stdout!r}")

    return _measure(run, repeat)


def bench_list(path: Path, generators: dict[str, Generator], *, repeat: int, cli_repeat: int, work: Path) -> ListResult:
    config = Config()
    result = check_file(path, config)
    if result.model is None:
        raise SystemExit(f"{path}: в перечне ошибки — замер возможен только на корректном перечне")
    model = result.model
    validate = _measure(lambda: check_file(path, config), repeat)

    counter = iter(range(1_000_000))

    def fresh() -> None:
        _run_generators(model, generators, work / f"{path.stem}-{next(counter)}", config)

    generate = _measure(fresh, repeat)
    stable = work / f"{path.stem}-stable"
    files = _run_generators(model, generators, stable, config)
    regenerate = _measure(lambda: _run_generators(model, generators, stable, config), repeat, warmup=0)
    if _run_generators(model, generators, stable, config) != 0:
        raise SystemExit(f"{path}: повторная генерация изменила файлы — генерация не идемпотентна")

    cli_validate = cli_generate = None
    if cli_repeat > 0:
        cli_validate = _cli(["validate", str(path), "--no-config", "-q"], cli_repeat)
        cli_out = work / f"{path.stem}-cli"
        only = ["--only", ",".join(generators)] if generators else []
        cli_generate = _cli(["generate", str(path), "--no-config", "--out", str(cli_out), *only], cli_repeat)
    return ListResult(path, result, files, validate, generate, regenerate, cli_validate, cli_generate)


# --- сведения о машине -------------------------------------------------------------------------


def cpu_name() -> str:
    """Название процессора: реестр Windows, /proc/cpuinfo в Linux, sysctl в macOS."""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return str(value).strip()
        except OSError:
            pass
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    if sys.platform == "darwin":
        try:
            completed = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, check=False
            )
            if completed.stdout.strip():
                return completed.stdout.strip()
        except OSError:
            pass
    return platform.processor() or platform.machine() or "неизвестно"


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "—"


def machine_info() -> list[tuple[str, str]]:
    return [
        ("Процессор", f"{cpu_name()}, логических ядер: {os.cpu_count() or '?'}"),
        ("ОС", platform.platform()),
        ("Python", f"{platform.python_implementation()} {platform.python_version()}"),
        ("iolistgen", __version__),
        (
            "Зависимости",
            f"pydantic {_version('pydantic')}, openpyxl {_version('openpyxl')}, Jinja2 {_version('jinja2')}",
        ),
    ]


# --- отчёт ---------------------------------------------------------------------------------------


def _ms(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def render(
    results: Sequence[ListResult],
    generators: dict[str, Generator],
    *,
    repeat: int,
    cli_repeat: int,
    startup: Timing | None = None,
) -> str:
    today = dt.date.today().isoformat()
    names = ", ".join(f"`{name}`" for name in generators) or "нет"
    lines = [
        "# Замер времени iolistgen",
        "",
        "<!-- Отчёт записан скриптом examples/benchmark.py: перезапустите его, а не правьте вручную. -->",
        "",
        f"Проверка и генерация по перечню сигналов: медиана {repeat} повторов после прогрева; "
        f"команда целиком — медиана {cli_repeat} запусков отдельного процесса. Дата замера: {today}.",
        "",
        "## Машина",
        "",
        "| | |",
        "|---|---|",
    ]
    lines += [f"| {key} | {value} |" for key, value in machine_info()]
    lines += ["", f"Генераторы в замере: {names}.", "", "## Перечни", ""]
    lines += [
        "| Перечень | Сигналов | Устройств | Типы сигналов | Файлов генерации |",
        "|---|---:|---:|---|---:|",
    ]
    for item in results:
        stats = item.result.stats
        kinds = " · ".join(f"{name} {count}" for name, count in stats.by_signal_type.items())
        lines.append(f"| `{_display(item.path)}` | {stats.signals} | {stats.devices} | {kinds} | {item.files} |")
    lines += ["", "## Результат, мс", ""]
    lines += [
        "| Перечень | Шаг | Медиана | Мин. | Макс. |",
        "|---|---|---:|---:|---:|",
    ]
    for item in results:
        name = f"`{item.path.name}`"
        rows: list[tuple[str, Timing | None]] = [
            ("проверка (`check_file`)", item.validate),
            ("генерация в пустой каталог", item.generate),
            ("повторная генерация (файлы не меняются)", item.regenerate),
            ("`iolistgen validate` — процесс целиком", item.cli_validate),
            ("`iolistgen generate` — процесс целиком", item.cli_generate),
        ]
        for title, timing in rows:
            if timing is None:
                continue
            lines.append(f"| {name} | {title} | {_ms(timing.median)} | {_ms(timing.minimum)} | {_ms(timing.maximum)} |")
        lines.append(f"| {name} | **проверка + генерация** | **{_ms(item.total)}** | | |")
    lines += [
        "",
        "Процесс целиком включает старт интерпретатора Python и импорт пакета (pydantic, openpyxl, "
        "Jinja2) — это большая часть времени команды на перечне такого размера.",
    ]
    if startup is not None:
        lines.append(
            f"Старт команды без работы (`iolistgen --version`): медиана {_ms(startup.median)} мс "
            f"(мин. {_ms(startup.minimum)}, макс. {_ms(startup.maximum)})."
        )
    lines += [
        "",
        "## Как повторить",
        "",
        "```bash",
        "python examples/synthetic/make_synthetic.py      # перечень на 300 сигналов (зерно 2026)",
        f"python examples/benchmark.py --repeat {repeat} --cli-repeat {cli_repeat}",
        "```",
        "",
        "Оценку ручного заведения тех же сигналов автор приводит в README (раздел «Замер времени»).",
    ]
    return "\n".join(lines) + "\n"


def readme_summary(results: Sequence[ListResult], report: Path) -> str:
    """Краткий итог для README: таблица «перечень — проверка — генерация — команда»."""
    lines = [
        "| Перечень | Сигналов | Проверка, мс | Генерация, мс | Проверка + генерация, мс "
        "| `iolistgen generate` целиком, мс |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        cli = _ms(item.cli_generate.median) if item.cli_generate is not None else "—"
        lines.append(
            f"| `{item.path.name}` | {item.result.stats.signals} | {_ms(item.validate.median)} | "
            f"{_ms(item.generate.median)} | **{_ms(item.total)}** | {cli} |"
        )
    machine = dict(machine_info())
    lines += [
        "",
        f"Медианы; {machine['Процессор']}, {machine['ОС']}, {machine['Python']}. Генераторы, методика и "
        f"разброс — [{report.name}](docs/{report.name}); повторить — `python examples/benchmark.py`.",
    ]
    return "\n".join(lines)


def update_readme(readme: Path, summary: str) -> bool:
    """Заменить текст между маркерами ``BEGIN benchmark`` и ``END benchmark``; без маркеров — ничего."""
    if not readme.is_file():
        return False
    text = readme.read_text(encoding="utf-8")
    begin, end = text.find(README_BEGIN), text.find(README_END)
    if begin < 0 or end < begin:
        return False
    updated = text[: begin + len(README_BEGIN)] + "\n" + summary + "\n" + text[end:]
    if updated != text:
        readme.write_bytes(updated.encode("utf-8"))
    return True


def _configure_streams() -> None:
    """Вывод в файл или канал — UTF-8 (в Windows по умолчанию кодировка консоли)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None and not stream.isatty():
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_streams()
    parser = argparse.ArgumentParser(description="Замер времени проверки и генерации iolistgen.")
    parser.add_argument("--list", type=Path, action="append", metavar="ПЕРЕЧЕНЬ", help="перечень (можно повторять)")
    parser.add_argument("--repeat", type=int, default=30, help="повторов в процессе (по умолчанию 30)")
    parser.add_argument("--cli-repeat", type=int, default=5, help="запусков команды (по умолчанию 5; 0 — без них)")
    parser.add_argument("--only", help="только эти генераторы, через запятую")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="отчёт Markdown (по умолчанию docs/benchmark.md)")
    parser.add_argument(
        "--readme",
        type=Path,
        default=DEFAULT_README,
        help="README с блоком <!-- BEGIN benchmark --> … <!-- END benchmark --> для краткого итога",
    )
    parser.add_argument("--no-readme", action="store_true", help="не обновлять README")
    args = parser.parse_args(argv)
    if args.repeat < 1 or args.cli_repeat < 0:
        parser.error("--repeat не меньше 1, --cli-repeat не меньше 0")
    lists: list[Path] = args.list or list(DEFAULT_LISTS)
    only = [name.strip() for name in args.only.split(",") if name.strip()] if args.only else None
    generators = _generators(only)
    results = []
    startup = _cli(["--version"], args.cli_repeat) if args.cli_repeat > 0 else None
    with tempfile.TemporaryDirectory(prefix="iolistgen-bench-") as work:
        for path in lists:
            item = bench_list(path, generators, repeat=args.repeat, cli_repeat=args.cli_repeat, work=Path(work))
            results.append(item)
            print(
                f"{path.name}: проверка {_ms(item.validate.median)} мс, генерация {_ms(item.generate.median)} мс, "
                f"итого {_ms(item.total)} мс"
            )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = render(results, generators, repeat=args.repeat, cli_repeat=args.cli_repeat, startup=startup)
    args.out.write_bytes(report.encode("utf-8"))
    print(f"отчёт: {args.out}")
    if not args.no_readme and update_readme(args.readme, readme_summary(results, args.out)):
        print(f"итог в README: {args.readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
