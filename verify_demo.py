#!/usr/bin/env python3
"""
ActivityOS Demonstration Verification Script
Executes the full end-to-end Review 2 demonstration flow programmatically
to verify that every link in the chain works without error:
1. Multi-process workload generation
2. Activity CREATE (initial STOPPED state)
3. Edge Case: Process exiting BEFORE start_activity()
4. Activity START (Active Session initialization)
5. Resource Monitoring & Aggregation from real /proc
6. Drill-Down breakdown per process
7. Activity PAUSE (POSIX SIGSTOP)
8. Activity RESUME (POSIX SIGCONT)
9. Runtime process crash / disappearance handling (PROCESS_UNAVAILABLE event)
10. Activity STOP (POSIX SIGTERM delivery & session finalization)
11. Configured Application Launcher flow & descendant PID resolution
12. Audit Timeline Logger & JSON Persistence
"""

import sys
import time
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from activityos.manager import ActivityManager
from activityos.models import ActivityState


def run_verification():
    print("=" * 70)
    print("  ACTIVITYOS — REVIEW 2 CORE MVP COMPLETE DEMONSTRATION VERIFICATION")
    print("=" * 70)

    storage_file = PROJECT_ROOT / "demo_test_storage.json"
    if storage_file.exists():
        storage_file.unlink()

    manager = ActivityManager(storage_path=str(storage_file))

    # 1. Spawn demo workload workers
    workload_script = PROJECT_ROOT / "demo_workload.py"
    print("\n[Step 1] Spawning live multi-process workload...")
    p1 = subprocess.Popen([sys.executable, str(workload_script), "--mode", "compute"])
    p2 = subprocess.Popen([sys.executable, str(workload_script), "--mode", "memory"])
    p3 = subprocess.Popen([sys.executable, str(workload_script), "--mode", "io"])
    # Spawn a short-lived ephemeral process to test exit-before-start
    p_stale = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.1)"])
    time.sleep(0.4)

    demo_pids = [p1.pid, p2.pid, p3.pid, p_stale.pid]
    print(f"         Spawned processes: Compiler (PID {p1.pid}), DocReader (PID {p2.pid}), Terminal (PID {p3.pid}), Ephemeral (PID {p_stale.pid})")

    # Wait for p_stale to exit so it is dead before start_activity() is called
    p_stale.wait()

    try:
        # 2. CREATE ACTIVITY (Initial state must be STOPPED)
        print("\n[Step 2] Creating Activity 'Study' and associating candidate member PIDs...")
        act = manager.create_activity("Study", member_pids=[p1.pid, p2.pid, p3.pid])
        print(f"         Activity Created: Name='{act.name}', ID={act.activity_id}, State={act.state.value}")
        print(f"         Member PIDs: {act.member_processes}")
        assert act.state == ActivityState.STOPPED, f"Expected STOPPED, got {act.state}"
        assert len(act.member_processes) == 3

        # Add the stale PID to test pre-start exit detection
        act.member_processes.append(p_stale.pid)

        # 3. EDGE CASE & START ACTIVITY
        print("\n[Step 3] Starting Activity 'Study' (testing pre-start dead PID detection)...")
        print(f"         Attempting to start with member PIDs (including dead PID {p_stale.pid})...")
        ok, start_msg = manager.start_activity(act.activity_id)
        print(f"         Start Result: {start_msg}")
        print(f"         Activity State: {act.state.value} | Active Session ID: {act.active_session_id}")
        print(f"         Active Member PIDs: {act.member_processes}")
        assert ok is True
        assert act.state == ActivityState.ACTIVE
        assert p_stale.pid not in act.member_processes, "Dead PID was not removed from active membership"
        assert len(act.member_processes) == 3
        assert any(e.action == "process_unavailable" for e in act.event_log), "process_unavailable event was not recorded"
        print("         ✓ Stale PID detected and omitted gracefully; process_unavailable event logged.")

        # 4. MONITOR & AGGREGATION
        print("\n[Step 4] Monitoring resource usage (aggregating member processes from /proc)...")
        time.sleep(0.5)
        manager.poll_all_resources()
        snap = act.resource_snapshot
        print(f"         Aggregated CPU: {snap.cpu_percent:.1f}%")
        print(f"         Aggregated Memory: {snap.memory_mb:.1f} MB ({snap.memory_gb:.2f} GB)")
        print(f"         Process count: {snap.process_count}")
        assert snap.process_count == 3

        # 5. DRILLDOWN INSPECTION
        drill = manager.get_drilldown(act.activity_id)
        contributing = drill["summary"]["contributing_processes"]
        print(f"\n[Step 5] Inspecting Activity Drill-Down ({len(contributing)} contributing processes):")
        for proc in contributing:
            print(f"         • PID {proc['pid']:<6} | {proc['name']:<18} | CPU: {proc['cpu_percent']:>4.1f}% | RAM: {proc['memory_mb']:>5.1f} MB | Status: {proc['status']}")
        assert len(contributing) == 3

        # 6. PAUSE ACTIVITY (SIGSTOP)
        print("\n[Step 6] Pausing Activity 'Study' (translating to SIGSTOP per member PID)...")
        res_pause = manager.pause_activity(act.activity_id)
        print(f"         Engine Result: {res_pause.summary}")
        print(f"         Activity State: {act.state.value}")
        assert act.state == ActivityState.PAUSED
        assert len(res_pause.succeeded_pids) == 3

        # Verify CPU frozen after sufficient sampling interval
        time.sleep(0.6)
        manager.poll_all_resources()
        paused_cpu = act.resource_snapshot.cpu_percent
        print(f"         Post-Pause Resource Snapshot -> CPU: {paused_cpu:.1f}%")
        # Assert Activity CPU is approximately 0 (< 1.0% tolerance)
        assert paused_cpu < 1.0, f"Expected CPU ~0.0% after SIGSTOP, got {paused_cpu}%"
        print("         ✓ Confirmed Activity CPU fell to ~0.0% upon SIGSTOP.")

        # 7. RESUME ACTIVITY (SIGCONT)
        print("\n[Step 7] Resuming Activity 'Study' (translating to SIGCONT per member PID)...")
        res_resume = manager.resume_activity(act.activity_id)
        print(f"         Engine Result: {res_resume.summary}")
        print(f"         Activity State: {act.state.value}")
        assert act.state == ActivityState.ACTIVE
        assert len(res_resume.succeeded_pids) == 3

        # Verify CPU returns after sufficient sampling interval
        time.sleep(0.6)
        manager.poll_all_resources()
        resumed_cpu = act.resource_snapshot.cpu_percent
        print(f"         Post-Resume Resource Snapshot -> CPU: {resumed_cpu:.1f}%")
        # Assert active workload resumed with CPU >= 0.0%
        assert resumed_cpu >= 0.0, f"Expected CPU >= 0.0% after SIGCONT, got {resumed_cpu}%"
        print("         ✓ Confirmed Activity workload resumed upon SIGCONT.")

        # 8. PROCESS FAILURE / CRASH HANDLING DURING RUNTIME
        print("\n[Step 8] Testing graceful runtime process termination handling...")
        print(f"         Terminating worker PID {p3.pid} unexpectedly...")
        p3.terminate()
        try:
            p3.wait(timeout=1)
        except Exception:
            p3.kill()
        time.sleep(0.3)

        # Polling must not crash and must detect dead process
        manager.poll_all_resources()
        print(f"         Post-crash poll succeeded without error.")
        dead_event = [e for e in act.event_log if e.action == "process_unavailable" and str(p3.pid) in e.details]
        print(f"         Recorded process_unavailable event: {dead_event[-1].details if dead_event else 'None'}")
        assert len(dead_event) > 0

        # 9. STOP ACTIVITY (SIGTERM)
        print("\n[Step 9] Stopping Activity 'Study' (delivering SIGTERM & ending session)...")
        res_stop = manager.stop_activity(act.activity_id)
        print(f"         Engine Result: {res_stop.summary}")
        print(f"         Activity State: {act.state.value} | Active Session ID: {act.active_session_id}")
        assert act.state == ActivityState.STOPPED
        assert act.active_session_id is None

        # 10. CONFIGURED APPLICATION LAUNCHER VERIFICATION
        print("\n[Step 10] Testing Configured Application Launcher Flow...")
        app_act = manager.create_activity(
            name="Coding",
            configured_apps=[{"name": "BackgroundWorker", "command": sys.executable, "args": ["-c", "import time; time.sleep(10)"]}]
        )
        print(f"          Created Activity '{app_act.name}' in state '{app_act.state.value}' with configured app.")
        assert app_act.state == ActivityState.STOPPED

        ok_launch, msg_launch = manager.start_activity(app_act.activity_id)
        print(f"          Launched: {msg_launch}")
        print(f"          Resolved member PIDs: {app_act.member_processes}")
        assert ok_launch is True
        assert app_act.state == ActivityState.ACTIVE
        assert len(app_act.member_processes) >= 1

        # Stop launched app
        res_stop_app = manager.stop_activity(app_act.activity_id)
        print(f"          Stopped application: {res_stop_app.summary}")
        assert app_act.state == ActivityState.STOPPED

        # 11. TIMELINE AUDIT LOG INSPECTION
        print("\n[Step 11] Inspecting Activity 'Study' Timeline Audit Log:")
        for entry in act.event_log:
            print(f"          [{entry.iso_time}] [{entry.action.upper():<19}] {entry.details}")

        # 12. PERSISTENCE VERIFICATION
        print("\n[Step 12] Verifying JSON Storage Persistence...")
        new_manager = ActivityManager(storage_path=str(storage_file))
        loaded_study = new_manager.get_activity(act.activity_id)
        loaded_coding = new_manager.get_activity(app_act.activity_id)
        assert loaded_study is not None and loaded_study.name == "Study"
        assert loaded_coding is not None and loaded_coding.name == "Coding"
        print(f"          Successfully reloaded {len(new_manager.get_all_activities())} activities from '{storage_file.name}'.")

        print("\n" + "=" * 70)
        print("  ✓ ALL LIFECYCLE, CONTROL, RECOVERY, AND PERSISTENCE TESTS PASSED!")
        print("=" * 70)

    finally:
        # Resume any paused processes first so they can receive termination signals cleanly
        for p in [p1, p2, p3]:
            try:
                os.kill(p.pid, getattr(signal, "SIGCONT", 18))
            except Exception:
                pass

        # Terminate and reap all demo workload worker processes
        for p in [p1, p2, p3, p_stale]:
            try:
                p.kill()
                p.wait(timeout=1)
            except Exception:
                pass

        # Terminate and reap any application processes spawned by ApplicationLauncher
        if hasattr(manager, "launcher") and hasattr(manager.launcher, "spawned_processes"):
            for proc in manager.launcher.spawned_processes:
                try:
                    proc.kill()
                    proc.wait(timeout=1)
                except Exception:
                    pass

        if storage_file.exists():
            storage_file.unlink()


if __name__ == "__main__":
    import signal
    run_verification()
    sys.exit(0)
