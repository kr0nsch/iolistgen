// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 4.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
{attribute 'qualified_only'}
TYPE E_ValveAlarm :
(
    FailToOpen := 0,
    FailToClose := 1,
    BothLimits := 2,
    PositionLost := 3,
    TorqueTrip := 4,
    ExtFault := 5,
    InterlockAct := 6
) UINT;
END_TYPE
