# Отчёт о тестировании

Результаты юнит-тестов CfUnit (coUnit 1.2.0.0) в CODESYS Control Win V3 и проверок без CODESYS.
Запись «проверено в CODESYS» появляется только после реального прогона. Раздел «Последний прогон
в CODESYS» обновляет `python tools/codesys/cds.py report` по итогам `cds.py test`
(`build/test-results.json`); правки внутри него вручную перезаписываются.

<!-- cds:test-report:begin (раздел обновляет `python tools/codesys/cds.py report`) -->
## Последний прогон в CODESYS

Проверено в CODESYS 3.5.17.30 / CODESYS Control Win V3 (пользовательский процесс) — 2026-10-19 13:19:30. Итог: **все тесты пройдены**.

| Параметр | Значение |
|---|---|
| Дата прогона | 2026-10-19 13:19:30 |
| Коммит | ab0f622 |
| CODESYS | 3.5.17.30 (профиль `CODESYS V3.5 SP17 Patch 3`) |
| Устройство в проекте | CODESYS Control Win V3 (4096 / 0000 0001 / 3.5.17.30) |
| Рантайм | CODESYS Control Win V3 (пользовательский процесс) |
| Фреймворк тестов | coUnit (CfUnit) 1.2.0.0 |
| Сборка | ошибок 0, предупреждений 0 |
| Способ запуска | `python tools/codesys/cds.py test` |

| Набор | Тестов | Пройдено | Упало | Пропущено | Итог |
|---|---|---|---|---|---|
| `PRG_Tests.fbProjectCfgTest` | 4 | 4 | 0 | 0 | пройдено |
| **Всего** | 4 | 4 | 0 | 0 | **пройдено** |

### Результаты тестов

| Набор | Тест | Итог |
|---|---|---|
| `PRG_Tests.fbProjectCfgTest` | `AllDevicesProjectCfgPassCheckConfig` | пройден |
| `PRG_Tests.fbProjectCfgTest` | `PidCfgComesFromIoList` | пройден |
| `PRG_Tests.fbProjectCfgTest` | `AlarmArrayWrittenWholeKeepsLibraryDefaults` | пройден |
| `PRG_Tests.fbProjectCfgTest` | `ApplyProjectCfgCopiesCfgKeepsRetain` | пройден |

### Упавшие тесты

_Нет._

Машиночитаемые результаты: `build/test-results.json`, `build/junit.xml` (не в git).
<!-- cds:test-report:end -->

## Что проверяют тесты

Набор `FB_ProjectCfg_Test` (`tests/POUs/FB_ProjectCfg_Test`) проверяет код, который `iolistgen` сгенерировал по
перечню КНС-1 (`src/GVLs/Generated`, `src/POUs/Generated`), вместе с настоящей библиотекой plc-process-lib
1.0.0.0. Главный вопрос — совпадает ли зеркало `CheckConfig` валидатора с ФБ библиотеки: перечень, который
`iolistgen validate` пропустил, не должен дать устройство с отклонённой Cfg.

| Набор | Тест | Что проверяет |
|---|---|---|
| `FB_ProjectCfg_Test` | `AllDevicesProjectCfgPassCheckConfig` | после «применить уставки проекта» и вызова `PRG_Devices` (и регулятора `LIC101` — его вызывает логика станции) у всех 30 устройств `stSts.stCommon.wCfgErr = 0` и снят бит `DEV_STS_CFG_ERROR`: Cfg проекта — уставки перечня, `params`, выводы из состава — принимает `CheckConfig` каждого ФБ |
| `FB_ProjectCfg_Test` | `PidCfgComesFromIoList` | Cfg регулятора `LIC101` из строки устройства перечня: `eAction = Direct`, `xUseOutAct`, диапазон PV из `range_max`, пределы задания из `params`, `udiAlarmIdBase = dev_no · 10`, тревога PVF выключена |
| `FB_ProjectCfg_Test` | `AlarmArrayWrittenWholeKeepsLibraryDefaults` | инициализатор с массивом `astAlarm`, записанным целиком (контракт 18.3, правило 3): у `LT101` слоты, которые меняет колонка `alarm_priority`, получили High и Medium, остальные (`Failure`, `OutOfRange`) сохранили умолчания DUT библиотеки; уставка HH включена со значением перечня |
| `FB_ProjectCfg_Test` | `ApplyProjectCfgCopiesCfgKeepsRetain` | `PRG_ApplyProjectCfg`: изменённая с HMI уставка `tMinStop` насоса `P101` возвращается к значению перечня, Retain (`udiOpCount`) не меняется (контракт 18.3, правило 2) |

Отрицательный контроль (2026-10-19, вручную, в git не попал): в `GVL_CfgProject` насосу `P101` задан
`tResetWindow := T#0S` — `cds.py test` дал «упало 1 из 4»: `AllDevicesProjectCfgPassCheckConfig` —
«P101: wCfgErr must be 0 for the project Cfg» (бит `MOT_CFG_RESET`). Набор находит Cfg, которую ФБ отклоняет.

Объект Persistent Variables `GVL_Persist` в проектах `cds.py` создаёт `tools_project/codesys_pvl.py`
(импорт PLCopenXML): скриптом SP17 он не создаётся ([MANUAL_STEPS.md](MANUAL_STEPS.md#9-код-сгенерированный-iolistgen-в-проекте-codesys)).

## Сборка в CODESYS

| Дата | Команда | Итог |
|---|---|---|
| 2026-10-19 | `python tools/codesys/cds.py check` | `check: OK (объектов 9, ошибок 0, предупреждений 0)` — все объекты `src/` |
| 2026-10-19 | `python tools/codesys/cds.py check --tests` | `check: OK (объектов 11, ошибок 0, предупреждений 0)` |
| 2026-10-19 | `python tools/codesys/cds.py build` | без объекта Persistent Variables — 134 ошибки (C0046 «Идентификатор 'GVL_Persist' не задан», C0018); после `tools_project/codesys_pvl.py` — `build: OK (ошибок 0, предупреждений 0)` |
| 2026-10-19 | `python tools/codesys/cds.py build --tests` | `build: OK (ошибок 0, предупреждений 0)` |

Библиотеки проекта: `plc-process-lib, 1.0.0.0 (plc-portfolio)`, `#Standard`, в режиме тестов — coUnit 1.2.0.0.

## Проверки без CODESYS

Итоги последнего прогона CI (ссылка на запуск GitHub Actions) или локального прогона.

| Проверка | Итог | Примечание |
|---|---|---|
| `ruff check`, `ruff format --check`, `mypy`, `pytest` | пройдено, 2026-10-19, локально | pytest: все тесты, включая интеграционные с настоящими `plc` и iec_checker и сверку с исходниками plc-process-lib |
| `tools/assemble.py` (все варианты, с `--tests` и без) | пройдено, 2026-10-19, локально | 9 объектов `src/` + 2 объекта `tests/` |
| `tools/check/st_lint.py --strict` | пройдено, 2026-10-19, локально | 26 файлов, 0 замечаний |
| iec_checker 0.4 (локально, `run_iec_checker.py --tests`) | пройдено, 2026-10-19 | 11 объектов, ошибок разбора нет; необоснованных находок 0, обоснованных 243 — разбор в [STATIC_ANALYSIS.md](STATIC_ANALYSIS.md) |
| RuSTy 1.0.6 (локально, `tests_support/check_generated_st.py --repo` и без ключа) | пройдено, 2026-10-19 | `src/` с заглушкой plc-process-lib и 4 случая сгенерированного ST: 0 ошибок, 0 предупреждений |
| `tests_support/check_library.py` | пройдено, 2026-10-19 | каталог и заглушка совпадают с исходниками plc-process-lib 1.0.0: перечислений 23, структур Cfg 9, Cmd/Sts/Retain 15, ФБ 7, констант 33, слотов тревог 34, шаблоны текстов тревог |
