"""
ActivityOS Linux OS Adapter
Direct interface to the Linux operating system kernel and process mechanisms.
Reads process accounting strictly through the Linux /proc pseudo-filesystem
and issues POSIX signals (SIGSTOP, SIGCONT, SIGTERM) and priority controls (setpriority).

Target OS: Linux (unmodified kernel).
"""

from __future__ import annotations
import os
import sys
import time
import signal
from typing import Dict, List, Tuple, Optional, Any

# Standard Linux POSIX signals
SIGSTOP = getattr(signal, "SIGSTOP", 19)
SIGCONT = getattr(signal, "SIGCONT", 18)
SIGTERM = getattr(signal, "SIGTERM", 15)


class LinuxProcReader:
    """
    Direct parser for the Linux /proc pseudo-filesystem.
    Reads:
      - /proc/<pid>/stat   (process CPU jiffies, state, ppid)
      - /proc/<pid>/status (process RSS physical memory)
      - /proc/<pid>/cmdline (process command line arguments)
      - /proc/stat         (system total CPU jiffies)
      - /proc/meminfo      (system total & available RAM)
    """

    def __init__(self, proc_root: str = "/proc"):
        self.proc_root = proc_root
        self._prev_proc_times: Dict[int, Tuple[int, float]] = {}  # pid -> (proc_jiffies, timestamp)
        self._prev_sys_jiffies: Optional[int] = None
        self._prev_sys_time: Optional[float] = None
        self._num_cpus = os.cpu_count() or 1

    def is_available(self) -> bool:
        """Verifies that the Linux /proc filesystem is present and accessible."""
        return os.path.isdir(self.proc_root) and os.path.exists(os.path.join(self.proc_root, "stat"))

    def read_system_total_jiffies(self) -> int:
        """Reads cumulative CPU jiffies from /proc/stat across all cores."""
        stat_path = os.path.join(self.proc_root, "stat")
        try:
            with open(stat_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("cpu "):
                        # Format: cpu user nice system idle iowait irq softirq steal guest guest_nice
                        parts = line.split()[1:]
                        return sum(int(x) for x in parts)
        except Exception:
            pass
        return 0

    def read_system_overview(self) -> Dict[str, Any]:
        """
        Reads system-wide CPU and Memory directly from /proc/stat and /proc/meminfo.
        """
        cpu_pct = 0.0
        now = time.time()
        try:
            curr_sys_jiffies = self.read_system_total_jiffies()
            if self._prev_sys_jiffies is not None and self._prev_sys_time is not None:
                delta_jiffies = curr_sys_jiffies - self._prev_sys_jiffies
                delta_time = now - self._prev_sys_time
                if delta_time > 0 and delta_jiffies > 0:
                    # In Linux /proc/stat, total jiffies increase at HZ * num_cpus
                    clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
                    expected_jiffies = delta_time * clk_tck * self._num_cpus
                    if expected_jiffies > 0:
                        cpu_pct = min(100.0, max(0.0, (delta_jiffies / expected_jiffies) * 100.0))
            self._prev_sys_jiffies = curr_sys_jiffies
            self._prev_sys_time = now
        except Exception:
            pass

        # Memory from /proc/meminfo
        total_kb = 0
        avail_kb = 0
        try:
            meminfo_path = os.path.join(self.proc_root, "meminfo")
            with open(meminfo_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
        except Exception:
            pass

        used_kb = max(0, total_kb - avail_kb)
        mem_pct = (used_kb / total_kb * 100.0) if total_kb > 0 else 0.0

        return {
            "cpu_percent": round(cpu_pct, 1),
            "memory_percent": round(mem_pct, 1),
            "memory_total_mb": round(total_kb / 1024, 1),
            "memory_used_mb": round(used_kb / 1024, 1),
        }

    def parse_proc_stat(self, pid: int) -> Optional[Dict[str, Any]]:
        """
        Parses /proc/<pid>/stat.
        Handles processes with spaces or parentheses in comm by locating rightmost ')'.
        Extracts utime, stime, state, ppid.
        """
        stat_path = os.path.join(self.proc_root, str(pid), "stat")
        try:
            with open(stat_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            return None

        rparen = content.rfind(")")
        lparen = content.find("(")
        if rparen == -1 or lparen == -1:
            return None

        comm = content[lparen + 1 : rparen]
        rest = content[rparen + 2 :].split()

        try:
            # Field 3: state ('R', 'S', 'D', 'Z', 'T', 't')
            # Field 4: ppid
            # Field 14: utime (index 11 of rest)
            # Field 15: stime (index 12 of rest)
            # Field 16: cutime (index 13 of rest)
            # Field 17: cstime (index 14 of rest)
            state = rest[0]
            ppid = int(rest[1])
            utime = int(rest[11])
            stime = int(rest[12])
            cutime = int(rest[13])
            cstime = int(rest[14])
            # Process-level CPU accounting strictly uses process's own utime + stime
            # to avoid double-counting child processes when parent & child belong to the same activity.
            total_jiffies = utime + stime
            return {
                "pid": pid,
                "comm": comm,
                "state": state,
                "ppid": ppid,
                "utime": utime,
                "stime": stime,
                "cutime": cutime,
                "cstime": cstime,
                "total_jiffies": total_jiffies,
            }
        except (IndexError, ValueError):
            return None

    def parse_proc_status(self, pid: int) -> Dict[str, Any]:
        """
        Parses /proc/<pid>/status for exact physical RSS memory (VmRSS) and process state.
        """
        status_path = os.path.join(self.proc_root, str(pid), "status")
        rss_bytes = 0
        state_str = "running"
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            rss_kb = int(parts[1])
                            rss_bytes = rss_kb * 1024
                    elif line.startswith("State:"):
                        state_str = line.split(":", 1)[1].strip()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass

        return {"rss_bytes": rss_bytes, "state_str": state_str}

    def read_cmdline(self, pid: int) -> str:
        """Reads /proc/<pid>/cmdline, separated by null bytes."""
        cmd_path = os.path.join(self.proc_root, str(pid), "cmdline")
        try:
            with open(cmd_path, "rb") as f:
                data = f.read()
            parts = data.split(b"\x00")
            cleaned = [p.decode("utf-8", errors="replace") for p in parts if p]
            return " ".join(cleaned)
        except Exception:
            return ""

    def calculate_cpu_percent(self, pid: int, current_proc_jiffies: int) -> float:
        """
        Derives per-process CPU utilization strictly from /proc/<pid>/stat jiffies over interval dt:
          cpu_seconds = (proc_jiffies_2 - proc_jiffies_1) / SC_CLK_TCK
          cpu_percent = (cpu_seconds / delta_time) * 100
        """
        now = time.time()
        cpu_pct = 0.0

        if pid in self._prev_proc_times:
            prev_jiffies, prev_time = self._prev_proc_times[pid]
            delta_time = now - prev_time
            delta_jiffies = current_proc_jiffies - prev_jiffies

            try:
                clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
            except Exception:
                clk_tck = 100

            if delta_time > 0 and delta_jiffies >= 0:
                cpu_seconds = delta_jiffies / clk_tck
                cpu_pct = (cpu_seconds / delta_time) * 100.0

        self._prev_proc_times[pid] = (current_proc_jiffies, now)
        return min(max(round(cpu_pct, 1), 0.0), 100.0 * self._num_cpus)

    def enumerate_pids(self) -> List[int]:
        """Enumerates active PIDs from integer subdirectories in /proc."""
        pids = []
        if not os.path.isdir(self.proc_root):
            return pids
        for entry in os.listdir(self.proc_root):
            if entry.isdigit():
                try:
                    pids.append(int(entry))
                except ValueError:
                    continue
        return sorted(pids)


class LinuxOSAdapter:
    """
    Linux-only OS Adapter.
    Strictly uses:
      - Linux /proc filesystem for real process discovery and resource metrics
      - POSIX system calls (os.kill, os.setpriority) for process control
    """

    def __init__(self, proc_root: str = "/proc"):
        self.proc = LinuxProcReader(proc_root=proc_root)

    def is_linux_environment(self) -> bool:
        """Returns True if running on a real Linux system with /proc available."""
        return sys.platform.startswith("linux") and self.proc.is_available()

    def discover_processes(self) -> List[Dict[str, Any]]:
        """
        Discovers running Linux processes by reading /proc/<pid>/stat and status.
        Never fakes process values.
        """
        results = []
        state_map = {
            "R": "running",
            "S": "sleeping",
            "D": "disk sleep",
            "Z": "zombie",
            "T": "stopped",
            "t": "stopped",
        }

        for pid in self.proc.enumerate_pids():
            stat_data = self.proc.parse_proc_stat(pid)
            if not stat_data:
                continue
            status_data = self.proc.parse_proc_status(pid)
            cmdline = self.proc.read_cmdline(pid)
            name = stat_data["comm"] or (cmdline.split()[0] if cmdline else f"PID {pid}")
            mem_bytes = status_data["rss_bytes"]

            st = stat_data["state"]
            status_str = state_map.get(st, "running")

            results.append({
                "pid": pid,
                "name": name,
                "cmdline": cmdline or name,
                "status": status_str,
                "memory_bytes": mem_bytes,
                "memory_mb": round(mem_bytes / (1024 * 1024), 2),
                "cpu_percent": 0.0,
                "is_alive": True,
            })

        return results

    def get_process_metrics(self, pid: int) -> Optional[Dict[str, Any]]:
        """
        Reads real-time CPU% and RSS Memory for a PID strictly from /proc.
        """
        stat_data = self.proc.parse_proc_stat(pid)
        if not stat_data:
            return None

        status_data = self.proc.parse_proc_status(pid)
        cmdline = self.proc.read_cmdline(pid)
        cpu_pct = self.proc.calculate_cpu_percent(pid, stat_data["total_jiffies"])
        mem_bytes = status_data["rss_bytes"]

        st = stat_data["state"]
        is_stopped = st in ("T", "t")
        status_str = "stopped" if is_stopped else "running"

        return {
            "pid": pid,
            "name": stat_data["comm"],
            "cmdline": cmdline or stat_data["comm"],
            "cpu_percent": cpu_pct,
            "memory_bytes": mem_bytes,
            "memory_mb": round(mem_bytes / (1024 * 1024), 2),
            "status": status_str,
            "is_alive": True,
        }

    def get_system_overview(self) -> Dict[str, Any]:
        """Reads overall machine CPU and Memory utilization from /proc."""
        return self.proc.read_system_overview()

    def send_signal(self, pid: int, sig: int) -> Tuple[bool, str]:
        """
        Sends POSIX signal to a process using standard os.kill(pid, sig).
        Handles:
          - SIGSTOP: Kernel stops scheduling the process.
          - SIGCONT: Kernel resumes scheduling the process.
          - SIGTERM: Kernel delivers graceful termination signal.
        """
        try:
            os.kill(pid, sig)
            action_name = {SIGSTOP: "SIGSTOP (Suspend)", SIGCONT: "SIGCONT (Resume)", SIGTERM: "SIGTERM (Stop)"}.get(sig, str(sig))
            return True, f"Signal {action_name} delivered to PID {pid}"
        except ProcessLookupError:
            return False, f"PID {pid} no longer exists"
        except PermissionError:
            return False, f"Permission denied delivering signal to PID {pid}"
        except Exception as e:
            return False, f"Error signaling PID {pid}: {e}"

    def set_priority(self, pid: int, nice_value: int) -> Tuple[bool, str]:
        """
        Adjusts process nice priority using standard POSIX os.setpriority().
        Nice values range from -20 (highest priority) to 19 (lowest priority).
        """
        nice_value = max(-20, min(19, nice_value))
        if hasattr(os, "setpriority") and hasattr(os, "PRIO_PROCESS"):
            try:
                os.setpriority(os.PRIO_PROCESS, pid, nice_value)
                return True, f"Priority set to nice {nice_value} for PID {pid}"
            except PermissionError:
                return False, f"Permission denied setting nice {nice_value} for PID {pid} (requires root/CAP_SYS_NICE)"
            except ProcessLookupError:
                return False, f"PID {pid} no longer exists"
            except Exception as e:
                return False, f"Error setting priority for PID {pid}: {e}"

        # Fallback to standard renice system command if available
        ret = os.system(f"renice -n {nice_value} -p {pid} > /dev/null 2>&1")
        if ret == 0:
            return True, f"Priority set to nice {nice_value} for PID {pid}"
        return False, f"Failed to renice PID {pid}"

    def is_pid_alive(self, pid: int) -> bool:
        """Checks whether a process is alive by checking its Linux /proc directory or signal 0."""
        if self.proc.is_available():
            stat_path = os.path.join(self.proc.proc_root, str(pid), "stat")
            return os.path.exists(stat_path)
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError, PermissionError):
            return False

    def find_child_pids(self, parent_pid: int) -> List[int]:
        """
        Discovers descendant child processes spawned by an application
        by traversing parent PIDs (ppid) in /proc.
        """
        children = []
        all_pids = self.proc.enumerate_pids()
        queue = [parent_pid]

        while queue:
            current = queue.pop(0)
            for pid in all_pids:
                stat_data = self.proc.parse_proc_stat(pid)
                if stat_data and stat_data["ppid"] == current:
                    children.append(pid)
                    queue.append(pid)

        return children


# Primary alias
OSAdapter = LinuxOSAdapter
