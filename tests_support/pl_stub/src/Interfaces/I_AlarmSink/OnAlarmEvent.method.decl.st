METHOD OnAlarmEvent : BOOL
VAR_IN_OUT CONSTANT
    // lint:allow STL007 VAR_IN_OUT CONSTANT — ссылка только для чтения, а не константа (API.md, раздел 0)
    stEvent : ST_AlarmEvent;
END_VAR
