"""Проверка перечня целиком: чтение, разбор, устройства, Modbus, Cfg — и модель без ошибок.

Точка входа — ``check_file()``. Результат содержит все сообщения (ошибки и предупреждения,
отсортированные по месту в файле), сводку и модель ``IoList``, если ошибок нет.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from iolistgen.build import DeviceDraft, group_devices
from iolistgen.checks import check_attributes, check_channels, check_device_names, check_modbus, check_tags
from iolistgen.config import Config
from iolistgen.devcfg import build_device_cfg
from iolistgen.diagnostics import Diagnostic, Severity
from iolistgen.enums import Role
from iolistgen.loaders import load_table
from iolistgen.loaders.table import RawTable
from iolistgen.model import Device, IoList, ModbusAddress, Setpoints, Signal, SourceInfo
from iolistgen.parse import SignalDraft, parse_table


@dataclass(frozen=True)
class Stats:
    """Сводка перечня: сколько сигналов и устройств разобрано."""

    signals: int = 0
    devices: int = 0
    modbus: int = 0
    by_signal_type: dict[str, int] = field(default_factory=dict)
    by_device_type: dict[str, int] = field(default_factory=dict)


@dataclass
class CheckResult:
    """Итог проверки перечня."""

    source: SourceInfo
    config: Config
    diagnostics: list[Diagnostic]
    stats: Stats
    model: IoList | None = None

    @property
    def errors(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def exit_code(self, *, strict: bool = False) -> int:
        """0 — без ошибок; 1 — есть ошибки (при ``strict`` — и предупреждения)."""
        if self.errors or (strict and self.warnings):
            return 1
        return 0


def _source_info(table: RawTable, path: Path | None) -> SourceInfo:
    return SourceInfo(
        path=table.file,
        name=path.name if path is not None else Path(table.file).name,
        sheet=table.sheet,
        format=table.format,
        sha256=table.sha256,
    )


def check_table(table: RawTable, config: Config, *, path: Path | None = None) -> CheckResult:
    """Проверить уже прочитанную таблицу."""
    bag = table.diagnostics
    drafts = parse_table(table, bag)
    check_tags(drafts, bag, config.naming, has_tag=table.has_column("tag"))
    devices = group_devices(drafts, bag)
    check_device_names(devices, bag, config.naming)
    check_attributes(devices, bag)
    addresses = check_modbus(devices, bag, config.modbus)
    check_channels(drafts, bag)
    for device in devices:
        device.cfg, device.params = build_device_cfg(device, bag, addresses)
    diagnostics = bag.finalize(config.severity)
    stats = _stats(drafts, devices, addresses)
    result = CheckResult(
        source=_source_info(table, path),
        config=config,
        diagnostics=diagnostics,
        stats=stats,
    )
    if result.ok and table.header_row is not None:
        result.model = _build_model(table, result.source, drafts, devices, addresses)
    return result


def check_file(path: Path, config: Config | None = None, *, sheet: str | None = None) -> CheckResult:
    """Прочитать и проверить перечень (``InputError`` — файла нет или формат не тот)."""
    settings = config if config is not None else Config()
    table = load_table(path, settings.input, sheet=sheet)
    return check_table(table, settings, path=path)


def _stats(drafts: list[SignalDraft], devices: list[DeviceDraft], addresses: dict[int, ModbusAddress]) -> Stats:
    signal_types = Counter(d.signal_type.value for d in drafts if d.signal_type is not None)
    device_types = Counter(d.device_type.value for d in devices if d.device_type is not None)
    return Stats(
        signals=len(drafts),
        devices=len([device for device in devices if not device.plain]),
        modbus=len(addresses),
        by_signal_type=dict(sorted(signal_types.items())),
        by_device_type=dict(sorted(device_types.items())),
    )


def _build_model(
    table: RawTable,
    source: SourceInfo,
    drafts: list[SignalDraft],
    devices: list[DeviceDraft],
    addresses: dict[int, ModbusAddress],
) -> IoList:
    signals_by_id: dict[int, Signal] = {}
    model_devices: list[Device] = []
    for device in devices:
        if device.plain:
            draft = device.signals[0]
            assert draft.tag is not None and draft.ident is not None and draft.description is not None
            assert draft.signal_type is not None and draft.role is Role.AUX
            signals_by_id[id(draft)] = _signal(draft, None, is_main=False, address=addresses.get(id(draft)))
            continue
        main = device.main
        assert main is not None and device.device_type is not None and device.dev_no is not None
        assert device.cfg is not None and main.role is not None
        signals: list[Signal] = []
        for draft in device.signals:
            signal = _signal(draft, device.ident, is_main=draft is main, address=addresses.get(id(draft)))
            signals.append(signal)
            signals_by_id[id(draft)] = signal
        link_power = device.link_targets.get("link_power")
        link_fb = device.link_targets.get("link_fb")
        model_devices.append(
            Device(
                name=device.name,
                ident=device.ident,
                device_type=device.device_type,
                dev_no=device.dev_no,
                description=main.dev_desc or main.description or device.name,
                main_role=main.role,
                signals=tuple(signals),
                setpoints=Setpoints(
                    hh=main.setpoints.get("hh"),
                    h=main.setpoints.get("h"),
                    l=main.setpoints.get("l"),
                    ll=main.setpoints.get("ll"),
                ),
                delay_on_ms=main.delay_on_ms,
                delay_off_ms=main.delay_off_ms,
                alarm_priority=main.alarm_priority,
                hmi_group=main.hmi_group,
                link_power=link_power.ident if link_power is not None else None,
                link_fb=link_fb.ident if link_fb is not None else None,
                params=tuple(device.params),
                cfg=device.cfg,
                source=main.source,
            )
        )
    ordered = [signals_by_id[id(draft)] for draft in drafts if id(draft) in signals_by_id]
    return IoList(
        source=source,
        columns=tuple(binding.field for binding in table.columns if binding.field is not None),
        signals=tuple(ordered),
        devices=tuple(model_devices),
    )


def _signal(draft: SignalDraft, device: str | None, *, is_main: bool, address: ModbusAddress | None) -> Signal:
    assert draft.tag is not None and draft.ident is not None and draft.description is not None
    assert draft.signal_type is not None and draft.role is not None
    return Signal(
        tag=draft.tag,
        ident=draft.ident,
        description=draft.description,
        signal_type=draft.signal_type,
        device=device,
        role=draft.role,
        is_main=is_main,
        range_min=draft.range_min,
        range_max=draft.range_max,
        units=draft.units,
        hmi_group=draft.hmi_group,
        io_module=draft.io_module,
        io_channel=draft.io_channel,
        modbus=address,
        extra={header: cell.text for header, cell in draft.row.extra.items()},
        source=draft.source,
    )
