"""DataUpdateCoordinator for Lefant M1 robot vacuum (push-based)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_DEVICE_ID, CONF_LOCAL_KEY, DOMAIN
from .pytuya_client import TuyaClient

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY = 10.0


class LefantDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that manages the persistent Tuya LAN connection and DP state cache."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}",
            always_update=False,
        )
        self.entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self.local_key: str = entry.data[CONF_LOCAL_KEY]

        self.dps: dict[str, Any] = {}
        self.client: TuyaClient = TuyaClient(
            host=self.host,
            device_id=self.device_id,
            local_key=self.local_key,
            listener=self,
        )
        self._reconnect_task: asyncio.Task[None] | None = None
        self._stopping: bool = False

    @property
    def is_connected(self) -> bool:
        """Return True if the Tuya client connection is active."""
        return self.client._writer is not None and not self.client._closing

    async def async_start(self) -> None:
        """Connect to the robot and fetch initial state snapshot."""
        try:
            await self.client.connect()
            self.dps = await self.client.query_dps()
            self.async_set_updated_data(self.dps)
            _LOGGER.info("Connected to Lefant M1 (%s at %s)", self.device_id, self.host)
        except Exception as err:
            self.client.close()
            raise ConfigEntryNotReady(
                f"Could not connect to Lefant M1 at {self.host}: {err}"
            ) from err

    async def async_stop(self) -> None:
        """Stop the coordinator and close active socket."""
        self._stopping = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        self.client.close()

    def status_updated(self, dps: dict[str, Any]) -> None:
        """Callback from TuyaClient on incoming status push."""
        self.dps.update(dps)
        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, dict(self.dps))

    def disconnected(self) -> None:
        """Callback from TuyaClient when the socket is dropped."""
        if self._stopping:
            return
        _LOGGER.warning("Connection to Lefant M1 (%s) lost, scheduling reconnect", self.host)
        # Notify entities that connection is dropped (data is still cached, availability may check is_connected)
        self.hass.loop.call_soon_threadsafe(self.async_update_listeners)
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = self.hass.async_create_background_task(
                self._reconnect_loop(), f"lefant_m1_reconnect_{self.device_id}"
            )

    async def _reconnect_loop(self) -> None:
        """Background loop to periodically attempt reconnection."""
        backoff = RECONNECT_DELAY
        while not self._stopping:
            await asyncio.sleep(backoff)
            if self._stopping:
                break
            _LOGGER.debug("Attempting to reconnect to Lefant M1 at %s", self.host)
            try:
                self.client = TuyaClient(
                    host=self.host,
                    device_id=self.device_id,
                    local_key=self.local_key,
                    listener=self,
                )
                await self.client.connect()
                fresh_dps = await self.client.query_dps()
                if fresh_dps:
                    self.dps.update(fresh_dps)
                self.async_set_updated_data(dict(self.dps))
                _LOGGER.info("Reconnected successfully to Lefant M1 at %s", self.host)
                return
            except Exception as err:
                _LOGGER.debug("Reconnection attempt to %s failed: %s", self.host, err)
                backoff = min(backoff * 1.5, 60.0)

    async def async_set_dps(self, dps: dict[str, Any]) -> None:
        """Send DPs to robot and optimistically update local state."""
        self.client.set_dps(dps)
        self.dps.update(dps)
        self.async_set_updated_data(dict(self.dps))

    async def async_set_dp(self, dp: str, value: Any) -> None:
        """Send a single DP to the robot."""
        await self.async_set_dps({dp: value})
