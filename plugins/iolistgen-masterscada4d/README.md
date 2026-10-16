# iolistgen-masterscada4d — заготовка плагина

Пример плагина iolistgen (точка входа `iolistgen.generators`) и место для будущего импорта в
MasterSCADA 4D. Генератор сейчас **не пишет файлов**: документированного формата импорта тегов
у MasterSCADA 4D не найдено, а придуманный формат в проекте не используется.

Что сказано в справке вендора (IEK Digital, проверено 2026-10-16):

- переменные OPC UA сервера CODESYS добавляются обзором сервера в диалоге подключения
  ([справка](https://help.iek-digital.ru/Help-web/dialog_podklyucheniya_k_serveru_opc_ua.html));
- каналы Modbus импортируются в редактор каналов из xlsx «собственного формата, совместимого
  с операцией экспорта» — колонки таблицы названы, раскладка файла не описана
  ([справка](https://help.iek-digital.ru/Help-web/dialog_importa_kanalov_modbus1.html));
- табличное представление проекта правится через экспорт и импорт CSV, набор столбцов задаёт
  запрос ([справка](https://help.iek-digital.ru/Help-web/redact_rez_zaprosov_csv.html)).

Пока формата нет, для MasterSCADA 4D используйте встроенные генераторы: `scada-csv` (пути
переменных и узлы OPC UA — сверка с обзором сервера) и `modbus-map` (карта slave для заведения
каналов вручную). Что нужно для реализации — TODO в `iolistgen_masterscada4d.py`.

```bash
pipx inject iolistgen ./plugins/iolistgen-masterscada4d
iolistgen generate --list          # masterscada4d — заготовка
```
