"""
ActivityOS Timeline Logger
Maintains the application-level audit trail of ActivityOS events,
state changes, and Control Engine actions.
"""

from __future__ import annotations
import time
from typing import List, Dict, Callable, Optional, Any
from .models import Activity, EventRecord


class TimelineLogger:
    """
    Component: Timeline Logger (Review 1 & 2 Methodology)
    Role: Records Activity-level decisions and Control Engine actions into
    the Activity's event_log[] and notifies dashboard subscribers.
    """

    def __init__(self):
        self._listeners: List[Callable[[EventRecord], None]] = []

    def subscribe(self, callback: Callable[[EventRecord], None]):
        """Registers a callback to receive new events in real time."""
        self._listeners.append(callback)

    def log_event(
        self,
        activity: Activity,
        action: str,
        details: str = "",
        outcomes: Optional[Dict[str, Any]] = None
    ) -> EventRecord:
        """
        Creates an EventRecord, appends it to activity.event_log,
        and broadcasts to subscribers.
        """
        record = EventRecord(
            action=action,
            activity_id=activity.activity_id,
            details=details,
            timestamp=time.time(),
            iso_time=time.strftime("%H:%M:%S"),
            outcomes=outcomes or {},
        )
        activity.event_log.append(record)

        # Notify any UI subscribers
        for listener in self._listeners:
            try:
                listener(record)
            except Exception:
                pass

        return record
