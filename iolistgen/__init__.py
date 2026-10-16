"""iolistgen — проверка перечня сигналов АСУ ТП и генерация кода ПЛК, карт обмена и документации.

Основной API::

    from pathlib import Path
    from iolistgen import check_file, resolve_config

    config = resolve_config(None, Path("docs/03_io_list.csv"))
    result = check_file(Path("docs/03_io_list.csv"), config)
    for item in result.diagnostics:
        print(item.render())
    if result.model is not None:  # ошибок нет
        for device in result.model.devices:
            print(device.ident, device.spec.fb, device.cfg.initializer())
"""

from __future__ import annotations

from iolistgen.config import Config, ConfigError, load_config, resolve_config
from iolistgen.diagnostics import RULES, Diagnostic, Severity
from iolistgen.loaders import InputError
from iolistgen.model import Device, IoList, Signal
from iolistgen.validate import CheckResult, check_file

__version__ = "0.1.0"

__all__ = [
    "RULES",
    "CheckResult",
    "Config",
    "ConfigError",
    "Device",
    "Diagnostic",
    "InputError",
    "IoList",
    "Severity",
    "Signal",
    "__version__",
    "check_file",
    "load_config",
    "resolve_config",
]
