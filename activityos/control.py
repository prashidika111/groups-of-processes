"""
ActivityOS Activity Control Engine
Translates single Activity-level control commands (pause, resume, stop, priority)
into per-process Linux operations (SIGSTOP, SIGCONT, SIGTERM, setpriority).
Tracks and records granular outcomes per member process without crashing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from .os_adapter import OSAdapter, SIGSTOP, SIGCONT, SIGTERM
from .models import Activity, ActivityState


@dataclass
class ControlResult:
    """Detailed outcome of translating an Activity command to member processes."""
    action: str
    activity_id: str
    succeeded_pids: List[int] = field(default_factory=list)
    failed_pids: Dict[int, str] = field(default_factory=dict)
    summary: str = ""
    is_success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "activity_id": self.activity_id,
            "succeeded_pids": self.succeeded_pids,
            "failed_pids": self.failed_pids,
            "summary": self.summary,
            "is_success": self.is_success,
        }


class ActivityControlEngine:
    """
    Component: Activity Control Engine (Review 1 & 2 Methodology)
    Role: Receives resolved PID set from Activity Manager, translates the single
    Activity-level command into one Linux system call per PID, and records results.
    """

    def __init__(self, os_adapter: Optional[OSAdapter] = None):
        self.os_adapter = os_adapter or OSAdapter()

    def pause_activity(self, activity: Activity) -> ControlResult:
        """
        Translates 'Pause Activity' into kill(pid, SIGSTOP) for each member PID.
        Suspends process execution without terminating them.
        """
        succeeded = []
        failed = {}

        for pid in activity.member_processes:
            ok, msg = self.os_adapter.send_signal(pid, SIGSTOP)
            if ok:
                succeeded.append(pid)
            else:
                failed[pid] = msg

        total = len(activity.member_processes)
        if total == 0:
            summary = "Activity has no associated processes to pause."
            activity.state = ActivityState.PAUSED
            return ControlResult(
                action="pause",
                activity_id=activity.activity_id,
                succeeded_pids=[],
                failed_pids={},
                summary=summary,
                is_success=True,
            )

        if len(succeeded) == total:
            summary = f"All {total} member processes paused successfully (SIGSTOP)."
            activity.state = ActivityState.PAUSED
            is_success = True
        elif len(succeeded) > 0:
            summary = f"{len(succeeded)} / {total} processes paused; {len(failed)} unavailable or failed."
            activity.state = ActivityState.PAUSED
            is_success = True
        else:
            summary = f"Failed to pause processes: {', '.join(f'PID {p}: {m}' for p, m in failed.items())}"
            is_success = False

        return ControlResult(
            action="pause",
            activity_id=activity.activity_id,
            succeeded_pids=succeeded,
            failed_pids=failed,
            summary=summary,
            is_success=is_success,
        )

    def resume_activity(self, activity: Activity) -> ControlResult:
        """
        Translates 'Resume Activity' into kill(pid, SIGCONT) for each member PID.
        Resumes process execution in the Linux scheduler.
        """
        succeeded = []
        failed = {}

        for pid in activity.member_processes:
            ok, msg = self.os_adapter.send_signal(pid, SIGCONT)
            if ok:
                succeeded.append(pid)
            else:
                failed[pid] = msg

        total = len(activity.member_processes)
        if total == 0:
            summary = "Activity has no associated processes to resume."
            activity.state = ActivityState.ACTIVE
            return ControlResult(
                action="resume",
                activity_id=activity.activity_id,
                succeeded_pids=[],
                failed_pids={},
                summary=summary,
                is_success=True,
            )

        if len(succeeded) == total:
            summary = f"All {total} member processes resumed successfully (SIGCONT)."
            activity.state = ActivityState.ACTIVE
            is_success = True
        elif len(succeeded) > 0:
            summary = f"{len(succeeded)} / {total} processes resumed; {len(failed)} unavailable or failed."
            activity.state = ActivityState.ACTIVE
            is_success = True
        else:
            summary = f"Failed to resume processes: {', '.join(f'PID {p}: {m}' for p, m in failed.items())}"
            is_success = False

        return ControlResult(
            action="resume",
            activity_id=activity.activity_id,
            succeeded_pids=succeeded,
            failed_pids=failed,
            summary=summary,
            is_success=is_success,
        )

    def stop_activity(self, activity: Activity) -> ControlResult:
        """
        Translates 'Stop Activity' into kill(pid, SIGTERM) for member processes.
        Gracefully terminates the run/session.
        """
        succeeded = []
        failed = {}

        for pid in activity.member_processes:
            ok, msg = self.os_adapter.send_signal(pid, SIGTERM)
            if ok:
                succeeded.append(pid)
            else:
                failed[pid] = msg

        total = len(activity.member_processes)
        activity.state = ActivityState.STOPPED

        if total == 0:
            summary = "Activity stopped (no active member processes)."
        else:
            summary = f"SIGTERM delivered to {len(succeeded)}/{total} member processes."
            if failed:
                summary += f" ({len(failed)} processes failed or already exited)."

        return ControlResult(
            action="stop",
            activity_id=activity.activity_id,
            succeeded_pids=succeeded,
            failed_pids=failed,
            summary=summary,
            is_success=True,
        )

    def set_activity_priority(self, activity: Activity, nice_value: int) -> ControlResult:
        """
        Translates Activity-level priority setting into setpriority() per member process.
        Nice values range from -20 (highest priority) to 19 (lowest priority).
        """
        succeeded = []
        failed = {}

        # Clamp nice value
        nice_value = max(-20, min(19, nice_value))

        for pid in activity.member_processes:
            ok, msg = self.os_adapter.set_priority(pid, nice_value)
            if ok:
                succeeded.append(pid)
            else:
                failed[pid] = msg

        total = len(activity.member_processes)
        activity.priority_level = nice_value

        summary = f"Priority adjusted to nice {nice_value} for {len(succeeded)}/{total} processes."
        return ControlResult(
            action="set_priority",
            activity_id=activity.activity_id,
            succeeded_pids=succeeded,
            failed_pids=failed,
            summary=summary,
            is_success=len(succeeded) > 0 or total == 0,
        )
