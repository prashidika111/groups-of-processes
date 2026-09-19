#!/usr/bin/env python3
"""
ActivityOS Automated Test Suite
Validates the core 60% functional implementation:
- Activity Data Models & Serialization
- Linux /proc Stat & Status Parser with mock fixtures
- Process Grouper & PID validation
- Resource Monitor & Activity-level aggregation
- Activity Control Engine & Signal translation (SIGSTOP, SIGCONT, SIGTERM)
- Activity Manager & End-to-End Activity Lifecycle
- Storage Persistence
"""

import os
import sys
import time
import shutil
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from activityos.models import Activity, ActivityState, Session, ProcessDetail, ResourceSnapshot, EventRecord
from activityos.os_adapter import LinuxProcReader, OSAdapter, SIGSTOP, SIGCONT, SIGTERM
from activityos.grouper import ProcessGrouper
from activityos.monitor import ResourceMonitor
from activityos.control import ActivityControlEngine
from activityos.manager import ActivityManager
from activityos.storage import ActivityStorage


class TestDataModels(unittest.TestCase):
    """Tests for ActivityOS data structures and state machines."""

    def test_activity_creation_and_dict(self):
        act = Activity(name="Study", member_processes=[101, 102])
        self.assertEqual(act.name, "Study")
        self.assertEqual(act.member_processes, [101, 102])
        self.assertEqual(act.state, ActivityState.STOPPED)

        d = act.to_dict()
        self.assertEqual(d["name"], "Study")
        self.assertEqual(d["state"], "STOPPED")
        self.assertEqual(d["member_processes"], [101, 102])

        restored = Activity.from_dict(d)
        self.assertEqual(restored.name, "Study")
        self.assertEqual(restored.activity_id, act.activity_id)
        self.assertEqual(restored.member_processes, [101, 102])

    def test_session_lifecycle(self):
        sess = Session(activity_id="act-1", started_at=time.time())
        self.assertIsNone(sess.ended_at)
        self.assertEqual(sess.peak_cpu, 0.0)

        sess.peak_cpu = 42.5
        sess.ended_at = time.time() + 100
        d = sess.to_dict()
        self.assertEqual(d["peak_cpu"], 42.5)
        self.assertIsNotNone(d["ended_at"])


class TestLinuxProcReader(unittest.TestCase):
    """Tests Linux /proc parsing with realistic mock fixtures."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.proc_root = os.path.join(self.temp_dir, "proc")
        os.makedirs(self.proc_root)

        # Mock /proc/stat
        with open(os.path.join(self.proc_root, "stat"), "w", encoding="utf-8") as f:
            f.write("cpu  1000 200 300 5000 50 10 20 0 0 0\n")

        # Mock /proc/meminfo
        with open(os.path.join(self.proc_root, "meminfo"), "w", encoding="utf-8") as f:
            f.write("MemTotal:        16384000 kB\nMemFree:          4096000 kB\nMemAvailable:     8192000 kB\n")

        # Mock /proc/1821/stat (Chrome with spaces in comm)
        p1_dir = os.path.join(self.proc_root, "1821")
        os.makedirs(p1_dir)
        with open(os.path.join(p1_dir, "stat"), "w", encoding="utf-8") as f:
            f.write("1821 (Web Content) S 1 1821 1821 0 -1 4194304 100 0 0 0 150 250 10 20 20 0 4 0 50000 12345 6789\n")

        with open(os.path.join(p1_dir, "status"), "w", encoding="utf-8") as f:
            f.write("Name:\tWeb Content\nState:\tS (sleeping)\nVmRSS:\t  204800 kB\n")

        with open(os.path.join(p1_dir, "cmdline"), "wb") as f:
            f.write(b"/usr/lib/firefox/firefox\x00--content-proc\x00")

        # Mock /proc/1942/stat (Suspended process with state 'T')
        p2_dir = os.path.join(self.proc_root, "1942")
        os.makedirs(p2_dir)
        with open(os.path.join(p2_dir, "stat"), "w", encoding="utf-8") as f:
            f.write("1942 (code) T 1 1942 1942 0 -1 4194304 50 0 0 0 300 400 0 0 20 0 2 0 60000 98765 4321\n")

        with open(os.path.join(p2_dir, "status"), "w", encoding="utf-8") as f:
            f.write("Name:\tcode\nState:\tT (stopped)\nVmRSS:\t  409600 kB\n")

        self.reader = LinuxProcReader(proc_root=self.proc_root)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_proc_stat_parsing(self):
        stat = self.reader.parse_proc_stat(1821)
        self.assertIsNotNone(stat)
        self.assertEqual(stat["pid"], 1821)
        self.assertEqual(stat["comm"], "Web Content")
        self.assertEqual(stat["state"], "S")
        self.assertEqual(stat["utime"], 150)
        self.assertEqual(stat["stime"], 250)
        # Process total jiffies = utime + stime (excluding child process time)
        self.assertEqual(stat["total_jiffies"], 150 + 250)

    def test_proc_status_memory(self):
        status = self.reader.parse_proc_status(1821)
        # 204800 kB = 209715200 bytes
        self.assertEqual(status["rss_bytes"], 204800 * 1024)

        status_stopped = self.reader.parse_proc_status(1942)
        self.assertEqual(status_stopped["rss_bytes"], 409600 * 1024)
        self.assertIn("stopped", status_stopped["state_str"].lower())

    def test_system_overview_read(self):
        overview = self.reader.read_system_overview()
        # 16384000 kB = 16000 MB, Avail 8000 MB -> 50%
        self.assertAlmostEqual(overview["memory_percent"], 50.0, places=0)


class TestGrouperAndMonitor(unittest.TestCase):
    """Tests ProcessGrouper and ResourceMonitor aggregation."""

    def test_resource_aggregation(self):
        # Create an Activity with mock metrics
        act = Activity(name="Coding", member_processes=[99901, 99902])

        class MockAdapter(OSAdapter):
            def is_pid_alive(self, pid: int) -> bool:
                return True

            def get_process_metrics(self, pid: int):
                if pid == 99901:
                    return {
                        "pid": 99901,
                        "name": "code",
                        "cmdline": "code .",
                        "cpu_percent": 12.5,
                        "memory_bytes": 500 * 1024 * 1024,
                        "memory_mb": 500.0,
                        "status": "running",
                        "is_alive": True,
                    }
                elif pid == 99902:
                    return {
                        "pid": 99902,
                        "name": "node",
                        "cmdline": "node server.js",
                        "cpu_percent": 8.5,
                        "memory_bytes": 300 * 1024 * 1024,
                        "memory_mb": 300.0,
                        "status": "running",
                        "is_alive": True,
                    }
                return None

        adapter = MockAdapter()
        monitor = ResourceMonitor(adapter)
        snapshot = monitor.aggregate_activity(act)

        self.assertAlmostEqual(snapshot.cpu_percent, 21.0, places=1)
        self.assertAlmostEqual(snapshot.memory_mb, 800.0, places=1)
        self.assertEqual(snapshot.process_count, 2)
        self.assertEqual(len(snapshot.contributing_processes), 2)
        self.assertEqual(snapshot.contributing_processes[0].name, "code")


class TestControlEngine(unittest.TestCase):
    """Tests translation of Activity commands into POSIX signals and failure handling."""

    def test_pause_and_resume_translation(self):
        act = Activity(name="Research", member_processes=[501, 502, 503])
        signals_sent = []

        class MockAdapter(OSAdapter):
            def send_signal(self, pid: int, sig: int):
                signals_sent.append((pid, sig))
                if pid == 503:
                    # Simulate process dying
                    return False, "Process no longer exists"
                return True, "Signal delivered"

        adapter = MockAdapter()
        engine = ActivityControlEngine(adapter)

        # 1. Pause
        res = engine.pause_activity(act)
        self.assertEqual(res.action, "pause")
        self.assertEqual(res.succeeded_pids, [501, 502])
        self.assertIn(503, res.failed_pids)
        self.assertEqual(act.state, ActivityState.PAUSED)
        self.assertEqual(len(signals_sent), 3)
        self.assertEqual(signals_sent[0], (501, SIGSTOP))

        # 2. Resume
        signals_sent.clear()
        res_resume = engine.resume_activity(act)
        self.assertEqual(res_resume.action, "resume")
        self.assertEqual(res_resume.succeeded_pids, [501, 502])
        self.assertEqual(act.state, ActivityState.ACTIVE)
        self.assertEqual(signals_sent[0], (501, SIGCONT))


class TestActivityManagerEndToEnd(unittest.TestCase):
    """Tests the full end-to-end lifecycle in ActivityManager."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_file = os.path.join(self.temp_dir, "test_activities.json")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_complete_activity_lifecycle(self):
        # 1. Initialize ActivityManager
        manager = ActivityManager(storage_path=self.storage_file)

        # Mock adapter with test PIDs
        class LifecycleMockAdapter(OSAdapter):
            def __init__(self):
                super().__init__()
                self.alive_pids = {1001, 1002}
                self.stopped_pids = set()

            def is_pid_alive(self, pid: int) -> bool:
                return pid in self.alive_pids

            def send_signal(self, pid: int, sig: int):
                if pid not in self.alive_pids:
                    return False, "Process not found"
                if sig == SIGSTOP:
                    self.stopped_pids.add(pid)
                    return True, "Suspended"
                elif sig == SIGCONT:
                    self.stopped_pids.discard(pid)
                    return True, "Resumed"
                elif sig == SIGTERM:
                    self.alive_pids.discard(pid)
                    return True, "Terminated"
                return True, "Signal sent"

            def get_process_metrics(self, pid: int):
                if pid not in self.alive_pids:
                    return None
                is_stopped = pid in self.stopped_pids
                return {
                    "pid": pid,
                    "name": f"worker_{pid}",
                    "cmdline": f"worker_{pid}",
                    "cpu_percent": 0.0 if is_stopped else 15.0,
                    "memory_bytes": 100 * 1024 * 1024,
                    "memory_mb": 100.0,
                    "status": "stopped" if is_stopped else "running",
                    "is_alive": True,
                }

        mock_adapter = LifecycleMockAdapter()
        manager.os_adapter = mock_adapter
        manager.grouper.os_adapter = mock_adapter
        manager.monitor.os_adapter = mock_adapter
        manager.control_engine.os_adapter = mock_adapter

        # 2. CREATE ACTIVITY (Initial state must be STOPPED)
        act = manager.create_activity("Study", member_pids=[1001, 1002])
        self.assertEqual(act.name, "Study")
        self.assertEqual(act.member_processes, [1001, 1002])
        self.assertEqual(act.state, ActivityState.STOPPED)
        self.assertTrue(any(e.action == "create" for e in act.event_log))

        # 3. START ACTIVITY (Transitions to ACTIVE, initiates Session)
        ok, start_msg = manager.start_activity(act.activity_id)
        self.assertTrue(ok)
        self.assertEqual(act.state, ActivityState.ACTIVE)
        self.assertIsNotNone(act.active_session_id)
        self.assertTrue(any(e.action == "start" for e in act.event_log))

        # 4. MONITOR & AGGREGATION
        snap = manager.monitor.aggregate_activity(act)
        self.assertAlmostEqual(snap.cpu_percent, 30.0, places=1)
        self.assertAlmostEqual(snap.memory_mb, 200.0, places=1)
        self.assertEqual(snap.process_count, 2)

        # 5. PAUSE ACTIVITY (SIGSTOP)
        res_pause = manager.pause_activity(act.activity_id)
        self.assertTrue(res_pause.is_success)
        self.assertEqual(act.state, ActivityState.PAUSED)
        self.assertEqual(mock_adapter.stopped_pids, {1001, 1002})
        # After pause, CPU drops to 0.0
        snap_paused = act.resource_snapshot
        self.assertEqual(snap_paused.cpu_percent, 0.0)
        self.assertTrue(any(e.action == "pause" for e in act.event_log))

        # 6. RESUME ACTIVITY (SIGCONT)
        res_resume = manager.resume_activity(act.activity_id)
        self.assertTrue(res_resume.is_success)
        self.assertEqual(act.state, ActivityState.ACTIVE)
        self.assertEqual(len(mock_adapter.stopped_pids), 0)
        # After resume, CPU returns
        snap_resumed = act.resource_snapshot
        self.assertAlmostEqual(snap_resumed.cpu_percent, 30.0, places=1)
        self.assertTrue(any(e.action == "resume" for e in act.event_log))

        # 7. DRILL-DOWN INSPECTION
        drill = manager.get_drilldown(act.activity_id)
        self.assertIsNotNone(drill)
        self.assertEqual(drill["name"], "Study")
        self.assertEqual(len(drill["summary"]["contributing_processes"]), 2)
        self.assertTrue(len(drill["event_log"]) >= 4)

        # 8. STOP ACTIVITY (SIGTERM)
        res_stop = manager.stop_activity(act.activity_id)
        self.assertEqual(act.state, ActivityState.STOPPED)
        self.assertIsNone(act.active_session_id)
        self.assertTrue(any(e.action == "stop" for e in act.event_log))

        # 9. PERSISTENCE VERIFICATION
        # Create a new manager instance loading from the saved storage file
        new_manager = ActivityManager(storage_path=self.storage_file)
        loaded_act = new_manager.get_activity(act.activity_id)
        self.assertIsNotNone(loaded_act)
        self.assertEqual(loaded_act.name, "Study")

    def test_process_exits_before_start(self):
        """Edge Case: A process associated with an Activity exits BEFORE start_activity() is called."""
        manager = ActivityManager(storage_path=self.storage_file)

        class EdgeCaseAdapter(OSAdapter):
            def __init__(self):
                super().__init__()
                self.alive_pids = {2001, 2002}

            def is_pid_alive(self, pid: int) -> bool:
                return pid in self.alive_pids

            def get_process_metrics(self, pid: int):
                if pid in self.alive_pids:
                    return {
                        "pid": pid,
                        "name": f"worker_{pid}",
                        "cmdline": f"worker_{pid}",
                        "cpu_percent": 10.0,
                        "memory_bytes": 50 * 1024 * 1024,
                        "memory_mb": 50.0,
                        "status": "running",
                        "is_alive": True,
                    }
                return None

        mock_adapter = EdgeCaseAdapter()
        manager.os_adapter = mock_adapter
        manager.grouper.os_adapter = mock_adapter
        manager.monitor.os_adapter = mock_adapter
        manager.control_engine.os_adapter = mock_adapter

        # Create activity with PIDs 2001 and 2002 while both are alive
        act = manager.create_activity("Research", member_pids=[2001, 2002])
        self.assertEqual(act.state, ActivityState.STOPPED)
        self.assertEqual(act.member_processes, [2001, 2002])

        # Simulate PID 2002 dying BEFORE start_activity is called
        mock_adapter.alive_pids.remove(2002)

        # Call start_activity()
        ok, msg = manager.start_activity(act.activity_id)
        self.assertTrue(ok)
        self.assertEqual(act.state, ActivityState.ACTIVE)
        # PID 2002 is omitted from active membership
        self.assertEqual(act.member_processes, [2001])
        # A process_unavailable event must be logged
        self.assertTrue(any(e.action == "process_unavailable" for e in act.event_log))
        # Resource snapshot should only count alive PID 2001
        self.assertEqual(act.resource_snapshot.cpu_percent, 10.0)

    def test_process_exits_during_runtime(self):
        """Edge Case: A process exits while the Activity is running."""
        manager = ActivityManager(storage_path=self.storage_file)

        class RuntimeExitAdapter(OSAdapter):
            def __init__(self):
                super().__init__()
                self.alive_pids = {3001, 3002}

            def is_pid_alive(self, pid: int) -> bool:
                return pid in self.alive_pids

            def get_process_metrics(self, pid: int):
                if pid in self.alive_pids:
                    return {
                        "pid": pid,
                        "name": f"worker_{pid}",
                        "cmdline": f"worker_{pid}",
                        "cpu_percent": 15.0,
                        "memory_bytes": 50 * 1024 * 1024,
                        "memory_mb": 50.0,
                        "status": "running",
                        "is_alive": True,
                    }
                return None

        mock_adapter = RuntimeExitAdapter()
        manager.os_adapter = mock_adapter
        manager.grouper.os_adapter = mock_adapter
        manager.monitor.os_adapter = mock_adapter
        manager.control_engine.os_adapter = mock_adapter

        act = manager.create_activity("Coding", member_pids=[3001, 3002])
        manager.start_activity(act.activity_id)

        # First poll: both alive
        manager.poll_all_resources()
        self.assertAlmostEqual(act.resource_snapshot.cpu_percent, 30.0, places=1)

        # Simulate PID 3002 crashing / disappearing
        mock_adapter.alive_pids.remove(3002)

        # Second poll: handles without crashing, logs process_unavailable
        manager.poll_all_resources()
        self.assertAlmostEqual(act.resource_snapshot.cpu_percent, 15.0, places=1)
        self.assertTrue(any(e.action == "process_unavailable" for e in act.event_log))


def run_all_tests():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
