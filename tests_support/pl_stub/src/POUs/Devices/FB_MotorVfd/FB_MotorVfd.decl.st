// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 14.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK FB_MotorVfd EXTENDS FB_Motor
VAR_INPUT
    rSpeedSpAuto_pct : REAL;
    xCommOk          : BOOL := TRUE;
    xVfdRunning      : BOOL;
    xVfdReady        : BOOL := TRUE;
    xVfdFault        : BOOL;
    rSpeedAct_pct    : REAL;
END_VAR
VAR_OUTPUT
    rSpeedRef_pct    : REAL;
    xSpeedAutoActive : BOOL;
END_VAR
