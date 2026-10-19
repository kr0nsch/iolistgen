// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 16.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_ControlValveSts :
STRUCT
    stCommon       : ST_DeviceSts;
    rPosSp_pct     : REAL;
    rOut_pct       : REAL;
    rOut_mA        : REAL;
    rPosFb_pct     : REAL;
    rDeviation_pct : REAL;
    wInterlock     : WORD;
    uiFirstOut     : UINT;
END_STRUCT
END_TYPE
