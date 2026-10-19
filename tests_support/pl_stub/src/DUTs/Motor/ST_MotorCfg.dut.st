// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 13.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_MotorCfg :
STRUCT
    xFbUsed            : BOOL := TRUE;
    tFbStart           : TIME := T#5S;
    tFbStop            : TIME := T#5S;
    tFbLossFilter      : TIME := T#500MS;
    tExtFaultFilter    : TIME := T#200MS;
    tMinRun            : TIME := T#0S;
    tMinStop           : TIME := T#0S;
    uiMaxStartsPerHour : UINT := 0;
    tResetWindow       : TIME := T#3S;
    tResetPulse        : TIME := T#1S;
    wInterlockMask     : WORD := 16#FFFF;
    wPermitMask        : WORD := 16#FFFF;
    udiMaintInterval_h : UDINT := 0;
    udiMaintStarts     : UDINT := 0;
    stVfd              : ST_VfdCfg;
    udiAlarmIdBase     : UDINT := 0;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    astAlarm       : ARRAY[0..GVL_Const.DEV_ALARMS_MAX - 1] OF ST_AlarmCfg := [
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.High),
            (ePriority := E_AlarmPriority.High),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Low)];
END_STRUCT
END_TYPE
