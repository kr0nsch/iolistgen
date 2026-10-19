// LT101: колонка alarm_priority меняет слоты 0–3, поэтому генератор пишет массив astAlarm целиком
// (контракт 18.3, правило 3): слоты, которых колонка не касалась, сохраняют умолчания DUT библиотеки.
METHOD PRIVATE AlarmArrayWrittenWholeKeepsLibraryDefaults
