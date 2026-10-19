// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 17.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_PidSts :
STRUCT
    stCommon     : ST_DeviceSts;
    rSpTarget_eu : REAL;
    rSp_eu       : REAL;
    rPv_eu       : REAL;
    rErr_pct     : REAL;
    rOut_pct     : REAL;
    rP_pct       : REAL;
    rI_pct       : REAL;
    rD_pct       : REAL;
    rDt_ms       : REAL;
END_STRUCT
END_TYPE
