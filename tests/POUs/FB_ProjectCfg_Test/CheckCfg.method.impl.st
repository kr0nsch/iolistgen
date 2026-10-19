AssertEquals_WORD(Expected := W_NO_ERRORS,
                  Actual := stCommon.wCfgErr,
                  Message := CONCAT(sDevice, ': wCfgErr must be 0 for the project Cfg'));
AssertEquals_WORD(Expected := W_NO_ERRORS,
                  Actual := stCommon.wStatus AND PL.GVL_Const.DEV_STS_CFG_ERROR,
                  Message := CONCAT(sDevice, ': DEV_STS_CFG_ERROR must be clear'));
