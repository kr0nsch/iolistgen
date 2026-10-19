// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 17.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_PidCfg :
STRUCT
    eAction        : E_PidAction := E_PidAction.Reverse;
    rKp            : REAL := 1.0;
    rTi_s          : REAL := 30.0;
    rTd_s          : REAL := 0.0;
    rDFilterN      : REAL := 10.0;
    rTt_s          : REAL := 0.0;
    rPvMin_eu      : REAL := 0.0;
    rPvMax_eu      : REAL := 100.0;
    rSpMin_eu      : REAL := 0.0;
    rSpMax_eu      : REAL := 100.0;
    rSpRate_ups    : REAL := 0.0;
    rOutMin_pct    : REAL := 0.0;
    rOutMax_pct    : REAL := 100.0;
    rOutRate_pctps : REAL := 0.0;
    rDeadband_pct  : REAL := 0.0;
    tSample        : TIME := T#0S;
    tDtMax         : TIME := T#2S;
    ePvFailAction  : E_PidPvFailAction := E_PidPvFailAction.Hold;
    rSafeOut_pct   : REAL := 0.0;
    xSpTrackPv     : BOOL := FALSE;
    xUseOutAct     : BOOL := FALSE;
    udiAlarmIdBase : UDINT := 0;
    // lint:allow STL007 имя массива по контракту API.md (префикс a + тип элемента)
    astAlarm       : ARRAY[0..GVL_Const.DEV_ALARMS_MAX - 1] OF ST_AlarmCfg := [
            (ePriority := E_AlarmPriority.Medium),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None),
            (ePriority := E_AlarmPriority.None)];
END_STRUCT
END_TYPE
