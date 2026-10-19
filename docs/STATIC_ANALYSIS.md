# Статический анализ

Находки `iec_checker` по `build/assembled/` (и `st_lint` по `src/`, `tests/`), которые не
исправлены в коде, — с обоснованием. Исправленные находки сюда не пишутся. Здесь же — итог
проверки компиляции RuSTy.

С версии 0.2.0 в `src/` — не пример шаблона, а код, который `iolistgen` сгенерировал по перечню
КНС-1 (`src/GVLs/Generated`, `src/POUs/Generated`, команда — в [MANUAL_STEPS.md](MANUAL_STEPS.md#9-код-сгенерированный-iolistgen-в-проекте-codesys)),
и ручная точка входа `PRG_Main`; в `tests/` — набор coUnit `FB_ProjectCfg_Test`. Код ссылается на
библиотеку plc-process-lib (`PL.`), поэтому RuSTy проверяет его вместе с заглушкой библиотеки.

## Как запускается

| Инструмент | Где | Вход | Отчёт |
|---|---|---|---|
| `tools/check/st_lint.py --strict` | локально и в CI | `src/`, `tests/` | вывод в консоль, код выхода ≠ 0 при нарушениях |
| `tools/check/run_iec_checker.py --tests` | локально и в CI (обязательно): бинарник iec_checker v0.4 из релизов github.com/jubnzv/iec-checker | `build/assembled/iec-checker/` (вариант сборки `iec-checker`) | `build/iec_checker.json`, `build/iec_checker.md` |
| то же с `--docker` | CI, необязательное задание: образ `jubnzv1/iec-checker:nightly`, закреплённый по дайджесту в `ci.yml` | то же | то же, артефакт `iec-checker-nightly-reports` |
| `tests_support/check_generated_st.py --repo` | локально и в CI (необязательное задание): st_lint, сборка раскладки и RuSTy `plc --check` | `src/` репозитория вместе с заглушкой `tests_support/pl_stub/` | `build/st_check/repo_src/rusty/` |
| `tests_support/check_generated_st.py` | то же | ST, сгенерированный по перечням примеров и тестов (4 случая) | `build/st_check/<случай>/` |

Обоснования в `tools/check/iec_checker_allow.toml` подобраны под находки v0.4 — той же версии, что в
обязательном шаге CI. Образ `nightly` разбирает больше конструкций и может находить иначе: если
находка есть только в одной версии — укажите это в столбце «решение». Интеграционный тест
`tools/tests/test_run_iec_checker.py::test_integration_repository_sources` проверяет, что каждое
обоснование используется: после правок `src/` или перегенерации уберите устаревшие записи.

## Последний прогон

| Дата | Инструмент | Вход | Итог |
|---|---|---|---|
| 2026-10-19 | `st_lint --strict` | `src/`, `tests/` (26 файлов) | 0 ошибок, 0 предупреждений |
| 2026-10-19 | `run_iec_checker.py` (iec_checker 0.4, Windows, локально) | 9 объектов `src/` | ошибок разбора нет; необоснованных 0; обоснованных 219: CP3 — 214, CP9 — 3, L17 — 2; артефактов сборки 0 |
| 2026-10-19 | `run_iec_checker.py --tests` (iec_checker 0.4, Windows, локально) | 11 объектов `src/` и `tests/` | ошибок разбора нет; необоснованных 0; обоснованных 243: CP3 — 218, UnusedVariable — 14, CP9 — 9, L17 — 2; неиспользованных обоснований нет |
| 2026-10-19 | `check_generated_st.py --repo` (RuSTy 1.0.6, `plc --check`, Windows, локально) | `src/` и заглушка plc-process-lib (71 файл) | 0 ошибок, 0 предупреждений |
| — | iec_checker 0.4 (CI, Linux) | 11 объектов `src/` и `tests/` | _перенести из отчёта CI_ |
| — | iec_checker `nightly` (CI, необязательно) | то же | _перенести из отчёта CI_ |

## Находки

| Правило | Файл | Находка | Решение / обоснование |
|---|---|---|---|
| PLCOPEN-CP3 | GVL и POU `src/` (214) | «Variable … shall be initialized before being used» для переменных без явного начального значения | Обосновано. В CODESYS, как и по МЭК 61131-3, переменная без явного начального значения получает значение по умолчанию своего типа (0, `FALSE`): каналы `GVL_IO`, команды `GVL_Hmi`, экземпляры `GVL_Devices`, Retain устройств. Вариант сборки `iec-checker` убирает и неконстантные начальные значения (инициализаторы Cfg в `GVL_Persist`, `GVL_CfgProject`), поэтому находка есть и для них |
| PLCOPEN-CP9 | `PRG_Devices` (сложность 118, 188 операторов), `PRG_ApplyProjectCfg` (30 операторов) | «Code is too complex» | Обосновано. Код сгенерирован по перечню: линейная последовательность вызовов устройств, присваиваний выходов и копирований Cfg, единственное ветвление — команда HMI «применить уставки проекта». iec_checker 0.4 считает каждое обращение к экземпляру и присваивание (сложность завышена, см. ниже), и число растёт с числом устройств перечня; делить сгенерированный вызов на части ради метрики незачем |
| PLCOPEN-L17 | `PRG_Devices`: команда `GVL_Hmi.xApplyProjectCfg` | «Each IF instruction should have an ELSE clause» | Обосновано: команда не пришла — делать нечего; пустая ветка `ELSE` в сгенерированном коде только добавит шум |
| PLCOPEN-L17 | `PRG_Main`: восстановление задания оператора после старта | то же | Обосновано: задание восстанавливается из `GVL_Persist` один раз; в остальных циклах делать нечего |

Сложность iec_checker 0.4 считает завышенно: на синтетическом примере одна конструкция
`IF … ELSE … END_IF` прибавляет 5 (проверено при разборе примера шаблона, версия 0.1.0).

### Если анализируются и тесты (`assemble --tests`)

| Правило | Файл | Находка | Решение / обоснование |
|---|---|---|---|
| UnusedVariable | `FB_ProjectCfg_Test`: константы набора `W_NO_ERRORS`, `T_MIN_STOP_PROJECT`, … `R_EXACT` (11) | «Found unused local variable» | Артефакт понижения: константы набора (`VAR CONSTANT`) используются в методах-тестах, которые сборка выносит в отдельные функции |
| UnusedVariable | `FB_ProjectCfg_Test.CheckCfg`: `sDevice`, `stCommon` | то же | Ложное срабатывание: вход используется в `CONCAT(sDevice, …)`, структура — чтением полей `stCommon.wCfgErr` и `stCommon.wStatus`; обращения к полям iec_checker 0.4 использованием не считает |
| UnusedVariable | `PRG_Tests`: `fbProjectCfgTest` | то же | Ложное срабатывание: экземпляр используется вызовом `AreAllTestsFinished()` и регистрируется в coUnit самим объявлением |
| PLCOPEN-CP9 | `FB_ProjectCfg_Test` и его методы (6) | «Code is too complex», «… statements» | Обосновано: в наборе и методах-тестах нет ветвлений (классическая сложность — 1), это последовательности вызовов и проверок — 30 проверок Cfg устройств подряд; для тестов метрика не показательна |
| PLCOPEN-CP3 | `FB_ProjectCfg_Test`, `PRG_Tests` (4) | как выше | Обосновано, как для `src/` |

## RuSTy (`plc --check`)

Компилятор RuSTy 1.0.6 проверяет синтаксис и типы; компоновки нет. `src/` ссылается на plc-process-lib,
поэтому `tests_support/check_generated_st.py --repo` объединяет раскладку с заглушкой библиотеки
(`tests_support/pl_stub/`: DUT, константы, интерфейсы и публичные секции ФБ выпуска 1.0.0, сверены с
исходниками библиотеки `tests_support/check_library.py`) и убирает пространство имён `PL.`; правки копии
перед RuSTy и их причины — [GENERATORS.md](GENERATORS.md#проверка-st-без-codesys). `tests/` (coUnit и `PL.`)
RuSTy не проверяет: его компилирует CODESYS (`cds.py check --tests`, `cds.py test`). Последний прогон — в
таблице выше: 0 ошибок, 0 предупреждений. Шаблонный `tools/check/run_rusty.py` по `src/` без заглушки в
этом репозитории не запускается: типы `PL.` ему неизвестны.

## Ограничения разборщика

Конструкции CODESYS, которые iec_checker 0.4 не разбирает, — и что с ними делает вариант сборки
`iec-checker` (подробно — [LAYOUT.md](LAYOUT.md#собранный-текст-buildassembled) и `tools/README.md`):

| Конструкция | Где | Как обходится |
|---|---|---|
| неконстантные начальные значения (инициализаторы Cfg с `PL.E_…`, `T#…`, массивы структур) | `GVL_Persist`, `GVL_CfgProject` | сборка убирает начальное значение (отсюда часть находок CP3) |
| `VAR_GLOBAL` вне `CONFIGURATION`, прагмы `{attribute …}`, объект Persistent Variables | все GVL `src/GVLs/Generated` | сборка понижает |
| типы и ФБ библиотеки с пространством имён (`PL.FB_MotorVfd`, `PL.ST_PidCfg`) | `GVL_Devices`, `GVL_Hmi`, `GVL_Persist`, `PRG_Devices` | сборка убирает пространство имён; объявлений библиотеки у разборщика нет — типы не проверяются (это делают RuSTy с заглушкой и CODESYS) |
| методы внутри `FUNCTION_BLOCK`, `EXTENDS` | `FB_ProjectCfg_Test` | сборка выносит методы в функции `<ФБ>__<метод>` — анализ методов приблизительный |
