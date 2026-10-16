// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 12.2); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK FB_DigitalInput EXTENDS FB_DeviceBase
VAR_INPUT
    xIn           : BOOL;
    xChannelFault : BOOL;
END_VAR
VAR_IN_OUT
    stCmd : ST_DigitalInputCmd;
END_VAR
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа (API.md, раздел 0)
    stCfg : ST_DigitalInputCfg;
END_VAR
VAR_OUTPUT
    xValue : BOOL;
    xValid : BOOL;
    stSts  : ST_DigitalInputSts;
END_VAR
