// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 15.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_ValveCfg :
STRUCT
    eType            : E_ValveType := E_ValveType.Motorized;
    xZsoUsed         : BOOL := TRUE;
    xZscUsed         : BOOL := TRUE;
    tTravel          : TIME := T#60S;
    tLimitFilter     : TIME := T#500MS;
    tReverse         : TIME := T#1S;
    xTorqueUsed      : BOOL := FALSE;
    xCloseOnTorque   : BOOL := FALSE;
    eSafePos         : E_ValveSafePos := E_ValveSafePos.Closed;
    wInterlockMask   : WORD := 16#FFFF;
    wPermitOpenMask  : WORD := 16#FFFF;
    wPermitCloseMask : WORD := 16#FFFF;
    tResetWindow     : TIME := T#3S;
    udiMaintCycles   : UDINT := 0;
    udiAlarmIdBase   : UDINT := 0;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    astAlarm       : ARRAY[0..GVL_Const.DEV_ALARMS_MAX - 1] OF ST_AlarmCfg := [
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None)];
END_STRUCT
END_TYPE
