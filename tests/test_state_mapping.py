"""Unit tests for the Lefant M1 state mapping logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "lefant_m1"))

from const import (
    ACTIVITY_CLEANING,
    ACTIVITY_DOCKED,
    ACTIVITY_ERROR,
    ACTIVITY_IDLE,
    ACTIVITY_PAUSED,
    ACTIVITY_RETURNING,
    map_status_to_activity,
)


def test_cleaning_states() -> None:
    assert map_status_to_activity("smart_clean") == ACTIVITY_CLEANING
    assert map_status_to_activity("wall_clean") == ACTIVITY_CLEANING
    assert map_status_to_activity("spot_clean") == ACTIVITY_CLEANING
    assert map_status_to_activity("random_clean") == ACTIVITY_CLEANING
    assert map_status_to_activity("cleaning") == ACTIVITY_CLEANING
    assert map_status_to_activity("smart") == ACTIVITY_CLEANING
    assert map_status_to_activity("edge") == ACTIVITY_CLEANING


def test_paused_states() -> None:
    assert map_status_to_activity("smart_clean_pause") == ACTIVITY_PAUSED
    assert map_status_to_activity("wall_clean_pause") == ACTIVITY_PAUSED
    assert map_status_to_activity("spot_clean_pause") == ACTIVITY_PAUSED
    assert map_status_to_activity("goto_charge_pause") == ACTIVITY_PAUSED
    assert map_status_to_activity("pause") == ACTIVITY_PAUSED
    assert map_status_to_activity("paused") == ACTIVITY_PAUSED


def test_returning_and_docked_states() -> None:
    assert map_status_to_activity("goto_charge") == ACTIVITY_RETURNING
    assert map_status_to_activity("returning") == ACTIVITY_RETURNING
    assert map_status_to_activity("charging") == ACTIVITY_DOCKED
    assert map_status_to_activity("charge_done") == ACTIVITY_DOCKED
    assert map_status_to_activity("docked") == ACTIVITY_DOCKED


def test_idle_and_sleep_states() -> None:
    assert map_status_to_activity("standby") == ACTIVITY_IDLE
    assert map_status_to_activity("dormant") == ACTIVITY_IDLE
    assert map_status_to_activity("sleep") == ACTIVITY_IDLE
    assert map_status_to_activity("idle") == ACTIVITY_IDLE
    assert map_status_to_activity("") == ACTIVITY_IDLE
    assert map_status_to_activity(None) == ACTIVITY_IDLE
    assert map_status_to_activity("unknown_custom_mode") == ACTIVITY_IDLE


def test_error_code_override() -> None:
    # Any nonzero error code must force activity to ERROR regardless of status
    assert map_status_to_activity("smart_clean", error_code=3) == ACTIVITY_ERROR
    assert map_status_to_activity("charging", error_code=1) == ACTIVITY_ERROR
    assert map_status_to_activity("standby", error_code=255) == ACTIVITY_ERROR
    # Zero error code allows normal mapping
    assert map_status_to_activity("smart_clean", error_code=0) == ACTIVITY_CLEANING


if __name__ == "__main__":
    test_cleaning_states()
    test_paused_states()
    test_returning_and_docked_states()
    test_idle_and_sleep_states()
    test_error_code_override()
    print("all state mapping tests passed")
