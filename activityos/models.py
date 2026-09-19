"""
ActivityOS Data Models
Defines the core Activity representation, Session lifecycle entity,
Process details, Resource snapshots, and Timeline event records.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Any


class ActivityState(str, Enum):
    STOPPED = "STOPPED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


@dataclass
class ProcessDetail:
    """Represents real-time status and resource usage of a member process."""
    pid: int
    name: str = ""
    cmdline: str = ""
    cpu_percent: float = 0.0
    memory_bytes: int = 0
    memory_mb: float = 0.0
    status: str = "running"  # e.g., 'running', 'sleeping', 'stopped' (SIGSTOP), 'unavailable'
    is_alive: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceSnapshot:
    """Aggregated resource snapshot for an Activity across its member processes."""
    cpu_percent: float = 0.0
    memory_bytes: int = 0
    memory_mb: float = 0.0
    memory_gb: float = 0.0
    process_count: int = 0
    timestamp: float = field(default_factory=time.time)
    contributing_processes: List[ProcessDetail] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["contributing_processes"] = [p.to_dict() for p in self.contributing_processes]
        return d


@dataclass
class EventRecord:
    """Application-level record of ActivityOS actions and lifecycle transitions."""
    action: str
    activity_id: str
    details: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    iso_time: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    outcomes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConfiguredApp:
    """Specification of an application associated with an Activity for launching."""
    name: str
    command: str
    args: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Session:
    """
    Represents one execution period / run of an Activity.
    Maintains clear separation: Activity = reusable definition, Session = run.
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    activity_id: str = ""
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    peak_cpu: float = 0.0
    peak_memory_mb: float = 0.0
    final_state: str = "ACTIVE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Activity:
    """
    The central Activity abstraction.
    Maintained at the application layer above Linux processes.
    """
    activity_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    member_processes: List[int] = field(default_factory=list)  # Active PIDs
    state: ActivityState = ActivityState.STOPPED
    priority_level: int = 0  # Nice value: -20 to 19 (0 is normal)
    configured_apps: List[ConfiguredApp] = field(default_factory=list)
    resource_snapshot: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    event_log: List[EventRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    active_session_id: Optional[str] = None
    sessions: List[Session] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "name": self.name,
            "member_processes": self.member_processes,
            "state": self.state.value if isinstance(self.state, ActivityState) else str(self.state),
            "priority_level": self.priority_level,
            "configured_apps": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.configured_apps],
            "resource_snapshot": self.resource_snapshot.to_dict(),
            "event_log": [e.to_dict() for e in self.event_log],
            "created_at": self.created_at,
            "active_session_id": self.active_session_id,
            "sessions": [s.to_dict() for s in self.sessions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Activity:
        state = ActivityState(data.get("state", ActivityState.STOPPED.value))
        apps = [
            ConfiguredApp(**a) if isinstance(a, dict) else a
            for a in data.get("configured_apps", [])
        ]
        events = [
            EventRecord(**e) if isinstance(e, dict) else e
            for e in data.get("event_log", [])
        ]
        sessions = [
            Session(**s) if isinstance(s, dict) else s
            for s in data.get("sessions", [])
        ]
        snap_data = data.get("resource_snapshot", {})
        processes = [
            ProcessDetail(**p) if isinstance(p, dict) else p
            for p in snap_data.get("contributing_processes", [])
        ]
        snapshot = ResourceSnapshot(
            cpu_percent=snap_data.get("cpu_percent", 0.0),
            memory_bytes=snap_data.get("memory_bytes", 0),
            memory_mb=snap_data.get("memory_mb", 0.0),
            memory_gb=snap_data.get("memory_gb", 0.0),
            process_count=snap_data.get("process_count", 0),
            timestamp=snap_data.get("timestamp", time.time()),
            contributing_processes=processes,
        )

        return cls(
            activity_id=data.get("activity_id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Untitled Activity"),
            member_processes=data.get("member_processes", []),
            state=state,
            priority_level=data.get("priority_level", 0),
            configured_apps=apps,
            resource_snapshot=snapshot,
            event_log=events,
            created_at=data.get("created_at", time.time()),
            active_session_id=data.get("active_session_id"),
            sessions=sessions,
        )
