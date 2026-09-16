"""Sensor platform for Lefant M1 robot vacuum."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DP_BATTERY, DP_CLEAN_AREA, DP_CLEAN_TIME
from .coordinator import LefantDataUpdateCoordinator

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=DP_BATTERY,
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=DP_CLEAN_TIME,
        name="Cleaning Time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key=DP_CLEAN_AREA,
        name="Cleaned Area",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:texture-box",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lefant M1 sensors from a config entry."""
    coordinator: LefantDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LefantM1Sensor(coordinator, description) for description in SENSOR_TYPES
    )


class LefantM1Sensor(CoordinatorEntity[LefantDataUpdateCoordinator], SensorEntity):
    """Representation of a Lefant M1 sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LefantDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=f"Lefant M1 ({coordinator.device_id[-4:] if len(coordinator.device_id) >= 4 else coordinator.device_id})",
            manufacturer="Lefant",
            model="M1",
            sw_version="Tuya LAN 3.5",
        )

    @property
    def native_value(self) -> int | float | None:
        """Return the state of the sensor."""
        val = self.coordinator.dps.get(self.entity_description.key)
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None
