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
# Source: design addendum 2026-09-17, local reconciliation policy, not wire spec.
RECONCILE_DELAY = 7.0


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
        self._reconcile_task: asyncio.Task[None] | None = None
        self._observed: dict[str, Any] = {}
        self._pending: dict[str, tuple[Any, int, float]] = {}
        self._revision = 0
        self._versions: dict[str, int] = {}

    @property
    def is_connected(self) -> bool:
        """Return True if the Tuya client connection is active."""
        return self.client.is_connected

    async def async_start(self) -> None:
        """Connect to the robot and fetch initial state snapshot."""
        try:
            await self.client.connect()
            self.status_updated(await self.client.query_dps())
            _LOGGER.info("Connected to Lefant M1 (%s at %s)", self.device_id, self.host)
        except Exception as err:
            self.client.close()
            raise ConfigEntryNotReady(
                f"Could not connect to Lefant M1 at {self.host}: {err}"
            ) from err

    async def async_stop(self) -> None:
        """Stop the coordinator and close active socket."""
        self._stopping = True
        self._cancel_reconciliation()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        self.client.close()

    def status_updated(self, dps: dict[str, Any]) -> None:
        """Callback from TuyaClient on incoming status push."""
        # Source: design addendum: only matching STATUS DPs confirm commands.
        self._observed.update(dps)
        self._revision += 1
        for dp, value in dps.items():
            self._versions[dp] = self._revision
            pending = self._pending.get(dp)
            if pending is not None and value == pending[0]:
                self._pending.pop(dp)
        self.dps.update(dps)
        self.async_set_updated_data(dict(self.dps))

    def disconnected(self) -> None:
        """Callback from TuyaClient when the socket is dropped."""
        self._cancel_reconciliation()
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
        if self._stopping or not self.is_connected:
            raise ConnectionError("Lefant M1 is disconnected")
        self.client.set_dps(dps)
        if not dps:
            return
        # Source: design addendum: command optimism expires unless STATUS confirms.
        self._revision += 1
        deadline = self.hass.loop.time() + RECONCILE_DELAY
        for dp, value in dps.items():
            self._pending[dp] = (value, self._revision, deadline)
            self._versions[dp] = self._revision
        self.dps.update(dps)
        self.async_set_updated_data(dict(self.dps))
        if self._reconcile_task is None or self._reconcile_task.done():
            self._reconcile_task = self.hass.async_create_background_task(
                self._reconcile_loop(), f"{DOMAIN}_reconcile_{self.device_id}"
            )

    def _cancel_reconciliation(self) -> None:
        """Cancel stale work and discard unconfirmed optimistic state."""
        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()
        for dp in self._pending:
            if dp in self._observed:
                self.dps[dp] = self._observed[dp]
            else:
                self.dps.pop(dp, None)
        self._pending.clear()

    async def _reconcile_loop(self) -> None:
        """Query after missing confirmation; protect newer commands and pushes."""
        # Source: design addendum 2026-09-17. No new Tuya acknowledgement semantics.
        while self._pending and not self._stopping:
            deadline = min(item[2] for item in self._pending.values())
            await asyncio.sleep(max(0, deadline - self.hass.loop.time()))
            if not self._pending or self._stopping or not self.is_connected:
                return
            client = self.client
            pending = dict(self._pending)
            versions = dict(self._versions)
            _LOGGER.warning("No STATUS confirmation from %s; querying actual DPs", self.host)
            try:
                fresh = await client.query_dps()
            except (TimeoutError, ConnectionError, OSError) as err:
                _LOGGER.warning("DP reconciliation failed for %s: %s", self.host, err)
                fresh = {}
            if self._stopping or client is not self.client or not client.is_connected:
                return
            # A newer command or push wins over a potentially stale query response.
            for dp, value in fresh.items():
                if self._versions.get(dp) == versions.get(dp):
                    self._observed[dp] = value
                    self.dps[dp] = value
            for dp, command in pending.items():
                if self._pending.get(dp) != command:
                    continue
                self._pending.pop(dp)
                if dp in self._observed:
                    self.dps[dp] = self._observed[dp]
                else:
                    self.dps.pop(dp, None)
            self.async_set_updated_data(dict(self.dps))

    async def async_set_dp(self, dp: str, value: Any) -> None:
        """Send a single DP to the robot."""
        await self.async_set_dps({dp: value})
