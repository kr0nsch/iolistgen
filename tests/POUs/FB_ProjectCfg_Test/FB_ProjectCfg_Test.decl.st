// Назначение: набор тестов CfUnit (coUnit 1.2.0.0) для кода, сгенерированного iolistgen по примеру КНС-1
//             (src/GVLs/Generated, src/POUs/Generated): Cfg проекта каждого устройства — уставки перечня,
//             params и выводы из состава — принимает CheckConfig библиотеки plc-process-lib 1.0.0 (зеркало
//             CheckConfig валидатора совпадает с ФБ); инициализаторы Cfg дают значения перечня, в том числе
//             массивы тревог целиком; «применить уставки проекта» копирует Cfg и не трогает Retain.
//             Экземпляр объявлен в PRG_Tests: объявление регистрирует набор в coUnit.
// Автор:      kr0nsch
// Версия:     0.2.0
// Документ:   docs/TEST_REPORT.md
FUNCTION_BLOCK FB_ProjectCfg_Test EXTENDS coUnit.FB_TestSuite
VAR CONSTANT
    W_NO_ERRORS        : WORD := 16#0000;   // wCfgErr: все проверки Cfg пройдены
    T_MIN_STOP_PROJECT : TIME := T#30S;     // P101: tMinStop из params перечня КНС-1
    T_MIN_STOP_HMI     : TIME := T#45S;     // P101: уставка, изменённая наладчиком с HMI
    UDI_OP_COUNT       : UDINT := 7;        // P101: операций в Retain — «применить уставки» их не трогает
    UDI_LIC101_ALARMS  : UDINT := 1040;     // LIC101: dev_no 104 · 10
    UDI_LT101_ALARMS   : UDINT := 1010;     // LT101: dev_no 101 · 10
    R_LIC101_PV_MAX    : REAL := 5.0;       // LIC101: range_max перечня → rPvMax_eu
    R_LIC101_SP_MIN    : REAL := 1.0;       // LIC101: rSpMin_eu из params
    R_LIC101_SP_MAX    : REAL := 3.5;       // LIC101: rSpMax_eu из params
    R_LT101_SP_HH      : REAL := 4.0;       // LT101: sp_hh перечня
    R_EXACT            : REAL := 0.0;       // значения из инициализаторов — точное сравнение
END_VAR
