"""
Trail Weather App – Configuration
Defines available trails, supports uploaded custom trails.
"""

import os
import tempfile

# ─── Available Trails ────────────────────────────────────────────────

TRAILS = {
    "AZT": {
        "name": "Arizona Trail",
        "emoji": "🏜️",
        "timezone": "America/Phoenix",
    },
    "PCT": {
        "name": "Pacific Crest Trail",
        "emoji": "🏔️",
        "timezone": "America/Los_Angeles",
    },
    "CDT": {
        "name": "Continental Divide Trail",
        "emoji": "⛰️",
        "timezone": "America/Denver",
    },
    "AT": {
        "name": "Appalachian Trail",
        "emoji": "🌲",
        "timezone": "America/New_York",
    },
    "CT": {
        "name": "Colorado Trail",
        "emoji": "🗻",
        "timezone": "America/Denver",
    },
    "Rennsteig": {
        "name": "Rennsteig",
        "emoji": "🌳",
        "timezone": "Europe/Berlin",
    },
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "trail_weather_uploads")


def get_trail_files(trail_key: str) -> dict:
    """Return all file paths for a given trail key."""
    trail_dir = os.path.join(DATA_DIR, trail_key)
    return {
        "trackpoints": os.path.join(trail_dir, f"{trail_key}_trackpoints.csv"),
        "mm_nobo": os.path.join(trail_dir, f"{trail_key}_MM_points_list_NOBO.csv"),
        "mm_sobo": os.path.join(trail_dir, f"{trail_key}_MM_points_list_SOBO.csv"),
        "emblem": os.path.join(trail_dir, f"{trail_key}_emblem.png"),
        "poi": os.path.join(trail_dir, f"{trail_key}_POI.csv"),
    }


def get_available_trails() -> dict:
    """Return only trails that have the required data files present."""
    available = {}
    for key, meta in TRAILS.items():
        files = get_trail_files(key)
        if os.path.isfile(files["trackpoints"]) and os.path.isfile(files["mm_nobo"]):
            available[key] = meta
    return available
