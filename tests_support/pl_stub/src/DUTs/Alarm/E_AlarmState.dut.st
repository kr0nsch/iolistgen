// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_AlarmState :
(
    Normal := 0,
    ActiveUnack := 1,
    ActiveAck := 2,
    RtnUnack := 3,
    Shelved := 4,
    SuppressedByDesign := 5,
    OutOfService := 6
) INT;
END_TYPE
