---
date: 2026-09-08T21:11:22+0200
author: Andrea Forlin
commit: ab8f5dc
branch: develop
repository: ha-lefant
topic: "Lefant M1 Home Assistant integration"
tags: [intent, frd, home-assistant, vacuum]
status: ready
last_updated: 2026-09-08T21:11:22+0200
last_updated_by: Andrea Forlin
---

# FRD: Lefant M1 Home Assistant integration

## Summary
A HACS-ready Home Assistant custom component that exposes the user's Lefant M1 robot vacuum as a native vacuum entity. The integration authenticates to the Lefant cloud with the user's app credentials (email + password via HA config flow) and polls the cloud REST API to reflect state and battery in HA, with services for start / pause / stop / return-to-base. Built for personal use first, structured for community distribution from the start.

## Problem & Intent
"I own a Lefant M1 and want to control it from Home Assistant."

Success for me =
- M1 appears as a vacuum entity in HA
- start/stop/pause from dashboard
- sees battery state

The M1 has no official HA integration; the repo starts greenfield. The user already runs the Lefant app with the robot bound to an account, so the cloud path (same channel the app uses) is the replicable, low-risk route.

## Goals
- M1 shows up in HA as a `vacuum` entity under the integration domain.
- Start, pause, stop, and return-to-base commands work from the HA dashboard.
- Battery level and cleaning state are reflected in HA (updated on a polling cadence).
- Component is installable via HACS and structured for public repo distribution.
- Onboarding happens through the HA config flow (email + password login).

## Non-Goals
- No extra sensor platforms in v1 (detailed cleaning stats, wifi signal, maintenance status).
- No advanced features in v1 (schedule management, zone/spot cleaning, map visualization).
- No local-LAN protocol reverse engineering in v1 — cloud API only for now.
- No mobile/companion surface beyond the standard HA dashboard entities.

## Functional Requirements
1. The integration SHALL register a config flow accepting Lefant account email and password, authenticate against the Lefant cloud, and store the session token.
2. The integration SHALL expose one `vacuum` entity per detected device (M1 bound to the account).
3. The `vacuum` entity SHALL expose: current state (cleaning / idle / docked), battery level, and the standard HA vacuum services `start`, `pause`, `stop`, `return_to_base`.
4. The integration SHALL poll the Lefant cloud for device state on a fixed interval (default 30-60s), updating entity attributes and state.
5. The integration SHALL handle expired/invalid session tokens by re-authenticating with stored credentials, and surface authentication failures to the user (config entry diagnostics / log).
6. The integration SHALL be unloadable and reloadable without HA restart (config entry cleanup on unload).

## Non-Functional Requirements
- **Performance**: state polling at 30-60s interval is acceptable; no real-time requirement. Command latency up to one poll cycle for state reflection is accepted.
- **Security**: user password must never be stored in plaintext — HA credentials storage pattern (hass storage / auth tokens only). No data leaves the user's HA instance except API calls to the Lefant cloud with the user's own token. TLS for all cloud calls.
- **UX / Accessibility**: setup via standard HA config flow UI (no YAML required); errors in the config flow must be human-readable; entities work with standard HA dashboard cards (default vacuum card, battery display).
- **Reliability**: graceful handling of transient cloud errors (retry with backoff on polling); integration must not block HA startup on unreachable cloud; clear log messages on auth failure.

## Constraints & Assumptions
- Platform: Home Assistant (Python, custom_components structure), running the user's instance.
- The Lefant cloud exposes a REST API reachable from HA with email/password authentication — to be verified during research.
- The cloud API behavior mirrors the consumer Lefant app protocol; exact endpoints/auth scheme may require reverse engineering from app traffic or existing community integrations.
- Distribution: GitHub repo + `hacs.json` for HACS install; repo is currently empty (greenfield, no codebase precedent).
- No real Lefant device/API credentials are available in this environment for live end-to-end testing — verification will rely on unit tests + mock HTTP, with real-device UAT by the user.

## Acceptance Criteria
- [ ] `HA` shows the integration via config flow; entering valid Lefant credentials completes setup without error.
- [ ] A `vacuum.lefant_m1` entity (or per-device equivalent) appears with battery level and state populated.
- [ ] Clicking start / pause / stop / return-to-base on the HA vacuum card issues the corresponding cloud API calls (observable in debug logs with mocked or real API).
- [ ] Polling updates entity state every configured interval; a state change at the cloud is reflected in HA within 2 poll cycles.
- [ ] Invalid credentials produce a clear, recoverable error in the config flow; an expired token mid-run triggers silent re-auth and recovers.
- [ ] Reloading the integration (or restarting HA) does not require re-auth and entities restore correctly.
- [ ] Repo structure passes HACS validation (`hacs.json` present, manifest valid, `custom_components/lefant_m1/` layout).

## Recommended Approach
A Home Assistant custom component under `custom_components/lefant_m1/`, HACS-structured from the start (GitHub repo, `hacs.json`, README). Core is an async cloud API client that logs in with email+password (config flow), then polls the Lefant cloud REST API on a fixed interval to update a `vacuum` entity (state, battery, start/pause/stop/return-to-base). No persistence layer beyond HA's credential storage; components and tests model the cloud API with mocks since no live device is available in the dev environment.

## Decisions

### Target audience and distribution
**Question**: È per uso personale o distribuzione community?
**Recommended**: End user (personal use) with a HACS-ready structure.
**Chosen**: HACS-ready da subito.
**Rationale**: Most likely no public Lefant M1 integration exists; structuring for HACS costs little and keeps the option to share.

### App binding and protocol domain
**Question**: Conosci il protocollo dell'M1 (MQTT/CoAP/HTTP)?
**Recommended**: Cloud via the Lefant app (robot already bound to the account).
**Chosen**: Uso l'app Lefant — robot già configurato in app e wifi.
**Rationale**: The app-bound account and its credentials are concrete, replicable assets; local LAN reverse engineering is heavier.

### Functional scope
**Question**: Quale insieme di funzionalità per la prima versione?
**Recommended**: Base — vacuum entity, start/stop/battery.
**Chosen**: Solo base: vacuum entity + start/stop/pause/return + battery.
**Rationale**: Smallest useful slice; extra sensors and advanced features are a later, separate increment.

### Integration path (cloud vs LAN)
**Question**: L'integrazione parla col cloud Lefant (stessa strada dell'app) o col robot in LAN?
**Recommended**: Cloud API.
**Chosen**: Cloud API.
**Rationale**: Same channel the app already uses — replicable and documented; works remotely; community Lefant integrations almost all go through cloud.

### Authentication scheme
**Question**: Come si autentica l'integrazione al cloud Lefant?
**Recommended**: Login email+password nel config flow; token salvato.
**Chosen**: Login email+password (config flow), token stored via HA credentials storage.
**Rationale**: Standard HA cloud-integration UX; avoids hardcoding fragile API secrets (the APK-derived appKey/appSecret alternative is brittle to secret rotation).

### State update mechanism
**Question**: Polling REST o MQTT streaming per lo stato?
**Recommended**: Polling REST a intervallo fisso.
**Chosen**: Polling (30-60s) via REST.
**Rationale**: Simplest robust pattern, matches known Lefant cloud behavior; MQTT streaming only if the backend is later confirmed to expose it.

## Open Questions

_None — every branch resolved during the interview._

## Suggested Follow-ups

- Advanced features (schedule management, zone/spot cleaning, map visualization) — offered and declined for v1; same cloud API surface could support them later.
- Extra sensors (cleaning stats, wifi signal, maintenance/filter status) — declined for v1; addable as additional platforms on the same polling client.
- Local-LAN protocol reverse engineering for offline/privacy control — explicitly deferred; would be a separate integration path.

## References
- No prior artifacts — repo is greenfield (no codebase precedent at probe time).
- Next: `/skill:research .rpiv/artifacts/discover/2026-09-08_21-11-22_lefant-m1-home-assistant-integration.md`