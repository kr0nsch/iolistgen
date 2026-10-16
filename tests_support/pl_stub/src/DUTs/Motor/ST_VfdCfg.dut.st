// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 13.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE ST_VfdCfg :
STRUCT
    rSpeedMin_pct    : REAL := 0.0;
    rSpeedMax_pct    : REAL := 100.0;
    rRampUp_pctps    : REAL := 0.0;
    rRampDown_pctps  : REAL := 0.0;
    xFbFromComm      : BOOL := TRUE;
    xCommLossIsFault : BOOL := TRUE;
    tCommLoss        : TIME := T#3S;
    rSpeedDev_pct    : REAL := 10.0;
    tSpeedDev        : TIME := T#10S;
END_STRUCT
END_TYPE
