"""
ActivityOS Activity Manager
The central orchestrator of the Activity-Centric layer.
Owns Activity records, state machines, and the authoritative Activity <-> Process membership.
Coordinates the Process Grouper, Resource Monitor, Activity Control Engine, Timeline Logger,
and Persistence Storage.
"""

from __future__ import annotations
import time
import uuid
from typing import Dict, List, Set, Tuple, Optional, Any
from .models import Activity, ActivityState, Session, ConfiguredApp, ResourceSnapshot, ProcessDetail
from .os_adapter import OSAdapter
from .grouper import ProcessGrouper
from .monitor import ResourceMonitor
from .control import ActivityControlEngine, ControlResult
from .launcher import ApplicationLauncher
from .logger import TimelineLogger
from .storage import ActivityStorage


class ActivityManager:
    """
    Component: Activity Manager (Review 1 & 2 Methodology)
    Role: Single owner of the activity <-> process mapping and Activity lifecycle.
    Exposes operations: create, start, pause, resume, stop, monitor, drilldown.
    """

    def __init__(
        self,
        os_adapter: Optional[OSAdapter] = None,
        storage_path: Optional[str] = None
    ):
        self.os_adapter = os_adapter or OSAdapter()
        self.grouper = ProcessGrouper(self.os_adapter)
        self.monitor = ResourceMonitor(self.os_adapter)
        self.control_engine = ActivityControlEngine(self.os_adapter)
        self.launcher = ApplicationLauncher(self.os_adapter)
        self.logger = TimelineLogger()
        self.storage = ActivityStorage(storage_path)

        # Dictionary of activity_id -> Activity
        self._activities: Dict[str, Activity] = {}
        self._notified_dead_pids: Dict[str, Set[int]] = {}
        self._load_persisted_activities()

    def _load_persisted_activities(self):
        """Loads activities from disk and validates live memberships."""
        loaded = self.storage.load_activities()
        for act_id, act in loaded.items():
            # Check which member PIDs are actually alive
            valid_pids, _ = self.grouper.validate_pids(act.member_processes)
            act.member_processes = valid_pids
            act.state = ActivityState.STOPPED
            self._activities[act_id] = act

    def get_all_activities(self) -> List[Activity]:
        """Returns all registered activities."""
        return list(self._activities.values())

    def get_activity(self, activity_id: str) -> Optional[Activity]:
        """Looks up an Activity by its unique activity_id."""
        return self._activities.get(activity_id)

    def create_activity(
        self,
        name: str,
        member_pids: Optional[List[int]] = None,
        configured_apps: Optional[List[Dict[str, Any]]] = None,
        priority_level: int = 0
    ) -> Activity:
        """
        Creates a new Activity definition with validated member processes and configured apps.
        The activity is initialized in STOPPED state, ready to be started explicitly.
        """
        act_id = str(uuid.uuid4())[:8]
        pids = member_pids or []
        valid_pids, dead_pids = self.grouper.validate_pids(pids)

        apps = []
        if configured_apps:
            for a in configured_apps:
                if isinstance(a, dict):
                    apps.append(ConfiguredApp(
                        name=a.get("name", "App"),
                        command=a.get("command", ""),
                        args=a.get("args", [])
                    ))
                elif isinstance(a, ConfiguredApp):
                    apps.append(a)

        activity = Activity(
            activity_id=act_id,
            name=name.strip() or "Untitled Activity",
            member_processes=valid_pids,
            state=ActivityState.STOPPED,
            priority_level=priority_level,
            configured_apps=apps,
            created_at=time.time(),
        )

        self._activities[act_id] = activity
        self._notified_dead_pids[act_id] = set()

        # Initial resource poll (cached baseline)
        self.monitor.aggregate_activity(activity)

        # Record creation in timeline log
        detail_msg = f"Created activity '{activity.name}' in STOPPED state with {len(valid_pids)} initial processes."
        if dead_pids:
            detail_msg += f" (Omitted {len(dead_pids)} dead/invalid PIDs: {dead_pids})."
        self.logger.log_event(
            activity,
            action="create",
            details=detail_msg,
            outcomes={"valid_pids": valid_pids, "omitted_dead_pids": dead_pids}
        )

        self.storage.save_activities(self._activities)
        return activity

    def start_activity(self, activity_id: str) -> Tuple[bool, str]:
        """
        Starts an Activity:
        1. Validates existing member PIDs; removes stale PIDs that exited before start.
        2. Launches any configured applications and discovers real running child PIDs.
        3. Initializes a new Session run.
        4. Updates state to ACTIVE.
        5. Logs the action and records events.
        """
        activity = self.get_activity(activity_id)
        if not activity:
            return False, f"Activity ID '{activity_id}' not found."

        # 1. Check if member processes previously associated are still alive
        valid_existing, dead_existing = self.grouper.validate_pids(activity.member_processes)
        if dead_existing:
            self.logger.log_event(
                activity,
                action="process_unavailable",
                details=f"Process(es) {dead_existing} exited before activity start and were removed from active membership.",
                outcomes={"dead_pids": dead_existing}
            )
        activity.member_processes = valid_existing

        # 2. Launch configured applications if any
        launched_pids: List[int] = []
        messages: List[str] = []

        if activity.configured_apps:
            pids, msgs = self.launcher.launch_activity_apps(activity.configured_apps)
            launched_pids = pids
            messages = msgs

        # 3. Merge and validate all member PIDs
        combined_pids = list(set(activity.member_processes + launched_pids))
        valid_pids, dead_pids = self.grouper.validate_pids(combined_pids)
        activity.member_processes = valid_pids
        activity.state = ActivityState.ACTIVE

        # 4. Start a new Session run
        session = Session(
            activity_id=activity.activity_id,
            started_at=time.time(),
            final_state="ACTIVE"
        )
        activity.sessions.append(session)
        activity.active_session_id = session.session_id

        # 5. Aggregate initial live resources
        self.monitor.aggregate_activity(activity)

        summary = f"Started activity '{activity.name}'. Associated {len(valid_pids)} active processes."
        if messages:
            summary += f" ({'; '.join(messages)})"
        if dead_existing:
            summary += f" ({len(dead_existing)} dead PIDs omitted: {dead_existing})"

        self.logger.log_event(
            activity,
            action="start",
            details=summary,
            outcomes={
                "associated_pids": valid_pids,
                "messages": messages,
                "omitted_dead_pids": dead_existing,
            }
        )

        self.storage.save_activities(self._activities)
        return True, summary

    def pause_activity(self, activity_id: str) -> ControlResult:
        """
        Pauses an Activity:
        Passes the PID set to Activity Control Engine to deliver kill(pid, SIGSTOP).
        Records per-process results and timeline log.
        """
        activity = self.get_activity(activity_id)
        if not activity:
            return ControlResult(
                action="pause",
                activity_id=activity_id,
                summary="Activity not found",
                is_success=False
            )

        res = self.control_engine.pause_activity(activity)

        # Update resource snapshot to reflect stopped state
        self.monitor.aggregate_activity(activity)

        self.logger.log_event(
            activity,
            action="pause",
            details=res.summary,
            outcomes={"succeeded": res.succeeded_pids, "failed": res.failed_pids}
        )

        self.storage.save_activities(self._activities)
        return res

    def resume_activity(self, activity_id: str) -> ControlResult:
        """
        Resumes an Activity:
        Passes the PID set to Activity Control Engine to deliver kill(pid, SIGCONT).
        Records per-process results and timeline log.
        """
        activity = self.get_activity(activity_id)
        if not activity:
            return ControlResult(
                action="resume",
                activity_id=activity_id,
                summary="Activity not found",
                is_success=False
            )

        res = self.control_engine.resume_activity(activity)

        # Update resource snapshot
        self.monitor.aggregate_activity(activity)

        self.logger.log_event(
            activity,
            action="resume",
            details=res.summary,
            outcomes={"succeeded": res.succeeded_pids, "failed": res.failed_pids}
        )

        self.storage.save_activities(self._activities)
        return res

    def stop_activity(self, activity_id: str) -> ControlResult:
        """
        Stops an Activity:
        Signals member processes with SIGTERM and ends the current Session run.
        """
        activity = self.get_activity(activity_id)
        if not activity:
            return ControlResult(
                action="stop",
                activity_id=activity_id,
                summary="Activity not found",
                is_success=False
            )

        res = self.control_engine.stop_activity(activity)

        # Finalize active session
        if activity.active_session_id:
            for s in activity.sessions:
                if s.session_id == activity.active_session_id:
                    s.ended_at = time.time()
                    s.final_state = "STOPPED"
                    break
            activity.active_session_id = None

        # Clean up member PIDs (since processes were terminated)
        activity.member_processes = []
        self.monitor.aggregate_activity(activity)

        # Reset notified dead PIDs tracker for this activity
        if activity_id in self._notified_dead_pids:
            self._notified_dead_pids[activity_id].clear()

        self.logger.log_event(
            activity,
            action="stop",
            details=res.summary,
            outcomes={"succeeded": res.succeeded_pids, "failed": res.failed_pids}
        )

        self.storage.save_activities(self._activities)
        return res

    def delete_activity(self, activity_id: str) -> bool:
        """Stops and permanently deletes an Activity."""
        if activity_id in self._activities:
            self.stop_activity(activity_id)
            del self._activities[activity_id]
            if activity_id in self._notified_dead_pids:
                del self._notified_dead_pids[activity_id]
            self.storage.save_activities(self._activities)
            return True
        return False

    def poll_all_resources(self) -> Dict[str, Any]:
        """
        Periodic heartbeat: updates resource snapshots for all activities
        and returns overall system stats.
        Handles processes exiting gracefully without crashing and logs process_unavailable.
        """
        for act in self._activities.values():
            if act.state in (ActivityState.ACTIVE, ActivityState.PAUSED):
                snap = self.monitor.aggregate_activity(act)

                # Check for member processes that exited/became unavailable during active session
                if act.activity_id not in self._notified_dead_pids:
                    self._notified_dead_pids[act.activity_id] = set()

                for proc in snap.contributing_processes:
                    if not proc.is_alive and proc.pid not in self._notified_dead_pids[act.activity_id]:
                        self._notified_dead_pids[act.activity_id].add(proc.pid)
                        self.logger.log_event(
                            act,
                            action="process_unavailable",
                            details=f"Process PID {proc.pid} ({proc.name}) exited or became unavailable.",
                            outcomes={"pid": proc.pid, "name": proc.name}
                        )

                # Track peak resource usage for the active session
                if act.active_session_id:
                    for s in act.sessions:
                        if s.session_id == act.active_session_id:
                            if snap.cpu_percent > s.peak_cpu:
                                s.peak_cpu = snap.cpu_percent
                            if snap.memory_mb > s.peak_memory_mb:
                                s.peak_memory_mb = snap.memory_mb

        return {
            "system": self.monitor.get_system_overview(),
            "activities": [a.to_dict() for a in self._activities.values()]
        }

    def get_drilldown(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns full drill-down data for an activity:
        Activity summary, CPU, Memory, and each individual process's contribution.
        """
        activity = self.get_activity(activity_id)
        if not activity:
            return None

        # Freshen the snapshot
        snapshot = self.monitor.aggregate_activity(activity)
        return {
            "activity_id": activity.activity_id,
            "name": activity.name,
            "state": activity.state.value,
            "priority_level": activity.priority_level,
            "summary": snapshot.to_dict(),
            "event_log": [e.to_dict() for e in activity.event_log[-15:]],  # Most recent 15
        }
