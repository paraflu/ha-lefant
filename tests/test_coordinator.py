"""Coordinator policy tests with deterministic fake transport, not physical M1."""

import asyncio
from types import SimpleNamespace
from typing import Any


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.is_connected = True
        self.queries = 0
        self.sent = []
        self.snapshot = {"14": "normal"}

    async def connect(self):
        self.is_connected = True

    async def query_dps(self) -> dict[str, Any]:
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


def test_reconnect_backoff_cleanup_and_single_task(integration, monkeypatch):
    async def run():
        coordinator = make_coordinator(integration)
        coordinator.client.close()
        clients = []
        delays = []
        real_sleep = asyncio.sleep

        class RetryClient(FakeClient):
            def __init__(self, **kwargs):
                super().__init__()
                self.number = len(clients)
                clients.append(self)

            async def query_dps(self) -> dict[str, Any]:
                if self.number < 7:
                    raise OSError("query failed after connect")
                return {"23": 81}

        async def sleep(delay):
            delays.append(delay)
            await real_sleep(0)

        # The coordinator builds its LAN client through _make_client().
        monkeypatch.setattr(integration.coordinator, "TinytuyaClient", RetryClient)
        monkeypatch.setattr(integration.coordinator.asyncio, "sleep", sleep)
        coordinator.disconnected()
        task = coordinator._reconnect_task
        coordinator.disconnected()
        assert coordinator._reconnect_task is task
        await task
        # Research/design reconnect policy: 10s, x1.5, capped at 60s.
        assert delays == [10, 15, 22.5, 33.75, 50.625, 60, 60, 60]
        assert all(not client.is_connected for client in clients[:-1])
        assert coordinator.is_connected
        assert coordinator.dps["23"] == 81
        assert coordinator._observed["23"] == 81
        await coordinator.async_stop()
        coordinator.disconnected()
        assert coordinator._reconnect_task is task
    asyncio.run(run())


def test_reconcile_failure_rolls_back(integration, monkeypatch, caplog):
    async def run():
        monkeypatch.setattr(integration.coordinator, "RECONCILE_DELAY", 0)
        coordinator = make_coordinator(integration)
        coordinator.status_updated({"14": "normal"})

        async def fail():
            raise TimeoutError("test timeout")

        coordinator.client.query_dps = fail
        await coordinator.async_set_dps({"14": "strong", "24": True})
        await coordinator._reconcile_task
        assert coordinator.dps == {"14": "normal"}
        assert not coordinator._pending
        assert "reconciliation failed" in caplog.text
        await coordinator.async_stop()
    asyncio.run(run())


def test_new_command_and_push_win_over_inflight_query(integration, monkeypatch):
    async def run():
        monkeypatch.setattr(integration.coordinator, "RECONCILE_DELAY", 0)
        coordinator = make_coordinator(integration)
        started, release = asyncio.Event(), asyncio.Event()

        async def query():
            started.set()
            await release.wait()
            return {"14": "normal", "23": 10}

        coordinator.client.query_dps = query
        await coordinator.async_set_dps({"14": "strong"})
        await started.wait()
        await coordinator.async_set_dps({"14": "quiet"})
        coordinator.status_updated({"14": "quiet", "23": 90})
        release.set()
        await coordinator._reconcile_task
        assert coordinator.dps == {"14": "quiet", "23": 90}
        await coordinator.async_stop()
    asyncio.run(run())


def test_disconnect_cancels_timer_and_stop_cancels_backoff(integration):
    async def run():
        coordinator = make_coordinator(integration)
        coordinator.status_updated({"14": "normal"})
        await coordinator.async_set_dps({"14": "strong"})
        reconcile = coordinator._reconcile_task
        coordinator.client.close()
        coordinator.disconnected()
        reconnect = coordinator._reconnect_task
        await asyncio.sleep(0)
        assert reconcile.cancelled()
        assert coordinator.dps["14"] == "normal"
        assert not coordinator.is_connected
        await coordinator.async_stop()
        await asyncio.sleep(0)
        assert reconnect.cancelled()
    asyncio.run(run())


def test_client_uses_configured_protocol(integration):
    # The M1 answers 3.3; tinytuya covers 3.4/3.5 for other models, so the
    # protocol has to come from the entry rather than be hardcoded.
    async def run():
        coordinator = make_coordinator(integration)
        assert coordinator.protocol == 3.3
        client = coordinator._make_client()
        assert client.version == 3.3
        assert client.host == coordinator.host
        assert client.dev_id == coordinator.device_id
        assert client.listener is coordinator

        coordinator.entry.data["protocol"] = 3.5
        coordinator.protocol = float(coordinator.entry.data["protocol"])
        assert coordinator._make_client().version == 3.5
    asyncio.run(run())


def test_unknown_protocol_is_rejected(integration):
    async def run():
        coordinator = make_coordinator(integration)
        coordinator.protocol = 9.9
        try:
            coordinator._make_client()
        except ValueError as err:
            assert "non supportata" in str(err)
        else:  # pragma: no cover - guard must not regress silently
            raise AssertionError("una versione non supportata deve essere rifiutata")
    asyncio.run(run())
