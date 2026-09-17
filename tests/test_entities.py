"""Entity mapping regression tests, not physical M1 validation (M1-DP-1)."""

import asyncio
from types import SimpleNamespace


def test_fan_speed_and_locate_mapping(integration):
    async def run():
        calls = []

        async def set_dp(dp, value):
            calls.append((dp, value))

        coordinator = SimpleNamespace(device_id="test", is_connected=True,
                                      dps={}, async_set_dp=set_dp)
        vacuum = integration.vacuum.LefantM1Vacuum(coordinator)
        # Research Decision Log M1-DP-1: retained provisional DP14/DP24.
        for speed in ("quiet", "normal", "strong"):
            coordinator.dps = {"14": speed}
            assert vacuum.fan_speed == speed
            await vacuum.async_set_fan_speed(speed)
            assert calls[-1] == ("14", speed)
        await vacuum.async_set_fan_speed("invalid")
        assert len(calls) == 3
        await vacuum.async_locate()
        assert calls[-1] == ("24", True)

    asyncio.run(run())


def test_cleaning_sensor_mapping(integration):
    # Research M1-DP-1: current IDs and units are implementation assumptions.
    coordinator = SimpleNamespace(device_id="test", is_connected=True,
                                  dps={"18": 12, "19": 34})
    descriptions = {item.key: item for item in integration.sensor.SENSOR_TYPES}
    for dp, value, unit in (("18", 12, "min"), ("19", 34, "m²")):
        sensor = integration.sensor.LefantM1Sensor(coordinator, descriptions[dp])
        assert sensor.native_value == value
        assert descriptions[dp].native_unit_of_measurement == unit
        coordinator.dps.pop(dp)
        assert sensor.native_value is None
