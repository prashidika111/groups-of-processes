#!/usr/bin/env python3
"""
ActivityOS — Main Application Entry Point
Assessment 6 — Review 2 Core MVP (60% Functional Implementation)

Launches the ActivityOS desktop application window.
"""

from __future__ import annotations
import argparse
import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from activityos.manager import ActivityManager
from activityos.ui import launch_desktop_gui, launch_tk_gui


def main():
    parser = argparse.ArgumentParser(
        description="ActivityOS — Activity-Centric Operating System Layer (Review 2 Core MVP)"
    )
    parser.add_argument(
        "--gui",
        choices=["auto", "webview", "tk", "cli"],
        default="auto",
        help="Desktop GUI engine: 'auto' (prefer native pywebview, fallback to tk), 'webview', 'tk', or 'cli' text dashboard."
    )
    parser.add_argument(
        "--storage",
        type=str,
        default=None,
        help="Custom path to activities.json persistence file."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Launch background demo workload workers and pre-configure 'Study' activity for immediate demonstration."
    )

    args = parser.parse_args()

    print("=" * 65)
    print("  ACTIVITYOS — Review 2 Core MVP (60% Functional Implementation)")
    print("  Manage your work as activities, not isolated processes.")
    print("=" * 65)

    manager = ActivityManager(storage_path=args.storage)

    # If --demo flag was passed, launch demo_workload workers and pre-create 'Study'
    if args.demo:
        print("[Demo Mode] Launching background demo processes...")
        workload_script = PROJECT_ROOT / "demo_workload.py"
        try:
            # Spawn worker processes
            p1 = subprocess.Popen([sys.executable, str(workload_script), "--mode", "compute"])
            p2 = subprocess.Popen([sys.executable, str(workload_script), "--mode", "memory"])
            p3 = subprocess.Popen([sys.executable, str(workload_script), "--mode", "io"])
            time.sleep(0.5)

            demo_pids = [p1.pid, p2.pid, p3.pid]
            print(f"[Demo Mode] Spawned demo worker PIDs: {demo_pids}")

            # Check if 'Study' already exists
            existing = [a for a in manager.get_all_activities() if a.name == "Study"]
            if not existing:
                manager.create_activity("Study", member_pids=demo_pids)
                print("[Demo Mode] Pre-configured activity 'Study' with demo PIDs.")
            else:
                existing[0].member_processes = demo_pids
                manager.storage.save_activities(manager._activities)
                print("[Demo Mode] Updated existing 'Study' activity with new demo PIDs.")
        except Exception as e:
            print(f"[Demo Mode] Warning: Could not launch demo workers: {e}")

    # Launch GUI according to preference
    if args.gui == "tk":
        print("[ActivityOS] Launching Tkinter native desktop GUI...")
        launch_tk_gui(manager)
    elif args.gui == "webview":
        print("[ActivityOS] Launching PyWebView desktop GUI...")
        launch_desktop_gui(manager, force_tk=False)
    elif args.gui == "cli":
        print("[ActivityOS] Launching CLI monitor mode...")
        run_cli_monitor(manager)
    else:
        # Auto mode: try pywebview, fallback to tk
        print("[ActivityOS] Launching desktop application window...")
        launch_desktop_gui(manager, force_tk=False)


def run_cli_monitor(manager: ActivityManager):
    """Simple terminal dashboard loop for headless / SSH environments."""
    try:
        while True:
            data = manager.poll_all_resources()
            sys_info = data.get("system", {})
            activities = manager.get_all_activities()

            # Clear screen
            print("\033[H\033[J", end="")
            print("=" * 65)
            print("ACTIVITYOS — TERMINAL DASHBOARD")
            print(f"System CPU: {sys_info.get('cpu_percent', 0):.1f}% | Memory: {sys_info.get('memory_percent', 0):.1f}% ({sys_info.get('memory_used_mb', 0):.0f}/{sys_info.get('memory_total_mb', 0):.0f} MB)")
            print("=" * 65)

            if not activities:
                print("No activities tracked. Use GUI to create activities.")
            else:
                for act in activities:
                    snap = act.resource_snapshot
                    print(f"\n[ACTIVITY] {act.name.upper()}  [{act.state.value}]")
                    print(f"  CPU Total: {snap.cpu_percent:.1f}% | Memory: {snap.memory_mb:.1f} MB | Processes: {len(act.member_processes)}")
                    print("  Contributing processes:")
                    for p in snap.contributing_processes:
                        print(f"    • PID {p.pid:<6} | {p.name:<18} | {p.cpu_percent:>5.1f}% CPU | {p.memory_mb:>6.1f} MB | {p.status}")

            print("\nPress Ctrl+C to exit monitor.")
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\nExiting ActivityOS.")


if __name__ == "__main__":
    main()
