"""Плагин iolistgen для MasterSCADA 4D — заготовка: документированного формата импорта тегов нет.

Что найдено в документации вендора (справка MasterSCADA 4D, IEK Digital, проверено 2026-10-16):

1. Переменные OPC UA сервера CODESYS добавляются **обзором сервера**: диалог подключения к серверу
   OPC UA, «Подключиться без загрузки» или «Загрузить все», выбор параметров, «Применить».
   Импорта списка переменных из файла на странице нет.
   https://help.iek-digital.ru/Help-web/dialog_podklyucheniya_k_serveru_opc_ua.html
2. Каналы Modbus импортируются в редактор каналов из csv («формат старого Modbus драйвера»), xlsx
   («собственный формат, совместимый с операцией экспорта»), sdv (MasterOPC) и map (Segnetics).
   Названы колонки таблицы редактора — «Имя канала», «Регион», «Адрес», «Тип в устройстве»,
   «Тип в SCADA», «Доступ», «Тип строки», «Шкала», «Комментарий», — но не раскладка файла:
   заголовки ячеек, значения «Региона» и «Доступа», запись адреса и типов.
   https://help.iek-digital.ru/Help-web/dialog_importa_kanalov_modbus1.html
3. Табличное представление проекта экспортирует результаты запроса в CSV (разделитель — запятая),
   правленый файл импортируется обратно; столбец ``Property~Id элемента~Id`` менять нельзя.
   Набор столбцов задаёт запрос, фиксированного формата для создания тегов нет.
   https://help.iek-digital.ru/Help-web/redact_rez_zaprosov_csv.html

Поэтому генератор формат не выдумывает: ``generate()`` отказывает с объяснением, а теги для
MasterSCADA 4D даёт встроенный ``scada-csv`` (пути и узлы OPC UA для сверки с обзором сервера) и
``modbus-map`` (карта slave для ручного заведения каналов).

TODO: реализовать импорт каналов Modbus (xlsx редактора каналов). Нужен образец: в MasterSCADA 4D
завести устройство Modbus с каналами всех типов (WORD, INT, UINT, REAL, DINT в областях holding и
input), выполнить «Экспорт» в xlsx и зафиксировать по нему заголовки, значения «Региона», «Доступа»,
типов и запись адреса. Отображение колонок в ``channel_rows()`` ниже — по названиям из справки,
без проверки на настоящем файле.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from iolistgen.generators import GenerationError, GeneratorContext, GeneratorOption
from iolistgen.generators.modbus_map import slave_blocks, slave_rows
from iolistgen.generators.plc import build_plc
from iolistgen.model import IoList

SOURCES = (
    "https://help.iek-digital.ru/Help-web/dialog_podklyucheniya_k_serveru_opc_ua.html",
    "https://help.iek-digital.ru/Help-web/dialog_importa_kanalov_modbus1.html",
    "https://help.iek-digital.ru/Help-web/redact_rez_zaprosov_csv.html",
)

# Колонки таблицы редактора каналов Modbus — названия из справки (п. 2 выше); раскладка файла не проверена
CHANNEL_COLUMNS = ("Имя канала", "Регион", "Адрес", "Тип в устройстве", "Тип в SCADA", "Доступ", "Комментарий")


def channel_rows(model: IoList, *, base: int = 0) -> list[dict[str, str]]:
    """Черновое отображение карты slave (блоки ``stSts``) на колонки редактора каналов MasterSCADA 4D.

    Значения «Региона», «Доступа» и записи адреса — предположение до сверки с экспортом (TODO выше).
    """
    plc = build_plc(model)
    blocks = slave_blocks(plc, base=base, layout="packed", stride=0)
    rows: list[dict[str, str]] = []
    for row in slave_rows(blocks, area="holding", word_order="LH", application="Application"):
        rows.append(
            {
                "Имя канала": f"{row['device']}.{str(row['field']).removeprefix('stSts.')}",
                "Регион": "Holding Registers",
                "Адрес": str(row["address"]),
                "Тип в устройстве": str(row["data_type"]),
                "Тип в SCADA": str(row["data_type"]),
                "Доступ": "ReadOnly",
                "Комментарий": str(row["description"]),
            }
        )
    return rows


class MasterScada4dGenerator:
    """Заготовка генератора импорта для MasterSCADA 4D (формат вендора не задокументирован)."""

    name = "masterscada4d"
    description = "MasterSCADA 4D — заготовка: документированного формата импорта нет (см. docs/GENERATORS.md)"
    options: Sequence[GeneratorOption] = (GeneratorOption("dir", "каталог файлов относительно --out", "str", "scada"),)

    def generate(self, model: IoList, out_dir: Path, ctx: GeneratorContext) -> list[Path]:
        raise GenerationError(
            "формат импорта тегов MasterSCADA 4D в документации вендора не описан: переменные OPC UA "
            "добавляются обзором сервера, раскладка xlsx каналов Modbus не задана "
            f"({'; '.join(SOURCES)}). Используйте scada-csv (пути и узлы OPC UA) и modbus-map; "
            "реализация — TODO в iolistgen_masterscada4d.py"
        )
