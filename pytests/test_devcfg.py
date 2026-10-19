"""Cfg устройства: колонки, params, выводы из состава устройства и зеркало CheckConfig."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from iolistgen.enums import DeviceType, Role
from iolistgen.model import Device
from iolistgen.validate import CheckResult
from pytests.helpers import ai, codes, di, motor_vfd, pid, signal, valve

Check = Callable[..., CheckResult]


def only_device(result: CheckResult, ident: str) -> Device:
    assert result.model is not None, [d.render() for d in result.diagnostics]
    return result.model.device(ident)


def test_analog_input_columns_go_to_cfg(check_rows: Check) -> None:
    rows = [ai(sp_hh=4.5, sp_h=4, sp_l=1, sp_ll=0.5, delay_on_s=2, delay_off_s="500 мс", alarm_priority="High")]
    cfg = only_device(check_rows(rows), "LT101").cfg
    assert cfg.value("rRangeHi_eu") == 5.0
    assert cfg.value("udiAlarmIdBase") == 10
    assert [cfg.value(f"astLimit[{i}].xEnable") for i in range(4)] == [True] * 4
    assert [cfg.value(f"astLimit[{i}].rSetpoint_eu") for i in range(4)] == [4.5, 4.0, 1.0, 0.5]
    assert cfg.value("astLimit[0].tOnDelay") == 2000
    assert cfg.value("astLimit[3].tOffDelay") == 500
    assert [cfg.value(f"astAlarm[{i}].ePriority") for i in range(6)] == [
        "High",
        "Medium",
        "Medium",
        "High",
        "Medium",
        "Low",
    ]
    assert cfg.get("rRangeHi_eu").origin == "column"


def test_analog_delay_only_for_enabled_limits(check_rows: Check) -> None:
    cfg = only_device(check_rows([ai(sp_hh=4.5, delay_on_s=2)]), "LT101").cfg
    assert cfg.value("astLimit[0].tOnDelay") == 2000
    assert cfg.value("astLimit[1].tOnDelay") == 0
    assert cfg.value("astLimit[1].xEnable") is False


@pytest.mark.parametrize(
    ("priority", "levels"),
    [
        ("Low", ["Low", "Low", "Low", "Low"]),
        ("Critical", ["Critical", "High", "High", "Critical"]),
        ("0", ["None"] * 4),
    ],
)
def test_analog_priority_steps_down(check_rows: Check, priority: str, levels: list[str]) -> None:
    cfg = only_device(check_rows([ai(alarm_priority=priority)]), "LT101").cfg
    assert [cfg.value(f"astAlarm[{i}].ePriority") for i in range(4)] == levels


def test_digital_input_priority_and_delays(check_rows: Check) -> None:
    cfg = only_device(check_rows([di(alarm_priority="высокий", delay_on_s=1, delay_off_s=3)]), "LS101").cfg
    assert cfg.value("astAlarm[0].ePriority") == "High"
    assert cfg.value("astAlarm[1].ePriority") == "Medium"
    assert (cfg.value("tOnDelay"), cfg.value("tOffDelay")) == (1000, 3000)


def test_motor_priority_replaces_only_medium_slots(check_rows: Check) -> None:
    rows = motor_vfd()
    rows[0] = {**rows[0], "alarm_priority": "Low", "delay_on_s": 10, "delay_off_s": 20}
    cfg = only_device(check_rows(rows), "P101").cfg
    priorities = [cfg.value(f"astAlarm[{i}].ePriority") for i in range(8)]
    assert priorities == ["Low", "Low", "High", "High", "Low", "None", "Low", "Low"]
    assert (cfg.value("tFbStart"), cfg.value("tFbStop")) == (10_000, 20_000)
    assert cfg.value("udiAlarmIdBase") == 110


def test_motor_priority_leaves_vfd_slots_of_shared_cfg(check_rows: Check) -> None:
    """Регрессия: у Motor (Cfg общая с MotorVfd) колонка не меняла слот 6 «потеря связи с ПЧ»."""
    rows = [
        {
            "tag": "V1_RUN",
            "description": "Вентилятор: команда «Работа»",
            "signal_type": "DO",
            "device": "V1",
            "device_type": "Motor",
            "dev_no": 14,
            "role": "CMD_RUN",
            "alarm_priority": "Low",
        }
    ]
    device = only_device(check_rows(rows), "V1")
    priorities = [device.cfg.value(f"astAlarm[{i}].ePriority") for i in range(8)]
    assert priorities == ["Low", "Low", "High", "High", "Low", "None", "Medium", "Low"]
    assert [slot.index for slot in device.spec.alarm_slots] == [0, 1, 2, 3, 4, 5]


def test_motor_without_feedback_disables_supervision(check_rows: Check) -> None:
    rows = [
        {
            "tag": "M201",
            "description": "Мешалка",
            "signal_type": "DO",
            "device_type": "Motor",
            "dev_no": 31,
            "role": "CMD_RUN",
        }
    ]
    cfg = only_device(check_rows(rows), "M201").cfg
    assert cfg.value("xFbUsed") is False
    assert cfg.get("xFbUsed").origin == "inferred"


def test_vfd_feedback_from_status_word_keeps_supervision(check_rows: Check) -> None:
    cfg = only_device(check_rows(motor_vfd()), "P101").cfg
    assert cfg.value("xFbUsed") is True
    rows = motor_vfd()
    rows[0] = {**rows[0], "params": "stVfd.xFbFromComm=FALSE"}
    cfg = only_device(check_rows(rows), "P101").cfg
    assert cfg.value("xFbUsed") is False


def test_vfd_params_are_typed(check_rows: Check) -> None:
    rows = motor_vfd()
    rows[0] = {
        **rows[0],
        "params": "tMinStop=T#30S; uiMaxStartsPerHour=6; stVfd.rSpeedMin_pct=30.0; wPermitMask=16#0001",
    }
    device = only_device(check_rows(rows), "P101")
    assert device.cfg.value("tMinStop") == 30_000
    assert device.cfg.value("uiMaxStartsPerHour") == 6
    assert device.cfg.value("stVfd.rSpeedMin_pct") == 30.0
    assert device.cfg.value("wPermitMask") == 1
    assert [p.path for p in device.params] == ["tMinStop", "uiMaxStartsPerHour", "stVfd.rSpeedMin_pct", "wPermitMask"]
    assert device.params[0].literal() == "T#30S"


def test_valve_inference(check_rows: Check) -> None:
    rows = [*valve(), signal("FV101", "TQO", "TQO", "DI"), signal("FV101", "TQC", "TQC", "DI")]
    rows = [row for row in rows if row["role"] != "ZSO"]
    cfg = only_device(check_rows(rows), "FV101").cfg
    assert cfg.value("eType") == "Motorized"
    assert cfg.value("xZsoUsed") is False
    assert cfg.value("xZscUsed") is True
    assert cfg.value("xTorqueUsed") is True


def test_solenoid_valve(check_rows: Check) -> None:
    rows = [
        {
            "tag": "XV101",
            "description": "Клапан промывки",
            "signal_type": "DO",
            "device_type": "Valve",
            "dev_no": 22,
            "role": "CMD_COIL",
            "params": "eType=SolenoidEtc",
        }
    ]
    cfg = only_device(check_rows(rows), "XV101").cfg
    assert cfg.value("eType") == "SolenoidEtc"
    assert (cfg.value("xZsoUsed"), cfg.value("xZscUsed")) == (False, False)


def test_control_valve_feedback_link(check_rows: Check) -> None:
    rows = [
        {
            "tag": "FCV101",
            "description": "Регулирующий клапан",
            "signal_type": "AO",
            "device_type": "ControlValve",
            "dev_no": 41,
            "role": "POS_OUT",
            "units": "%",
            "link_fb": "zt101",
            "delay_on_s": 20,
        },
        ai("ZT101", 42, units="%", range_max=100),
    ]
    device = only_device(check_rows(rows), "FCV101")
    assert device.link_fb == "ZT101"
    assert device.cfg.value("xFbUsed") is True
    assert device.cfg.value("tDev") == 20_000


@pytest.mark.parametrize(
    ("data_type", "params", "expected"),
    [("REAL", "", "Eng"), ("INT", "rRawLo_cnt=0.0; rRawHi_cnt=10000.0", "Raw"), ("INT", "eInput=Eng", "Eng")],
)
def test_modbus_pv_input_type(check_rows: Check, data_type: str, params: str, expected: str) -> None:
    row = ai("TT101", 7, signal_type="MB", mb_slave=1, mb_func=4, mb_reg=0, mb_type=data_type, params=params)
    if data_type == "REAL":
        row["mb_order"] = "HL"
    cfg = only_device(check_rows([row]), "TT101").cfg
    assert cfg.value("eInput") == expected


def test_modbus_integer_pv_needs_raw_range(check_rows: Check) -> None:
    row = ai("TT101", 7, signal_type="MB", mb_slave=1, mb_func=4, mb_reg=0, mb_type="UINT")
    result = check_rows([row])
    assert codes(result) == ["IOL507"]
    assert "AI_CFG_RAW_RANGE" in result.diagnostics[0].message


def test_modbus_pv_rejects_milliamp(check_rows: Check) -> None:
    row = ai("TT101", 7, signal_type="MB", mb_slave=1, mb_func=4, mb_reg=0, mb_type="UINT", params="eInput=MilliAmp")
    assert "IOL509" in codes(check_rows([row]))


VFD = DeviceType.MOTOR_VFD


def vfd_params(params: str) -> list[dict[str, object]]:
    rows = motor_vfd()
    rows[0] = {**rows[0], "params": params}
    return rows


def cv_params(params: str) -> list[dict[str, object]]:
    return [
        {
            "tag": "FCV101",
            "description": "Регулирующий клапан",
            "signal_type": "AO",
            "device_type": "ControlValve",
            "dev_no": 41,
            "role": "POS_OUT",
            "units": "%",
            "params": params,
            "link_fb": "ZT101",
        },
        ai("ZT101", 42, units="%", range_max=100),
    ]


def valve_params(params: str) -> list[dict[str, object]]:
    rows = valve()
    rows[0] = {**rows[0], "params": params}
    return rows


@pytest.mark.parametrize(
    ("rows", "bit"),
    [
        ([ai(sp_h=4, params="astLimit[1].rHyst_eu=-0.1")], "AI_CFG_HYST"),
        ([ai(sp_h=4, params="astLimit[1].rHyst_eu=5.0")], "AI_CFG_HYST"),
        ([ai(params="rLowCut_pct=25.0")], "AI_CFG_LOW_CUT"),
        ([ai(params="eInput=Raw")], "AI_CFG_RAW_RANGE"),
        (vfd_params("tFbStart=T#0S"), "MOT_CFG_FB_TIMES"),
        (vfd_params("uiMaxStartsPerHour=31"), "MOT_CFG_STARTS_LIMIT"),
        (vfd_params("tResetPulse=T#5S"), "MOT_CFG_RESET"),
        (vfd_params("stVfd.rSpeedMin_pct=60.0; stVfd.rSpeedMax_pct=50.0"), "MOT_CFG_VFD_SPEED_LIMITS"),
        (vfd_params("stVfd.rRampUp_pctps=-1.0"), "MOT_CFG_VFD_RAMP"),
        (vfd_params("stVfd.tCommLoss=T#0S"), "MOT_CFG_VFD_COMM"),
        (vfd_params("stVfd.tSpeedDev=T#0S"), "MOT_CFG_VFD_SPEED_DEV"),
        (valve_params("tTravel=T#0S"), "VLV_CFG_TRAVEL"),
        (valve_params("tReverse=T#0S"), "VLV_CFG_REVERSE"),
        (valve_params("tResetWindow=T#0S"), "VLV_CFG_RESET"),
        (valve_params("xCloseOnTorque=TRUE"), "VLV_CFG_TORQUE"),
        (cv_params("rOutMin_pct=50.0; rOutMax_pct=40.0"), "CV_CFG_LIMITS"),
        (cv_params("rRateUp_pctps=-2.0"), "CV_CFG_RATE"),
        (cv_params("rSafePos_pct=120.0"), "CV_CFG_SAFE_POS"),
        (cv_params("rDevMax_pct=0.0"), "CV_CFG_DEVIATION"),
        (cv_params("rTightShut_pct=100.0"), "CV_CFG_TIGHT_SHUT"),
    ],
)
def test_check_config_mirror(check_rows: Check, rows: list[dict[str, object]], bit: str) -> None:
    result = check_rows(rows)
    mirror = [item for item in result.diagnostics if item.code == "IOL507"]
    assert mirror, [d.render() for d in result.diagnostics]
    assert any(bit in item.message for item in mirror)
    assert mirror[0].source is not None and mirror[0].source.header == "params"


def test_solenoid_specific_mirror_checks(check_rows: Check) -> None:
    rows = [
        {
            "tag": "XV101",
            "description": "Клапан",
            "signal_type": "DO",
            "device_type": "Valve",
            "dev_no": 22,
            "role": "CMD_COIL",
            "params": "eType=SolenoidEto; eSafePos=Stay; xTorqueUsed=TRUE",
        }
    ]
    messages = " ".join(item.message for item in check_rows(rows).diagnostics)
    assert "VLV_CFG_SAFE_POS" in messages
    assert "VLV_CFG_TORQUE" in messages


def test_zero_start_delay_points_to_delay_column(check_rows: Check) -> None:
    rows = motor_vfd()
    rows[0] = {**rows[0], "delay_on_s": 0}
    result = check_rows(rows)
    assert codes(result) == ["IOL507"]
    assert result.diagnostics[0].source is not None
    assert result.diagnostics[0].source.header == "delay_on_s"


def test_default_configurations_pass_check_config(check_rows: Check) -> None:
    """Инвариант библиотеки: Cfg по умолчанию проходит CheckConfig (Device_DefaultCfg_PassesCheck)."""
    rows = [
        ai(),
        di(),
        *motor_vfd(),
        *valve(),
        {
            "tag": "M201",
            "description": "Мешалка",
            "signal_type": "DO",
            "device_type": "Motor",
            "dev_no": 31,
            "role": "CMD_RUN",
        },
        *cv_params(""),
        pid(dev_no=51),
    ]
    result = check_rows(rows)
    assert result.diagnostics == [], [d.render() for d in result.diagnostics]
    assert result.model is not None
    assert {d.device_type for d in result.model.devices} == set(DeviceType)


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ("xZsoUsed=TRUE", "IOL509"),
        ("xTorqueUsed=TRUE", "IOL509"),
        ("eType=SolenoidEto", "IOL509"),
    ],
)
def test_valve_contradictions(check_rows: Check, params: str, code: str) -> None:
    rows = valve_params(params)
    if "xZsoUsed" in params:
        rows = [row for row in rows if row["role"] != "ZSO"]
    assert code in codes(check_rows(rows))


def test_control_valve_contradictions(check_rows: Check) -> None:
    rows = cv_params("xFbUsed=TRUE")
    rows[0] = {**rows[0], "link_fb": ""}
    assert "IOL509" in codes(check_rows(rows))
    assert "IOL315" in codes(check_rows(cv_params("xFbUsed=FALSE")))


def test_motor_feedback_contradiction(check_rows: Check) -> None:
    rows = [
        {
            "tag": "M201",
            "description": "Мешалка",
            "signal_type": "DO",
            "device_type": "Motor",
            "dev_no": 31,
            "role": "CMD_RUN",
            "params": "xFbUsed=TRUE",
        }
    ]
    assert codes(check_rows(rows)) == ["IOL509"]


def test_modbus_start_with_comm_loss_warning(check_rows: Check) -> None:
    rows = motor_vfd()
    rows[0] = {
        **rows[0],
        "signal_type": "MB",
        "role": "VFD_CTW",
        "mb_link": "RS485-1",
        "mb_slave": 1,
        "mb_func": 6,
        "mb_reg": 0,
        "mb_type": "WORD",
        "params": "stVfd.xCommLossIsFault=FALSE",
    }
    result = check_rows(rows)
    assert codes(result) == ["IOL316"]
    assert result.model is not None
    assert result.model.device("P101").main_role is Role.VFD_CTW


def test_initializer_writes_only_changes(check_rows: Check) -> None:
    rows = motor_vfd()
    rows[0] = {**rows[0], "params": "tMinStop=T#30S; stVfd.rSpeedMin_pct=30.0"}
    device = only_device(check_rows(rows), "P101")
    assert device.cfg.initializer() == "(tMinStop := T#30S, stVfd := (rSpeedMin_pct := 30.0), udiAlarmIdBase := 110)"
