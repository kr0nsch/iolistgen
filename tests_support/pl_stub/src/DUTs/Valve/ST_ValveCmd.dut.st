// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 15.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_ValveCmd :
STRUCT
    stCommon    : ST_DeviceCmd;
    xOpen       : BOOL;
    xClose      : BOOL;
    xStop       : BOOL;
    xResetMaint : BOOL;
END_STRUCT
END_TYPE
