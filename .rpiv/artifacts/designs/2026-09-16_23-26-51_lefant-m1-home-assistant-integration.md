---
date: 2026-09-16T23:26:51+0200
author: Andrea Forlin
commit: e935121
branch: develop
repository: ha-lefant
topic: lefant-m1-home-assistant-integration
tags: [design, home-assistant, tuya, vacuum, asyncio]
status: completed
parent: .rpiv/artifacts/research/2026-09-08_22-09-21_lefant-m1-home-assistant-integration.md
last_updated: 2026-09-16T23:26:51+0200
last_updated_by: Andrea Forlin
---

# Design: Lefant M1 Home Assistant Custom Component

## Summary
Componente custom Home Assistant (`custom_components/lefant_m1`) che parla il **protocollo Tuya locale (LAN, handshake 3.5)** con un **client asyncio minimal scritto ad hoc** (niente vendoring GPL di localtuya, niente tinytuya sync). Socket TCP persistente con heartbeat: il robot **spinge** ogni cambio DP (stato, batteria) e un coordinator custom push-based (pattern localtuya) propaga lo stato alle entità. Config flow manuale (Device ID + Local Key + IP). Deliverable: entità `vacuum` (start/pause/stop/return) + sensore batteria.

## Requirements
- Entità vacuum con start/pause/stop/return-to-base + stato (FRD scope base)
- Sensore batteria (DP23 `battery_percentage`)
- Config flow: Device ID + Local Key + IP manuale, validazione connessione prima del salvataggio
- Protocollo Tuya locale (TCP 6668, handshake 3.5) — nessun cloud, nessun doppio pairing (il robot resta appaiato nell'app Lefant)
- Local Key estratta una volta dall'app Lefant (MITM, v. research Q5)
- Unit test minimi (mapping stato, framing protocollo)

## Current State Analysis
Repo greenfield: solo commit `ab8f5dc` con albero vuoto; niente codice, niente test infra, niente dipendenze.

### Key Discoveries
- **Il M1 è un device Tuya**: schema DP della famiglia Lefant (research Q5, da confermare sul device) — DP1 `switch_go` bool rw (start), DP2 `pause` bool rw, DP3 `switch_charge` bool rw (return), DP4 `mode` enum, DP5 `status` enum ro, DP9 `suction`, DP23 `battery_percentage`, DP27 `seek`, DP28 `total_error`. Protocollo **3.5** (validato da hectorzin/Lefant-Home-Assistant-LocalTuya su M210 Pro Omni, app Lefant 3.3.25).
- **Mapping stato→HA** (research L72): DP5 `cleaning`→CLEANING, `paused`→PAUSED, `goto_charge`/`relocating`→RETURNING, `charging`/`charge_done`→DOCKED, `standby`/`sleep`→IDLE; DP28 ≠0 → ERROR.
- **Bitmask features** `START|PAUSE|STOP|RETURN_HOME|STATE` = 12316 (research: frontend `src/data/vacuum.ts` nasconde i pulsanti senza i bit; websocket gating in `vacuum/websocket.py:36-44`).
- **Setup lifecycle**: `ConfigEntryNotReady` → retry esponenziale automatico di HA (max 600s, `config_entries.py:839-876`); pattern aurora (`async_config_entry_first_refresh` + `async_forward_entry_setups`).
- **localtuya (GPL-3.0)**: coordinator **custom push-based** (`coordinator.py`, 677 righe) — NON usa `DataUpdateCoordinator`; il suo `core/pytuya/` è pure asyncio con `TuyaProtocol`, heartbeat 8.3s, protocollo 3.5 incluso. Non vendibile (GPL contamina), ma è il pattern da replicare.
- **tinytuya (MIT)**: sync/thread-based — non adatto al loop HA; però documenta con esattezza il protocollo 3.5 (`core/header.py`, `core/command_types.py`, `core/XenonDevice.py:893-982` negoziazione chiave sessione, `core/message_helper.py` framing 6699).
- **Protocollo 3.5** (verificato su tinytuya source): frame prefix `0x00006699`, header `>IHIII` (prefix, 0, seqno, cmd, length), payload GCM AES-128 (IV 12B random prepeso, AAD = header da 16B dopo prefix, tag 16B), suffix `0x00009966`. Comandi: SESS_KEY_NEG_START=3, SESS_KEY_NEG_RESP=4, SESS_KEY_NEG_FINISH=5, CONTROL_NEW=0x0d, STATUS=0x08, HEART_BEAT=0x09, DP_QUERY_NEW=0x10, UPDATEDPS=0x12. Chiave sessione = AES-GCM(local_key, iv=nonce[:12]).encrypt(XOR(local_nonce, remote_nonce))[12:28].

## Scope
### Building
- `pytuya_client.py`: client Tuya LAN 3.5 pure-asyncio (framing 6699, negoziazione chiave sessione, heartbeat 8.3s, send DP, ricezione push DP, close)
- `coordinator.py`: coordinator push-based custom (socket persistente, riconnessione, fan-out ai listener)
- `config_flow.py`: form device_id/local_key/host con test connessione reale
- `vacuum.py`: `StateVacuumEntity` con features 12316, comandi DP1/DP2/DP3, activity da DP5+DP28
- `sensor.py`: batteria da DP23
- `manifest.json`, `const.py`, `__init__.py`, `hacs.json`, `README.md`
- Unit test minimi: framing/codec client + mapping stato→activity

### Not Building
- Suction/fan (DP9), locate (DP27), clean time/area/record — scope base FRD; aggiungere in v2 se richiesto
- Auto-discovery UDP (IP manuale; il device_id filtrerebbe il broadcast in futuro)
- Harness `pytest-homeassistant-custom-component` (test unit minimi, basta per codec+mapping)
- Integration Tuya cloud HA core (scartata dal developer al checkpoint)
- Vendoring localtuya (GPL-3.0) o tinytuya (sync)
- Reauth flow (chiave statica; chiave rifiutata = `cannot_connect` in v1)
- MQTT, scene, mappa pulizia, scheduling

## Decisions
- **D1 Transport — client asyncio minimal, 3.5-only**: ~300 righe MIT; skip completo dei path 55AA/3.3/3.4 (il Lefant fa 3.5, validated). Rischio crittografico mitigato dagli spec pubblici (tinytuya + tuya-iotos-embeded-sdk lan_protocol.h) e dai test di framing.
- **D2 Update — push su socket persistente** (non polling): heartbeat 8.3s come localtuya (`core/pytuya/__init__.py:132` HEARTBEAT_INTERVAL); il robot spinge ogni cambio DP. `iot_class: local_push`. Coordinator custom (pattern localtuya `coordinator.py`), niente `DataUpdateCoordinator` (non c'è nulla da "poll").
- **D3 Config flow — IP manuale** (decisione developer): Device ID + Local Key + host obbligatorio; test connessione + handshake nel flow; errori `cannot_connect`/`invalid_key`/`AlreadyConfigured`.
- **D4 Entità — vacuum + battery sensor separata**: convenzione HA (vacuum entity non ha batteria; research Q6: roomba core espone sensor separato).
- **D5 Comandi**: start → DP1=true; pause → DP2=true, resume → DP2=false; stop → DP2=true (pause; M1 non distingue stop da pause, come localtuya DEFAULT_STOP_STATUS) + update stato; return → DP3=true. (Schema DP research Q5; conferma sul device al primo test.)
- **D6 Test — unit minimi**: `test_pytuya_client.py` (codec frame round-trip, negoziazione chiave con nonce noti, parse push JSON) + `test_state_mapping.py` (DP5→VacuumActivity). Zero framework HA.
- **D7 Setup/retry**: `async_setup_entry` apre la connessione; robot irraggiungibile → `ConfigEntryNotReady` (HA riprova da solo); unload chiude socket. Chiave statica → nessun reauth.

## Desired End State
Un componente HACS installabile: dopo config flow (device_id + local_key + IP), in HA compaiono `vacuum.lefant_m1` e `sensor.lefant_m1_battery`; lo stato segue il robot in tempo reale (push); start/pause/stop/return funzionano dai pulsanti della vacuum card. Robot non raggiungibile → entità `unavailable`, HA riprova con backoff. Nessun cloud coinvolto.

## File Map
```
custom_components/lefant_m1/
├── manifest.json        (NEW)
├── const.py             (NEW)  # DP ids, mapping stato, costanti protocollo
├── pytuya_client.py     (NEW)  # transport 3.5 asyncio
├── config_flow.py       (NEW)
├── coordinator.py       (NEW)
├── __init__.py          (NEW)
├── vacuum.py            (NEW)
└── sensor.py            (NEW)
hacs.json                (NEW)
tests/
├── test_pytuya_client.py (NEW)
└── test_state_mapping.py (NEW)
README.md                (NEW)
```

## Ordering Constraints
- Slice 1 (transport) è foundation: config flow (Slice 2) ne usa il client per validare; coordinator (Slice 3) lo incapsula; entità (Slice 4) consumano il coordinator.
- `const.py` nasce in Slice 2 ma i DP id citati dal client (Slice 1) restano parametri generici (dict dp→value) — nessuna dipendenza inversa.

## Verification Notes
- Framing client: test round-trip pack/unpack + un vettore fisso (nonce noti) per la negoziazione chiave → hash della session key attesa. Copre il rischio crittografico di D1.
- Mapping stato: tabella DP5→activity, incl. total_error≠0→ERROR.
- Setup/retry: manuale sul device (ConfigEntryNotReady). Copertura unit per il resto.
- Success criteria dettagliati in ciascuna slice.

## Performance Considerations
- Una sola connessione TCP persistente; push = zero polling; heartbeat 8.3s è traffico trascurabile.
- Listener fan-out O(n) su n entità (2) — irrilevante.
- `MAX_PAYLOAD_LENGTH` cap 1440B come tinytuya (`core/const.py`) per respingere stream corrotti.

## Migration Notes
Greenfield — nessuna migrazione. Dati persistenti: solo `core.config_entries` (gestito da HA).

## Pattern References
- Setup entry completo: `homeassistant/components/aurora/__init__.py` (research Q1)
- Vacuum entity: HA core `roomba/vacuum.py:29-40` (activity mapping), `tuya/vacuum.py:29-38`
- Push coordinator: localtuya `coordinator.py` (HassLocalTuyaData + TuyaDevice, `status_update`)
- Protocollo 3.5: tinytuya `core/XenonDevice.py:893-982`, `core/message_helper.py`, `core/header.py`, `core/command_types.py` (MIT)

## Developer Context
- Pivot dal checkpoint (2026-09-16): cloud Lefant inesistente → protocollo Tuya LAN. Robot resta appaiato nell'app Lefant; Local Key estratta via MITM dell'app una sola volta.
- Appaia M210 Pro Omni validato con protocollo 3.5; M1 famiglia stessa (DP da confermare al primo test con log del device).
- Developer ha scartato l'integrazione Tuya ufficiale HA (UX).
- Python: usare la stdlib `cryptography` per AES-GCM (dependency già comune; dichiarata in manifest).

## References
- Research: `.rpiv/artifacts/research/2026-09-08_22-09-21_lefant-m1-home-assistant-integration.md`
- FRD: `.rpiv/artifacts/discover/2026-09-08_21-11-22_lefant-m1-home-assistant-integration.md`
- localtuya: https://github.com/xZetsubou/hass-localtuya (GPL-3.0, pattern reference)
- tinytuya: https://github.com/jasonacox/tinytuya (MIT, protocol reference)
- hectorzin/Lefant-Home-Assistant-LocalTuya (estrazione chiave, validazione 3.5)

## Architecture
<!-- placeholder — riempito slice per slice -->

### custom_components/lefant_m1/pytuya_client.py — NEW
```python
# placeholder Slice 1
```

### tests/test_pytuya_client.py — NEW
```python
# placeholder Slice 1
```

### custom_components/lefant_m1/manifest.json — NEW
```json
# placeholder Slice 2
```

### custom_components/lefant_m1/const.py — NEW
```python
# placeholder Slice 2
```

### custom_components/lefant_m1/config_flow.py — NEW
```python
# placeholder Slice 2
```

### custom_components/lefant_m1/coordinator.py — NEW
```python
# placeholder Slice 3
```

### custom_components/lefant_m1/__init__.py — NEW
```python
# placeholder Slice 3
```

### custom_components/lefant_m1/vacuum.py — NEW
```python
# placeholder Slice 4
```

### custom_components/lefant_m1/sensor.py — NEW
```python
# placeholder Slice 4
```

### tests/test_state_mapping.py — NEW
```python
# placeholder Slice 4
```

### hacs.json — NEW
```json
# placeholder Slice 4
```

### README.md — NEW
```markdown
# placeholder Slice 4
```

## Slices

### Slice 1 — Transport Tuya LAN 3.5
Client asyncio minimal: framing 6699 (pack/unpack), negoziazione chiave sessione (3 step), client `asyncio.Protocol` con heartbeat 8.3s, `send_dp`/`query_dps`, dispatch push ai listener, `close`.
Files: `custom_components/lefant_m1/pytuya_client.py` (NEW), `tests/test_pytuya_client.py` (NEW)
Depends on: nothing (foundation)

### Slice 2 — Costanti, manifest, config flow
DP id + mapping stato→activity in `const.py`; `manifest.json` (domain, iot_class local_push, requirement `cryptography`); config flow con test connessione reale.
Files: `const.py` (NEW), `manifest.json` (NEW), `config_flow.py` (NEW)
Depends on: Slice 1

### Slice 3 — Coordinator push + setup entry
Coordinator custom: possiede connessione e riconnessione, bridge `status_update` → listener; `__init__.py` con `async_setup_entry` (ConfigEntryNotReady) e unload.
Files: `coordinator.py` (NEW), `__init__.py` (NEW)
Depends on: Slice 1, 2

### Slice 4 — Entità + packaging + test mapping
`vacuum.py` (StateVacuumEntity, features 12316), `sensor.py` (batteria), test mapping stato, `hacs.json`, `README.md`.
Files: `vacuum.py` (NEW), `sensor.py` (NEW), `tests/test_state_mapping.py` (NEW), `hacs.json` (NEW), `README.md` (NEW)
Depends on: Slice 3

## Design History
- Slice 1 — Transport Tuya LAN 3.5 — completed
- Slice 2 — Costanti, manifest, config flow — completed
- Slice 3 — Coordinator push + setup entry — completed
- Slice 4 — Entità + packaging + test mapping — completed
