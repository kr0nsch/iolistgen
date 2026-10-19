// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 13.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_MotorCmd :
STRUCT
    stCommon     : ST_DeviceCmd;
    xStart       : BOOL;
    xStop        : BOOL;
    xResetMaint  : BOOL;
    rSpeedSp_pct : REAL;
END_STRUCT
END_TYPE
