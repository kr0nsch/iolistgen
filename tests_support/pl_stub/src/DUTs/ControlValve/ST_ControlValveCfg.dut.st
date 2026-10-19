// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 16.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_ControlValveCfg :
STRUCT
    rOutMin_pct     : REAL := 0.0;
    rOutMax_pct     : REAL := 100.0;
    rRateUp_pctps   : REAL := 0.0;
    rRateDown_pctps : REAL := 0.0;
    rTightShut_pct  : REAL := 0.0;
    xOutInvert      : BOOL := FALSE;
    rSafePos_pct    : REAL := 0.0;
    eFaultAction    : E_CvFaultAction := E_CvFaultAction.Hold;
    xFbUsed         : BOOL := FALSE;
    rDevMax_pct     : REAL := 5.0;
    tDev            : TIME := T#30S;
    xDevIsFault     : BOOL := FALSE;
    wInterlockMask  : WORD := 16#FFFF;
    udiAlarmIdBase  : UDINT := 0;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    astAlarm       : ARRAY[0..GVL_Const.DEV_ALARMS_MAX - 1] OF ST_AlarmCfg := [
            (ePriority := E_AlarmPriority.Low),
            (ePriority := E_AlarmPriority.Low),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None)];
END_STRUCT
END_TYPE
