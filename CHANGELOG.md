# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases state explicitly what was verified on physical hardware and what was
not. "Tested" means run against a real Lefant M1, not against a fake client.

## [Unreleased]

## [1.0.0] - 2026-10-27

First release that can actually talk to the robot.

### Added

- **Tuya LAN 3.3 transport** (`tuya_lan_adapter.py`), built on tinytuya, covering
  protocols 3.1–3.5. This is the version the M1 answers: `55AA` framing, AES-ECB
  with the local key.
- **Protocol version as a config field**, defaulting to 3.3, so 3.4/3.5 Lefant
  models can be configured as well.
- **Diagnostics tools**: `tools/diagnose_tuya_lan.py` identifies Tuya devices on
  the LAN with the public discovery key only, and `tools/probe_robot.py` reads
  datapoints using `LEFANT_LOCAL_KEY` from the environment and never prints it.
- **Local key extraction guide**: `tools/get_local_key.sh` plus
  `tools/frida_get_local_key.js` recover the key from the app's SDK object on a
  rootable emulator, with no rooted phone and no re-pairing of the robot.
- **Integration brand assets** under `custom_components/lefant_m1/brand/`.
- **Repository conventions** in `AGENTS.md`.
- **My Home Assistant badges** for installation and setup.

### Changed

- **Datapoint IDs corrected** against the APK's `LaserDP` catalog and against
  `DP_QUERY` answers from physical units (firmware 1.8.71 and 1.9.13):

  | Function | Before | After |
  |---|---|---|
  | Clean duration | 18 | **6** |
  | Clean area | 19 | **7** |
  | Battery | 23 | **8** |
  | Fan speed | 14 | **9** |
  | Fault | 25 | **28** |
  | Locate | 24 | **11** (APK evidence only) |

- **Fan speed `quiet` → `gentle`**, the value the `SuctionLevel` enum actually
  uses. Sending `quiet` was invalid on this robot.
- **`iot_class` is now `local_polling`** instead of `local_push`. Tinytuya is
  request/response, so the robot is polled every 4 seconds; there is no push
  channel to listen on.
- **Sensor `unique_id`s are frozen** to the ids the integration originally
  shipped with, so a datapoint correction does not recreate entities and lose
  history.

### Deprecated

- `pytuya_client.py`. It speaks only 3.5 (`0x6699`, AES-GCM) and could never
  complete a first frame against the M1. Unused since the transport swap;
  scheduled for removal.

### Fixed

- Connecting with a correct local key no longer fails at the first frame.
- `Relocating` and `wall_follow_clean` no longer silently report `idle` when a
  status is present that the mapping knows about.

### Verified on hardware

- Local LAN channel reachable on port 6668; protocol identified as **3.3** on two
  independent M1 units.
- Encrypted `DP_QUERY` answered with a real key: 9 datapoints read
  (`5=sleep`, `8=100`, `9=strong`, `10=high`, `27=true`, `28=0`, `45=true`,
  `122=true`, `125=true`).
- The full config-flow path (`connect()` + `query_dps()`) executed against the
  robot outside Home Assistant.

### Not verified

- **No command has been sent to the robot.** Start, pause, stop, return to dock,
  fan speed, locate and spot clean are untested; the write path is unproven.
- The cleaning status enum is only partly observed. An unknown status falls back
  to `idle` by design rather than guessing.
- Datapoint 45 is reported by the robot and its purpose is unknown.
- Whether the transport behaves correctly inside a running Home Assistant
  instance (setup, reload, unload, reconnection) is untested.

[Unreleased]: https://github.com/paraflu/ha-lefant/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/paraflu/ha-lefant/releases/tag/v1.0.0
