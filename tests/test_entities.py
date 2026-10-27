"""Entity regressions using issue #1 evidence; no live robot I/O."""

import asyncio
from types import SimpleNamespace


# Sanitized physical M1 snapshot shared by McRosbeef in issue #1.
# Firmware 1.9.13, official app 3.4.5, TinyTuya protocol 3.3.
M1_SNAPSHOT = {
    "4": "smart", "5": "sleep", "6": 1, "7": 0, "8": 100,
    "9": "strong", "10": "high", "27": True, "28": 0,
    "45": True, "122": True, "125": True,
}


def test_fan_speed_and_locate_mapping(integration):
    async def run():
        calls = []

        async def set_dp(dp, value):
            calls.append((dp, value))

        coordinator = SimpleNamespace(device_id="test", protocol=3.3, is_connected=True,
                                      dps={}, async_set_dp=set_dp)
        vacuum = integration.vacuum.LefantM1Vacuum(coordinator)
        # DP9 is corroborated by issue #1; gentle/normal come from the APK.
        for speed in ("gentle", "normal", "strong"):
            coordinator.dps = {"9": speed}
            assert vacuum.fan_speed == speed
            await vacuum.async_set_fan_speed(speed)
            assert calls[-1] == ("9", speed)
        for speed in ("quiet", "invalid"):
            await vacuum.async_set_fan_speed(speed)
        assert len(calls) == 3
        assert vacuum._attr_fan_speed_list == ["gentle", "normal", "strong"]
        # APK LaserDP.SEEK=11; this asserts routing, not device acceptance.
        await vacuum.async_locate()
        assert calls[-1] == ("11", True)

    asyncio.run(run())


def test_cleaning_sensor_mapping(integration):
    coordinator = SimpleNamespace(device_id="test", protocol=3.3, is_connected=True,
                                  dps={"6": 12, "7": 34, "8": 81})
    descriptions = {item.key: item for item in integration.sensor.SENSOR_TYPES}
    for dp, value, unit in (("6", 12, "min"), ("7", 34, "m²"), ("8", 81, "%")):
        sensor = integration.sensor.LefantM1Sensor(coordinator, descriptions[dp])
        assert sensor.native_value == value
        assert descriptions[dp].native_unit_of_measurement == unit
        coordinator.dps.pop(dp)
        assert sensor.native_value is None


def test_sensor_registry_ids_survive_dp_correction(integration):
    coordinator = SimpleNamespace(device_id="test", protocol=3.3, is_connected=True,
                                  dps=dict(M1_SNAPSHOT))
    expected_suffixes = {"8": "23", "6": "18", "7": "19"}
    for description in integration.sensor.SENSOR_TYPES:
        sensor = integration.sensor.LefantM1Sensor(coordinator, description)
        assert sensor._attr_unique_id == f"test_{expected_suffixes[description.key]}"
        assert sensor.native_value == M1_SNAPSHOT[description.key]


def test_physical_m1_snapshot_mapping(integration):
    coordinator = SimpleNamespace(device_id="test", protocol=3.3, is_connected=True,
                                  dps=dict(M1_SNAPSHOT))
    vacuum = integration.vacuum.LefantM1Vacuum(coordinator)
    assert vacuum.battery_level == 100
    assert vacuum.fan_speed == "strong"
    # MODE=smart must not override STATUS=sleep.
    assert vacuum.activity == integration.vacuum.VacuumActivity.IDLE
    assert vacuum.extra_state_attributes == {
        "clean_time_min": 1,
        "clean_area_m2": 0,
        "clean_mode": "smart",
        "raw_status": "sleep",
        "error_code": 0,
    }
    descriptions = {item.key: item for item in integration.sensor.SENSOR_TYPES}
    for dp, value in (("6", 1), ("7", 0), ("8", 100)):
        sensor = integration.sensor.LefantM1Sensor(coordinator, descriptions[dp])
        assert sensor.native_value == value


def test_fault_uses_dp28_not_legacy_dp25(integration):
    coordinator = SimpleNamespace(device_id="test", protocol=3.3, is_connected=True,
                                  dps={**M1_SNAPSHOT, "25": 99})
    vacuum = integration.vacuum.LefantM1Vacuum(coordinator)
    assert vacuum.activity == integration.vacuum.VacuumActivity.IDLE
    coordinator.dps["28"] = 1
    assert vacuum.activity == integration.vacuum.VacuumActivity.ERROR
    assert vacuum.extra_state_attributes["error_code"] == 1


def test_legacy_dp_ids_do_not_supply_telemetry(integration):
    coordinator = SimpleNamespace(device_id="test", protocol=3.3, is_connected=True,
                                  dps={"14": "strong", "18": 12,
                                       "19": 34, "23": 90, "25": 1})
    vacuum = integration.vacuum.LefantM1Vacuum(coordinator)
    assert vacuum.battery_level is None
    assert vacuum.fan_speed == "normal"
    assert vacuum.extra_state_attributes["clean_time_min"] is None
    assert vacuum.extra_state_attributes["clean_area_m2"] is None
    for description in integration.sensor.SENSOR_TYPES:
        sensor = integration.sensor.LefantM1Sensor(coordinator, description)
        assert sensor.native_value is None
