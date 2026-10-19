// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 17.2); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK FB_PID EXTENDS FB_DeviceBase
VAR_INPUT
    rPv_eu      : REAL;
    xPvValid    : BOOL;
    xSpExt      : BOOL;
    rSpExt_eu   : REAL;
    xTrack      : BOOL;
    rTrack_pct  : REAL;
    rOutAct_pct : REAL;
END_VAR
VAR_IN_OUT
    stCmd    : ST_PidCmd;
    stRetain : ST_DeviceRetain;
END_VAR
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа (API.md, раздел 0)
    stCfg : ST_PidCfg;
END_VAR
VAR_OUTPUT
    rOut_pct : REAL;
    xSatHigh : BOOL;
    xSatLow  : BOOL;
    stSts    : ST_PidSts;
END_VAR
