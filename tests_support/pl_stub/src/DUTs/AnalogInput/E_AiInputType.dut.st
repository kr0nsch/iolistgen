// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 11.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_AiInputType :
(
    MilliAmp := 0,
    Norm420 := 1,
    Norm01 := 2,
    Eng := 3,
    Raw := 4
) INT;
END_TYPE
