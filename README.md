# Lefant M1 Robot Vacuum Home Assistant Integration

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Custom Home Assistant integration for the **Lefant M1** robot vacuum cleaner communicating directly over the **local Wi-Fi network (Tuya LAN protocol 3.5)**.

## Features

- **100% Local Communication**: No cloud latency, no cloud dependency after obtaining the local key.
- **Push-Based Updates (`local_push`)**: The robot pushes state and battery changes in real time via persistent TCP socket with periodic heartbeats.
- **Vacuum Entity (`StateVacuumEntity`)**:
  - Start, Pause, Stop, Return to Dock
  - Spot Clean mode
  - Fan Speed control (`quiet`, `normal`, `strong`)
  - Locate robot (beep)
  - Real-time status mapping (Cleaning, Paused, Returning, Docked, Idle, Error)
- **Sensor Platform**:
  - Battery percentage (`%`)
  - Cleaning duration (`minutes`)
  - Cleaned area (`m²`)
- **UI Config Flow**: Simple setup from the Home Assistant UI with connection validation.

## Prerequisites: Finding Device ID and Local Key

Because the Lefant M1 runs on the Tuya protocol (3.5 with AES-GCM encryption), Home Assistant requires:
1. **IP Address**: The local IP assigned to the robot (recommended: configure a static DHCP lease on your router).
2. **Device ID**: 20-character virtual device ID.
3. **Local Key**: 16-character encryption key.

You can extract the `Device ID` and `Local Key` using:
- **Tuya IoT Developer Platform** (e.g. via Cloud API Device Details explorer)
- **TinyTuya CLI scan**: `tinytuya scan`
- **Network Proxy / MITM** on the Lefant mobile app traffic.

*Note:* You do not need to re-pair the vacuum or disconnect it from the Lefant mobile app; the robot supports concurrent local LAN sessions.

## Installation

### Method 1: HACS (Recommended)
1. Open **HACS** in Home Assistant.
2. Click **Integrations** > **Three dots (top right)** > **Custom repositories**.
3. Add `https://github.com/paraflu/ha-lefant` as an **Integration**.
4. Search for **Lefant M1 Vacuum** and click **Download**.
5. Restart Home Assistant.

### Method 2: Manual Installation
1. Copy the directory `custom_components/lefant_m1` into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Lefant M1 Vacuum**.
3. Enter:
   - **IP Address**
   - **Device ID**
   - **Local Key**
4. Click **Submit**. Home Assistant will test the connection and negotiate a session key before saving.

## Data Points (DPs) Reference

| DP ID | Function | Type | Values |
|-------|----------|------|--------|
| `1` | Switch / Start | `bool` | `true` (start/resume), `false` (stop/pause) |
| `2` | Pause | `bool` | `true` (pause) |
| `3` | Return to Dock | `bool` | `true` (dock/charge) |
| `4` | Cleaning Mode | `enum` | `smart`, `edge`, `spot`, `random`, `standby` |
| `5` | Status | `enum` | `smart_clean`, `charging`, `standby`, `goto_charge`, etc. |
| `14` | Fan Speed | `enum` | `quiet`, `normal`, `strong` |
| `18` | Clean Duration | `int` | minutes |
| `19` | Clean Area | `int` | m² |
| `23` | Battery Level | `int` | 0-100% |
| `24` | Locate Robot | `bool` | `true` (beep) |
| `25` | Fault / Error | `bitmap/int` | Error code |

## Running Unit Tests

```bash
python3 tests/test_pytuya_client.py
python3 tests/test_state_mapping.py
```

## License

MIT License. See [LICENSE](LICENSE) for details.
