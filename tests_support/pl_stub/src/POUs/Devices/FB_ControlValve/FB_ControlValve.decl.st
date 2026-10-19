// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 16.2); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK FB_ControlValve EXTENDS FB_DeviceBase
VAR_INPUT
    rPosSpAuto_pct   : REAL;
    rPosFb_pct       : REAL;
    xPosFbValid      : BOOL;
    xLocal           : BOOL;
    wInterlock       : WORD := 16#0000;
    xPositionerFault : BOOL;
END_VAR
VAR_IN_OUT
    stCmd    : ST_ControlValveCmd;
    stRetain : ST_DeviceRetain;
END_VAR
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа (API.md, раздел 0)
    stCfg : ST_ControlValveCfg;
END_VAR
VAR_OUTPUT
    rOut_pct    : REAL;
    rOut_mA     : REAL := 4.0;
    xAutoActive : BOOL;
    stSts       : ST_ControlValveSts;
END_VAR
