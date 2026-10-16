// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.2); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_DeviceSts :
STRUCT
    wStatus     : WORD;
    wFault      : WORD;
    wWarning    : WORD;
    wCfgErr     : WORD;
    eMode       : E_DeviceMode := E_DeviceMode.Manual;
    eNe107      : E_Ne107Status := E_Ne107Status.CheckFunction;
    eCmdResult  : E_CmdResult := E_CmdResult.None;
    uiCmdSeq    : UINT;
    wAlmActive  : WORD;
    wAlmUnack   : WORD;
    wAlmShelved : WORD;
    ePrioUnack  : E_AlarmPriority := E_AlarmPriority.None;
    eDevType    : E_DeviceType := E_DeviceType.None;
    wReserve    : WORD;
END_STRUCT
END_TYPE
