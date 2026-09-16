"""Constants for the Lefant M1 vacuum integration."""

from __future__ import annotations

DOMAIN = "lefant_m1"

# Config entries keys
CONF_HOST = "host"
CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"

# Tuya Data Points (DPs) for Lefant M1
DP_SWITCH_GO = "1"  # bool: rw - True=start/resume, False=pause/stop
DP_PAUSE = "2"  # bool: rw - True=pause, False=resume
DP_SWITCH_CHARGE = "3"  # bool: rw - True=return to dock
DP_MODE = "4"  # str: rw - clean mode ("smart", "edge", "spot", "random", "standby")
DP_STATUS = "5"  # str: ro - working status string
DP_SUCTION = "14"  # str: rw - fan speed ("quiet", "normal", "strong")
DP_CLEAN_TIME = "18"  # int: ro - clean duration in minutes
DP_CLEAN_AREA = "19"  # int: ro - cleaned area in m²
DP_BATTERY = "23"  # int: ro - battery percentage (0-100)
DP_LOCATE = "24"  # bool: rw - locate robot beep
DP_ERROR_CODE = "25"  # int: ro - fault error bitmap / integer

# Vacuum Fan Speeds
FAN_SPEED_QUIET = "quiet"
FAN_SPEED_NORMAL = "normal"
FAN_SPEED_STRONG = "strong"
FAN_SPEED_LIST = [FAN_SPEED_QUIET, FAN_SPEED_NORMAL, FAN_SPEED_STRONG]

# Cleaning Modes
MODE_SMART = "smart"
MODE_EDGE = "edge"
MODE_SPOT = "spot"
MODE_RANDOM = "random"
MODE_STANDBY = "standby"

# Fallback string activities (compatible with HA VacuumActivity)
ACTIVITY_CLEANING = "cleaning"
ACTIVITY_DOCKED = "docked"
ACTIVITY_IDLE = "idle"
ACTIVITY_PAUSED = "paused"
ACTIVITY_RETURNING = "returning"
ACTIVITY_ERROR = "error"

# Mapping from DP5 (and raw status strings) to HA VacuumActivity values
STATUS_TO_ACTIVITY: dict[str, str] = {
    # Cleaning states
    "smart_clean": ACTIVITY_CLEANING,
    "wall_clean": ACTIVITY_CLEANING,
    "spot_clean": ACTIVITY_CLEANING,
    "random_clean": ACTIVITY_CLEANING,
    "cleaning": ACTIVITY_CLEANING,
    "smart": ACTIVITY_CLEANING,
    "edge": ACTIVITY_CLEANING,
    "spot": ACTIVITY_CLEANING,
    "random": ACTIVITY_CLEANING,
    # Paused states
    "smart_clean_pause": ACTIVITY_PAUSED,
    "wall_clean_pause": ACTIVITY_PAUSED,
    "spot_clean_pause": ACTIVITY_PAUSED,
    "goto_charge_pause": ACTIVITY_PAUSED,
    "pause": ACTIVITY_PAUSED,
    "paused": ACTIVITY_PAUSED,
    # Docking / Docked states
    "goto_charge": ACTIVITY_RETURNING,
    "returning": ACTIVITY_RETURNING,
    "charging": ACTIVITY_DOCKED,
    "charge_done": ACTIVITY_DOCKED,
    "docked": ACTIVITY_DOCKED,
    # Idle / Sleep states
    "standby": ACTIVITY_IDLE,
    "dormant": ACTIVITY_IDLE,
    "sleep": ACTIVITY_IDLE,
    "idle": ACTIVITY_IDLE,
    # Error states
    "error": ACTIVITY_ERROR,
    "fault": ACTIVITY_ERROR,
}


def map_status_to_activity(status: str | None, error_code: int | None = None) -> str:
    """Map robot raw status and error code to standard HA activity string."""
    if error_code and error_code != 0:
        return ACTIVITY_ERROR
    if not status:
        return ACTIVITY_IDLE
    normalized = str(status).strip().lower()
    return STATUS_TO_ACTIVITY.get(normalized, ACTIVITY_IDLE)
