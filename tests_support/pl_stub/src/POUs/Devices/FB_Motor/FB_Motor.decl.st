// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 13.2); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK FB_Motor EXTENDS FB_DeviceBase
VAR_INPUT
    xAutoRun   : BOOL;
    xFbRun     : BOOL;
    xExtFault  : BOOL;
    xLocal     : BOOL;
    xPowerOk   : BOOL := TRUE;
    wInterlock : WORD := 16#0000;
    wPermit    : WORD := 16#FFFF;
END_VAR
VAR_IN_OUT
    stCmd    : ST_MotorCmd;
    stRetain : ST_DeviceRetain;
END_VAR
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа (API.md, раздел 0)
    stCfg : ST_MotorCfg;
END_VAR
VAR_OUTPUT
    xQRun    : BOOL;
    xQReset  : BOOL;
    xRunning : BOOL;
    stSts    : ST_MotorSts;
END_VAR
