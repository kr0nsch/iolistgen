// Назначение: заглушка plc-process-lib 1.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.1); не библиотека — тел и внутренних переменных нет
// Автор:      <ИМЯ ФАМИЛИЯ>
// Версия:     1.0.0-rc2 (контракт API.md)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE E_MotorAlarm :
(
    FailToStart := 0,
    FeedbackLost := 1,
    FailToStop := 2,
    UncommandedRun := 3,
    ExtFault := 4,
    InterlockTrip := 5,
    CommLoss := 6,
    SpeedDeviation := 7
) UINT;
END_TYPE
