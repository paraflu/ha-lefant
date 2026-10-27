# Lefant M1 Robot Vacuum Home Assistant Integration

> **⚠️ Experimental.** The local LAN channel, the protocol version (3.3) and the
> telemetry datapoints below are confirmed on physical M1 units. **Commands**
> (start, pause, dock, fan speed, locate, spot) are **not** yet validated on
> hardware, and the cleaning status enum is only partly observed. Passing tests
> are not hardware validation. See [issue #1](https://github.com/paraflu/ha-lefant/issues/1).


[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=paraflu&repository=ha-lefant&category=integration)
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=lefant_m1)

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Custom Home Assistant integration for the **Lefant M1** robot vacuum cleaner, communicating directly over the **local Wi-Fi network**.

The robot answers the **Tuya LAN protocol 3.3** (`55AA` framing, AES-ECB with the
local key). That version was measured on two independent M1 units — firmware
`1.8.71` and `1.9.13` — via the UDP announce and a successful encrypted
`DP_QUERY`. It is *not* 3.5.

## Features

- **100% Local Communication**: no cloud latency or dependency once you have the local key.
- **Vacuum Entity (`StateVacuumEntity`)**: Start, Pause, Stop, Return to Dock, Spot Clean, Fan Speed, Locate.
- **Sensor Platform**: Battery (`%`), Cleaning duration (`minutes`), Cleaned area (`m²`).
- **UI Config Flow**: setup from the Home Assistant UI with connection validation.
- **Diagnostics tools** (see [Tools](#tools)): network identification and read-only DP probing.

### Private LAN transport

The integration talks to the robot with [tinytuya](https://github.com/jasonacox/tinytuya),
which implements Tuya LAN 3.1–3.5. The protocol version is a config field
defaulting to **3.3**, the version the M1 actually answers. Updates arrive from a
4-second poll (`local_polling`), not from a device push: Tinytuya is
request/response, so there is no persistent push channel to listen on.

## Prerequisites: IP Address, Device ID and Local Key

1. **IP Address** — the robot's LAN IP (recommended: a static DHCP lease on your router).
2. **Device ID** — 20-character virtual device ID, shown in the Lefant app's device info.
3. **Local Key** — 16-character per-device encryption key.

### Getting them

`Device ID` and `IP` are easy: the app shows the ID, the router shows the IP, and
`tools/diagnose_tuya_lan.py` confirms the robot on the network using **only the
public discovery key** (no user credentials).

The **local key is different**: it is a per-device cloud credential, delivered to
the app after login and kept in memory by the Tuya SDK. It is **not** in the APK,
not in the LAN announce, and not in any local file. In particular:

- `tinytuya scan` **does not** return keys (it only discovers devices).
- A Tuya IoT Platform project is **not** a verified path for a device bound to a
  Lefant account.
- MITM of the app traffic requires defeating certificate pinning: heavier than the
  method below, for the same result.

### Verified method: read the key from the app's SDK object

The Tuya SDK exposes the key through a public getter,
`com.thingclips.smart.sdk.bean.DeviceBean.getLocalKey()`. Hook it with
[Frida](https://frida.re/docs/android/) and read the value the app already holds.
This needs **no root on your phone** — it runs on an Android emulator on a PC —
and requires **no reset and no re-pairing**: the robot keeps its maps and the
official app keeps working. This is the method reported working on a physical M1
in [issue #1](https://github.com/paraflu/ha-lefant/issues/1).

#### Fast path

```bash
pip install frida-tools                     # Frida 17 or newer
XAPK=~/Downloads/Lefant_v3.4.5_APKPure.xapk tools/get_local_key.sh
```

The script prepares the emulator, installs the app, starts `frida-server`, attaches
`tools/frida_get_local_key.js` to the running app and waits. Log in in the emulator
window, open the vacuum's control screen, and it prints:

```
[M1] com.thingclips.smart.sdk.bean.DeviceBean
[M1]   devId    = bf23...
[M1]   localKey = ................   (len=16)
```

The hook only **reads**: it returns the original value, so the app behaves exactly
as before. Nothing is intercepted on the network, no certificate pinning is involved.

#### What the script does, step by step

1. **System image.** Downloads and validates `system-images;android-35;google_apis;x86_64`.
   Two properties are checked, because either one missing wastes hours:
   `ro.build.type=userdebug` (Play Store images are `user` builds and refuse
   `adb root`) and `libndk_translation` (the app ships **arm64-only** libraries, so
   an x86_64 image needs ARM translation).
2. **AVD.** Creates `Lefant_Root_API35` on a Pixel 6 profile.
3. **Boot with `-qemu -cpu host`.** **Required**: without AES-NI exposed to the
   guest, the translated arm64 code aborts in `libthingmmkv.so` with
   `CHECK failed: host_platform::kHasAES` and the app dies at startup. The script
   verifies AES is visible inside the guest.
4. **Root.** `adb root` → `uid=0(root)`; then `frida-server` is pushed to
   `/data/local/tmp` and started as root, matched to the installed `frida` version
   and to the emulator ABI (`x86_64`, not the app's `arm64-v8a`).
5. **App install.** Extracts base APK plus `arm64_v8a`, `en` and `xhdpi` splits from
   the XAPK and installs them together with `adb install-multiple`.
6. **Attach, not spawn.** The app is started normally and Frida attaches to its pid.
   Spawning through Frida (`-f`) is slower on a translated emulator and if the
   session drops, the hook is lost with it.

Manual equivalent, if you prefer to see every command:

```bash
sdkmanager "system-images;android-35;google_apis;x86_64"
avdmanager create avd -n Lefant_Root_API35 \
  -k "system-images;android-35;google_apis;x86_64" -d pixel_6
emulator -avd Lefant_Root_API35 -no-snapshot -memory 2048 -cores 2 \
  -gpu swiftshader_indirect -qemu -cpu host &
adb root && adb shell id                     # expect uid=0(root)
adb install-multiple -r -g ./*.apk           # base + arm64 + locale + density splits
curl -fL -o frida-server.xz \
  https://github.com/frida/frida/releases/download/$(frida --version)/frida-server-$(frida --version)-android-x86_64.xz
unxz -f frida-server.xz
adb push frida-server /data/local/tmp/ && adb shell chmod 755 /data/local/tmp/frida-server
adb shell '/data/local/tmp/frida-server -D' &
adb shell monkey -p com.yunshi.robotlife -c android.intent.category.LAUNCHER 1
frida -U -p $(adb shell pidof com.yunshi.robotlife) -l tools/frida_get_local_key.js
```

#### Troubleshooting the extraction

| Symptom | Cause |
|---|---|
| `adbd cannot run as root in production builds` | Play Store image; use `google_apis` |
| App dies instantly, `CHECK failed: host_platform::kHasAES` | missing `-qemu -cpu host` |
| Emulator killed with `QEMU2 CPU0 thread` hanging | host out of RAM; needs ~4 GB free |
| New emulator never appears, Frida attaches to an invisible one | a previous emulator still holds port 5554 — `adb emu kill` first |
| Frida exits immediately after `Resuming main thread!` | its REPL reads stdin: don't pipe the output (`\| head`, `\| grep`) and don't close the terminal |
| Hooks never fire, no output at all | wrong overload filter; a 17.x `returnType` check must use `.className` |

Treat the key as a secret: it does not belong in issues, logs, screenshots or
committed files. Some app stores' terms prohibit reverse engineering — that
judgement is yours. Note also that the key is **per device** and **rotates** if you
remove and re-pair the robot, so do not re-pair after extracting it.

### Verifying the key

```bash
export LEFANT_LOCAL_KEY='...'          # read from the environment, never argv
.venv/bin/python tools/probe_robot.py --host <robot-ip> --device-id <device-id> --dump-json
```

Exit codes: `0` success, `3` key rejected, `4` connection, `5` other. The tool is
read-only and never prints the key.

## Installation

### Method 1: HACS (Recommended)

Click the badge at the top of this page, or add the repository manually:

1. Open **HACS** > **Integrations** > **Three dots (top right)** > **Custom repositories**.
2. Add `https://github.com/paraflu/ha-lefant` as an **Integration**.
3. Search for **Lefant M1 Vacuum** and click **Download**.
4. Restart Home Assistant.

### Method 2: Manual Installation
1. Copy `custom_components/lefant_m1` into your Home Assistant `config/custom_components/`.
2. Restart Home Assistant.

## Configuration

Click the **Add integration** badge at the top of this page (it only works once
the integration is installed), or:

1. **Settings** > **Devices & Services** > **Add Integration** > **Lefant M1 Vacuum**.
2. Enter **IP Address**, **Device ID**, **Local Key**.
3. Submit; the integration tests the connection before saving.

The key is stored by Home Assistant in `.storage/core.config_entries`, not in this
repository.

## Data Points (DPs) Reference

IDs corroborated by the APK's `LaserDP` catalog **and** an encrypted `DP_QUERY`
answered by a physical M1. Values shown are what a docked robot reports.

| DP | Function | Type | Observed | Notes |
|-------|----------|------|----------|-------|
| `1` | Switch / Start | `bool` | — | `true` start/resume, `false` stop/pause (unvalidated) |
| `2` | Pause | `bool` | — | unvalidated |
| `3` | Return to Dock | `bool` | — | unvalidated |
| `4` | Cleaning Mode | `enum` | `smart` (issue #1) | other modes unconfirmed |
| `5` | Status | `enum` | `sleep` | case varies; cleaning states unconfirmed |
| `6` | Clean Duration | `int` | *not reported when idle* | minutes |
| `7` | Clean Area | `int` | *not reported when idle* | m² |
| `8` | Battery Level | `int` | `100` | 0–100 % |
| `9` | Fan Speed | `enum` | `strong` | values `gentle`, `normal`, `strong` (`gentle` = quiet) |
| `10` | Water Tank / Cistern | `enum` | `high` | not yet exposed as an entity |
| `27` | Break Clean | `bool` | `true` | not yet exposed |
| `28` | Fault / Error | `int` | `0` | non-zero forces the entity into `error` |
| `11` | Locate Robot | `bool` | — | **APK-only evidence** (`LaserDP.SEEK`), unvalidated |
| `45` | Unknown | `bool` | `true` | purpose still unidentified |
| `122` | Map Save Switch | `bool` | `true` | not yet exposed |
| `125` | Charging Pile | `bool` | `true` | not yet exposed |

Fan speed constants map `gentle` to Home Assistant's "quiet" semantics; sending
`quiet` — the value used by pre-3.3 assumptions and by the M210 reference — is
**not** valid on this robot.

## Tools

```bash
# identify Tuya devices on the LAN (no key, no login, read-only)
python3 tools/diagnose_tuya_lan.py --udp-wait 12

# read datapoints from the robot (needs LEFANT_LOCAL_KEY in the environment)
.venv/bin/python tools/probe_robot.py --host <ip> --device-id <id> --dump-json
.venv/bin/python tools/probe_robot.py --host <ip> --device-id <id> --watch 60
```

`--watch` is the way to learn the real enum values: run it and start a cleaning
from the app.

## Command confirmation

Commands update the local cache optimistically. If no matching status arrives
within 7 seconds, the integration logs a warning and queries actual DPs. Unrelated
pushes do not confirm commands; disconnect/unload cancels pending reconciliation.
Query failure discards unconfirmed optimism and retains last observed values.
This recovery policy does not prove that the robot performed an action.

## Running Unit Tests

```bash
python3 -m pytest tests/ -q
```

The suite is offline: Home Assistant is replaced by minimal doubles and the
transport by a fake client. No robot, network or credentials involved.

## License

MIT License. See [LICENSE](LICENSE) for details.
