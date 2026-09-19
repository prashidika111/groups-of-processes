"""
ActivityOS Application Launcher
Launches configured applications associated with an Activity, discovers the
resulting real Linux processes and descendant child PIDs, and returns the resolved PIDs.
"""

from __future__ import annotations
import os
import shlex
import subprocess
import time
from typing import List, Dict, Tuple, Optional, Any
from .os_adapter import OSAdapter
from .models import ConfiguredApp


class ApplicationLauncher:
    """
    Component: Application Launcher (Start Activity / Launch Flow)
    Role: Spawns configured application executables and discovers the resulting
    active Linux PIDs (including child/forked processes).
    """

    def __init__(self, os_adapter: Optional[OSAdapter] = None):
        self.os_adapter = os_adapter or OSAdapter()
        self.spawned_processes: List[subprocess.Popen] = []

    def launch_app(self, app: ConfiguredApp) -> Tuple[Optional[int], List[int], str]:
        """
        Launches an application and discovers its parent PID and child processes.
        Returns: (parent_pid, all_resolved_pids, message)
        """
        cmd = app.command.strip()
        if not cmd:
            return None, [], "Empty launch command"

        # Split command and args safely
        try:
            if isinstance(cmd, list):
                args = list(cmd)
            elif app.args:
                args = [cmd] + list(app.args)
            else:
                args = shlex.split(cmd)
        except Exception as e:
            return None, [], f"Command parse error: {e}"

        try:
            # Spawn in a new process group / detached where appropriate
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True if hasattr(os, "setsid") else False,
            )
            self.spawned_processes.append(proc)
            parent_pid = proc.pid
        except FileNotFoundError:
            return None, [], f"Application executable not found: '{args[0]}'"
        except PermissionError:
            return None, [], f"Permission denied executing: '{args[0]}'"
        except Exception as e:
            return None, [], f"Failed to launch '{cmd}': {e}"

        # Brief delay to allow initial fork/exec of child processes
        time.sleep(0.3)

        # Resolve descendant child processes (e.g. Chrome / VS Code subprocesses)
        child_pids = self.os_adapter.find_child_pids(parent_pid)
        all_pids = [parent_pid] + [p for p in child_pids if p != parent_pid]

        return parent_pid, all_pids, f"Launched '{app.name}' (PID {parent_pid}, {len(all_pids)} total processes)"

    def launch_activity_apps(self, apps: List[ConfiguredApp]) -> Tuple[List[int], List[str]]:
        """
        Launches all configured applications for an Activity and aggregates all resolved PIDs.
        Returns: (all_pids, status_messages)
        """
        total_pids: List[int] = []
        messages: List[str] = []

        for app in apps:
            parent_pid, pids, msg = self.launch_app(app)
            messages.append(msg)
            if pids:
                total_pids.extend(pids)

        return sorted(list(set(total_pids))), messages
