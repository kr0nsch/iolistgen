// Назначение: заглушка приложения для проверки сгенерированного кода без CODESYS: источник времени и
//             приёмник тревог, на которые ссылаются опции st-codesys time_source и alarm_sink
// Автор:      kr0nsch
// Версия:     0.1.0
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
VAR_GLOBAL
    itfClock : PL.I_TimeSource;   // в приложении — PL.FB_SystemTime или PL.FB_FakeTime (модель)
    itfSink : PL.I_AlarmSink;     // в приложении — журнал событий тревог
END_VAR
