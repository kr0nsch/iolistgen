// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 12.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_DigitalInputCfg :
STRUCT
    xInvert        : BOOL := FALSE;
    tOnDelay       : TIME := T#0S;
    tOffDelay      : TIME := T#0S;
    eFailValue     : E_DiFailValue := E_DiFailValue.HoldLast;
    xAlarmOnTrue   : BOOL := TRUE;
    tSubstMax      : TIME := T#8H;
    udiAlarmIdBase : UDINT := 0;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    astAlarm       : ARRAY[0..GVL_Const.DEV_ALARMS_MAX - 1] OF ST_AlarmCfg := [
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None)];
END_STRUCT
END_TYPE
