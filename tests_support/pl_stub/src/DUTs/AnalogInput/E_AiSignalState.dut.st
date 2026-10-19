// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 11.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_AiSignalState :
(
    Good := 0,
    UnderRange := 1,
    OverRange := 2,
    FailLow := 3,
    FailHigh := 4,
    ChannelFault := 5,
    NotFinite := 6
) INT;
END_TYPE
