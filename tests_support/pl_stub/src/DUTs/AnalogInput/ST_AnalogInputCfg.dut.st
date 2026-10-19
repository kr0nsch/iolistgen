// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 11.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_AnalogInputCfg :
STRUCT
    eInput         : E_AiInputType := E_AiInputType.MilliAmp;
    rRangeLo_eu    : REAL := 0.0;
    rRangeHi_eu    : REAL := 100.0;
    rRawLo_cnt     : REAL := 0.0;
    rRawHi_cnt     : REAL := 0.0;
    xSqrt          : BOOL := FALSE;
    rLowCut_pct    : REAL := 0.0;
    tFilter        : TIME := T#0S;
    tFailDelay     : TIME := T#2S;
    eFailValue     : E_AiFailValue := E_AiFailValue.HoldLast;
    rFailValue_eu  : REAL := 0.0;
    xLimitsOnFail  : BOOL := FALSE;
    xClamp         : BOOL := FALSE;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    astLimit       : ARRAY[0..3] OF ST_AiLimitCfg;
    tSubstMax      : TIME := T#8H;
    udiAlarmIdBase : UDINT := 0;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    astAlarm       : ARRAY[0..GVL_Const.DEV_ALARMS_MAX - 1] OF ST_AlarmCfg := [
            (ePriority := E_AlarmPriority.High),
            (ePriority := E_AlarmPriority.Low),
            (ePriority := E_AlarmPriority.Low),
            (ePriority := E_AlarmPriority.High),
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.Low),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None)];
END_STRUCT
END_TYPE
