coUnit.TEST('PidCfgComesFromIoList');

AssertTrue(Condition := GVL_CfgProject.stLIC101Cfg.eAction = PL.E_PidAction.Direct,
           Message := 'eAction from params');
AssertTrue(Condition := GVL_CfgProject.stLIC101Cfg.xUseOutAct, Message := 'xUseOutAct from params');
AssertEquals_REAL(Expected := R_LIC101_PV_MAX, Actual := GVL_CfgProject.stLIC101Cfg.rPvMax_eu,
                  Delta := R_EXACT, Message := 'rPvMax_eu from range_max');
AssertEquals_REAL(Expected := R_LIC101_SP_MIN, Actual := GVL_CfgProject.stLIC101Cfg.rSpMin_eu,
                  Delta := R_EXACT, Message := 'rSpMin_eu from params');
AssertEquals_REAL(Expected := R_LIC101_SP_MAX, Actual := GVL_CfgProject.stLIC101Cfg.rSpMax_eu,
                  Delta := R_EXACT, Message := 'rSpMax_eu from params');
AssertEquals_UDINT(Expected := UDI_LIC101_ALARMS, Actual := GVL_CfgProject.stLIC101Cfg.udiAlarmIdBase,
                   Message := 'udiAlarmIdBase = dev_no * 10');
AssertTrue(Condition := GVL_CfgProject.stLIC101Cfg.astAlarm[PL.E_PidAlarm.PvInvalid].ePriority
                        = PL.E_AlarmPriority.None,
           Message := 'PVF disabled by alarm_priority None');

coUnit.TEST_FINISHED();
