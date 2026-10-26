"""Unit test per l'adapter Tinytuya (nessuna rete, nessuna credenziale).

Verifica il contratto che il coordinator si aspetta dal client:
connect/query_dps/set_dps/close, traduzione degli errori tinytuya in eccezioni
tipizzate, aggiornamento del listener. Usa un dispositivo finto iniettato,
quindi non serve tinytuya installato.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "lefant_m1"))

from tuya_lan_adapter import (  # noqa: E402
    TinytuyaClient,
    TuyaLanAuthError,
    TuyaLanConnectionError,
)

FAKE_ID = "bf0000000000000000000000"
FAKE_KEY = "0123456789abcdef"


class FakeListener:
    def __init__(self):
        self.updates = []
        self.disconnects = 0

    def status_updated(self, dps):
        self.updates.append(dict(dps))

    def disconnected(self):
        self.disconnects += 1


class FakeDevice:
    """Sostituto minimo di tinytuya.Device."""

    def __init__(self, dev_id, address=None, local_key="", version=3.3, persist=False,
                 connection_timeout=5, responses=None, write_result=None):
        self.dev_id = dev_id
        self.address = address
        self.local_key = local_key
        self.version = version
        self.persist = persist
        self.closed = False
        self.writes = []
        self._responses = list(responses or [{"dps": {"1": False}}])
        self._write_result = write_result if write_result is not None else {"dps": {}}

    def status(self):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    def set_multiple_values(self, dps):
        self.writes.append(dict(dps))
        return self._write_result

    def close(self):
        self.closed = True


def _factory(device_holder, **kwargs):
    def build(dev_id, address=None, local_key="", version=3.3):
        device = FakeDevice(dev_id, address, local_key, version=version, **kwargs)
        device_holder.append(device)
        return device

    return build


def test_connect_returns_dps_and_notifies_listener() -> None:
    async def scenario():
        holder = []
        listener = FakeListener()
        client = TinytuyaClient(
            host="192.0.2.10",
            device_id=FAKE_ID,
            local_key=FAKE_KEY,
            listener=listener,
            poll_interval=0.01,
            device_factory=_factory(holder, responses=[{"dps": {"1": True, "8": 90}}]),
        )
        await client.connect()
        assert client.is_connected
        dps = await client.query_dps()
        assert dps == {"1": True, "8": 90}
        await asyncio.sleep(0.05)
        assert listener.updates, "il polling deve notificare il listener"
        client.close()
        assert holder[0].closed
        assert listener.disconnects == 1

    asyncio.run(scenario())


def test_set_dps_writes_through_fake_device() -> None:
    async def scenario():
        holder = []
        client = TinytuyaClient(
            host="192.0.2.10",
            device_id=FAKE_ID,
            local_key=FAKE_KEY,
            poll_interval=5.0,
            device_factory=_factory(holder, responses=[{"dps": {}}]),
        )
        await client.connect()
        client.set_dps({"1": True})
        await asyncio.sleep(0.05)
        assert holder[0].writes == [{"1": True}], holder[0].writes
        client.close()

    asyncio.run(scenario())


def test_wrong_key_raises_auth_error() -> None:
    async def scenario():
        holder = []
        client = TinytuyaClient(
            host="192.0.2.10",
            device_id=FAKE_ID,
            local_key=FAKE_KEY,
            device_factory=_factory(
                holder, responses=[{"Error": "Check device key or version", "Err": 914, "Payload": None}]
            ),
        )
        try:
            await client.connect()
        except TuyaLanAuthError:
            pass
        else:  # pragma: no cover
            raise AssertionError("atteso TuyaLanAuthError")
        assert not client.is_connected

    asyncio.run(scenario())


def test_string_error_codes_are_coerced() -> None:
    """tinytuya restituisce a volte il codice come stringa: deve restare tipizzato."""

    async def scenario():
        holder = []
        client = TinytuyaClient(
            host="192.0.2.10",
            device_id=FAKE_ID,
            local_key=FAKE_KEY,
            device_factory=_factory(
                holder, responses=[{"Error": "Unexpected Payload from Device", "Err": "904", "Payload": None}]
            ),
        )
        try:
            await client.connect()
        except TuyaLanAuthError:
            return
        raise AssertionError("atteso TuyaLanAuthError anche con codice stringa")

    asyncio.run(scenario())


def test_unreachable_raises_connection_error() -> None:
    async def scenario():
        holder = []
        client = TinytuyaClient(
            host="192.0.2.10",
            device_id=FAKE_ID,
            local_key=FAKE_KEY,
            device_factory=_factory(holder, responses=[{"Error": "Network Error: timed out", "Err": 901}]),
        )
        try:
            await client.connect()
        except TuyaLanConnectionError:
            pass
        else:  # pragma: no cover
            raise AssertionError("atteso TuyaLanConnectionError")

    asyncio.run(scenario())


def test_rejects_unsupported_version() -> None:
    try:
        TinytuyaClient(host="192.0.2.10", device_id=FAKE_ID, local_key=FAKE_KEY, version=4.2)
    except ValueError:
        return
    raise AssertionError("atteso ValueError per versione non supportata")


def test_coordinator_compatibility_shims() -> None:
    async def scenario():
        holder = []
        client = TinytuyaClient(
            host="192.0.2.10",
            device_id=FAKE_ID,
            local_key=FAKE_KEY,
            poll_interval=5.0,
            device_factory=_factory(holder, responses=[{"dps": {}}]),
        )
        assert client._writer is None and not client._closing
        await client.connect()
        assert client._writer is not None
        client.close()
        assert client._writer is None

    asyncio.run(scenario())


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print(f"ok  {_name}")
    print("\nTutti i test dell'adapter passano.")
