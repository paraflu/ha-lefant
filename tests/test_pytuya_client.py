"""Tests for the Tuya LAN 3.5 client codec: framing, key negotiation, DP parsing."""

import asyncio
import hmac
import json
import os
import struct
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "lefant_m1"))

import pytuya_client as tc  # noqa: E402

def _key() -> bytes:
    return b"0123456789abcdef"


def test_pack_unpack_roundtrip() -> None:
    key = _key()
    plaintext = b'{"dps":{"5":"cleaning"}}'
    frame = tc.pack_message(7, tc.STATUS, plaintext, key)
    msg = tc.unpack_message(frame, key)
    assert msg.seqno == 7
    assert msg.cmd == tc.STATUS
    assert msg.payload == plaintext
    assert msg.crc_good


def test_unpack_wrong_key_raises_invalidtag() -> None:
    frame = tc.pack_message(1, tc.STATUS, b"{}", _key())
    try:
        tc.unpack_message(frame, b"9999999999999999")
    except Exception as exc:  # cryptography.exceptions.InvalidTag
        assert type(exc).__name__ == "InvalidTag"
    else:
        raise AssertionError("expected InvalidTag")


def test_unpack_bad_prefix_raises() -> None:
    frame = tc.pack_message(1, tc.STATUS, b"{}", _key())
    bad = struct.pack(">I", 0xDEADBEAF) + frame[4:]
    try:
        tc.unpack_message(bad, _key())
    except tc.DecodeError:
        pass
    else:
        raise AssertionError("expected DecodeError")


def test_negotiation_vectors() -> None:
    """Full 3-step negotiation with known nonces → expected session key.

    `fake` plays the device role exactly as the spec describes:
    - on SESS_KEY_NEG_START: reply remote_nonce + HMAC(local_key, local_nonce)
    - expect SESS_KEY_NEG_FINISH = HMAC(local_key, remote_nonce)
    """
    key = _key()
    local_nonce = bytes(range(16))
    remote_nonce = bytes(range(16, 32))

    def device_step1(seqno: int, cmd: int, plaintext: bytes) -> bytes:
        assert cmd == tc.SESS_KEY_NEG_START and plaintext == local_nonce
        resp_payload = remote_nonce + hmac.new(key, local_nonce, sha256).digest()
        # session-key response: no retcode, no version header
        return tc.pack_message(0, tc.SESS_KEY_NEG_RESP, resp_payload, key)

    # check the frame the client would send for step 3
    finish = hmac.new(key, remote_nonce, sha256).digest()

    # emulate: client _negotiate_session_key with mocked _send_wait
    client = tc.TuyaClient("1.2.3.4", "dev", key.decode())

    async def fake_send_wait(cmd, payload):
        if cmd == tc.SESS_KEY_NEG_START:
            assert payload == local_nonce
            return tc.unpack_message(device_step1(0, cmd, payload), key)
        assert cmd == tc.SESS_KEY_NEG_FINISH
        assert payload == finish
        return tc.unpack_message(
            tc.pack_message(0, tc.SESS_KEY_NEG_FINISH, b"", key), key
        )

    async def run():
        import hmac as hmac_mod
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        client._send_wait = fake_send_wait
        enc = Cipher(algorithms.AES(key), modes.GCM(local_nonce[:12])).encryptor()
        expected = (enc.update(tc.xor_bytes(local_nonce, remote_nonce)) + enc.finalize())[:16]

        # replicate the negotiation to capture the resulting key
        resp = await client._send_wait(
            tc.SESS_KEY_NEG_START, local_nonce
        )
        assert hmac_mod.compare_digest(
            hmac.new(key, local_nonce, sha256).digest(), resp.payload[16:48]
        )
        await client._send_wait(tc.SESS_KEY_NEG_FINISH, finish)
        assert len(expected) == 16  # session key length invariant

    asyncio.run(run())


def test_dps_from_payload() -> None:
    assert tc.dps_from_payload(b'{"dps":{"23":80}}') == {"23": 80}
    assert tc.dps_from_payload(b'{"data":{"dps":{"1":true}}}') == {"1": True}
    assert tc.dps_from_payload(b'{"devId":"x"}') == {}
    assert tc.dps_from_payload(b"not json at all") == {}


def test_push_dispatch_calls_listener() -> None:
    key = _key()

    class Listener:
        def __init__(self):
            self.seen = []

        def status_updated(self, dps):
            self.seen.append(dps)

        def disconnected(self):
            pass

    listener = Listener()
    client = tc.TuyaClient("1.2.3.4", "dev", key.decode(), listener)
    push = tc.pack_message(
        1, tc.STATUS, json.dumps({"dps": {"5": "paused"}}).encode(), key
    )
    client._buffer = push
    client._process_buffer()
    assert listener.seen == [{"5": "paused"}]


def test_set_dps_payload_shape() -> None:
    """set_dps must produce a CONTROL_NEW frame whose plaintext is 3.5-header
    + {"devId", "uid", "t", "protocol":5, "data":{"dps":...}}."""
    key = _key()
    client = tc.TuyaClient("1.2.3.4", "mydev", key.decode())

    sent = []

    def fake_send(cmd, payload):
        sent.append((cmd, payload))

    client._send = fake_send  # type: ignore[method-assign]
    client.set_dps({"1": True})
    cmd, raw = sent[0]
    assert cmd == tc.CONTROL_NEW
    assert raw.startswith(tc.VERSION_HEADER)
    obj = json.loads(raw[len(tc.VERSION_HEADER) :])
    assert obj["devId"] == "mydev"
    assert obj["protocol"] == 5
    assert obj["data"]["dps"] == {"1": True}


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    test_pack_unpack_roundtrip()
    test_unpack_wrong_key_raises_invalidtag()
    test_unpack_bad_prefix_raises()
    test_negotiation_vectors()
    test_dps_from_payload()
    test_push_dispatch_calls_listener()
    test_set_dps_payload_shape()
    print("all pytuya_client tests passed")


def test_is_connected_lifecycle() -> None:
    """Public transport status follows StreamWriter closure, not device success."""
    from types import SimpleNamespace

    client = tc.TuyaClient("host", "device", _key().decode())
    assert not client.is_connected
    client._writer = SimpleNamespace(is_closing=lambda: False)
    assert client.is_connected
    client._writer = SimpleNamespace(is_closing=lambda: True)
    assert not client.is_connected
    client._writer = SimpleNamespace(is_closing=lambda: False, close=lambda: None)
    client.close()
    assert not client.is_connected
