coUnit.TEST('AlarmArrayWrittenWholeKeepsLibraryDefaults');

AssertTrue(Condition := GVL_CfgProject.stLT101Cfg.astAlarm[PL.E_AiAlarm.HH].ePriority = PL.E_AlarmPriority.High,
           Message := 'HH priority from the alarm_priority column');
AssertTrue(Condition := GVL_CfgProject.stLT101Cfg.astAlarm[PL.E_AiAlarm.H].ePriority = PL.E_AlarmPriority.Medium,
           Message := 'H one step lower than the column');
AssertTrue(Condition := GVL_CfgProject.stLT101Cfg.astAlarm[PL.E_AiAlarm.Failure].ePriority
                        = PL.E_AlarmPriority.Medium,
           Message := 'Failure keeps the library default Medium');
AssertTrue(Condition := GVL_CfgProject.stLT101Cfg.astAlarm[PL.E_AiAlarm.OutOfRange].ePriority
                        = PL.E_AlarmPriority.Low,
           Message := 'OutOfRange keeps the library default Low');
AssertTrue(Condition := GVL_CfgProject.stLT101Cfg.astLimit[PL.E_AiAlarm.HH].xEnable, Message := 'HH enabled');
AssertEquals_REAL(Expected := R_LT101_SP_HH,
                  Actual := GVL_CfgProject.stLT101Cfg.astLimit[PL.E_AiAlarm.HH].rSetpoint_eu,
                  Delta := R_EXACT, Message := 'HH setpoint from sp_hh');
AssertEquals_UDINT(Expected := UDI_LT101_ALARMS, Actual := GVL_CfgProject.stLT101Cfg.udiAlarmIdBase,
                   Message := 'udiAlarmIdBase = dev_no * 10');

coUnit.TEST_FINISHED();
