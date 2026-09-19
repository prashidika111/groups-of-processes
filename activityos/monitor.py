"""
ActivityOS Resource Monitor
Responsible for polling process-level Linux resource data (/proc/<pid>/stat and status),
aggregating resource utilization across an Activity's member processes,
and producing the Activity-level resource_snapshot and drill-down metrics.
"""

from __future__ import annotations
import time
from typing import List, Dict, Tuple, Optional, Any
from .os_adapter import OSAdapter
from .models import Activity, ResourceSnapshot, ProcessDetail


class ResourceMonitor:
    """
    Component: Resource Monitor (Review 1 & 2 Methodology)
    Role: Computes per-process CPU & Memory from Linux /proc accounting data,
    aggregates metrics per Activity, and supplies drill-down data to the Dashboard.
    """

    def __init__(self, os_adapter: Optional[OSAdapter] = None):
        self.os_adapter = os_adapter or OSAdapter()

    def sample_process(self, pid: int) -> ProcessDetail:
        """
        Samples a single process's live metrics from /proc.
        If the process has exited, returns an unavailable ProcessDetail.
        """
        metrics = self.os_adapter.get_process_metrics(pid)
        if not metrics:
            return ProcessDetail(
                pid=pid,
                name=f"PID {pid}",
                cmdline="Process exited / unavailable",
                cpu_percent=0.0,
                memory_bytes=0,
                memory_mb=0.0,
                status="unavailable",
                is_alive=False,
            )

        return ProcessDetail(
            pid=pid,
            name=metrics.get("name", f"PID {pid}"),
            cmdline=metrics.get("cmdline", ""),
            cpu_percent=metrics.get("cpu_percent", 0.0),
            memory_bytes=metrics.get("memory_bytes", 0),
            memory_mb=metrics.get("memory_mb", 0.0),
            status=metrics.get("status", "running"),
            is_alive=True,
        )

    def aggregate_activity(self, activity: Activity) -> ResourceSnapshot:
        """
        Iterates over member_processes[], queries /proc for each PID,
        and aggregates CPU utilization and memory into one Activity-level snapshot.
        """
        total_cpu = 0.0
        total_memory_bytes = 0
        alive_count = 0
        contributing: List[ProcessDetail] = []

        for pid in activity.member_processes:
            detail = self.sample_process(pid)
            contributing.append(detail)
            if detail.is_alive:
                alive_count += 1
                total_cpu += detail.cpu_percent
                total_memory_bytes += detail.memory_bytes

        total_mb = total_memory_bytes / (1024 * 1024)
        total_gb = total_memory_bytes / (1024 * 1024 * 1024)

        snapshot = ResourceSnapshot(
            cpu_percent=round(total_cpu, 1),
            memory_bytes=total_memory_bytes,
            memory_mb=round(total_mb, 2),
            memory_gb=round(total_gb, 2),
            process_count=len(activity.member_processes),
            timestamp=time.time(),
            contributing_processes=contributing,
        )

        # Update the Activity object's cached resource snapshot
        activity.resource_snapshot = snapshot
        return snapshot

    def get_system_overview(self) -> Dict[str, Any]:
        """Returns overall system CPU and Memory utilisation."""
        return self.os_adapter.get_system_overview()
