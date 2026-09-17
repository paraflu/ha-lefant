"""Coordinator policy tests with deterministic fake transport, not physical M1."""

import asyncio
from types import SimpleNamespace


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.is_connected = True
        self.queries = 0
        self.sent = []
        self.snapshot = {"14": "normal"}

    async def connect(self):
        self.is_connected = True

    async def query_dps(self):
        self.queries += 1
        return dict(self.snapshot)

    def set_dps(self, dps):
        if not self.is_connected:
            raise ConnectionError("offline")
        self.sent.append(dict(dps))

    def close(self):
        self.is_connected = False


def make_coordinator(integration):
    loop = asyncio.get_running_loop()
    hass = SimpleNamespace(loop=loop, async_create_background_task=
                           lambda coro, name: asyncio.create_task(coro, name=name))
    entry = SimpleNamespace(data={"host": "test", "device_id": "test",
                                  "local_key": "0123456789abcdef"})
    coordinator = integration.coordinator.LefantDataUpdateCoordinator(hass, entry)
    coordinator.client = FakeClient()
    return coordinator


def test_missing_confirmation_queries_and_restores(integration, monkeypatch, caplog):
    async def run():
        # Design addendum: reconciliation is local policy; DP14 is provisional.
        monkeypatch.setattr(integration.coordinator, "RECONCILE_DELAY", 0.001)
        coordinator = make_coordinator(integration)
        coordinator.status_updated({"14": "normal"})
        await coordinator.async_set_dps({"14": "strong"})
        assert coordinator.dps["14"] == "strong"
        await asyncio.wait_for(coordinator._reconcile_task, 1)
        assert coordinator.client.queries == 1
        assert coordinator.dps["14"] == "normal"
        assert "confirmation" in caplog.text
        await coordinator.async_stop()
    asyncio.run(run())


def test_matching_push_confirms_but_unrelated_does_not(integration, monkeypatch):
    async def run():
        monkeypatch.setattr(integration.coordinator, "RECONCILE_DELAY", 0.001)
        coordinator = make_coordinator(integration)
        await coordinator.async_set_dps({"14": "strong", "24": True})
        coordinator.status_updated({"23": 90, "14": "strong"})
        await asyncio.wait_for(coordinator._reconcile_task, 1)
        assert coordinator.client.queries == 1
        assert "24" not in coordinator.dps
        await coordinator.async_set_dps({"14": "strong"})
        coordinator.status_updated({"14": "strong"})
        await asyncio.wait_for(coordinator._reconcile_task, 1)
        assert coordinator.client.queries == 1
        await coordinator.async_stop()
    asyncio.run(run())


def test_stop_cancels_reconciliation(integration):
    async def run():
        coordinator = make_coordinator(integration)
        await coordinator.async_set_dps({"14": "strong"})
        task = coordinator._reconcile_task
        await coordinator.async_stop()
        await asyncio.sleep(0)
        assert task.cancelled()
        assert coordinator.client.queries == 0
    asyncio.run(run())
