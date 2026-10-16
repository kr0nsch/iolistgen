// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 13.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_MotorSts :
STRUCT
    stCommon          : ST_DeviceSts;
    eState            : E_MotorState;
    wInterlock        : WORD;
    wPermitMissing    : WORD;
    uiFirstOut        : UINT;
    uiInhibitRemain_s : UINT;
    uiStartsLastHour  : UINT;
    rRunTime_h        : REAL;
    udiStarts         : UDINT;
    rRunTimeMaint_h   : REAL;
    udiStartsMaint    : UDINT;
    rSpeedRef_pct     : REAL;
    rSpeedAct_pct     : REAL;
    udiRunCurrent_s   : UDINT;
END_STRUCT
END_TYPE
