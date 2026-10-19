// Назначение: программа запуска юнит-тестов CfUnit (coUnit 1.2.0.0). Объявляет
//             экземпляры наборов тестов (объявление регистрирует набор в coUnit)
//             и каждый цикл вызывает coUnit.RUN(). Назначается задаче только
//             тестового приложения (CODESYS Control Win), не рабочего ПЛК.
// Автор:      kr0nsch
// Версия:     0.2.0
// Документ:   docs/TEST_REPORT.md
PROGRAM PRG_Tests
VAR
    fbProjectCfgTest : FB_ProjectCfg_Test;   // Cfg сгенерированного кода КНС-1 и библиотека plc-process-lib
    // все наборы завершены — флаг для скрипта запуска тестов (read_value)
    xAllFinished : BOOL;
END_VAR
