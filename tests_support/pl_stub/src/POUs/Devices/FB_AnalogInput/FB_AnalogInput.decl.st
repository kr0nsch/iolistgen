// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 11.2); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK FB_AnalogInput EXTENDS FB_DeviceBase
VAR_INPUT
    rIn                  : REAL;
    xChannelFault        : BOOL;
    xSuppressLimitAlarms : BOOL;
END_VAR
VAR_IN_OUT
    stCmd : ST_AnalogInputCmd;
END_VAR
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа (API.md, раздел 0)
    stCfg : ST_AnalogInputCfg;
END_VAR
VAR_OUTPUT
    rValue_eu  : REAL;
    rValue_pct : REAL;
    xValid     : BOOL;
    xHH        : BOOL;
    xH         : BOOL;
    xL         : BOOL;
    xLL        : BOOL;
    stSts      : ST_AnalogInputSts;
END_VAR
