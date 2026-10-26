#!/usr/bin/env python3
"""Lettura DP dal Lefant M1 via adapter Tinytuya (protocollo 3.3).

Serve a due cose, nell'ordine:
  1. verificare che la local key sia corretta e che il robot risponda;
  2. leggere i datapoint reali, così da correggere `const.py` con i valori
     effettivi invece di quelli ereditati da un altro modello.

La chiave NON si passa da riga di comando (finirebbe nella history della shell
e in `ps`): si legge dalla variabile d'ambiente `LEFANT_LOCAL_KEY`.

Uso
---
    export LEFANT_LOCAL_KEY='...'          # 16 caratteri, non condividerla
    python3 tools/probe_robot.py --host 192.168.3.117 --device-id bf23...

Opzioni utili:
    --version 3.3        versione del protocollo (default 3.3, misurata sull'M1)
    --dump-json          stampa lo snapshot completo dei DP (valori inclusi)
    --watch 30           osserva per 30 secondi e mostra solo i DP che cambiano

Sicurezza: la chiave non viene mai stampata; il device id viene mascherato
nell'intestazione e i valori dei DP sono dati di stato, non credenziali.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "lefant_m1"))

from tuya_lan_adapter import (  # noqa: E402
    DEFAULT_PROTOCOL_VERSION,
    TinytuyaClient,
    TuyaLanAuthError,
    TuyaLanConnectionError,
    TuyaLanError,
)

EXIT_OK = 0
EXIT_AUTH = 3
EXIT_CONN = 4
EXIT_ERROR = 5


class Printer:
    """Listener minimo: raccoglie gli aggiornamenti."""

    def __init__(self, watch: float) -> None:
        self.watch = watch
        self.changes: list[tuple[str, object, object]] = []
        self._last: dict[str, object] = {}

    def status_updated(self, dps: dict) -> None:
        for key, value in dps.items():
            previous = self._last.get(key)
            if key not in self._last or previous != value:
                self.changes.append((str(key), previous, value))
            self._last[key] = value

    def disconnected(self) -> None:
        return


def mask(value: str) -> str:
    text = value or ""
    return f"{text[:4]}...{text[-4:]}" if len(text) > 8 else "<id>"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Legge i datapoint dal Lefant M1 (solo lettura).")
    parser.add_argument("--host", required=True, help="IP del robot")
    parser.add_argument("--device-id", required=True, help="device id del robot")
    parser.add_argument("--version", type=float, default=DEFAULT_PROTOCOL_VERSION, help="versione protocollo")
    parser.add_argument("--dump-json", action="store_true", help="stampa lo snapshot completo dei DP")
    parser.add_argument("--watch", type=float, default=0.0, help="secondi di osservazione dei cambi")
    parser.add_argument("--poll", type=float, default=3.0, help="intervallo di polling in secondi")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    local_key = os.environ.get("LEFANT_LOCAL_KEY", "").strip()
    if not local_key:
        print(
            "LEFANT_LOCAL_KEY non impostata.\n"
            "  export LEFANT_LOCAL_KEY='<chiave di 16 caratteri>'\n"
            "Non passare la chiave da riga di comando.",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if len(local_key) != 16:
        print(f"LEFANT_LOCAL_KEY ha lunghezza {len(local_key)}, attesi 16 caratteri.", file=sys.stderr)
        return EXIT_ERROR

    listener = Printer(args.watch)
    client = TinytuyaClient(
        host=args.host,
        device_id=args.device_id,
        local_key=local_key,
        listener=listener,
        version=args.version,
        poll_interval=args.poll,
    )

    print(f"Robot: {args.host}  device {mask(args.device_id)}  protocollo {args.version:.1f}", flush=True)
    try:
        await client.connect()
    except TuyaLanAuthError as err:
        print(f"CHIAVE O VERSIONE NON ACCETTATE: {err}", file=sys.stderr)
        print("  Se il robot e' davvero 3.3, la local key e' sbagliata o appartiene a un altro dispositivo.", file=sys.stderr)
        return EXIT_AUTH
    except TuyaLanConnectionError as err:
        print(f"ROBOT NON RAGGIUNGIBILE: {err}", file=sys.stderr)
        return EXIT_CONN
    except TuyaLanError as err:
        print(f"ERRORE: {err}", file=sys.stderr)
        return EXIT_ERROR

    try:
        dps = await client.query_dps()
        print(f"\nConnessione riuscita. Datapoint ricevuti: {len(dps)}")
        for key in sorted(dps, key=lambda k: (len(k), k)):
            print(f"  DP {key:>4} = {dps[key]!r}")

        if args.dump_json:
            print("\nSnapshot JSON:")
            print(json.dumps(dps, indent=2, sort_keys=True, ensure_ascii=False))

        if args.watch > 0:
            print(f"\nOsservazione per {args.watch:.0f}s (mostro solo i cambiamenti)...")
            before = len(listener.changes)
            await asyncio.sleep(args.watch)
            changes = listener.changes[before:]
            if not changes:
                print("  nessun cambiamento osservato")
            for key, previous, value in changes:
                print(f"  DP {key:>4}: {previous!r} -> {value!r}")
    finally:
        client.close()

    print("\nSuggerimento: confronta i DP sopra con custom_components/lefant_m1/const.py.")
    return EXIT_OK


def main(argv: list[str]) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
