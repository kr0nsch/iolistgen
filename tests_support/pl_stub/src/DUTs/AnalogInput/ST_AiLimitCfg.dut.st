// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 8.3); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_AiLimitCfg :
STRUCT
    xEnable      : BOOL := FALSE;
    rSetpoint_eu : REAL := 0.0;
    rHyst_eu     : REAL := 0.0;
    tOnDelay     : TIME := T#0S;
    tOffDelay    : TIME := T#0S;
END_STRUCT
END_TYPE
