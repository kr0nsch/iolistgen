// 1. Задание оператора регулятора уровня: после старта ПЛК — из энергонезависимой памяти
//    (GVL_Persist.rLIC101SpOper_m из persist_extra), дальше каждое изменение с HMI сохраняется туда же
IF NOT xSpRestored THEN
    GVL_Hmi.stLIC101Cmd.rSp_eu := GVL_Persist.rLIC101SpOper_m;
    xSpRestored := TRUE;
END_IF

// 2. Регулятор уровня LIC101: PV — уровнемер LT101, слежение и фактический выход — задание ведущего
//    насоса после его ограничений и рампы (с прошлого цикла). Насос не в Auto или стоит — регулятор следит
xLeadAuto := GVL_Devices.fbP101.xSpeedAutoActive;
GVL_Devices.fbLIC101(
    rPv_eu      := GVL_Devices.fbLT101.rValue_eu,
    xPvValid    := GVL_Devices.fbLT101.xValid,
    xTrack      := NOT xLeadAuto,
    rTrack_pct  := GVL_Devices.fbP101.rSpeedRef_pct,
    rOutAct_pct := GVL_Devices.fbP101.rSpeedRef_pct,
    stCmd       := GVL_Hmi.stLIC101Cmd,
    stCfg       := GVL_Persist.stLIC101Cfg,
    stRetain    := GVL_Persist.stLIC101Retain);
GVL_Devices.fbP101.rSpeedSpAuto_pct := GVL_Devices.fbLIC101.rOut_pct;
GVL_Persist.rLIC101SpOper_m := GVL_Hmi.stLIC101Cmd.rSp_eu;

// 3. Устройства перечня сигналов: вызовы и привязки сгенерированы iolistgen (src/POUs/Generated)
PRG_Devices();
