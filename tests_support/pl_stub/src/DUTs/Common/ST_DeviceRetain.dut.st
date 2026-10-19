// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.3); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_DeviceRetain :
STRUCT
    eRemoteMode      : E_DeviceMode := E_DeviceMode.Manual;
    xOutOfService    : BOOL;
    udiOpTime_s      : UDINT;
    udiOpCount       : UDINT;
    udiOpTimeMaint_s : UDINT;
    udiOpCountMaint  : UDINT;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    audiReserve      : ARRAY[0..3] OF UDINT;
END_STRUCT
END_TYPE
