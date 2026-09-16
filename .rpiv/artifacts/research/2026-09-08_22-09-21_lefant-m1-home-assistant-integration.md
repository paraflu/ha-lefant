---
title: "Research: Lefant M1 Home Assistant Integration"
topic: lefant-m1-home-assistant-integration
date: 2026-09-08T22:09:21+0200
last_updated: 2026-09-08T22:09:21+0200
author: Andrea Forlin
repository: ha-lefant
branch: develop
commit: ab8f5dc
stage: research
chained_from: .rpiv/artifacts/discover/2026-09-08_21-11-22_lefant-m1-home-assistant-integration.md
---

# Research — Lefant M1 Home Assistant Integration

## Developer Context

Held decisions from discover, carried verbatim:

- **Target audience and distribution** — Q: "È per uso personale o distribuzione community?" → A: "HACS-ready da subito."
- **App binding and protocol domain** — Q: "Conosci il protocollo dell'M1 (MQTT/CoAP/HTTP)?" → A: "Uso l'app Lefant — robot già configurato in app e wifi."
- **Functional scope** — Q: "Quale insieme di funzionalità per la prima versione?" → A: "Solo base: vacuum entity + start/stop/pause/return + battery."
- **Integration path (cloud vs LAN)** — Q: "L'integrazione parla col cloud Lefant (stessa strada dell'app) o col robot in LAN?" → A: "Cloud API."
- **Authentication scheme** — Q: "Come si autentica l'integrazione al cloud Lefant?" → A: "Login email+password (config flow), token stored via HA credentials storage."
- **State update mechanism** — Q: "Polling REST o MQTT streaming per lo stato?" → A: "Polling (30-60s) via REST."

⚠️ **Research pivot (developer checkpoint, 2026-09-16)**: la strada "Cloud API Lefant + email/password" è **non implementabile** — non esiste una REST API Lefant pubblica; l'M1 è un device Tuya. L'integrazione Tuya ufficiale di HA è stata scartata dal developer ("risulta diversa l'esperienza utente e il robot non funziona bene con tuya"). Deciso al checkpoint: **component custom che parla il protocollo Tuya LOCALE (LAN) con chiave estratta una volta dall'app Lefant** — il robot resta appaiato nell'app Lefant, niente cloud, niente doppio pairing. Le tre decisioni FRD sopra marcate (Cloud API / email+password / polling REST) sono quindi superate: auth = inserimento Device ID + Local Key nel config flow; stato = polling locale 30-60s (o push, da decidere in design); `iot_class` = `local_polling`.

## Historical Context

- FRD discover: `.rpiv/artifacts/discover/2026-09-08_21-11-22_lefant-m1-home-assistant-integration.md`
- Scope questions: `.rpiv/scopetracer_result.txt`

## Precedents

- Greenfield assoluto: 1 solo commit `ab8f5dc` "Initial commit" (2026-09-08 20:42:57 +0200) con **albero vuoto**; nessun progetto simile in git history. Nessuna lezione da diff passati.
- Lezione strutturale: l'FRD e gli artifact sono **untracked in git** — non contare sulla cronologia git per recuperare artifact di fasi precedenti.

## Findings

Tutte le fonti verificate su **home-assistant/core tag 2026.9.1** (ultima release al 2026-09-08). Il repo è greenfield: nessun riferimento a file locali oltre agli artifact.

### Q1 — Config flow lifecycle

- `homeassistant/exceptions.py:240-255`: `ConfigEntryNotReady` ("config entry is not ready") e `ConfigEntryAuthFailed` ("config entry could not authenticate") sono i due esiti contrattuali del setup.
- `homeassistant/config_entries.py:839-876`: durante `async_setup_entry` → `ConfigEntryNotReady` imposta stato `SETUP_RETRY` con backoff **esponenziale automatico** `wait_time = min(2**tries * 5, SETUP_RETRY_MAX_WAIT=600)` + jitter microsecondi, retry via `async_call_later` (costanti a L141). `ConfigEntryAuthFailed` → warning + `async_start_reauth_if_available(hass)`.
- Pattern raccomandato:
  - `config_flow.py:async_step_user`: form `vol.Schema` con campo Device ID + Local Key (+ IP opzionale); chiave errata/non rispondente → `errors={"base": "cannot_connect"}`; device già presente → `AlreadyConfigured`.
  - `__init__.py:async_setup_entry`: robot non raggiungibile in LAN → `raise ConfigEntryNotReady` (HA gestisce retry; non blocca il bootstrap); credenziali Tuya invalidi → `raise ConfigEntryAuthFailed`.
  - `entry.data` = `{device_id, local_key, host}` → il reload riesegue il setup senza passare di nuovo per il flow.
- Worked example canonico (setup/unload completo): `homeassistant/components/aurora/__init__.py` — coordinator in `entry.runtime_data`, `async_config_entry_first_refresh()`, `async_forward_entry_setups`, `async_unload_platforms`.

### Q2 — Coordinator polling

- `homeassistant/helpers/update_coordinator.py` (725 righe):
  - `update_interval` è **property+setter** (L242-249) che normalizza a secondi; l'API `async_update_interval` non esiste più.
  - Scheduling via **`loop.call_at`** (L267-283; commento in fonte: "We use loop.call_at because DataUpdateCoordinator does not need an exact update interval") — non `async_track_time_interval`.
  - `_async_refresh` (L419-590): su errore log-once + `last_update_success=False`; nel `finally` (L582-583) rischedula solo se `not auth_failed and self._listeners and not self.hass.is_stopping`. **Nessun backoff automatico**: l'intervallo resta fisso; eventuale backoff adattivo è responsabilità dell'integrazione (override property `update_interval`).
  - `_retry_after` (L131, L272-274, L504): supporto nativo per rate-limit ("rispondi con eccezione che ha retry_after" → posticino il prossimo refresh).
  - `async_config_entry_first_refresh` (L317-330): alza `ConfigEntryNotReady` se il primo refresh fallisce → integrato col retry di setup.
  - `BaseCoordinatorEntity` (L650-681): `should_poll=False` (L664-667), listener in `async_added_to_hass`, update via `_handle_coordinator_update → async_write_ha_state`.
- Budget "stato aggiornato entro 2 poll cycles": un solo coordinator condiviso soddisfa il requisito con intervallo 30-60s.
- Nota LAN: il protocollo Tuya locale 3.4/3.5 **spinge lo stato** (status update / heartbeat ~4s) — LocalTuya usa il push. Per il vincolo FRD (30-60s) basta il polling; il push è un upgrade naturale da valutare in design.

### Q3 — Vacuum platform

- `homeassistant/components/vacuum/const.py:36-52` — `VacuumEntityFeature(IntFlag)` (valori verbatim): `TURN_ON=1`, `TURN_OFF=2` (entrambi deprecated per StateVacuumEntity), `PAUSE=4`, `STOP=8`, `RETURN_HOME=16`, `FAN_SPEED=32`, `STATUS=128` (deprecated), `SEND_COMMAND=256`, `LOCATE=512`, `CLEAN_SPOT=1024`, `MAP=2048`, `STATE=4096` (obbligatorio per StateVacuumEntity), `START=8192`, `CLEAN_AREA=16384`. **Nessun bit BATTERY** (bit 64 rimosso — battery è `_attr_battery_level`, sempre esposto). Gli alias legacy `SUPPORT_*` sono eliminati da core.
- Stato: `VacuumActivity(StrEnum)` (const.py:16-24): `CLEANING / DOCKED / IDLE / PAUSED / RETURNING / ERROR`.
- Comandi: subclassare **`StateVacuumEntity`**; `start` ha un percorso dedicato (`SERVICE_START` / `async_start()`, bit `START`); pause → `async_pause`/`PAUSE`, stop → `async_stop`/`STOP`, return → `async_return_to_base`/`RETURN_HOME`. `async_turn_on`/`TURN_ON` deprecati per StateVacuumEntity.
- **Bitmask da dichiarare: `START|PAUSE|STOP|RETURN_HOME|STATE` = 8192+4+8+16+4096 = 12316** — senza questi bit la vacuum card nasconde i pulsanti (frontend `src/data/vacuum.ts` espone `canStart/canStop/canReturnHome/isCleaning`); appaiono anche contestualmente allo stato (start nascosto mentre pulisce, stop se docked/idle, ecc.).
- Websocket gating: `vacuum/websocket.py:36-44` rifiuta con `ERR_NOT_SUPPORTED` se il bit mancante.
- Mapping stato Tuya→HA (da Q5): `status` DP5 `cleaning`→`CLEANING`, `paused`→`PAUSED`, `goto_charge`/`relocating`→`RETURNING`, `charging`/`charge_done`→`DOCKED`, `standby`/`sleep`→`IDLE`; `total_error`≠0 → `ERROR`. Worked examples core: `roomba/vacuum.py:29-40`, `tuya/vacuum.py:29-38`.

### Q4 — Credential storage + silent re-auth

- `ConfigEntry.async_start_reauth` (config_entries.py:1305-1322): **dedupe nativa** (se un flow reauth/reconfigure è già attivo, ritorna); `async_start_reauth_if_available` (L1324-1331) chiama reauth solo se l'integrazione implementa `async_step_reauth`.
- **Il coordinator fa già tutto**: quando `_async_update_data` solleva `ConfigEntryAuthFailed`, `_async_refresh` (update_coordinator.py:538-556) logga una volta, ferma il polling (auth_failed non rischedula) e chiama `config_entry.async_start_reauth_if_available`. L'integrazione deve solo convertire l'errore Tuya in `ConfigEntryAuthFailed` — non chiamare reauth a mano.
- `config_entry.data` via `async_update_entry` persiste su `.storage/core.config_entries`; l'update di data non ri-triggera il setup (a differenza di options, che chiama i listener).
- Per l'approccio LAN scelto: niente token refresh — la chiave è statica; caso reauth ridotto a "chiave cambiata dopo re-pairing" → `ConfigEntryAuthFailed` → step reauth con nuovo Local Key.
- Repair surface per problemi non-riparabili: `homeassistant/helpers/issue_registry.py` `ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, severity=IssueSeverity.ERROR, translation_key=...)`; diagnostics: `diagnostics.py:async_get_config_entry_diagnostics`.

### Q5 — Protocollo Lefant M1 (⚠ pivot strutturale)

**Finding chiave: Lefant M1 è un device Tuya.** L'app Lefant è un client verso un backend Tuya; **non esiste una REST API Lefant pubblica documentata**.

Evidenze verificate:

- `k1rak1ra/SuccuBotServer` (branch `master`, Kotlin/Gradle, GPL-3.0) — README.adoc: "reverse-engineered replacement backend for the Lefant M1 robot vacuum, designed to work in tandem with a local MQTT server to replace the Tuya/Lefant backend completely". Requisiti: robot **hackerato** (chiavi di cifraggio estratte, patch controlli SSL), server MQTT locale, CA+TLS — il robot parla **MQTT over TLS verso il cloud Tuya/Lefant**. Percorso escluso per un'integrazione standard.
- `hectorzin/Lefant-Home-Assistant-LocalTuya`: estrae Device ID + Local Key dall'app Lefant (emulatore Android + adb root). Setup validato nel README: **Lefant M210 Pro Omni, app Lefant 3.3.25, Tuya protocol 3.5**. Nota critica: "After a robot is paired in the Lefant app, its Local Key may not be available from a normal Tuya IoT Cloud project" — la chiave va estratta via MITM dell'app, non da un progetto IoT Tuya.
- **Schema DP Tuya** (`schemas/Lefant_M210_PRO_OMNI.json`, famiglia Lefant — per l'M1 da confermare sul device):
  - DP1 `switch_go` bool rw — start pulizia
  - DP2 `pause` bool rw — pausa/riprendi
  - DP3 `switch_charge` bool rw — ritorno in carica
  - DP4 `mode` enum rw — smart/chargego/zone/pose/fastmapping/…
  - DP5 `status` enum ro — standby/smart/cleaning/paused/goto_charge/charging/charge_done/sleep/relocating…
  - DP9 `suction` enum rw — closed/gentle/normal/strong/superStrong
  - DP23 `battery_percentage` value ro
  - DP27 `seek` bool rw (locate), DP28 `total_error` raw
- HA core `tuya` integration ha piattaforma vacuum, ma **scartata dal developer al checkpoint** (UX diversa dal pairing Lefant, robot non funziona bene).

**Strada decisa (checkpoint)**: component custom con protocollo Tuya locale (LocalTuya-style): connection LAN diretta al robot con `device_id` + `local_key`, protocollo 3.5 (validato sulla famiglia; confermare per M1). FRD aggiornato: LAN al posto di cloud, key-based auth al posto di email+password.

### Q6 — HTTP/Tuya client async

- `homeassistant/helpers/aiohttp_client.py` (510 righe): `async_get_clientsession(hass)` (L217-243) sessione condivisa con cleanup a `homeassistant_stop`; `async_create_clientsession(hass, auto_cleanup=True)` (L246-275) sessione dedicata (es. cookies) **chiusa automaticamente all'unload della config entry** (`_async_register_clientsession_shutdown` L381-403) — nessuna chiusura manuale da fare in `async_unload_entry`.
- Nota: per il protocollo Tuya locale la sessione HTTP non è il mezzo principale — i DP viaggiano su socket TCP cifrati (tuyaplus protocol). Se il transport è socket, usare `asyncio` nativo; la sessione aiohttp resta per eventuali endpoint HTTP di scoperta (discovery broadcast UDP 6666/6667 per Tuya locale).
- Timeout: `asyncio.timeout(...)` (Python 3.11+, standard core attuale) attorno a ogni I/O; il vecchio `async_timeout` è deprecato.
- Retry: nel coordinator (cadenza già degrada con grazia); retry manuale nel client solo se serve per transient DNS/TLS. La lib `requests` è vietata sull'event loop.
- TLS/SSL: `verify_ssl=True` default; `SSRFRedirectError` + resolver custom (L58-160) — pertinenti solo se si usa la sessione condivisa.

### Q7 — HACS acceptance contract

- https://www.hacs.xyz/docs/publish/integration/ — struttura: **una sola integrazione per repo** sotto `custom_components/<domain>/`; `manifest.json` minimo richiesto da HACS: `domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version` (più le chiavi HA core: `iot_class: local_polling`, `integration_type: device`, `requirements`). Releases GitHub opzionali (senza, HACS usa il default branch).
- https://www.hacs.xyz/docs/publish/start/ — `hacs.json` in root: `name` (required), `render_readme`, `zip_release`+`filename`, `content_in_root`, `hide_default_branch`, `homeassistant` (min version). Repo GitHub: description + **topics** obbligatori (ricercabilità store).
- https://www.hacs.xyz/docs/publish/action/ — workflow `hacs/action` (stesso codice di HACS): input `category: integration`, `ignore` spazio-separata; checks: `archived`, `brands`, `description`, `hacsjson`, `images`, `information`, `issues`, `topics`. Setup consigliato: workflow CI su push/PR con `category: integration`.
- Version: dai tag git (o `manifest.json` per HACS se non c'è `zip_release`).

### Q8 — Device registry per-device

- Device discovery LAN: broadcast UDP Tuya (porte 6666/6667, NewDeviceAnnouncement) oppure inserimento manuale di IP/device_id nel config flow — per la prima versione l'inserimento manuale è sufficiente; zero-device UX non si applica (l'utente configura un device per entry). Multi-device: una config entry per device (modello LocalTuya) — semplifica isolamento.
- `async_setup_entry` → `hass.config_entries.async_forward_entry_setups(entry, ("vacuum",))`; entità con `DeviceInfo(identifiers={(DOMAIN, device_id)}, manufacturer="Lefant", model="M1", model_id=<modello Tuya>)` + `unique_id=f"{DOMAIN}_{device_id}"` → entity_registry sopravvive a reload/restart.
- `DeviceInfo` (`homeassistant/helpers/device_registry.py`, dataclass ≈L200): `identifiers` set di tuple `(domain, id)`; preferire `model_id` stabile; nome device via `translation_key`/`translation_placeholders`.
- Isolamento: con una entry per device la failure isolation è nativa (un robot fallito non tocca gli altri).

### Q9 — Testing mock-only + traduzioni

- `pytest-homeassistant-custom-component` (README @master, traccia HA core **2026.9.2**): fixture `hass`, **`enable_custom_integrations` obbligatoria** per custom components; helper da `pytest_homeassistant_custom_component.common` (`MockConfigEntry`, `load_fixture` — file in `fixtures/` accanto ai test); richiede `asyncio_mode = auto` in pytest config.
- HTTP/socket mock: `aioresponses` per HTTP; per il transport Tuya locale (socket cifrato) meglio **mockare l'intero client device** (protocol-level fake che risponde ai DP commands) invece di mockare il socket — più stabile e meno brittleness.
- i18n: https://developers.home-assistant.io/docs/internationalization/core/ — `strings.json` nella dir dell'integrazione; categorie: `title`, `config` (steps/errors/abort del flow), `entity`, `entity_component`, `device`, `issues` (repair), `exceptions`, `options`, `services`; traduzioni in `translations/<lang>.json`.
- Diagnostics snapshot: `async_get_config_entry_diagnostics` + snapshot test.

## Decision Log (checkpoint research)

1. **Protocollo/trasporto (sostituisce FRD "Cloud API Lefant")**: component custom su protocollo Tuya locale — il robot resta appaiato nell'app Lefant, chiave estratta una volta con il tool di hectorzin. Integrazione Tuya ufficiale scartata dal developer (esperienza utente peggiora, robot non funziona bene). RE dell'API dell'app Lefant scartato (fragile, dipende dal backend Tuya, richiede MITM continuo). SuccuBotServer scartato (richiede hack firmware).
2. **Auth (sostituisce FRD "email+password")**: Device ID + Local Key (+ IP) nel config flow; caso reauth = chiave cambiata dopo re-pairing.
3. **Stato (sostituisce FRD "polling REST 30-60s")**: polling locale 30-60s via coordinator (requisito 2 cicli verificato); push Tuya locale come upgrade in design.

## Open Questions

Carried verbatim da discover: "_None — every branch resolved during the interview._"

Nuove dalla research (da risolvere in design/implementazione):

1. ❓ **M1 DPs esatti**: lo schema verificato è di Lefant M210 Pro Omni (stessa famiglia). L'M1 potrebbe differire (es. niente `suction`/`water_output`). Serve una lettura DP reale sul device (estrattore hectorzin + schema dump) prima di fissare il mapping. Prerequisito utente: estrarre Device ID + Local Key.
2. ❓ **Versione protocollo Tuya per l'M1**: 3.5 validato su M210 Pro Omni; confermare per l'M1 (3.3/3.4/3.5 cambiano la cifratura del handshake locale).
3. ❓ **Dispositivo in app Tuya vs solo app Lefant**: se l'M1 dell'utente non è mai stato appaiato a Tuya Smart, la chiave locale va estratta via MITM dell'app Lefant (tool hectorzin, emulatore Android). Se l'utente può appaiarlo a Tuya Smart, la chiave è leggibile da un progetto IoT Tuya — ma il pairing Tuya è ciò che il developer ha scartato per UX; clarificare in design se un pairing "solo per leggere la chiave" è accettabile e poi tornare all'app Lefant.

## Sources

- HA core tag `2026.9.1` (raw.githubusercontent.com/home-assistant/core/2026.9.1/...): `config_entries.py`, `exceptions.py`, `helpers/update_coordinator.py`, `helpers/aiohttp_client.py`, `components/aurora/{__init__,coordinator}.py`, `components/vacuum/const.py`, `components/vacuum/websocket.py`
- HA frontend `dev`: `src/data/vacuum.ts`, `src/dialogs/more-info/controls/more-info-vacuum.ts`
- HA developer docs: https://developers.home-assistant.io/docs/internationalization/core/
- HACS: https://www.hacs.xyz/docs/publish/integration/ · /docs/publish/start/ · /docs/publish/action/
- Tuya/Lefant: https://github.com/k1rak1ra/SuccuBotServer (README.adoc, branch master) · https://github.com/hectorzin/Lefant-Home-Assistant-LocalTuya (README.md + schemas/Lefant_M210_PRO_OMNI.json) · https://www.home-assistant.io/integrations/tuya/
- Testing: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component (README @master)
