coUnit.TEST('AllDevicesProjectCfgPassCheckConfig');

PRG_ApplyProjectCfg();   // Cfg — уставки проекта, как после команды HMI «применить уставки проекта»
PRG_Devices();           // вызов устройств: CheckConfig проверяет Cfg на первом вызове
GVL_Devices.fbLIC101(stCmd := GVL_Hmi.stLIC101Cmd,
                     stCfg := GVL_Persist.stLIC101Cfg,
                     stRetain := GVL_Persist.stLIC101Retain);

CheckCfg(sDevice := 'P101', stCommon := GVL_Devices.fbP101.stSts.stCommon);
CheckCfg(sDevice := 'P102', stCommon := GVL_Devices.fbP102.stSts.stCommon);
CheckCfg(sDevice := 'P103', stCommon := GVL_Devices.fbP103.stSts.stCommon);
CheckCfg(sDevice := 'V1', stCommon := GVL_Devices.fbV1.stSts.stCommon);
CheckCfg(sDevice := 'LT101', stCommon := GVL_Devices.fbLT101.stSts.stCommon);
CheckCfg(sDevice := 'LS102', stCommon := GVL_Devices.fbLS102.stSts.stCommon);
CheckCfg(sDevice := 'LS103', stCommon := GVL_Devices.fbLS103.stSts.stCommon);
CheckCfg(sDevice := 'LIC101', stCommon := GVL_Devices.fbLIC101.stSts.stCommon);
CheckCfg(sDevice := 'IT111', stCommon := GVL_Devices.fbIT111.stSts.stCommon);
CheckCfg(sDevice := 'TS112', stCommon := GVL_Devices.fbTS112.stSts.stCommon);
CheckCfg(sDevice := 'MS113', stCommon := GVL_Devices.fbMS113.stSts.stCommon);
CheckCfg(sDevice := 'IT121', stCommon := GVL_Devices.fbIT121.stSts.stCommon);
CheckCfg(sDevice := 'TS122', stCommon := GVL_Devices.fbTS122.stSts.stCommon);
CheckCfg(sDevice := 'MS123', stCommon := GVL_Devices.fbMS123.stSts.stCommon);
CheckCfg(sDevice := 'IT131', stCommon := GVL_Devices.fbIT131.stSts.stCommon);
CheckCfg(sDevice := 'TS132', stCommon := GVL_Devices.fbTS132.stSts.stCommon);
CheckCfg(sDevice := 'MS133', stCommon := GVL_Devices.fbMS133.stSts.stCommon);
CheckCfg(sDevice := 'PT201', stCommon := GVL_Devices.fbPT201.stSts.stCommon);
CheckCfg(sDevice := 'FT202', stCommon := GVL_Devices.fbFT202.stSts.stCommon);
CheckCfg(sDevice := 'LS203', stCommon := GVL_Devices.fbLS203.stSts.stCommon);
CheckCfg(sDevice := 'ES301', stCommon := GVL_Devices.fbES301.stSts.stCommon);
CheckCfg(sDevice := 'YS302', stCommon := GVL_Devices.fbYS302.stSts.stCommon);
CheckCfg(sDevice := 'YS303', stCommon := GVL_Devices.fbYS303.stSts.stCommon);
CheckCfg(sDevice := 'AT401', stCommon := GVL_Devices.fbAT401.stSts.stCommon);
CheckCfg(sDevice := 'AT402', stCommon := GVL_Devices.fbAT402.stSts.stCommon);
CheckCfg(sDevice := 'TT403', stCommon := GVL_Devices.fbTT403.stSts.stCommon);
CheckCfg(sDevice := 'ZS404', stCommon := GVL_Devices.fbZS404.stSts.stCommon);
CheckCfg(sDevice := 'YS405', stCommon := GVL_Devices.fbYS405.stSts.stCommon);
CheckCfg(sDevice := 'HS501', stCommon := GVL_Devices.fbHS501.stSts.stCommon);
CheckCfg(sDevice := 'HS502', stCommon := GVL_Devices.fbHS502.stSts.stCommon);

coUnit.TEST_FINISHED();
