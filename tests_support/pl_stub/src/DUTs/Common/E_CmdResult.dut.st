// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_CmdResult :
(
    None := 0,
    Accepted := 1,
    RejectedMode := 2,
    RejectedInterlock := 3,
    RejectedPermit := 4,
    RejectedInhibit := 5,
    RejectedFault := 6,
    RejectedState := 7,
    RejectedNotSupported := 8,
    RejectedCfg := 9,
    SubstExpired := 10
) INT;
END_TYPE
