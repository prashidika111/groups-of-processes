"""
ActivityOS Process Grouper
Responsible for process discovery and establishing the Activity <-> Process membership.
Validates candidate PIDs against the OS process table and returns verified process sets.
"""

from __future__ import annotations
from typing import List, Dict, Set, Tuple, Optional, Any
from .os_adapter import OSAdapter
from .models import ProcessDetail


class ProcessGrouper:
    """
    Component: Process Grouper (Review 1 & 2 Methodology)
    Role: Discovers system processes, validates user-selected candidate PIDs,
    and constructs the member_processes relationship.
    """

    def __init__(self, os_adapter: Optional[OSAdapter] = None):
        self.os_adapter = os_adapter or OSAdapter()

    def discover_available_processes(
        self,
        filter_text: str = "",
        exclude_system_threads: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Discovers all running processes on the system for user selection.
        Optionally filters out kernel threads or matches filter_text.
        """
        raw_list = self.os_adapter.discover_processes()
        filtered = []
        filter_lower = filter_text.lower() if filter_text else ""

        for p in raw_list:
            name = p.get("name", "")
            cmdline = p.get("cmdline", "")

            # Exclude kernel threads (e.g. kworker, rcu) on Linux if requested
            if exclude_system_threads:
                if name.startswith("[") and name.endswith("]"):
                    continue
                if name.startswith("kworker") or name.startswith("ksoftirqd"):
                    continue

            if filter_lower:
                if filter_lower not in name.lower() and filter_lower not in cmdline.lower():
                    continue

            filtered.append(p)

        # Sort by memory descending
        filtered.sort(key=lambda x: x.get("memory_bytes", 0), reverse=True)
        return filtered

    def validate_pids(self, candidate_pids: List[int]) -> Tuple[List[int], List[int]]:
        """
        Validates a list of user-selected PIDs against the live OS process table.
        Returns: (valid_pids, dead_pids)
        """
        valid = []
        dead = []
        for pid in set(candidate_pids):
            if pid <= 0:
                continue
            if self.os_adapter.is_pid_alive(pid):
                valid.append(pid)
            else:
                dead.append(pid)
        return sorted(valid), sorted(dead)

    def associate_processes(self, pids: List[int]) -> List[int]:
        """
        Finalizes process membership validation and returns the active PID list.
        """
        valid, _ = self.validate_pids(pids)
        return valid
