"""
ActivityOS Desktop Application Host
Initializes the desktop window via pywebview (with fallback to native Tkinter GUI)
and binds the ActivityManager API bridge for the user interface.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..manager import ActivityManager


class ActivityOSApi:
    """
    Python <-> JavaScript bridge API exposed to the desktop UI window.
    Translates UI events into ActivityManager operations.
    """

    def __init__(self, manager: ActivityManager):
        self.manager = manager

    def poll_heartbeat(self) -> Dict[str, Any]:
        """Returns fresh system overview and activity snapshots."""
        return self.manager.poll_all_resources()

    def get_available_processes(self, filter_text: str = "") -> List[Dict[str, Any]]:
        """Discovers running processes on the system."""
        return self.manager.grouper.discover_available_processes(filter_text)

    def create_activity(
        self,
        name: str,
        member_pids: List[int],
        configured_apps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Creates a new activity."""
        act = self.manager.create_activity(
            name=name,
            member_pids=member_pids,
            configured_apps=configured_apps
        )
        return act.to_dict()

    def start_activity(self, activity_id: str) -> Dict[str, Any]:
        """Starts an activity and launches configured apps."""
        ok, msg = self.manager.start_activity(activity_id)
        return {"success": ok, "message": msg}

    def pause_activity(self, activity_id: str) -> Dict[str, Any]:
        """Pauses member processes via SIGSTOP."""
        res = self.manager.pause_activity(activity_id)
        return res.to_dict()

    def resume_activity(self, activity_id: str) -> Dict[str, Any]:
        """Resumes member processes via SIGCONT."""
        res = self.manager.resume_activity(activity_id)
        return res.to_dict()

    def stop_activity(self, activity_id: str) -> Dict[str, Any]:
        """Stops member processes via SIGTERM."""
        res = self.manager.stop_activity(activity_id)
        return res.to_dict()

    def delete_activity(self, activity_id: str) -> bool:
        """Deletes an activity definition."""
        return self.manager.delete_activity(activity_id)

    def get_drilldown(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """Fetches granular contributing processes and audit log."""
        return self.manager.get_drilldown(activity_id)


def launch_desktop_gui(manager: ActivityManager, force_tk: bool = False):
    """
    Launches the desktop GUI.
    Uses pywebview native window by default, with automatic fallback to Tkinter.
    """
    if not force_tk:
        try:
            import webview

            api = ActivityOSApi(manager)
            html_path = Path(__file__).parent / "web" / "index.html"

            window = webview.create_window(
                title="ActivityOS — Activity-Centric Resource Manager",
                url=str(html_path.resolve()),
                js_api=api,
                width=1180,
                height=780,
                min_size=(960, 640),
                text_select=True,
            )
            webview.start(debug=False)
            return
        except Exception as e:
            print(f"[ActivityOS] PyWebView unavailable ({e}), falling back to native Tkinter GUI...")

    # Fallback to Tkinter native GUI
    from .tk_view import launch_tk_gui
    launch_tk_gui(manager)
