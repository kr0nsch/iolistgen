// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.4); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_AlarmEvent :
STRUCT
    udiId     : UDINT;
    ePriority : E_AlarmPriority;
    eOldState : E_AlarmState;
    eNewState : E_AlarmState;
    eReason   : E_AlarmEventReason;
    ltTime    : LTIME;
    rValue    : REAL;
END_STRUCT
END_TYPE
