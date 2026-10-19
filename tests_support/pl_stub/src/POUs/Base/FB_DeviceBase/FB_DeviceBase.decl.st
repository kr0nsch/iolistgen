// Назначение: заглушка plc-process-lib 1.0.0 для проверки типов сгенерированного кода без CODESYS
//             (API.md, раздел 9.1); не библиотека — тел и внутренних переменных нет
// Автор:      kr0nsch
// Версия:     1.0.0 (выпуск библиотеки)
// Документ:   docs/GENERATORS.md, раздел «Проверка ST без CODESYS»
FUNCTION_BLOCK ABSTRACT FB_DeviceBase
VAR_INPUT
    itfTime : I_TimeSource;   // источник времени; 0 — встроенный FB_SystemTime
END_VAR
