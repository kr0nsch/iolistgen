// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_DeviceType :
(
    None := 0,
    AnalogInput := 1,
    DigitalInput := 2,
    Motor := 3,
    MotorVfd := 4,
    Valve := 5,
    ControlValve := 6,
    Pid := 7
) INT;
END_TYPE
