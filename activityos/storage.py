"""
ActivityOS Local Storage
Provides lightweight persistent storage for Activity definitions,
configured applications, and historical session logs in JSON format.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from .models import Activity, ActivityState


class ActivityStorage:
    """
    Component: Persistence Layer
    Role: Saves and retrieves Activity definitions across restarts.
    Handles PID ephemeral nature cleanly by validating or clearing stale PIDs on load.
    """

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path:
            self.file_path = Path(storage_path)
        else:
            # Default to ~/.activityos/activities.json or local dir
            home = Path.home() / ".activityos"
            home.mkdir(parents=True, exist_ok=True)
            self.file_path = home / "activities.json"

    def save_activities(self, activities: Dict[str, Activity]) -> bool:
        """Serializes all activities to JSON."""
        try:
            data = {
                "version": "0.6.0",
                "activities": [act.to_dict() for act in activities.values()]
            }
            # Write atomically using a temporary file
            temp_path = self.file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.file_path)
            return True
        except Exception as e:
            print(f"[ActivityStorage] Error saving activities: {e}")
            return False

    def load_activities(self) -> Dict[str, Activity]:
        """
        Loads saved activities from JSON.
        Resets ephemeral runtime states (e.g. state defaults to STOPPED if process is dead).
        """
        if not self.file_path.exists():
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            activities = {}
            for act_dict in data.get("activities", []):
                act = Activity.from_dict(act_dict)
                # Ensure state is reset to STOPPED on fresh load
                act.state = ActivityState.STOPPED
                activities[act.activity_id] = act
            return activities
        except Exception as e:
            print(f"[ActivityStorage] Error loading activities: {e}")
            return {}
