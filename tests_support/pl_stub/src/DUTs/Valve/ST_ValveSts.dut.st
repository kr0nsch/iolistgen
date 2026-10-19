// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 15.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_ValveSts :
STRUCT
    stCommon         : ST_DeviceSts;
    eState           : E_ValveState;
    wInterlock       : WORD;
    wPermitMissing   : WORD;
    uiFirstOut       : UINT;
    uiTravelRemain_s : UINT;
    wReserve         : WORD;
    udiCycles        : UDINT;
    udiCyclesMaint   : UDINT;
    rActTime_h       : REAL;
END_STRUCT
END_TYPE
