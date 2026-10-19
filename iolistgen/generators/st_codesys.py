"""Встроенный генератор ``st-codesys``: исходники ST в раскладке шаблона (``docs/LAYOUT.md``).

Что пишется (контракт plc-process-lib, разделы 1, 18.3, 20.6), пути — от ``--out``:

- ``src/GVLs/Generated/GVL_IO.gvl.st`` — каналы модулей, значения Modbus, состояние слейвов,
  переменные адаптеров ПЧ;
- ``GVL_DevIdx.gvl.st`` — константы ``<DEV> : UINT := dev_no``;
- ``GVL_Hmi.gvl.st`` — ``st<DEV>Cmd`` и команда «применить уставки проекта»;
- ``GVL_Persist.pvl.st`` — объект Persistent Variables: ``st<DEV>Cfg`` с уставками перечня и
  ``st<DEV>Retain`` по возрастанию dev_no, затем данные приложения из файла ``persist_extra``;
- ``GVL_CfgProject.gvl.st`` — те же Cfg константами («уставки проекта»);
- ``GVL_Devices.gvl.st`` — экземпляры ``fb<DEV> : PL.FB_<Type>``;
- ``src/POUs/Generated/PRG_Devices/`` — вызовы устройств с привязками к ``GVL_IO``;
- ``src/POUs/Generated/PRG_ApplyProjectCfg/`` — копирование ``GVL_CfgProject`` → ``GVL_Persist``.

Ручной код (логика станции, адаптеры ПЧ, слой Modbus) лежит вне папки ``Generated``: генератор
пишет только свои файлы и чужие не трогает. Тексты собираются шаблонами Jinja2 пакета
(``iolistgen/templates/st/``); опция ``template_dir`` подставляет свои шаблоны.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from jinja2 import Environment

from iolistgen.catalog import LIBRARY_NAMESPACE
from iolistgen.generators import stfmt
from iolistgen.generators.base import GenerationError, GeneratorContext, GeneratorOption
from iolistgen.generators.persist_extra import ExtraVar, load_persist_extra
from iolistgen.generators.plc import (
    APPLY_CFG_CMD,
    GVL_CFG_PROJECT,
    GVL_DEV_IDX,
    GVL_DEVICES,
    GVL_HMI,
    GVL_IO,
    GVL_PERSIST,
    LAYOUT_VERSION_VAR,
    PRG_APPLY_CFG,
    PRG_DEVICES,
    SECTION_ORDER,
    SECTION_TITLES,
    DeviceBinding,
    PlcModel,
    build_plc,
)
from iolistgen.generators.templating import environment
from iolistgen.model import IoList

INDENT = stfmt.INDENT


def _device_title(binding: DeviceBinding, *, with_retain_note: bool = False) -> str:
    device = binding.device
    text = (
        f"--- dev_no {device.dev_no}: {device.ident} — {stfmt.one_line(device.description)} ({device.device_type.value}"
    )
    if with_retain_note and binding.retain is None:
        text += ", без Retain"
    return text + ") ---"


def _title_lines(text: str, indent: str = INDENT) -> list[str]:
    """Заголовок раздела одной строкой: длинное описание укорачивается, а не переносится.

    По строке ``// --- dev_no N: <DEV> …`` проверка ``persist_check`` находит устройство в
    предыдущем ``GVL_Persist``, поэтому она не должна разрываться.
    """
    line = f"{indent}// {text}"
    if len(line) <= stfmt.MAX_LINE:
        return [line]
    head, _, tail = text.rpartition(" (")
    room = stfmt.MAX_LINE - len(indent) - len("// ") - len(" (" + tail) - 1
    return [f"{indent}// {head[:room].rstrip()}… ({tail}"]


class StCodesysGenerator:
    """Исходники ST для CODESYS 3.5 в раскладке шаблона: GVL, Persistent Variables, вызовы устройств."""

    name = "st-codesys"
    description = "ST для CODESYS: GVL_IO, GVL_Devices, GVL_Hmi, GVL_Persist, GVL_CfgProject, PRG_Devices"
    options = (
        GeneratorOption("src_dir", "каталог раскладки ST относительно --out", "str", "src"),
        GeneratorOption(
            "folder", "папка проекта CODESYS для сгенерированных объектов (пусто — без папки)", "str", "Generated"
        ),
        GeneratorOption("namespace", "пространство имён библиотеки plc-process-lib", "str", LIBRARY_NAMESPACE),
        GeneratorOption(
            "time_source",
            "выражение I_TimeSource для входа itfTime всех устройств (пусто — встроенное системное время)",
            "str",
            "",
        ),
        GeneratorOption(
            "alarm_sink",
            "выражение I_AlarmSink: PRG_Devices присваивает его PL.GVL_Lib.itfAlarmSink каждый цикл (пусто — нет)",
            "str",
            "",
        ),
        GeneratorOption(
            "apply_command", "команда HMI GVL_Hmi.xApplyProjectCfg «применить уставки проекта»", "bool", True
        ),
        GeneratorOption("layout_version", "значение GVL_Persist.uiLayoutVersion", "int", 1),
        GeneratorOption(
            "persist_check", "сверить новый GVL_Persist с предыдущим в каталоге вывода (контракт 18.3)", "bool", True
        ),
        GeneratorOption(
            "persist_extra",
            "файл данных приложения для GVL_Persist: «имя : тип := значение; // комментарий» по строке, "
            "дописываются после устройств (контракт 18.3, правило 9); пусто — нет",
            "path",
            "",
        ),
        GeneratorOption(
            "doc", "документ в заголовках POU (правило STL001: путь docs/...)", "str", "docs/signal_list.md"
        ),
        GeneratorOption(
            "author", "строка «Автор» в заголовках POU", "str", "iolistgen (генератор по перечню сигналов)"
        ),
        GeneratorOption("template_dir", "каталог своих шаблонов Jinja2 (перекрывают шаблоны пакета)", "str", ""),
    )

    def generate(self, model: IoList, out_dir: Path, ctx: GeneratorContext) -> list[Path]:
        plc = build_plc(
            model,
            namespace=ctx.str_option("namespace"),
            time_source=ctx.str_option("time_source"),
        )
        env = environment(ctx.str_option("template_dir"))
        header = stfmt.normalize(ctx.comment_header("st")).rstrip("\n")
        extras = self.persist_extra(ctx, plc)
        texts = self.render(model, plc, ctx, header, env, extras)
        written: list[Path] = []
        persist_path = self._relative(ctx, f"GVLs/{GVL_PERSIST}.pvl.st")
        if ctx.bool_option("persist_check"):
            previous = out_dir / persist_path
            if previous.is_file():
                for message in check_persist(previous.read_text(encoding="utf-8"), plc, extras):
                    ctx.warn(message)
        for relative, text in texts.items():
            written.append(ctx.write_text(self._relative(ctx, relative), stfmt.normalize(text)))
        return written

    @staticmethod
    def persist_extra(ctx: GeneratorContext, plc: PlcModel) -> tuple[ExtraVar, ...]:
        """Данные приложения из файла опции ``persist_extra``; имена не совпадают с переменными устройств."""
        option = ctx.str_option("persist_extra").strip()
        if not option:
            return ()
        extras = load_persist_extra(Path(option))
        taken = {LAYOUT_VERSION_VAR.casefold(): LAYOUT_VERSION_VAR}
        for binding in plc.by_dev_no():
            taken[binding.cfg.casefold()] = binding.cfg
            if binding.retain is not None:
                taken[binding.retain.casefold()] = binding.retain
        for item in extras:
            clash = taken.get(item.name.casefold())
            if clash is not None:
                raise GenerationError(
                    f"persist_extra {Path(option).name}, строка {item.line}: {item.name} совпадает с переменной "
                    f"{GVL_PERSIST}.{clash}, которую генератор объявляет сам — переименуйте переменную приложения"
                )
        return extras

    # --- пути ---------------------------------------------------------------------------------

    @staticmethod
    def _relative(ctx: GeneratorContext, relative: str) -> str:
        """``GVLs/GVL_IO.gvl.st`` → ``src/GVLs/Generated/GVL_IO.gvl.st`` (папка проекта — опция)."""
        category, _, rest = relative.partition("/")
        folder = ctx.str_option("folder").strip().strip("/")
        parts = [ctx.str_option("src_dir").strip().strip("/") or ".", category]
        if folder:
            parts.append(folder)
        parts.append(rest)
        return str(PurePosixPath(*parts))

    # --- тексты ---------------------------------------------------------------------------------

    def render(
        self,
        model: IoList,
        plc: PlcModel,
        ctx: GeneratorContext,
        header: str,
        env: Environment,
        extras: tuple[ExtraVar, ...] = (),
    ) -> dict[str, str]:
        """Тексты файлов по путям внутри ``src/`` (без папки проекта)."""
        source = model.source.name
        common = {"header": header}
        pou_header = self._pou_header(ctx, source)
        files: dict[str, tuple[str, dict[str, Any]]] = {
            f"GVLs/{GVL_IO}.gvl.st": ("st/GVL_IO.gvl.st.j2", {**common, **self._gvl_io(plc)}),
            f"GVLs/{GVL_DEV_IDX}.gvl.st": ("st/GVL_DevIdx.gvl.st.j2", {**common, **self._dev_idx(plc)}),
            f"GVLs/{GVL_HMI}.gvl.st": ("st/GVL_Hmi.gvl.st.j2", {**common, **self._hmi(plc, ctx)}),
            f"GVLs/{GVL_PERSIST}.pvl.st": (
                "st/GVL_Persist.pvl.st.j2",
                {**common, **self._persist(plc, ctx, extras)},
            ),
            f"GVLs/{GVL_CFG_PROJECT}.gvl.st": ("st/GVL_CfgProject.gvl.st.j2", {**common, **self._cfg_project(plc)}),
            f"GVLs/{GVL_DEVICES}.gvl.st": ("st/GVL_Devices.gvl.st.j2", {**common, **self._devices(plc)}),
            f"POUs/{PRG_DEVICES}/{PRG_DEVICES}.decl.st": (
                "st/PRG_Devices.decl.st.j2",
                {**common, "pou_header": pou_header(self._prg_devices_purpose(plc))},
            ),
            f"POUs/{PRG_DEVICES}/{PRG_DEVICES}.impl.st": (
                "st/PRG_Devices.impl.st.j2",
                {**common, **self._prg_devices(plc, ctx)},
            ),
            f"POUs/{PRG_APPLY_CFG}/{PRG_APPLY_CFG}.decl.st": (
                "st/PRG_ApplyProjectCfg.decl.st.j2",
                {
                    **common,
                    "pou_header": pou_header(
                        f"«применить уставки проекта»: копирует {GVL_CFG_PROJECT}.st<DEV>Cfg в "
                        f"{GVL_PERSIST}.st<DEV>Cfg; Retain устройств не меняется (контракт plc-process-lib 18.3, "
                        f"правило 2). Вызывается из {PRG_DEVICES} по команде {GVL_HMI}.{APPLY_CFG_CMD} или из "
                        "логики станции"
                    ),
                },
            ),
            f"POUs/{PRG_APPLY_CFG}/{PRG_APPLY_CFG}.impl.st": (
                "st/PRG_ApplyProjectCfg.impl.st.j2",
                {**common, **self._apply(plc)},
            ),
        }
        return {path: env.get_template(template).render(**data) for path, (template, data) in files.items()}

    @staticmethod
    def _pou_header(ctx: GeneratorContext, source: str) -> Any:
        def build(purpose: str) -> list[str]:
            lines = stfmt.comment_lines(f"Назначение: {purpose}", width=stfmt.MAX_LINE)
            lines += [
                f"// Автор:      {ctx.str_option('author')}; перечень {source}",
                f"// Версия:     iolistgen {ctx.version}",
                f"// Документ:   {ctx.str_option('doc')}",
            ]
            return lines

        return build

    @staticmethod
    def _purpose(text: str) -> list[str]:
        return stfmt.comment_lines(text)

    def _gvl_io(self, plc: PlcModel) -> dict[str, Any]:
        sections = []
        for section in SECTION_ORDER:
            variables = plc.section(section)
            if not variables:
                continue
            lines: list[str] = []
            for var in variables:
                lines += stfmt.declaration(var.name, var.st_type, comment=var.comment)
            sections.append(
                {"title": stfmt.comment_lines(f"=== {SECTION_TITLES[section]} ===", INDENT), "lines": lines}
            )
        purpose = self._purpose(
            "Назначение: переменные ввода-вывода перечня сигналов — каналы модулей, обмен Modbus, адаптеры ПЧ. "
            "Адресов %I/%Q в коде нет: каналы привязываются в дереве устройств (I/O Mapping → «Map to existing "
            "variable»), значения Modbus пишет и читает слой Modbus, переменные ПЧ — адаптеры приложения "
            "(docs/MANUAL_STEPS.md)."
        )
        return {"purpose": purpose, "sections": sections}

    def _dev_idx(self, plc: PlcModel) -> dict[str, Any]:
        lines: list[str] = []
        for binding in plc.by_dev_no():
            device = binding.device
            comment = f"{device.device_type.value} · {stfmt.one_line(device.description)}"
            lines += stfmt.declaration(binding.index_constant, f"UINT := {device.dev_no}", comment=comment)
        purpose = self._purpose(
            "Назначение: номера устройств dev_no (контракт plc-process-lib 20.1): тревоги устройства — "
            "dev_no · 10 + слот; для SCADA и логики станции."
        )
        return {"purpose": purpose, "lines": lines}

    def _hmi(self, plc: PlcModel, ctx: GeneratorContext) -> dict[str, Any]:
        lines: list[str] = []
        if ctx.bool_option("apply_command"):
            lines += stfmt.declaration(
                APPLY_CFG_CMD,
                "BOOL",
                comment=f"импульс: применить уставки проекта ({PRG_APPLY_CFG}); сбрасывает {PRG_DEVICES}",
            )
        for binding in plc.by_dev_no():
            device = binding.device
            comment = f"{device.dev_no} · {stfmt.one_line(device.description)}"
            lines += stfmt.declaration(binding.cmd, binding.cmd_type, comment=comment)
        purpose = self._purpose(
            "Назначение: команды HMI и SCADA устройствам (ST_<Dev>Cmd, контракт plc-process-lib 1 и 2.1). "
            "WebVisu и OPC UA пишут сюда напрямую; команды по Modbus — только через адаптер приложения "
            "(импульс по фронту)."
        )
        return {"purpose": purpose, "lines": lines}

    def _persist(self, plc: PlcModel, ctx: GeneratorContext, extras: tuple[ExtraVar, ...]) -> dict[str, Any]:
        namespace = plc.namespace
        devices = []
        for binding in plc.by_dev_no():
            lines = stfmt.declaration(binding.cfg, binding.cfg_type, binding.device.cfg.initializer_tree(namespace))
            if binding.retain is not None:
                lines += stfmt.declaration(
                    binding.retain, binding.retain_type, comment="режим, вывод из работы, наработка, операции"
                )
            devices.append({"title": _title_lines(_device_title(binding, with_retain_note=True)), "lines": lines})
        version = stfmt.declaration(
            LAYOUT_VERSION_VAR, f"UINT := {ctx.int_option('layout_version')}", comment="версия раскладки списка"
        )
        purpose = self._purpose(
            "Назначение: объект Persistent Variables (контракт plc-process-lib 18.3): Cfg и Retain устройств, "
            "по переменной на устройство, по возрастанию dev_no. Новое устройство — dev_no больше прежних "
            "(переменные встают в конец); типы существующих переменных не меняются. Начальные значения — уставки "
            "перечня; после загрузки действуют сохранённые значения, уставки проекта применяет "
            f"{PRG_APPLY_CFG}. "
            + ("После устройств — данные приложения (persist_extra), новые — в конец. " if extras else "")
            + "Объект создаётся в CODESYS вручную (docs/MANUAL_STEPS.md); «Reorder List and Clear Gaps» не выполнять."
        )
        extra: dict[str, Any] | None = None
        if extras:
            source = Path(ctx.str_option("persist_extra")).name
            extra_lines: list[str] = []
            for item in extras:
                extra_lines += stfmt.declaration(item.name, item.type_text, comment=item.comment)
            title = _title_lines(f"{EXTRA_TITLE} ({source}): новые — только в конец ---")
            extra = {"title": title, "lines": extra_lines}
        return {"purpose": purpose, "layout_version": "\n".join(version), "devices": devices, "extra": extra}

    def _cfg_project(self, plc: PlcModel) -> dict[str, Any]:
        namespace = plc.namespace
        devices = []
        for binding in plc.by_dev_no():
            lines = stfmt.declaration(binding.cfg, binding.cfg_type, binding.device.cfg.initializer_tree(namespace))
            devices.append({"title": _title_lines(_device_title(binding)), "cfg": binding.cfg, "lines": lines})
        purpose = self._purpose(
            f"Назначение: уставки проекта — Cfg устройств из перечня сигналов, те же инициализаторы, что у "
            f"{GVL_PERSIST}. {PRG_APPLY_CFG} копирует их в {GVL_PERSIST} (контракт plc-process-lib 18.3, правило 2)."
        )
        return {"purpose": purpose, "devices": devices}

    def _devices(self, plc: PlcModel) -> dict[str, Any]:
        lines: list[str] = []
        for binding in plc.by_dev_no():
            device = binding.device
            comment = f"{device.dev_no} · {stfmt.one_line(device.description)}"
            lines += stfmt.declaration(binding.instance, binding.fb_type, comment=comment)
        purpose = self._purpose(
            "Назначение: экземпляры устройств plc-process-lib (объявление без параметров, контракт 20). "
            "Логика станции пишет их входы автоматики и читает выходы; HMI и SCADA читают stSts."
        )
        return {"purpose": purpose, "lines": lines}

    @staticmethod
    def _prg_devices_purpose(plc: PlcModel) -> str:
        return (
            f"вызовы устройств plc-process-lib по перечню сигналов: входы из {GVL_IO}, выходы в {GVL_IO}, "
            f"команды {GVL_HMI}, Cfg и Retain — {GVL_PERSIST} (контракт plc-process-lib, разделы 1 и 20). "
            "Входы автоматики (xAutoRun, xAutoOpen, wInterlock, wPermit…, rSpeedSpAuto_pct, rPosSpAuto_pct) пишет "
            f"логика станции до вызова {PRG_DEVICES}"
            + (
                "; ПИД-регуляторы (тип Pid) без сигналов ввода-вывода вызывает логика станции (контракт 17.3)"
                if any(not binding.called for binding in plc.devices)
                else ""
            )
        )

    def _prg_devices(self, plc: PlcModel, ctx: GeneratorContext) -> dict[str, Any]:
        targets = sorted(
            {d.device.link_power for d in plc.devices if d.device.link_power}
            | {d.device.link_fb for d in plc.devices if d.device.link_fb}
        )
        intro = []
        if targets:
            intro += stfmt.comment_lines(
                "Порядок: устройства, на которые ссылаются link_power и link_fb "
                f"({', '.join(str(t) for t in targets)}), вызываются раньше ссылающихся; дальше — по dev_no."
            )
        else:
            intro.append("// Порядок вызовов — по dev_no.")
        if not ctx.str_option("time_source"):
            intro.append("// Источник времени не привязан: устройства берут встроенное системное время (контракт 20).")
        devices = []
        for binding in plc.devices:
            title = _title_lines(_device_title(binding), indent="")
            for note in binding.notes:
                title += stfmt.comment_lines(note)
            if not binding.called:  # устройство без сигналов (Pid): вызов — в логике станции, здесь образец
                sample = [f"// {line}" for line in stfmt.call(binding.instance_path, binding.inputs)]
                devices.append({"title": title, "call": sample, "outputs": []})
                continue
            devices.append(
                {
                    "title": title,
                    "call": stfmt.call(binding.instance_path, binding.inputs),
                    "outputs": stfmt.assignments(binding.outputs, binding.instance_path),
                }
            )
        alarm_sink = ctx.str_option("alarm_sink").strip()
        namespace = plc.namespace
        sink = f"{namespace + '.' if namespace else ''}GVL_Lib.itfAlarmSink := {alarm_sink};" if alarm_sink else ""
        return {
            "intro": intro,
            "alarm_sink": sink,
            "apply_command": ctx.bool_option("apply_command"),
            "devices": devices,
        }

    def _apply(self, plc: PlcModel) -> dict[str, Any]:
        pairs = stfmt.aligned(
            (f"{GVL_PERSIST}.{binding.cfg}", f"{GVL_CFG_PROJECT}.{binding.cfg}") for binding in plc.by_dev_no()
        )
        return {"lines": [f"{target} := {value};" for target, value in pairs]}


# --- сверка с предыдущим GVL_Persist (контракт 18.3, правило 1) ----------------------------------

EXTRA_TITLE = "--- данные приложения, persist_extra"
_TITLE_RE = re.compile(r"^\s*//\s*---\s*dev_no\s+(\d+):\s*([A-Za-z][A-Za-z0-9_]*)")
_EXTRA_TITLE_RE = re.compile(r"^\s*//\s*---\s*данные приложения")
_DECL_RE = re.compile(r"^\s*(st[A-Za-z0-9_]+?(?:Cfg|Retain))\s*:\s*([A-Za-z_][A-Za-z0-9_.]*)")
_EXTRA_DECL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^:;]+?)\s*(?::=|;)")


@dataclass
class _Persist:
    """Прежний GVL_Persist: номера устройств, объявления устройств и данные приложения по порядку."""

    numbers: dict[int, str] = field(default_factory=dict)
    declarations: dict[str, str] = field(default_factory=dict)
    extras: list[tuple[str, str]] = field(default_factory=list)


def _parse_persist(text: str) -> _Persist:
    """Номера устройств, объявления ``st<DEV>Cfg``/``st<DEV>Retain`` и данные приложения прежнего GVL_Persist."""
    result = _Persist()
    in_extras = False
    for line in text.splitlines():
        if _EXTRA_TITLE_RE.match(line):
            in_extras = True
            continue
        title = _TITLE_RE.match(line)
        if title is not None:
            in_extras = False
            result.numbers[int(title.group(1))] = title.group(2)
            continue
        if in_extras:
            extra = _EXTRA_DECL_RE.match(line)
            if extra is not None:
                result.extras.append((extra.group(1), " ".join(extra.group(2).split())))
            continue
        decl = _DECL_RE.match(line)
        if decl is not None:
            result.declarations[decl.group(1)] = decl.group(2)
    return result


def check_persist(previous: str, plc: PlcModel, extras: tuple[ExtraVar, ...] = ()) -> list[str]:
    """Предупреждения о persistent-данных: смена типа, удаление, переиспользование dev_no, порядок."""
    old = _parse_persist(previous)
    if not old.declarations and not old.extras:
        return []
    old_decls = {**old.declarations, **dict(old.extras)}
    new_decls: dict[str, str] = {}
    new_numbers: dict[int, str] = {}
    for binding in plc.by_dev_no():
        new_numbers[binding.device.dev_no] = binding.device.ident
        new_decls[binding.cfg] = binding.cfg_type
        if binding.retain is not None:
            new_decls[binding.retain] = binding.retain_type
    new_decls.update({item.name: item.st_type for item in extras})
    messages: list[str] = []
    old_keys = {name.casefold(): name for name in old_decls}
    for name, st_type in new_decls.items():
        old_name = old_keys.get(name.casefold())
        if old_name is not None and old_decls[old_name].casefold() != st_type.casefold():
            messages.append(
                f"{GVL_PERSIST}.{name}: тип изменился ({old_decls[old_name]} → {st_type}) — CODESYS "
                "переинициализирует переменную целиком, сохранённые уставки и счётчики пропадут"
            )
    new_keys = {name.casefold() for name in new_decls}
    for name in old_decls:
        if name.casefold() not in new_keys:
            messages.append(
                f"{GVL_PERSIST}.{name} удалена: её сохранённые значения пропадут при загрузке "
                "(для удалённого устройства это ожидаемо)"
            )
    for number, old_device in sorted(old.numbers.items()):
        new_device = new_numbers.get(number)
        if new_device is not None and new_device.casefold() != old_device.casefold():
            messages.append(
                f"dev_no {number} был у {old_device}, теперь у {new_device} — переименование или "
                f"переиспользование номера: сохранённые уставки и счётчики {old_device} к {new_device} не "
                "перейдут (persistent-переменная с другим именем — новая), номера тревог останутся прежними"
            )
    if old.numbers:
        last = max(old.numbers)
        old_devices = {name.casefold() for name in old.numbers.values()}
        for number, device in sorted(new_numbers.items()):
            if device.casefold() not in old_devices and number < last:
                messages.append(
                    f"новое устройство {device} получило dev_no {number}, меньше прежнего наибольшего {last}: "
                    "по правилу 18.3 новые устройства получают номера больше всех прежних и встают в конец списка"
                )
    messages += _check_extra_order([name for name, _ in old.extras], [item.name for item in extras])
    return messages


def _check_extra_order(old: list[str], new: list[str]) -> list[str]:
    """Данные приложения: прежние — в прежнем порядке, новые — только после всех прежних (правило 18.3.1)."""
    old_keys = {name.casefold() for name in old}
    new_keys = {name.casefold() for name in new}
    kept_new = [name for name in new if name.casefold() in old_keys]
    kept_old = [name for name in old if name.casefold() in new_keys]
    messages: list[str] = []
    if [name.casefold() for name in kept_new] != [name.casefold() for name in kept_old]:
        messages.append(
            f"{GVL_PERSIST}: порядок данных приложения (persist_extra) изменился: было {', '.join(kept_old)}, "
            f"стало {', '.join(kept_new)} — прежние переменные не переставляют (контракт 18.3, правило 1)"
        )
    last_old = max((index for index, name in enumerate(new) if name.casefold() in old_keys), default=-1)
    for index, name in enumerate(new):
        if name.casefold() not in old_keys and index < last_old:
            messages.append(
                f"{GVL_PERSIST}.{name}: новая переменная данных приложения стоит перед прежними — добавляйте "
                "новые в конец файла persist_extra (контракт 18.3, правило 1)"
            )
    return messages
