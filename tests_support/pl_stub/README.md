# Заглушка plc-process-lib для проверки сгенерированного ST

Объявления библиотеки plc-process-lib 1.0.0 (выпуск 1.0.0.0, контракт `API.md` 1.0.0) в раскладке
[LAYOUT.md](../../docs/LAYOUT.md) — только то, к чему обращается код iolistgen:

- DUT: перечисления, `ST_<Dev>Cmd`, `ST_<Dev>Cfg` с умолчаниями, `ST_<Dev>Sts`, `ST_DeviceRetain`,
  `ST_AlarmCfg`, `ST_AiLimitCfg`, `ST_VfdCfg`, `ST_AlarmEvent`;
- `GVL_Const` — константы таблицы 5.1 (без масок битов), `GVL_Lib.itfAlarmSink`;
- интерфейсы `I_TimeSource`, `I_AlarmSink`;
- `FB_DeviceBase` (`ABSTRACT`, вход `itfTime`) и ФБ устройств с теми же `VAR_INPUT`, `VAR_OUTPUT`,
  `VAR_IN_OUT` и `VAR_IN_OUT CONSTANT`, что в контракте, **без тел и внутренних переменных**.

Это не библиотека: логики нет, интерфейсы `I_Device`, `I_Motor`, `I_MotorVfd`, методы и свойства
устройств не объявлены. Заглушка нужна, чтобы RuSTy проверил типы сгенерированного кода без
CODESYS (`python tests_support/check_generated_st.py`, docs/GENERATORS.md).

Согласованность: `pytests/test_pl_stub.py` сверяет каждое поле, тип, умолчание Cfg, перечисление,
константу и вход/выход ФБ с каталогом пакета (`iolistgen/catalog.py`, `iolistgen/fbapi.py`), а
`tests_support/check_library.py` (тест `pytests/test_library_source.py`) — каталог и каждый объект
заглушки с исходниками выпущенной библиотеки (`PL_REPO` или `../plc-process-lib`). Изменилась
библиотека — меняются каталог и заглушка вместе.

Имена `astAlarm`, `astLimit`, `audiReserve` и параметры `VAR_IN_OUT CONSTANT` взяты из контракта;
правило st_lint STL007 для них подавлено `lint:allow` с причиной (так же сделано в исходниках
библиотеки).
