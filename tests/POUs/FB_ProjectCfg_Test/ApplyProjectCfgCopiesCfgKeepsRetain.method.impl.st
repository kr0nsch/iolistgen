coUnit.TEST('ApplyProjectCfgCopiesCfgKeepsRetain');

GVL_Persist.stP101Cfg.tMinStop := T_MIN_STOP_HMI;
GVL_Persist.stP101Retain.udiOpCount := UDI_OP_COUNT;
PRG_ApplyProjectCfg();
AssertEquals_TIME(Expected := T_MIN_STOP_PROJECT, Actual := GVL_Persist.stP101Cfg.tMinStop,
                  Message := 'tMinStop back to the project value');
AssertEquals_UDINT(Expected := UDI_OP_COUNT, Actual := GVL_Persist.stP101Retain.udiOpCount,
                   Message := 'Retain must not change');

coUnit.TEST_FINISHED();
