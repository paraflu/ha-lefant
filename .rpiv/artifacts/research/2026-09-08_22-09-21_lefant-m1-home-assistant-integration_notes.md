# Working Notes — Research Lefant M1 HA Integration

> Nota di lavoro (non è il report finale). Data: 2026-09-16. Metodo: ricerca inline
> (niente subagenti, su richiesta del developer). Fonti ancorate a HA core 2026.9.1.

## Stato domande (9 dallo scope-tracer)

| Q | Argomento | Stato |
|---|---|---|
| Q1 | Config flow lifecycle (`async_step_user`, `ConfigEntryNotReady`, forward/unload) | ✅ verificata inline |
| Q2 | Polling coordinator (`DataUpdateCoordinator`, backoff, 2-poll budget) | ✅ verificata inline |
| Q3 | Vacuum platform (`VacuumEntityFeature`, `VacuumActivity`) | ✅ report subagente completo |
| Q4 | Storage credenziali + silent re-auth 401 | ✅ verificata inline |
| Q5 | Protocollo cloud Lefant (Tuya!) | ✅ completata inline — schema DP verificato (hectorzin), SuccuBotServer individuato (branch master, README.adoc) |
| Q7 | HACS acceptance contract | ✅ verificata inline (docs.hacs.xyz) |
| Q9 | Testing mock-only + traduzioni | ✅ verificata inline (PHACC + dev docs i18n) |

Precedent-locator: repo greenfield — 1 solo commit `ab8f5dc` "Initial commit", albero vuoto, nessun precedente. Lezione: l'FRD è untracked in git → non contare sulla cronologia git per recuperare gli artifact.

---

## Q1 — Config flow lifecycle (verificata inline, HA 2026.9.1)

Fonti:
- `homeassistant/exceptions.py:240-255` — `ConfigEntryNotReady` ("config entry is not ready"), `ConfigEntryAuthFailed` ("could not authenticate"), `ConfigEntryError`.
- `homeassistant/config_entries.py:839-876` — durante setup: `ConfigEntryAuthFailed` → warning + `async_start_reauth_if_available(hass)`; `ConfigEntryNotReady` → stato `SETUP_RETRY` con backoff esponenziale `min(2**tries * 5, SETUP_RETRY_MAX_WAIT=600)`s + jitter microsecondi, auto-retry via `async_call_later` (L141: `SETUP_RETRY_MAX_WAIT = 600`; L852 formula).
- `homeassistant/config_entries.py:2773-2800` — `async_forward_entry_setups(entry, platforms)`: da attendere prima di terminare `async_setup_entry`.

Pattern raccomandato per `custom_components/lefant_m1/`:
- `config_flow.py:async_step_user`: form `vol.Schema` EMAIL/PASSWORD; validazione chiamando il client cloud; credenziali errate → raise `InvalidAuth` → `async_show_form` con `errors={"base": "invalid_auth"}`; cloud irraggiungibile in flow → `CannotConnect` → `errors={"base": "cannot_connect"}`.
- `__init__.py:async_setup_entry`: cliente non raggiungibile → raise `ConfigEntryNotReady` (HA riprova da solo con backoff; NON blocca il bootstrap perché il setup riparte dopo). Credenziali sbagliate in setup → raise `ConfigEntryAuthFailed` (mostra "Reauthenticate" nella UI di HA).
- `entry.data` dopo setup: email + token (+ device list cache se serve) → reload non ri-verifica credenziali.

## Q2 — Coordinator polling (verificata inline)

Fonte: `homeassistant/helpers/update_coordinator.py` (725 righe, tag 2026.9.1):
- `DataUpdateCoordinator.__init__` (L73-150): parametri `config_entry`, `name`, `update_interval`, `update_method`, `setup_method`, `request_refresh_debouncer`, `always_update`. `update_interval` è property+setter (L242-249) che converte in secondi — **`async_update_interval` API è sparita, confermato**.
- Scheduling: `_schedule_refresh` (L253-283) usa **`loop.call_at`** (commento a riga 267-269: "We use loop.call_at because DataUpdateCoordinator does not need an exact update interval") — confermato, non `async_track_time_interval`.
- `_retry_after` (L131, 272-274, 504): supporto rate-limit — se `_async_update_data` solleva un'eccezione con `retry_after`, il prossimo refresh è posticipato di quel tempo.
- `_async_refresh` (L419-590): su TimeoutError/ClientError/UpdateFailed → log una volta, `last_update_success=False`; `finally` (L582-583) rischedula SOLO se `not auth_failed and self._listeners and not self.hass.is_stopping`. **Nessun backoff esponenziale automatico**: l'intervallo resta `update_interval`; backoff è responsabilità dell'integrazione (es. override property `update_interval` adattivo).
- `async_config_entry_first_refresh` (L317-330): raise `ConfigEntryNotReady` se il primo refresh fallisce; con `ConfigEntryAuthFailed` → re-raise (L377, nel path `_async_setup`/first refresh) → UI reauth.
- `async_request_refresh` (L304-309): debounce via `_debounced_refresh`.
- `BaseCoordinatorEntity` (L650-681): `should_poll=False` (L664-667), listener in `async_added_to_hass`, `_handle_coordinator_update` → `async_write_ha_state`.
- Worked example canonico: `homeassistant/components/aurora/{__init__,coordinator}.py` — coordinator in `entry.runtime_data`, `await coordinator.async_config_entry_first_refresh()`, `async_forward_entry_setups`, unload con `async_unload_platforms`.

Budget "2 poll cycles": OK con un solo coordinator condiviso — l'entità riceve il listener e si aggiorna alla fine di ogni ciclo (30-60s → stato aggiornato entro 2 cicli).

## Q3 — Vacuum platform (report subagente, HA 2026.9.1 + frontend dev)

- `homeassistant/components/vacuum/const.py:36-52` — `VacuumEntityFeature(IntFlag)`: `TURN_ON=1`, `TURN_OFF=2` (entrambi **deprecated per StateVacuumEntity**), `PAUSE=4`, `STOP=8`, `RETURN_HOME=16`, `FAN_SPEED=32`, `STATUS=128` (deprecated), `SEND_COMMAND=256`, `LOCATE=512`, `CLEAN_SPOT=1024`, `MAP=2048`, `STATE=4096` (obbligatorio per StateVacuumEntity), `START=8192`, `CLEAN_AREA=16384`. **Nessun bit BATTERY** (bit 64 rimosso; battery è `_attr_battery_level`, sempre esposto). Alias `SUPPORT_*` eliminati da core.
- Stato: `VacuumActivity(StrEnum)` (const.py:16-24): `CLEANING/DOCKED/IDLE/PAUSED/RETURNING/ERROR` ("cleaning"…"error"). Mapping worked examples: `roomba/vacuum.py:29-40`, `tuya/vacuum.py:29-38`.
- Comandi: subclassare **`StateVacuumEntity`**; start ha un percorso dedicato `SERVICE_START`/`async_start()` con bit `START` (8192); legacy `async_turn_on` deprecato. Pause→`async_pause`/PAUSE, stop→`async_stop`/STOP, return→`async_return_to_base`/RETURN_HOME.
- Bitmask da dichiarare: **`START|PAUSE|STOP|RETURN_HOME|STATE` = 8192+4+8+16+4096 = 12316** — senza questi bit la vacuum card nasconde i pulsanti (frontend `src/data/vacuum.ts`: `canStart/canStop/canReturnHome/isCleaning`).
- Websocket gating: `vacuum/websocket.py:36-44` rifiuta con `ERR_NOT_SUPPORTED` se il bit non è dichiarato.

## Q4 — Storage credenziali + silent re-auth (verificata inline)

- `ConfigEntry.async_start_reauth` (config_entries.py:1305-1322): **dedupe integrata** — se c'è già un flow reauth/reconfigure attivo per l'entry, ritorna senza creare il task. Non serve costruire la propria logica di dedupe.
- `async_start_reauth_if_available` (L1324-1331): chiama reauth solo se l'integrazione implementa `async_step_reauth`.
- Il coordinator chiama già `self.config_entry.async_start_reauth_if_available(self.hass)` automaticamente quando `_async_update_data` solleva `ConfigEntryAuthFailed` (update_coordinator.py:538-556) — **l'integrazione deve solo sollevare ConfigEntryAuthFailed dal client**; NON deve chiamare async_start_reauth a mano nel flusso 401.
- Storage: `config_entry.data` via `async_update_entry` persiste su `.storage/core.config_entries`. Aggiornare il token in place NON ri-triggera il setup (update di data non riesegue async_setup_entry; è diverso da options update che invece chiama i listener di update). Per un token non-OAuth2 ri-derivabile da email+password: pattern sanzionato = **silent in-place refresh in try del client; se le password/token sono del tutto invalidi → ConfigEntryAuthFailed** → reauth interattivo gestito da core.
- Problemi irrecuperabili per l'utente: `homeassistant/helpers/issue_registry.py` `ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, severity=IssueSeverity.ERROR, translation_key=...)`; diagnostics: `diagnostics.py:async_get_config_entry_diagnostics` standard.
- Worked examples con token custom: `tado`, `xiaomi_miio` (reauth step custom).

## Q5 — Protocollo Lefant M1 (completata inline — Tuya confermato)

**Finding chiave: Lefant M1 è un device Tuya.** L'API cloud "Lefant" che serve l'app è un backend Tuya; NON esiste una REST API Lefant pubblica documentata.

Evidenze (verificate inline):
- `k1rak1ra/SuccuBotServer` (branch `master`, Kotlin/Gradle, GPL-3.0) — README.adoc: "reverse-engineered replacement backend for the Lefant M1 robot vacuum, designed to work in tandem with a local MQTT server to replace the Tuya/Lefant backend completely". Requisiti: robot HACCATO (chiavi di cifraggio estratte + patch dei controlli SSL), server MQTT locale, CA+TLS — il robot parla **MQTT over TLS verso il cloud Tuya/Lefant**. Percorso inaccettabile per un'integrazione standard (richiede hack del firmware).
- `hectorzin/Lefant-Home-Assistant-LocalTuya`: estrae Device ID + Local Key dall'app Lefant (emulatore Android + adb root, MITM dell'app). Setup validato nel README: **Lefant M210 Pro Omni, app Lefant 3.3.25, Tuya protocol 3.5**.
- **Schema DP Tuya** (`schemas/Lefant_M210_PRO_OMNI.json` — stessa famiglia Lefant; per M1 verificare sul device): DP1 `switch_go` bool (start pulizia), DP2 `pause` bool, DP3 `switch_charge` bool (ritorno in carica), DP4 `mode` enum (smart/chargego/zone/pose/fastmapping/…), DP5 `status` enum ro (standby/smart/zone_clean/cleaning/paused/goto_charge/charging/charge_done/sleep/relocating…), DP9 `suction` enum, DP23 `battery_percentage` value ro, DP27 `seek` bool, DP28 `total_error` raw.
- HA core ha già l'integrazione `tuya` con piattaforma vacuum (doc home-assistant.io/integrations/tuya): login via QR code con app Tuya Smart/Smart Life; prerequisito: device nell'account Tuya.

Implicazione per l'FRD (da portare al checkpoint developer): la decisione "Cloud API Lefant + email/password" NON è implementabile così com'è — le opzioni reali sono: (1) integrazione ufficiale `tuya` (zero codice custom, se l'M1 espone l'entità vacuum), (2) custom component su Tuya Open API (account developer Tuya + OAuth Tuya), (3) LocalTuya LAN (chiavi estratte dall'app, fragile), (4) SuccuBotServer (hack firmware — escluso).
## Q6 — HTTP client async (verificata inline)

Fonte: `homeassistant/helpers/aiohttp_client.py` (510 righe, tag 2026.9.1):
- `async_get_clientsession(hass, verify_ssl=True, ...)` (L217-243): sessione condivisa, `auto_cleanup_method=_async_register_default_clientsession_shutdown` → chiusa a `homeassistant_stop`.
- `async_create_clientsession(hass, verify_ssl=True, auto_cleanup=True, **kwargs)` (L246-275): sessione dedicata (es. per cookies); con `auto_cleanup=True` viene chiusa **automaticamente all'unload della config entry** (`_async_register_clientsession_shutdown` L381-403). → Il client NON deve chiudere la sessione a mano se usa questa API.
- Timeout: in core moderno si usa `asyncio.timeout(...)` (Python 3.11+); il vecchio `async_timeout` è deprecato. (Da confermare con un esempio core — aurora usa la lib client dedicata; pattern standard comunque `async with asyncio.timeout(10)` attorno a ogni request.)
- Retry: metterlo nel coordinator (la cadenza 30-60s già degrada con grazia: su errore log-una-volta + rischedulazione); retry manuale nel client solo per transient DNS/TLS, se serve. requests su event loop è vietato (event loop bloccante).
- TLS: `verify_ssl=True` default su entrambe le API; `SSRFRedirectError` + DNS resolver custom per redirect bloccati (L58-160).

## Q7 — HACS acceptance contract (verificata inline, docs.hacs.xyz)

Fonti:
- https://www.hacs.xyz/docs/publish/integration/ — struttura: UNA sola integrazione per repo sotto `custom_components/<domain>/`; `manifest.json` minimo: `domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version`. Releases GitHub opzionali (senza: HACS usa il default branch).
- https://www.hacs.xyz/docs/publish/start/ — `hacs.json` in root: `name` (required), `render_readme`, `zip_release`+`filename`, `content_in_root`, `hide_default_branch`, `homeassistant` (min version). Repo GitHub richiede description + topics (ricercabilità nello store).
- https://www.hacs.xyz/docs/publish/action/ — workflow `hacs/action` (stesso codice di HACS): input `category: integration`, `ignore` spazio-separata; checks ignorabili: `archived`, `brands`, `description`, `hacsjson`, `images`, `information`, `issues`, `topics`.
## Q8 — Device registry per-device (report subagente)

- Device list dal client cloud (`async_get_devices()`); zero device in config flow → `async_abort(reason="no_devices")` con copia in `strings.json`.
- `async_setup_entry` → `async_forward_entry_setups(entry, ("vacuum",))`; piattaforma loop devices → `DeviceInfo(identifiers={(DOMAIN, serial)}, manufacturer="Lefant", model="M1")` + `unique_id=f"{DOMAIN}_{serial}"` → entity_registry sopravvive a reauth/reload.
- `DeviceInfo` (`homeassistant/helpers/device_registry.py`, dataclass ≈L200): `identifiers` set di tuple `(domain, id)`; preferire `model_id` stabile; traduzioni nome via `translation_key`/`translation_placeholders`.
- Isolamento: try/except per device nella creazione entità (log + `continue`); un solo coordinator condiviso.

## Q9 — Testing + traduzioni (verificata inline)

Fonti:
- `pytest-homeassistant-custom-component` (README @master, traccia HA core 2026.9.2): espone le fixture core di HA (`hass`, `enable_custom_integrations` — OBBLIGATORIA per custom), helper da `pytest_homeassistant_custom_component.common` (`MockConfigEntry`, `load_fixture` — file in `fixtures/` accanto ai test). Richiede `asyncio_mode = auto` in pytest config.
- HTTP mock: `aioresponses` (dipendenza di PHACC, usata da HA core per il mocking aiohttp).
- i18n: https://developers.home-assistant.io/docs/internationalization/core/ — `strings.json` nella dir dell'integrazione; categorie: `title`, `config` (steps/errors/abort del config flow), `entity`, `entity_component`, `device`, `issues` (repair), `exceptions`, `options`, `services`. Le traduzioni compilato va in `translations/<lang>.json`.
- Diagnostics snapshot: `async_get_config_entry_diagnostics` + test snapshot standard.

---

## Errori/ostacoli metodo (per riprendere)

- `raw.githubusercontent.com/.../2026.9` → 404: usare tag **`2026.9.1`**.
- curl inline nel contesto: vietato dal setup (usare ctx tools o `curl -s -o file`).
- GitHub HTML search: JS-rendered → usare GitHub REST API (`api.github.com`).
- GitHub REST search: rate limit anonimo; il tentativo con urllib ha avuto un errore banale (`'bytes' object has no attribute 'read'`) — rifare con `json.loads(r.read())`.
- docs developers.home-assistant.io: irraggiungibile per i subagenti; fallback docstring nei sorgenti.
- `k1rak1ra/SuccuBotServer` raw README → 404 su main/master: cercare via REST API (possibile rename).
