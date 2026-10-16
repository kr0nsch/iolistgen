// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 15.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_ValveState :
(
    Unknown := 0,
    Closed := 1,
    Opening := 2,
    Open := 3,
    Closing := 4,
    Intermediate := 5,
    Reversing := 6,
    Fault := 7
) INT;
END_TYPE
