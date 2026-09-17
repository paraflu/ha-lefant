"""Minimal HA API doubles; these tests do not validate a running HA instance."""

import importlib
import sys
import types
from enum import IntFlag
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def integration(monkeypatch):
    """Load integration modules without executing HA setup or installing HA."""
    def module(name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    class Base:
        @classmethod
        def __class_getitem__(cls, item):
            return cls

    class Coordinator(Base):
        def __init__(self, hass, *args, **kwargs):
            self.hass = hass
            self.data = None
            self.notifications = 0

        def async_set_updated_data(self, data):
            self.data = data
            self.async_update_listeners()

        def async_update_listeners(self):
            self.notifications += 1

    class Entity(Base):
        def __init__(self, coordinator):
            self.coordinator = coordinator

    class Features(IntFlag):
        START = 1
        PAUSE = 2
        STOP = 4
        RETURN_HOME = 8
        FAN_SPEED = 16
        LOCATE = 32
        CLEAN_SPOT = 64
        STATE = 128

    class NotReady(Exception):
        pass

    module("homeassistant")
    module("homeassistant.components")
    module("homeassistant.helpers")
    module("homeassistant.config_entries", ConfigEntry=object)
    module("homeassistant.core", HomeAssistant=object)
    module("homeassistant.const", CONF_HOST="host", PERCENTAGE="%",
           UnitOfArea=SimpleNamespace(SQUARE_METERS="m²"),
           UnitOfTime=SimpleNamespace(MINUTES="min"))
    module("homeassistant.exceptions", ConfigEntryNotReady=NotReady)
    module("homeassistant.helpers.update_coordinator",
           DataUpdateCoordinator=Coordinator, CoordinatorEntity=Entity)
    module("homeassistant.helpers.device_registry", DeviceInfo=dict)
    module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    module("homeassistant.components.vacuum", StateVacuumEntity=type("Vacuum", (), {}),
           VacuumEntityFeature=Features,
           VacuumActivity=SimpleNamespace(**{s.upper(): s for s in
               ("cleaning", "docked", "idle", "paused", "returning", "error")}))
    module("homeassistant.components.sensor", SensorEntity=type("Sensor", (), {}),
           SensorEntityDescription=SimpleNamespace,
           SensorDeviceClass=SimpleNamespace(BATTERY="battery", DURATION="duration"),
           SensorStateClass=SimpleNamespace(MEASUREMENT="measurement"))
    package = module("lefant_test")
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/lefant_m1")]
    # Ensure pytest restores all imported modules, not just the package.
    for name in ("const", "pytuya_client", "coordinator", "vacuum", "sensor"):
        monkeypatch.delitem(sys.modules, f"lefant_test.{name}", raising=False)
    yield SimpleNamespace(**{name: importlib.import_module(f"lefant_test.{name}")
                            for name in ("const", "pytuya_client", "coordinator", "vacuum", "sensor")})
    for name in list(sys.modules):
        if name.startswith("lefant_test."):
            sys.modules.pop(name)
