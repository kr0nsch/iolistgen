// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 5.1: константы без масок битов); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
VAR_GLOBAL CONSTANT
    NE43_FAIL_LOW_MA     : REAL := 3.6;           // NE 43: I <= — отказ, мА
    NE43_MEAS_LOW_MA     : REAL := 3.8;           // NE 43: I < — вне диапазона снизу, мА
    NE43_MEAS_HIGH_MA    : REAL := 20.5;          // NE 43: I > — вне диапазона сверху, мА
    NE43_FAIL_HIGH_MA    : REAL := 21.0;          // NE 43: I >= — отказ, мА
    MA_ZERO              : REAL := 4.0;           // ток нуля шкалы, мА
    MA_SPAN              : REAL := 16.0;          // диапазон тока, мА
    PCT_FULL             : REAL := 100.0;         // 100 %
    REAL_SANE_MAX        : REAL := 1.0E30;        // |x| больше — мусор (перепутан порядок слов Modbus)
    AI_LOWCUT_MAX_PCT    : REAL := 20.0;          // предел rLowCut_pct, %
    REAL_EXP_MASK        : DWORD := 16#7F800000;  // биты экспоненты REAL (F_IsFinite)
    WORD_ALL             : WORD := 16#FFFF;       // все биты слова
    WORD_LOW_BYTE        : WORD := 16#00FF;       // младший байт wStatus
    UINT_MAX             : UINT := 65535;         // предел счётчиков-секунд в Sts
    NS_PER_S             : LREAL := 1.0E9;        // нс в секунде
    MS_PER_S             : LREAL := 1000.0;       // мс в секунде
    S_PER_H              : UDINT := 3600;         // с в часе
    DT_ACCUM_MAX         : LTIME := LTIME#10S;    // больший шаг времени не идёт в счётчики наработки
    DEV_ALARMS_MAX       : UINT := 8;             // слотов тревог в устройстве
    NO_FIRST_OUT         : UINT := 16#FFFF;       // первопричины нет (uiFirstOut)
    STARTS_WINDOW_MAX    : UINT := 30;            // ёмкость окна пусков = максимум uiMaxStartsPerHour
    STARTS_WINDOW        : LTIME := LTIME#1H;     // длина окна пусков
    PID_DFILTER_N_MIN    : REAL := 2.0;           // допустимый rDFilterN, нижняя граница
    PID_DFILTER_N_MAX    : REAL := 50.0;          // допустимый rDFilterN, верхняя граница
    PID_DEADBAND_MAX_PCT : REAL := 10.0;          // предел зоны нечувствительности, %
    VLV_UNSEAT_BYPASS    : TIME := T#2S;          // FB_Valve: страгивание с седла без контроля муфты
    CV_TIGHT_HYST_PCT    : REAL := 1.0;           // FB_ControlValve: гистерезис снятия плотного закрытия, %
    VFD_POWER_UP_DELAY   : TIME := T#10S;         // FB_MotorVfd: готовность ПЧ к обмену после питания
    AI_ALARM_COUNT       : UINT := 6;             // FB_AnalogInput: используемых слотов тревог
    DI_ALARM_COUNT       : UINT := 2;             // FB_DigitalInput: используемых слотов тревог
    MOT_ALARM_COUNT      : UINT := 8;             // FB_Motor: слотов тревог (6–7 формирует только FB_MotorVfd)
    VLV_ALARM_COUNT      : UINT := 7;             // FB_Valve: используемых слотов тревог
    CV_ALARM_COUNT       : UINT := 4;             // FB_ControlValve: используемых слотов тревог
    PID_ALARM_COUNT      : UINT := 1;             // FB_PID: используемых слотов тревог
END_VAR
