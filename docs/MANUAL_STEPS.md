# Ручные шаги

Шаги, которые выполняет человек в консоли Windows и в IDE CODESYS. Всё, что можно выполнить без
CODESYS (сборка текстов, линтер, статанализ), описано в [README](../README.md#быстрый-старт-без-железа)
и выполняется в CI.

Команды разделов 3–7 проверены прогоном на CODESYS V3.5 SP17 Patch 3 (3.5.17.30, 32-битная сборка
ОВЕН) и CODESYS Control Win V3 в пользовательском процессе (16.10.2026). Что не проверено — отмечено
явно. Подробности об инструменте — [tools/README.md](../tools/README.md#codesyscdspy--codesys-из-консоли).

## 1. Установка CODESYS 3.5.17.30

1. Скачать CODESYS V3.5 SP17 Patch 3 (3.5.17.30) с сайта ОВЕН (раздел ПО для ПЛК2xx) и установить
   с компонентами CODESYS Control Win V3 и Gateway. Сборка ОВЕН 32-битная и ставится в
   `C:\Program Files (x86)\CODESYS 3.5.17.30\` — этот путь `cds.py` находит сам.
2. Для рабочего ПЛК — пакет таргет-файлов ОВЕН ПЛК210: «Инструменты → Установщик пакетов»
   (Tools → Package Manager). Версию таргет-файла сверить с прошивкой ПЛК. Для тестов он не нужен:
   тестовый проект собирается под CODESYS Control Win V3.
3. Имя профиля — по файлу в каталоге профилей (для 3.5.17.30 — `CODESYS V3.5 SP17 Patch 3`):

   ```bat
   dir "C:\Program Files (x86)\CODESYS 3.5.17.30\CODESYS\Profiles"
   ```

   `CODESYS.exe --help` и запуск без `--profile` открывают окно IDE (диалог выбора профиля), а не
   выводят справку в консоль — для проверки их не используйте.
4. Нужен Python 3.11+ (`python --version`), сторонние пакеты для `cds.py` не нужны.

## 2. coUnit (CfUnit) 1.2.0.0

В версии 1.2.0.0 CfUnit называется co♻e / coUnit, пространство имён в коде — `coUnit`
(см. [ASSUMPTIONS.md](ASSUMPTIONS.md), C6). Лицензия MIT.

1. Скачать `counit.library` из SVN проекта counit на CODESYS Forge (`tags/v1.2.0.0/`) обычным
   `GET` (браузером: запрос `HEAD` даёт 401).
2. Установить одним из способов:
   - в IDE: «Инструменты → Репозиторий библиотек → Установить» (Tools → Library Repository → Install);
   - или автоматически: задать путь к файлу в `COUNIT_LIBRARY` (раздел 3) — первый
     `cds.py import --tests`, не найдя coUnit 1.2.0.0 в репозиториях, установит её в репозиторий
     `System` (`librarymanager.install_library`). _Ветка установки на этой машине не выполнялась:
     библиотека уже была установлена; поиск по пространству имён и версии — проверен._
3. Параметры библиотеки менять не нужно: с параметрами по умолчанию тестовое приложение под
   Control Win собирается без ошибок (проверено, C7). Для ПЛК210 с меньшей памятью — сверить при
   переносе тестов на контроллер.

## 3. Переменные окружения

Абсолютных путей пользователя в репозитории нет: `cds.py` берёт их из переменных окружения, а без
них — из значений по умолчанию в `tools/codesys/config.json`. Обычно достаточно двух:

| Переменная | Значение | По умолчанию |
|---|---|---|
| `CODESYS_EXE` | полный путь к `CODESYS.exe` | `%ProgramFiles(x86)%\CODESYS 3.5.17.30\CODESYS\Common\CODESYS.exe`, затем `%ProgramFiles%\...` |
| `CODESYS_PROFILE` | имя профиля | `CODESYS V3.5 SP17 Patch 3` |
| `COUNIT_LIBRARY` | путь к `counit.library` (только если coUnit ещё не установлена) | — |
| `CODESYS_RUNTIME_CREDENTIALS` | файл с логином и паролем тестового пользователя рантайма | `%USERPROFILE%\.local\plc-tools\cds-runtime\credentials.json` |

Остальные (устройство, пути рантайма, таймауты, блокировка) — в
[tools/README.md](../tools/README.md#переменные-окружения). Задать для пользователя:

```bat
setx CODESYS_EXE "C:\Program Files (x86)\CODESYS 3.5.17.30\CODESYS\Common\CODESYS.exe"
setx CODESYS_PROFILE "CODESYS V3.5 SP17 Patch 3"
```

`setx` не меняет окружение уже открытых консолей; `cds.py` дочитывает переменные пользователя из
реестра (`HKCU\Environment`), поэтому перезапуск консоли не обязателен.

## 4. Рантайм CODESYS Control Win V3 без прав администратора

Служба Windows «CODESYS Control Win V3» требует прав администратора — её не используем. Тесты идут
в пользовательском процессе `CODESYSControlService.exe`, которым управляет `cds.py`:

```bat
python tools\codesys\cds.py runtime init      & rem один раз: каталог, boot.cfg, копия CODESYSControl.cfg, credentials.json
python tools\codesys\cds.py runtime start     & rem скрытый запуск, ждёт порт 11740
python tools\codesys\cds.py runtime status    & rem PID, сколько работает, остаток демо-режима
python tools\codesys\cds.py runtime restart
python tools\codesys\cds.py runtime stop
```

- `runtime init` создаёт `%USERPROFILE%\.local\plc-tools\cds-runtime\`: `boot.cfg`, `work\` с
  копией штатного `CODESYSControl.cfg` (из `C:\ProgramData\CODESYS\CODESYSControlWinV3\<id>\`, файл
  только читается) и `credentials.json` с пользователем `cdsci` и случайным паролем. Пароль не
  печатается; файл лежит вне репозитория — не копируйте и не коммитьте его.
- Без лицензии рантайм работает 2 часа с момента запуска. `cds.py test` сам перезапускает его, если
  он работает дольше 100 минут (`CODESYS_RUNTIME_MAX_AGE_MIN`). Запуск и остановка — только своего
  процесса (с `-d <boot.cfg>`); если порт 11740 занят службой или чужим экземпляром, `cds.py`
  использует его, но не перезапускает.
- Состояние рантайма (пользователи, загруженные приложения, сертификаты, PlcLogic) из-за
  виртуализации UAC лежит не в `work\`, а в
  `%LOCALAPPDATA%\VirtualStore\Program Files (x86)\CODESYS 3.5.17.30\GatewayPLC\`; туда же
  попадает XML-отчёт coUnit (`%LOCALAPPDATA%\VirtualStore\coUnit_xunit_testresults.xml`).
  Чтобы «обнулить» рантайм (забыть пользователей и приложения), остановите его и удалите этот
  каталог вручную — это необратимо.

**Первый вход и создание пользователя.** Управление пользователями рантайма остаётся включённым
(отключать его не нужно). На свежем рантайме без пользователей `cds.py test` сам создаёт первого
пользователя из `credentials.json` (`set_credentials_for_initial_user` и подключение), если обычный
вход не удался. _Эта ветка реализована по API, но на этой машине не выполнялась: пользователь
`cdsci` уже был создан._ Если автоматически не получится — вручную в IDE: открыть тестовый проект
(раздел 6), «Устройство → Настройки соединения» (Communication Settings), выбрать шлюз `Gateway-1`
(localhost:1217) и устройство, войти — IDE предложит создать пользователя; ввести логин и пароль
из `credentials.json`.

## 5. Импорт, сборка, тесты

Все команды — из корня репозитория. Каждая запускает CODESYS без окна (`--noUI`), длится
10–20 секунд и пишет журналы в `build/`.

```bat
python tools\codesys\cds.py import            & rem src\ -> build\<имя>.project (MainTask 20 мс -> PRG_Main)
python tools\codesys\cds.py import --tests    & rem src\ и tests\ -> build\<имя>-tests.project (TestTask 10 мс -> PRG_Tests, coUnit)
python tools\codesys\cds.py build             & rem импорт и полная сборка: build\build.log, build\build.json
python tools\codesys\cds.py build --tests     & rem то же для тестового проекта
python tools\codesys\cds.py test              & rem импорт с тестами, сборка, прогон в рантайме
python tools\codesys\cds.py roundtrip         & rem импорт в чистый проект -> экспорт -> сравнение с src\ и tests\
python tools\codesys\cds.py report            & rem итоги последнего test -> docs\TEST_REPORT.md
```

Что смотреть:

- `import` печатает, что создано, обновлено, удалено и перемещено. Повторный импорт без правок —
  «создано 0, обновлено 0, удалено 0». Ошибки раскладки (коды LAY) — отказ без изменений проекта.
- `build`: ошибки и предупреждения компилятора с файлом и строкой раскладки, например
  `src/POUs/F_Clamp/F_Clamp.impl.st:16: Error C0046 Идентификатор 'rValueX' не задан`. Сообщения
  IDE — на русском. Если в IDE видны ошибки, которых нет в выводе, — скопируйте их в
  [BUILD_ERRORS.md](BUILD_ERRORS.md).
- `test`: итог по наборам и тестам; упавшие — с сообщением coUnit. Результаты — в
  `build/test-results.json` и `build/junit.xml`, журнал — `build/test.log`.
- `roundtrip`: «экспорт совпадает с src/ и tests/ побайтно» и «повторный импорт … — 0 изменений».
  Любой дифф — ошибка скриптов (issue).

Коды выхода: 0 — успех; 1 — ошибки раскладки или сборки, упавшие тесты, дифф roundtrip;
2 — аргументы или `config.json`; 3 — окружение (нет CODESYS, рантайма, файла); 4 — таймаут;
5 — блокировка занята. Рантайм один на машину: команды, которые с ним работают, ждут друг друга
(блокировка `%LOCALAPPDATA%\plc-tools\codesys-runtime.lock`).

## 6. Работа в IDE и экспорт перед коммитом

1. Собрать проект: `python tools\codesys\cds.py import` (или `import --tests` для проекта с тестами).
2. Открыть его в IDE: «Файл → Открыть проект» → `build\<имя>.project` (`build\<имя>-tests.project`),
   либо из консоли:

   ```bat
   "%CODESYS_EXE%" --profile="CODESYS V3.5 SP17 Patch 3" --project="%CD%\build\iolistgen.project"
   ```

   Вход в рантайм из IDE: «Онлайн → Логин» с пользователем из `credentials.json`. _Открытие из
   консоли с `--project` здесь не проверялось._
3. Править, сохранить проект, **закрыть IDE** (проект, открытый в IDE, блокирует `cds.py`; через
   таймаут процесс CODESYS будет остановлен).
4. Выгрузить правки в тексты и проверить дифф:

   ```bat
   python tools\codesys\cds.py export            & rem build\<имя>.project -> src\
   python tools\codesys\cds.py export --tests    & rem build\<имя>-tests.project -> src\ и tests\
   git diff --stat
   ```

Защита от потери правок:

- `import` отказывается перезаписывать проект, сохранённый в IDE после последнего
  `import`/`export`, — сначала `export` (или `--force`, если правки не нужны);
- `export` в репозиторий отказывается, если `src/` (`tests/`) изменились после последнего
  `import`/`export` этого проекта: экспорт удаляет файлы, которых нет в проекте. Сравнить можно
  выгрузкой в отдельный каталог: `cds.py export --to build\cmp`; перезапись — `--force`.

Не входит в раскладку (только в IDE, при экспорте не сохраняется — описывайте здесь и в docs):

- [ ] дерево устройств ПЛК210 и конфигурация модулей ввода-вывода; конфигураторы обмена (Modbus, OPC UA);
- [ ] визуализации, графические языки (FBD/LD/SFC/CFC), действия (`ACTION`) — `export` предупреждает о них;
- [ ] **Persistent Variables** (`*.pvl.st`): в SP17 скриптом не создаются. Создайте объект вручную
  («Application → Добавить объект → Persistent Variables» с именем как у файла), затем
  `cds.py import` обновит его текст из файла, а `export` выгрузит обратно.

Задачи и ссылки на библиотеки не правьте в IDE: их создаёт `import` по `tools/codesys/config.json`
(лишние задачи удаляются).

## 7. Релиз: `.project` и `.library`

`.project` и `.library` в git не хранятся — прикладываются к релизу GitHub.

1. `python tools\codesys\cds.py build` — 0 ошибок; `python tools\codesys\cds.py test` — тесты зелёные.
2. `.project`: приложить `build\<имя>.project` (рабочий проект; тестовый — по желанию). Для
   переноса на другую машину удобнее архив: «Файл → Архив проекта → Сохранить/Отправить архив»
   (`.projectarchive`).
3. `.library` (для репозиториев-библиотек): открыть проект в IDE, заполнить «Проект → Информация о
   проекте» (компания, название, версия), выполнить «Сборка → Проверить все объекты пула» и
   сохранить «Файл → Сохранить проект как скомпилированную библиотеку» (`.compiled-library`) или
   «Сохранить проект как…» с типом «Библиотека» (`.library`). _Названия пунктов меню — сверить с
   русской IDE 3.5.17.30; в этом прогоне не выполнялось._
4. Записать в [TEST_REPORT.md](TEST_REPORT.md) итоги (`cds.py report`) и в `CHANGELOG.md` — версию.

## 8. Зеркало на GitVerse или GitFlic

1. Создать пустой репозиторий на GitVerse или GitFlic (без README и лицензии).
2. Добавить его как второй remote и отправить все ветки и теги:

   ```bash
   git remote add mirror <url-зеркала>
   git push mirror --all
   git push mirror --tags
   ```

3. После каждого релиза повторять `git push mirror --all` и `git push mirror --tags`.
