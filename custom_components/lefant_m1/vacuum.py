"""Vacuum entity platform for Lefant M1."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ACTIVITY_CLEANING,
    ACTIVITY_DOCKED,
    ACTIVITY_ERROR,
    ACTIVITY_IDLE,
    ACTIVITY_PAUSED,
    ACTIVITY_RETURNING,
    DOMAIN,
    DP_BATTERY,
    DP_CLEAN_AREA,
    DP_CLEAN_TIME,
    DP_ERROR_CODE,
    DP_LOCATE,
    DP_MODE,
    DP_PAUSE,
    DP_STATUS,
    DP_SUCTION,
    DP_SWITCH_CHARGE,
    DP_SWITCH_GO,
    FAN_SPEED_LIST,
    FAN_SPEED_NORMAL,
    MODE_SPOT,
    map_status_to_activity,
)
from .coordinator import LefantDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = (
    VacuumEntityFeature.START
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.FAN_SPEED
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.CLEAN_SPOT
    | VacuumEntityFeature.STATE
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lefant M1 vacuum entity based on a config entry."""
    coordinator: LefantDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LefantM1Vacuum(coordinator)])


class LefantM1Vacuum(CoordinatorEntity[LefantDataUpdateCoordinator], StateVacuumEntity):
    """Representation of a Lefant M1 robot vacuum."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_fan_speed_list = FAN_SPEED_LIST

    def __init__(self, coordinator: LefantDataUpdateCoordinator) -> None:
        """Initialize the vacuum entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_vacuum"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=f"Lefant M1 ({coordinator.device_id[-4:] if len(coordinator.device_id) >= 4 else coordinator.device_id})",
            manufacturer="Lefant",
            model="M1",
            sw_version=f"Tuya LAN {coordinator.protocol:.1f}",
        )

    @property
    def activity(self) -> VacuumActivity | None:
        """Return the current activity of the vacuum."""
        raw_status = self.coordinator.dps.get(DP_STATUS)
        error_code = self.coordinator.dps.get(DP_ERROR_CODE)
        act_str = map_status_to_activity(raw_status, error_code)

        mapping = {
            ACTIVITY_CLEANING: VacuumActivity.CLEANING,
            ACTIVITY_DOCKED: VacuumActivity.DOCKED,
            ACTIVITY_IDLE: VacuumActivity.IDLE,
            ACTIVITY_PAUSED: VacuumActivity.PAUSED,
            ACTIVITY_RETURNING: VacuumActivity.RETURNING,
            ACTIVITY_ERROR: VacuumActivity.ERROR,
        }
        return mapping.get(act_str, VacuumActivity.IDLE)

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the vacuum cleaner."""
        val = self.coordinator.dps.get(DP_BATTERY)
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def fan_speed(self) -> str | None:
        """Return the current fan speed."""
        return self.coordinator.dps.get(DP_SUCTION, FAN_SPEED_NORMAL)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device-specific state attributes."""
        return {
            "clean_time_min": self.coordinator.dps.get(DP_CLEAN_TIME),
            "clean_area_m2": self.coordinator.dps.get(DP_CLEAN_AREA),
            "clean_mode": self.coordinator.dps.get(DP_MODE),
            "raw_status": self.coordinator.dps.get(DP_STATUS),
            "error_code": self.coordinator.dps.get(DP_ERROR_CODE, 0),
        }

    async def async_start(self) -> None:
        """Start or resume cleaning."""
        await self.coordinator.async_set_dp(DP_SWITCH_GO, True)

    async def async_pause(self) -> None:
        """Pause cleaning."""
        await self.coordinator.async_set_dp(DP_PAUSE, True)

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop cleaning."""
        await self.coordinator.async_set_dp(DP_SWITCH_GO, False)

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Send robot back to charging dock."""
        await self.coordinator.async_set_dp(DP_SWITCH_CHARGE, True)

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set vacuum fan speed."""
        if fan_speed in FAN_SPEED_LIST:
            await self.coordinator.async_set_dp(DP_SUCTION, fan_speed)

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the robot vacuum."""
        await self.coordinator.async_set_dp(DP_LOCATE, True)

    async def async_clean_spot(self, **kwargs: Any) -> None:
        """Perform a spot clean."""
        await self.coordinator.async_set_dps({DP_MODE: MODE_SPOT, DP_SWITCH_GO: True})
