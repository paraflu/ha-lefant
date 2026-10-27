"""Minimal pure-asyncio client for the Tuya LAN protocol, version 3.5.

Speaks only 0x6699 GCM frames (protocol 3.5) — the version used by Lefant
robots. Persistent connection: the device pushes DP updates, forwarded to
the listener (`status_updated(dps)` / `disconnected()` duck-typed interface).

Protocol reference (public specs): tinytuya core/ (MIT) and
tuya-iotos-embeded-sdk-wifi-ble-bk7231n sdk/include/lan_protocol.h.

.. deprecated:: 1.1.0
   Unused by the integration since the coordinator moved to
   :mod:`custom_components.lefant_m1.tuya_lan_adapter` (tinytuya). This file
   speaks **only** 3.5 (0x6699 framing, AES-GCM, session negotiation) and the
   M1 answers 3.3, so it cannot complete even its first frame. Kept temporarily
   for reference and its own tests; scheduled for removal.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import struct
import time
from collections import namedtuple
from hashlib import sha256
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

TCP_PORT = 6668
HEARTBEAT_INTERVAL = 8.3
TIMEOUT_REPLY = 5.0
MAX_PAYLOAD_LENGTH = 1440

PREFIX = 0x00006699
SUFFIX = 0x00009966
HEADER_FMT = ">IHIII"  # prefix, unknown, seqno, cmd, length
HEADER_LEN = struct.calcsize(HEADER_FMT)
# 6699 on-wire payload: iv(12) + ciphertext + tag(16); the header length
# field counts exactly these bytes.
GCM_OVERHEAD = 12 + 16
VERSION_HEADER = b"3.5" + 12 * b"\x00"

# Commands (lan_protocol.h)
SESS_KEY_NEG_START = 3
SESS_KEY_NEG_RESP = 4
SESS_KEY_NEG_FINISH = 5
STATUS = 8
HEART_BEAT = 9
CONTROL_NEW = 0x0D
DP_QUERY_NEW = 0x10

# Commands whose plaintext carries no version header
NO_VERSION_HEADER = {
    SESS_KEY_NEG_START,
    SESS_KEY_NEG_RESP,
    SESS_KEY_NEG_FINISH,
    HEART_BEAT,
    DP_QUERY_NEW,
}

TuyaMessage = namedtuple("TuyaMessage", "seqno cmd retcode payload crc_good")


class DecodeError(Exception):
    """Frame could not be parsed (bad prefix, size or suffix)."""


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def gcm_encrypt(key: bytes, plaintext: bytes, aad: bytes, iv: bytes | None = None) -> bytes:
    """AES-GCM encrypt into iv(12) + ciphertext + tag(16)."""
    iv = iv or os.urandom(12)
    enc = Cipher(algorithms.AES(key), modes.GCM(iv)).encryptor()
    if aad:
        enc.authenticate_additional_data(aad)
    return iv + enc.update(plaintext) + enc.finalize() + enc.tag


def pack_message(seqno: int, cmd: int, plaintext: bytes, key: bytes) -> bytes:
    """Pack a plaintext payload into an encrypted 0x6699 frame."""
    length = len(plaintext) + GCM_OVERHEAD
    header = struct.pack(HEADER_FMT, PREFIX, 0, seqno, cmd, length)
    encrypted = gcm_encrypt(key, plaintext, aad=header[4:])
    return header + encrypted + struct.pack(">I", SUFFIX)


def unpack_message(data: bytes, key: bytes) -> TuyaMessage:
    """Parse one 0x6699 frame; return it with the decrypted plaintext payload.

    Raises InvalidTag when the frame was not encrypted with `key` (wrong local
    key during negotiation, or session mismatch) and DecodeError on framing.
    """
    if len(data) < HEADER_LEN:
        raise DecodeError("short header")
    prefix, _, seqno, cmd, length = struct.unpack(HEADER_FMT, data[:HEADER_LEN])
    if prefix != PREFIX:
        raise DecodeError(f"bad prefix {prefix:#x}")
    if length > MAX_PAYLOAD_LENGTH:
        raise DecodeError(f"oversized payload {length}")
    frame_len = HEADER_LEN + length + 4
    if len(data) < frame_len:
        raise DecodeError("incomplete frame")
    encrypted = data[HEADER_LEN : HEADER_LEN + length]
    (suffix,) = struct.unpack(">I", data[frame_len - 4 : frame_len])
    if suffix != SUFFIX:
        raise DecodeError(f"bad suffix {suffix:#x}")
    dec = Cipher(
        algorithms.AES(key), modes.GCM(encrypted[:12], encrypted[-16:])
    ).decryptor()
    dec.authenticate_additional_data(data[4:HEADER_LEN])
    plaintext = dec.update(encrypted[12:-16]) + dec.finalize()
    # Response framing inside the plaintext: [retcode(4)]? and/or
    # ["3.5"+12*NUL(15)]? + JSON. The device mixes both conventions; the
    # session-key response carries neither (raw nonce + hmac bytes).
    retcode = 0
    if cmd != SESS_KEY_NEG_RESP:
        if plaintext[0:1] != b"{" and plaintext[4:5] == b"{":
            (retcode,) = struct.unpack(">I", plaintext[:4])
            plaintext = plaintext[4:]
        if plaintext.startswith(b"3.5"):
            plaintext = plaintext[15:]
    return TuyaMessage(seqno, cmd, retcode, plaintext, True)


def dps_from_payload(plaintext: bytes) -> dict[str, Any]:
    """Extract the dps dict from a decrypted JSON payload ({} if none).

    v3.4+ stuffs it as {"data": {"dps": {...}}} in some responses.
    """
    try:
        obj = json.loads(plaintext)
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    if "dps" not in obj and isinstance(obj.get("data"), dict):
        obj = obj["data"]
    dps = obj.get("dps")
    return dps if isinstance(dps, dict) else {}


class TuyaClient:
    """Persistent Tuya LAN 3.5 connection with push-based DP updates.

    Reconnect logic lives with the caller (listener.disconnected()).
    """

    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        listener: Any = None,
    ):
        self.host = host
        self.dev_id = device_id
        self.listener = listener
        self.local_key = local_key.encode() if isinstance(local_key, str) else local_key
        self._key = self.local_key  # session key after negotiation
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = b""
        self._seqno = 0
        self._waiters: dict[int, asyncio.Future] = {}  # cmd → Future
        self._tasks: list[asyncio.Task] = []
        self._closing = False

    @property
    def is_connected(self) -> bool:
        """Return whether the transport is open (not a command acknowledgement)."""
        return (
            self._writer is not None
            and not self._closing
            and not self._writer.is_closing()
        )

    async def connect(self) -> None:
        """Open the socket and negotiate the session key.

        Raises ConnectionError / OSError when the robot is unreachable,
        InvalidTag when the local key is wrong, asyncio.TimeoutError on stall.
        """
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, TCP_PORT), TIMEOUT_REPLY
        )
        self._tasks.append(asyncio.create_task(self._read_loop()))
        await self._negotiate_session_key()
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))

    async def query_dps(self) -> dict[str, Any]:
        """Request the full DP snapshot. Returns {dp_id: value}."""
        msg = await self._send_wait(
            DP_QUERY_NEW, self._encode_json(DP_QUERY_NEW, {})
        )
        return dps_from_payload(msg.payload)

    def set_dps(self, dps: dict[str, Any]) -> None:
        """Send DP values to the device (fire-and-forget).

        Confirmation arrives as a STATUS push, which reaches the listener.
        """
        payload = {
            "devId": self.dev_id,
            "uid": "",
            "t": int(time.time()),
            "protocol": 5,
            "data": {"dps": dps},
        }
        self._send(CONTROL_NEW, self._encode_json(CONTROL_NEW, payload))

    def close(self) -> None:
        """Close the connection (idempotent)."""
        self._on_disconnected(None)

    # -- internals ---------------------------------------------------------

    async def _negotiate_session_key(self) -> None:
        local_nonce = os.urandom(16)
        resp = await self._send_wait(SESS_KEY_NEG_START, local_nonce)
        if len(resp.payload) < 48:
            raise DecodeError("session key negotiation: short response")
        remote_nonce = resp.payload[:16]
        want = hmac.new(self._key, local_nonce, sha256).digest()
        if not hmac.compare_digest(want, resp.payload[16:48]):
            raise InvalidTag("session key negotiation: HMAC mismatch")
        self._send(
            SESS_KEY_NEG_FINISH,
            hmac.new(self._key, remote_nonce, sha256).digest(),
        )
        # session key = AES-GCM(local_key, iv=local_nonce[:12])(n1 xor n2)[:16]
        enc = Cipher(
            algorithms.AES(self._key), modes.GCM(local_nonce[:12])
        ).encryptor()
        session_key = enc.update(xor_bytes(local_nonce, remote_nonce)) + enc.finalize()
        self._key = session_key[:16]
        _LOGGER.debug("Tuya session key established with %s", self.host)

    def _encode_json(self, cmd: int, obj: dict[str, Any]) -> bytes:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        if cmd not in NO_VERSION_HEADER:
            raw = VERSION_HEADER + raw
        return raw

    def _send(self, cmd: int, payload: bytes) -> None:
        self._seqno += 1
        self._writer.write(pack_message(self._seqno, cmd, payload, self._key))

    async def _send_wait(self, cmd: int, payload: bytes) -> TuyaMessage:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiters[cmd] = fut
        try:
            self._send(cmd, payload)
            return await asyncio.wait_for(fut, TIMEOUT_REPLY)
        finally:
            self._waiters.pop(cmd, None)

    async def _read_loop(self) -> None:
        err: Exception | None = None
        try:
            while not self._closing:
                data = await self._reader.read(4096)
                if not data:
                    break
                self._buffer += data
                self._process_buffer()
        except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
            err = e
        self._on_disconnected(err)

    def _process_buffer(self) -> None:
        """Consume every complete frame in the buffer; recover from desync."""
        while True:
            buf = self._buffer
            if len(buf) < HEADER_LEN:
                return
            prefix, _, _, cmd, length = struct.unpack(HEADER_FMT, buf[:HEADER_LEN])
            if prefix != PREFIX or length > MAX_PAYLOAD_LENGTH:
                self._buffer = buf[1:]  # desynced stream: rescan byte by byte
                continue
            frame_len = HEADER_LEN + length + 4
            if len(buf) < frame_len:
                return
            frame, self._buffer = buf[:frame_len], buf[frame_len:]
            try:
                msg = unpack_message(frame, self._key)
            except InvalidTag as e:
                # wrong key (or session): surface to the pending waiter
                fut = self._waiters.get(cmd)
                if fut and not fut.done():
                    fut.set_exception(e)
                continue
            except DecodeError as e:
                _LOGGER.warning("Dropping undecodable frame (cmd=%s): %s", cmd, e)
                continue
            self._dispatch(msg)

    def _dispatch(self, msg: TuyaMessage) -> None:
        fut = self._waiters.pop(msg.cmd, None)
        if fut and not fut.done():
            fut.set_result(msg)
            return
        if msg.cmd == STATUS and msg.payload and self.listener:
            dps = dps_from_payload(msg.payload)
            if dps:
                self.listener.status_updated(dps)

    async def _heartbeat_loop(self) -> None:
        while not self._closing:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await self._send_wait(
                    HEART_BEAT,
                    self._encode_json(
                        HEART_BEAT, {"gwId": self.dev_id, "devId": self.dev_id}
                    ),
                )
            except (TimeoutError, ConnectionError, OSError) as err:
                _LOGGER.warning("Heartbeat to %s failed, closing: %s", self.host, err)
                self.close()
                return

    def _on_disconnected(self, err: Exception | None) -> None:
        if self._closing:
            return
        self._closing = True
        for task in self._tasks:
            task.cancel()
        for fut in self._waiters.values():
            if not fut.done():
                fut.set_exception(ConnectionError("connection lost"))
        self._waiters.clear()
        if self._writer:
            self._writer.close()
        if err:
            _LOGGER.warning("Tuya connection to %s lost: %s", self.host, err)
        else:
            _LOGGER.info("Tuya connection to %s closed", self.host)
        if self.listener:
            self.listener.disconnected()
