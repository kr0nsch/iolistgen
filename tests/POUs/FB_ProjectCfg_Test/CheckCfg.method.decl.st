// Cfg устройства принята: нет непройденных проверок и бит DEV_STS_CFG_ERROR снят (была корректная Cfg).
METHOD PRIVATE CheckCfg
VAR_INPUT
    sDevice : STRING;   // имя устройства для сообщения
END_VAR
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа
    stCommon : PL.ST_DeviceSts;   // общий заголовок состояния устройства
END_VAR
