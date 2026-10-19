// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_AlarmEventReason :
(
    None := 0,
    Activated := 1,
    Cleared := 2,
    Acked := 3,
    Shelved := 4,
    Unshelved := 5,
    ShelveExpired := 6,
    Suppressed := 7,
    Unsuppressed := 8,
    OosOn := 9,
    OosOff := 10,
    Disabled := 11
) INT;
END_TYPE
