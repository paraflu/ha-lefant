"""Adapter Tinytuya per il canale locale Tuya del Lefant M1.

Perché esiste
-------------
`pytuya_client.py` parla **solo** il protocollo 3.5 (framing 0x6699, AES-GCM,
negoziazione di sessione). Il robot M1 misurato in rete dichiara e usa il
protocollo **3.3** (framing 55AA, AES-ECB sulla local key, nessun handshake),
quindi quel client non può completare nemmeno il primo frame.

Questo adapter delega il protocollo a `tinytuya` (MIT, supporta 3.1/3.3/3.4/3.5)
e mantiene la stessa interfaccia usata dal coordinator:

    await client.connect()
    dps = await client.query_dps()
    client.set_dps({dp: value})
    client.close()
    listener.status_updated(dps) / listener.disconnected()

Il blocco sincrono di tinytuya viene eseguito in un thread dedicato, quindi
l'event loop di Home Assistant non viene mai bloccato.

Differenza di semantica da tenere presente: Tinytuya è request/response, quindi
gli aggiornamenti arrivano da un ciclo di polling interno (default 4 s) e non
da un push del dispositivo. Resta comunque traffico minimo su LAN.

La local key non viene mai registrata nei log: se un errore la contiene, il
messaggio viene filtrato prima di essere emesso.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

# Versione misurata sul Lefant M1 (annuncio di rete + risposta 55AA alla DP_QUERY).
DEFAULT_PROTOCOL_VERSION = 3.3
SUPPORTED_VERSIONS = (3.1, 3.2, 3.3, 3.4, 3.5)

DEFAULT_POLL_INTERVAL = 4.0
DEFAULT_TIMEOUT = 5.0

# Codici errore tinytuya (dict {'Error','Err','Payload'}).
_ERR_CONNECT = 901
_ERR_TIMEOUT = 902
_ERR_DEVTYPE = 908
_ERR_KEY_OR_VER = 914
_AUTH_ERROR_CODES = frozenset({904, 914})  # payload non decifrabile / chiave o versione errate


class TuyaLanError(Exception):
    """Errore generico del canale locale Tuya."""


class TuyaLanConnectionError(TuyaLanError):
    """Dispositivo irraggiungibile o connessione interrotta."""


class TuyaLanAuthError(TuyaLanError):
    """Local key errata o versione di protocollo non corretta."""


class TinytuyaClient:
    """Client LAN Tuya basato su tinytuya, con interfaccia compatibile col coordinator.

    Parametri
    ---------
    host, device_id, local_key:
        Stessi dati del config flow attuale.
    listener:
        Oggetto duck-typed con `status_updated(dps: dict)` e `disconnected()`.
    version:
        Versione del protocollo. Default 3.3 per il Lefant M1.
    device_factory:
        Iniettabile nei test per sostituire `tinytuya.Device`.
    """

    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        listener: Any = None,
        version: float = DEFAULT_PROTOCOL_VERSION,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        device_factory: Callable[..., Any] | None = None,
    ) -> None:
        if float(version) not in SUPPORTED_VERSIONS:
            raise ValueError(f"Versione protocollo non supportata: {version!r}")

        self.host = host
        self.dev_id = device_id
        self.listener = listener
        self.version = float(version)
        self.poll_interval = poll_interval
        self.timeout = timeout

        self._local_key = local_key
        self._device_factory = device_factory
        self._device: Any | None = None
        self._dps: dict[str, Any] = {}
        self._connected = False
        self._closing = False
        self._poll_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ API

    async def connect(self) -> None:
        """Apre la connessione e valida chiave/versione con una prima query."""
        self._closing = False
        async with self._lock:
            await asyncio.to_thread(self._connect_sync)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def query_dps(self) -> dict[str, Any]:
        """Legge lo snapshot completo dei datapoint."""
        async with self._lock:
            return await asyncio.to_thread(self._query_sync)

    def set_dps(self, dps: dict[str, Any]) -> None:
        """Scrive datapoint. Fire-and-forget: l'esito arriva dal polling successivo."""
        if not dps:
            return
        if not self._connected:
            _LOGGER.debug("Scrittura DP ignorata: connessione non attiva (%s)", self.host)
            return
        asyncio.get_running_loop().create_task(self._write_dps(dps))

    def close(self) -> None:
        """Chiude connessione e ciclo di polling (idempotente)."""
        if self._closing:
            return
        self._closing = True
        self._connected = False
        task = self._poll_task
        self._poll_task = None
        if task and not task.done():
            task.cancel()
        device, self._device = self._device, None
        if device is not None:
            try:
                device.close()
            except Exception:  # pragma: no cover - chiusura best effort
                _LOGGER.debug("Errore in chiusura connessione verso %s", self.host, exc_info=True)
        if self.listener is not None:
            self.listener.disconnected()

    # ------------------------------------------------------------ proprietà

    @property
    def is_connected(self) -> bool:
        """True se la connessione è attiva e non in chiusura."""
        return self._connected and not self._closing

    @property
    def dps(self) -> dict[str, Any]:
        """Ultimo snapshot noto."""
        return dict(self._dps)

    # Compatibilità con il coordinator attuale, che legge `client._writer` e
    # `client._closing` per calcolare la disponibilità delle entità.
    # Questi due shim servono solo a permettere la sostituzione drop-in e
    # possono sparire quando il coordinator userà `is_connected`.
    @property
    def _writer(self) -> Any | None:  # noqa: N802 - nome privato per compatibilità
        return object() if self.is_connected else None

    # ------------------------------------------------------------ internals

    def _make_device(self) -> Any:
        if self._device_factory is not None:
            return self._device_factory(
                self.dev_id, self.host, self._local_key, version=self.version
            )
        import tinytuya  # import locale: dipendenza opzionale fino all'attivazione

        return tinytuya.Device(
            self.dev_id,
            address=self.host,
            local_key=self._local_key,
            version=self.version,
            persist=True,
            connection_timeout=self.timeout,
        )

    def _connect_sync(self) -> None:
        device = self._make_device()
        self._device = device
        result = device.status()
        self._raise_for_result(result)
        self._connected = True
        self._dps = dict(result.get("dps") or {})
        _LOGGER.debug(
            "Connesso a %s (device %s, protocollo %.1f)",
            self.host,
            _mask(self.dev_id),
            self.version,
        )

    def _query_sync(self) -> dict[str, Any]:
        device = self._device
        if device is None:
            raise TuyaLanConnectionError("connessione non aperta")
        result = device.status()
        self._raise_for_result(result)
        self._dps = dict(result.get("dps") or {})
        return dict(self._dps)

    def _write_sync(self, dps: dict[str, Any]) -> None:
        device = self._device
        if device is None:
            raise TuyaLanConnectionError("connessione non aperta")
        result = device.set_multiple_values(dps)
        self._raise_for_result(result)

    async def _write_dps(self, dps: dict[str, Any]) -> None:
        try:
            async with self._lock:
                await asyncio.to_thread(self._write_sync, dps)
        except TuyaLanError as err:
            _LOGGER.warning("Scrittura DP verso %s fallita: %s", self.host, err)
        except Exception:  # pragma: no cover - difensivo
            _LOGGER.debug("Errore inatteso in scrittura DP verso %s", self.host, exc_info=True)

    async def _poll_loop(self) -> None:
        """Aggiorna lo stato periodicamente e segnala la caduta della connessione."""
        try:
            while not self._closing:
                await asyncio.sleep(self.poll_interval)
                if self._closing:
                    return
                try:
                    async with self._lock:
                        dps = await asyncio.to_thread(self._query_sync)
                except TuyaLanError as err:
                    _LOGGER.warning("Polling verso %s fallito: %s", self.host, err)
                    self.close()
                    return
                if self.listener is not None and dps:
                    self.listener.status_updated(dps)
        except asyncio.CancelledError:  # pragma: no cover - chiusura normale
            raise

    @staticmethod
    def _raise_for_result(result: Any) -> None:
        """Traduce il dict d'errore di tinytuya in eccezioni tipizzate."""
        if not isinstance(result, dict):
            return
        if "dps" in result:
            return
        code = _coerce_code(result.get("Err"))
        message = _scrub(str(result.get("Error") or result))
        if code in _AUTH_ERROR_CODES:
            raise TuyaLanAuthError(f"local key o versione non accettate: {message}")
        if code in (_ERR_CONNECT, _ERR_TIMEOUT):
            raise TuyaLanConnectionError(message)
        if code == _ERR_DEVTYPE:
            raise TuyaLanError(f"tipo dispositivo non riconosciuto: {message}")
        if code is not None:
            raise TuyaLanError(f"errore dispositivo {code}: {message}")


def _coerce_code(value: Any) -> int | None:
    """tinytuya restituisce il codice errore come int oppure come stringa."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mask(value: str) -> str:
    text = str(value or "")
    if len(text) <= 8:
        return "<id>"
    return f"{text[:4]}...{text[-4:]}"


def _scrub(text: str) -> str:
    """Rimuove eventuali sequenze che possono contenere una chiave."""
    for token in ("local_key", "localkey", "local key", "key="):
        if token in text.lower():
            return "<messaggio contenente possibili credenziali, omesso>"
    return text
