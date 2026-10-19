// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 17.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_PidCmd :
STRUCT
    stCommon       : ST_DeviceCmd;
    rSp_eu         : REAL;
    rManualOut_pct : REAL;
END_STRUCT
END_TYPE
