// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 15.2); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK FB_Valve EXTENDS FB_DeviceBase
VAR_INPUT
    xAutoOpen    : BOOL;
    xZso         : BOOL;
    xZsc         : BOOL;
    xTorqueOpen  : BOOL;
    xTorqueClose : BOOL;
    xExtFault    : BOOL;
    xLocal       : BOOL;
    xPowerOk     : BOOL := TRUE;
    wInterlock   : WORD := 16#0000;
    wPermitOpen  : WORD := 16#FFFF;
    wPermitClose : WORD := 16#FFFF;
END_VAR
VAR_IN_OUT
    stCmd    : ST_ValveCmd;
    stRetain : ST_DeviceRetain;
END_VAR
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа (API.md, раздел 0)
    stCfg : ST_ValveCfg;
END_VAR
VAR_OUTPUT
    xQOpen  : BOOL;
    xQClose : BOOL;
    xQCoil  : BOOL;
    xOpened : BOOL;
    xClosed : BOOL;
    stSts   : ST_ValveSts;
END_VAR
