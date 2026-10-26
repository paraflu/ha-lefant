#!/usr/bin/env python3
"""Diagnostica di sola rete per il Lefant M1 (protocollo Tuya LAN).

Risponde a una sola domanda: **il robot accetta connessioni Tuya in LAN?**

Non usa e non chiede alcuna chiave: nessun local key, nessun login, nessun
segreto viene letto, scritto o registrato. Gli identificativi dei dispositivi
trovati vengono mascherati nell'output.

Fasi
----
A. Probe TCP sulla porta 6668 (la porta del protocollo Tuya locale).
B. Per ogni host che risponde, invio di un DP_QUERY non cifrato in framing
   55AA e classificazione della risposta:
     - JSON in chiaro            -> dispositivo v3.1
     - payload binario           -> dispositivo v3.3 (cifrato)
     - connessione chiusa/vuota  -> probabile v3.4/3.5 (negoziazione richiesta)
C. Ascolto passivo UDP 6666/6667 per eventuali annunci broadcast.

Uso
---
    python3 tools/diagnose_tuya_lan.py                      # scansione /24 locale
    python3 tools/diagnose_tuya_lan.py --host 192.168.1.50  # solo un IP
    python3 tools/diagnose_tuya_lan.py --subnet 10.0.0.0/24 --timeout 2

Attenzione: un esito negativo sulla fase C non e' una prova di assenza. Gli
annunci UDP possono essere disabilitati o filtrati; la fase A e' quella
dirimente.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import struct
import sys
import threading
import time
import zlib
from dataclasses import dataclass, field
from hashlib import md5

TCP_PORT = 6668
UDP_PORTS = (6666, 6667, 7000)
DEFAULT_TIMEOUT = 3.0
MAX_HOSTS = 1024  # rifiuta subnet piu' grandi: questa e' una diagnostica, non un port scanner

# Framing 55AA (v3.1 - v3.3, usato solo per la sonda di versione)
PREFIX_55AA = 0x000055AA
SUFFIX_55AA = 0x0000AA55
HEADER_55AA = ">IIII"  # prefix, seqno, cmd, length
CMD_DP_QUERY = 10

# Framing 6699 (v3.4 - v3.5)
PREFIX_6699 = 0x00006699
SUFFIX_6699 = 0x00009966
HEADER_6699 = ">IHIII"  # prefix, unknown, seqno, cmd, length (18 byte)
HEADER_55AA_FMT = ">4I"  # prefix, seqno, cmd, length (16 byte)
HEADER_LEN_6699 = struct.calcsize(HEADER_6699)
HEADER_LEN_55AA = struct.calcsize(HEADER_55AA_FMT)

# Chiave pubblica del protocollo per gli annunci UDP (tuya-convert / tinytuya).
# NON e' una chiave utente: e' una costante del protocollo, uguale per tutti i dispositivi.
UDP_DISCOVERY_KEY = md5(b"yGAdlopoPVldABfn").digest()


@dataclass
class ProbeResult:
    """Esito della sonda su un singolo host."""

    host: str
    port_open: bool = False
    version_guess: str = "sconosciuta"
    detail: str = ""
    responded_bytes: int = 0
    adverts: list[dict] = field(default_factory=list)


def mask(value: object, keep: int = 4) -> str:
    """Mascherа un identificativo lasciando visibili solo inizio e fine."""
    text = str(value or "")
    if len(text) <= keep * 2:
        return f"<{len(text)} caratteri>"
    return f"{text[:keep]}...{text[-keep:]}"


def local_ipv4() -> str | None:
    """IP IPv4 dell'interfaccia usata come default route (nessun pacchetto inviato)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))  # TEST-NET-1: non instradabile, nessun traffico reale
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def default_subnet() -> str | None:
    ip = local_ipv4()
    if not ip or ip.startswith("127."):
        return None
    network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
    return str(network)


def build_dp_query_frame(seqno: int = 1) -> bytes:
    """Frame 55AA con DP_QUERY vuoto, non cifrato (equivalente a una v3.1)."""
    payload = b""
    length = len(payload) + 8  # payload + crc(4) + suffix(4)
    header = struct.pack(HEADER_55AA, PREFIX_55AA, seqno, CMD_DP_QUERY, length)
    body = header + payload
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return body + struct.pack(">I", crc) + struct.pack(">I", SUFFIX_55AA)


def classify_response(data: bytes) -> tuple[str, str]:
    """Traduce la risposta grezza in una stima di versione protocollo."""
    if not data:
        return "v3.4/3.5 (probabile)", "connessione chiusa senza dati: negoziazione richiesta"

    stripped = data.lstrip(b"\x00")
    if stripped[:1] in (b"{", b"["):
        try:
            parsed = json.loads(stripped.decode("utf-8", "replace"))
        except ValueError:
            return "v3.1 (probabile)", "testo JSON non valido"
        if isinstance(parsed, dict) and "devId" in parsed:
            return "v3.1", f"JSON in chiaro (devId {mask(parsed.get('devId'))})"
        return "v3.1 (probabile)", "JSON in chiaro senza devId"

    if data[:4] == b"\x00\x00\x55\xaa":
        return "v3.3 (probabile)", "frame 55AA con payload cifrato"
    if data[:2] == b"\x00\x00":
        return "v3.4/3.5 (probabile)", "frame cifrato 6699 o handshake"
    return "sconosciuta", "risposta non riconosciuta"


def probe_tcp(host: str, timeout: float) -> ProbeResult:
    """Fase A+B su un host: apertura 6668 e sonda di versione."""
    result = ProbeResult(host=host)
    try:
        with socket.create_connection((host, TCP_PORT), timeout=timeout) as sock:
            result.port_open = True
            sock.settimeout(timeout)
            try:
                sock.sendall(build_dp_query_frame())
                data = sock.recv(4096)
            except socket.timeout:
                result.version_guess = "v3.4/3.5 (probabile)"
                result.detail = "porta aperta, nessuna risposta alla sonda non cifrata"
                return result
            except OSError as err:
                result.detail = f"porta aperta, errore in sonda: {err.__class__.__name__}"
                return result
            result.responded_bytes = len(data)
            result.version_guess, result.detail = classify_response(data)
    except ConnectionRefusedError:
        result.detail = "porta chiusa (rifiutata)"
    except (socket.timeout, TimeoutError):
        result.detail = "nessuna risposta (host assente o filtrato)"
    except OSError as err:
        result.detail = f"errore di rete: {err.__class__.__name__}"
    return result


CMD_REQ_DEVINFO = 0x25  # broadcast su UDP 7000: i device v3.5 rispondono con le loro info


def active_discovery(duration: float) -> list[dict]:
    """Discovery attiva su UDP 7000: sollecita i device che non trasmettono da soli.

    Usa solo la chiave pubblica del protocollo (la stessa del discovery passivo).
    """
    own_ip = local_ipv4()
    if not own_ip:
        return []

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        return []

    import os

    plaintext = json.dumps({"from": "app", "ip": own_ip}, separators=(",", ":")).encode()
    length = len(plaintext) + 28  # iv(12) + ciphertext + tag(16)
    header = struct.pack(HEADER_6699, PREFIX_6699, 0, 1, CMD_REQ_DEVINFO, length)
    iv = os.urandom(12)
    encryptor = Cipher(algorithms.AES(UDP_DISCOVERY_KEY), modes.GCM(iv)).encryptor()
    encryptor.authenticate_additional_data(header[4:])
    body = iv + encryptor.update(plaintext) + encryptor.finalize() + encryptor.tag
    frame = header + body + struct.pack(">I", SUFFIX_6699)

    subnet_broadcast = str(ipaddress.IPv4Network(f"{own_ip}/24", strict=False).broadcast_address)
    targets = [subnet_broadcast, "255.255.255.255"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    adverts: list[dict] = []
    try:
        sock.bind((own_ip, 0))
        sock.settimeout(0.5)
        deadline = time.monotonic() + duration
        sent_at = 0.0
        while time.monotonic() < deadline:
            if time.monotonic() - sent_at > 2.0:
                for target in targets:
                    try:
                        sock.sendto(frame, (target, 7000))
                    except OSError:
                        pass
                sent_at = time.monotonic()
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            adverts.append(summarize_advert(addr[0], data))
    finally:
        sock.close()
    return adverts


def arp_mac(host: str) -> str | None:
    """MAC dal cache ARP locale (Linux/procfs). Nessun traffico aggiuntivo."""
    try:
        with open("/proc/net/arp", "r", encoding="utf-8") as handle:
            for line in handle.readlines()[1:]:
                fields = line.split()
                if len(fields) >= 4 and fields[0] == host:
                    mac = fields[3]
                    if mac and mac != "00:00:00:00:00:00":
                        return mac
    except OSError:
        return None
    return None


def scan_hosts(hosts: list[str], timeout: float, workers: int = 64) -> list[ProbeResult]:
    """Fase A su piu' host, con concorrenza limitata."""
    results: list[ProbeResult] = []
    lock = threading.Lock()

    def worker(batch: list[str]) -> None:
        for host in batch:
            outcome = probe_tcp(host, timeout)
            if outcome.port_open:
                with lock:
                    results.append(outcome)

    chunks = [hosts[i::workers] for i in range(workers)]
    threads = [threading.Thread(target=worker, args=(chunk,), daemon=True) for chunk in chunks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(results, key=lambda r: ipaddress.IPv4Address(r.host))


def listen_udp(duration: float) -> list[dict]:
    """Fase C: ascolto passivo degli annunci broadcast Tuya."""
    adverts: list[dict] = []
    sockets: list[socket.socket] = []
    for port in UDP_PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", port))
        except OSError:
            sock.close()
            continue
        sock.settimeout(0.5)
        sockets.append(sock)

    deadline = time.monotonic() + duration
    while time.monotonic() < deadline and sockets:
        for sock in list(sockets):
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                sockets.remove(sock)
                continue
            adverts.append(summarize_advert(addr[0], data))

    for sock in sockets:
        sock.close()
    return adverts


def summarize_advert(host: str, data: bytes) -> dict:
    """Riepilogo non sensibile di un annuncio UDP."""
    summary: dict = {"host": host, "bytes": len(data), "source": "udp", "fields": {}}
    parsed = decode_advert(data)
    if parsed is None:
        summary["note"] = "annuncio non decodificabile"
        return summary
    if "gwId" in parsed:
        summary["fields"]["device_id"] = mask(parsed.get("gwId"))
    for key in ("productKey", "version", "encrypt", "active", "dev_type"):
        if key in parsed:
            summary["fields"][key] = parsed.get(key)
    if not summary["fields"]:
        summary["note"] = "annuncio decodificato senza campi utili"
    return summary


def decode_advert(data: bytes) -> dict | None:
    """Decodifica un annuncio UDP Tuya usando la chiave pubblica del protocollo."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:  # pragma: no cover - dipende dall'ambiente
        return None

    try:
        if len(data) >= HEADER_LEN_6699 and data[:4] == b"\x00\x00\x66\x99":
            prefix, _unknown, _seqno, _cmd, length = struct.unpack(HEADER_6699, data[:HEADER_LEN_6699])
            if prefix != PREFIX_6699 or length < 28 or len(data) < HEADER_LEN_6699 + length:
                return None
            body = data[HEADER_LEN_6699 : HEADER_LEN_6699 + length]
            aad = data[4:HEADER_LEN_6699]
            plain = AESGCM(UDP_DISCOVERY_KEY).decrypt(body[:12], body[12:], aad)
            return _as_json(plain)

        if len(data) >= HEADER_LEN_55AA and data[:4] == b"\x00\x00\x55\xaa":
            _prefix, _seqno, _cmd, length = struct.unpack(HEADER_55AA_FMT, data[:HEADER_LEN_55AA])
            if length < 8 or len(data) < HEADER_LEN_55AA + length:
                return None
            payload = data[HEADER_LEN_55AA : HEADER_LEN_55AA + length - 8]
            if payload[:1] == b"{":
                return _as_json(payload)
            # alcuni frame (cmd UDP_NEW=0x13) hanno un retcode di 4 byte prima del blob cifrato
            if len(payload) > 4 and payload[:1] == b"\x00" and (len(payload) - 4) % 16 == 0:
                payload = payload[4:]
            decryptor = Cipher(algorithms.AES(UDP_DISCOVERY_KEY), modes.ECB()).decryptor()
            padded = decryptor.update(payload) + decryptor.finalize()
            if not padded:
                return None
            pad = padded[-1]
            return _as_json(padded[:-pad] if 0 < pad <= 16 else padded)
    except Exception:  # decodifica best-effort: qualsiasi anomalia resta non conclusiva
        return None
    return None


def _as_json(raw: bytes) -> dict | None:
    text = raw.rstrip(b"\x00").decode("utf-8", "replace")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def print_report(
    results: list[ProbeResult],
    adverts: list[dict],
    scanned: int,
    duration: float,
    expect: str | None = None,
) -> int:
    """Stampa il verdetto. Ritorna l'exit code (0 tuya trovato, 1 nessun indizio)."""
    own_ip = local_ipv4()
    ident: dict[str, dict] = {}
    for advert in adverts:
        fields = advert.get("fields") or {}
        if fields:
            ident.setdefault(advert["host"], fields)

    candidates = [res for res in results if res.host != own_ip]
    identified = [res for res in candidates if res.host in ident]

    print("=" * 72)
    print("DIAGNOSTICA RETE — Lefant M1 / protocollo Tuya locale")
    print("=" * 72)
    print(f"Host analizzati: {scanned}    Porta TCP: {TCP_PORT}    Attesa UDP: {duration:.1f}s")
    print()

    if candidates:
        print(f"Host con porta {TCP_PORT} APERTA: {len(candidates)}")
        for res in candidates:
            print(f"  - {res.host}")
            print(f"      versione ipotizzata : {res.version_guess}")
            print(f"      dettaglio           : {res.detail}")
            mac = arp_mac(res.host)
            if mac:
                print(f"      MAC                 : {mac} (OUI {mac[:8]})")
            fields = ident.get(res.host)
            if fields:
                detail = ", ".join(f"{k}={v}" for k, v in fields.items())
                print(f"      identificato        : {detail}")
            if res.responded_bytes:
                print(f"      byte ricevuti       : {res.responded_bytes}")
    else:
        print(f"Host con porta {TCP_PORT} aperta: nessuno")
    print()

    decoded = [a for a in adverts if a.get("fields")]
    if decoded:
        print(f"Annunci UDP decodificati: {len(decoded)} (da {len(ident)} dispositivi)")
        for host, fields in ident.items():
            detail = ", ".join(f"{k}={v}" for k, v in fields.items())
            mark = ""
            if expect:
                masked = str(fields.get("device_id", ""))
                mark = "   <-- CORRISPONDE AL PREFISSO" if masked.startswith(expect) else ""
            print(f"  - {host}: {detail}{mark}")
    else:
        print("Annunci UDP decodificati: nessuno (non conclusivo: possono essere assenti o filtrati)")
    print()

    print("-" * 72)
    matched: list[ProbeResult] = []
    if expect:
        matched = [
            res
            for res in candidates
            if str((ident.get(res.host) or {}).get("device_id", "")).startswith(expect)
        ]

    if candidates:
        if matched:
            best = matched[0]
        elif identified:
            best = identified[0]
        else:
            best = candidates[0]
        print("VERDETTO: la rete espone almeno un listener Tuya in LAN.")
        print(f"  host candidato      : {best.host}")
        print(f"  versione ipotizzata : {best.version_guess}")
        if matched:
            print("  identificazione     : ROBOT ATTESO, confermato dal prefisso del device id")
        elif best.host in ident:
            print("  identificazione     : confermata da annuncio UDP (device id e productKey sopra)")
        else:
            print("  identificazione     : nessun annuncio UDP associato a questo IP")
        if expect and not matched:
            print(f"  attenzione          : nessun annuncio con prefisso '{expect}' in questa finestra.")
            print("                        Il robot annuncia a raffiche: ripetere con --udp-wait piu' alto,")
            print("                        oppure controllare che sia acceso e in rete.")
        print("  attenzione          : il tool non distingue il robot da altri dispositivi Tuya.")
        print("                        Per attribuire l'IP giusto: spegnere il robot e ripetere,")
        print("                        oppure confrontare l'IP con quello mostrato dal router.")
        return 0

    print("VERDETTO: nessun listener Tuya rilevato su questa rete.")
    print("  Possibili cause, in ordine di probabilita':")
    print("    1. IP del robot diverso dalla subnet scansionata (riprovare con --host)")
    print("    2. robot spento, in carica su base scollegata, o fuori dalla rete locale")
    print("    3. dispositivo non basato su Tuya LAN: l'ipotesi di questo repo decade")
    print("  Nota: gli annunci UDP assenti non dimostrano nulla.")
    return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica se il robot risponde al protocollo Tuya locale (nessuna chiave usata)."
    )
    parser.add_argument("--host", action="append", default=[], help="IP del robot (ripetibile)")
    parser.add_argument("--subnet", help="subnet da scansionare, es. 192.168.1.0/24")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="timeout per host in secondi")
    parser.add_argument("--udp-wait", type=float, default=5.0, help="secondi di ascolto annunci UDP")
    parser.add_argument("--expect", help="prefisso atteso del device id (es. le prime 4 cifre del seriale)")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    hosts: list[str] = list(dict.fromkeys(args.host))
    if not hosts:
        subnet = args.subnet or default_subnet()
        if not subnet:
            print("Impossibile determinare la subnet locale: usare --host o --subnet.", file=sys.stderr)
            return 2
        network = ipaddress.IPv4Network(subnet, strict=False)
        if network.num_addresses > MAX_HOSTS:
            print(
                f"Subnet {subnet} troppo ampia ({network.num_addresses} indirizzi, limite {MAX_HOSTS}). "
                "Usare --host con l'IP del robot.",
                file=sys.stderr,
            )
            return 2
        hosts = [str(addr) for addr in network.hosts()]
        print(f"Subnet in analisi: {network} ({len(hosts)} host)")

    results = scan_hosts(hosts, args.timeout)
    passive = listen_udp(args.udp_wait)
    active = active_discovery(max(args.udp_wait, 6.0))
    adverts = passive + active
    return print_report(results, adverts, len(hosts), args.udp_wait, args.expect)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
