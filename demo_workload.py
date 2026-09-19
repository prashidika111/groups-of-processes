#!/usr/bin/env python3
"""
ActivityOS Demonstration Workload
Simulates a realistic multi-process Activity workload (e.g. Study Session:
a compiler worker, a documentation reader, and an interactive terminal worker).

Outputs real PIDs, consumes measurable CPU and Memory, and demonstrates immediate
freezing upon SIGSTOP (Pause) and resumption upon SIGCONT (Resume).
"""

import os
import sys
import time
import math
import argparse
import multiprocessing


def memory_worker(name: str, target_mb: int = 80):
    """Worker that allocates memory and does periodic light work."""
    pid = os.getpid()
    print(f"[{name}] Started (PID {pid}). Allocating ~{target_mb} MB RAM...")
    # Allocate byte array
    data = bytearray(target_mb * 1024 * 1024)
    # Dirty memory so Linux pages it into RSS
    for i in range(0, len(data), 4096):
        data[i] = 1

    print(f"[{name}] (PID {pid}) Ready and running.")
    counter = 0
    try:
        while True:
            counter += 1
            # Periodically access memory
            data[(counter * 4096) % len(data)] = (counter % 255)
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass


def compute_worker(name: str):
    """Worker that generates active CPU load (simulating code compilation or rendering)."""
    pid = os.getpid()
    print(f"[{name}] Started (PID {pid}). Generating active CPU load...")
    try:
        while True:
            # Active computation loop
            for _ in range(250000):
                _ = math.sqrt(12345.6789)
            time.sleep(0.05)  # Yield CPU to regulate usage around 20-30%
    except KeyboardInterrupt:
        pass


def io_worker(name: str):
    """Worker that simulates interactive background terminal / editor."""
    pid = os.getpid()
    print(f"[{name}] Started (PID {pid}). Running interactive background loop...")
    counter = 0
    try:
        while True:
            counter += 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass


def run_single_worker(mode: str):
    if mode == "compute":
        compute_worker("Study-Compiler")
    elif mode == "memory":
        memory_worker("Study-DocReader", 60)
    else:
        io_worker("Study-Terminal")


def run_all_workers():
    print("=" * 60)
    print("ActivityOS — Multi-Process Workload Simulator")
    print("Spawning 3 real Linux processes to simulate 'Study' activity:")
    print("  1. Study-Compiler   (active CPU load)")
    print("  2. Study-DocReader  (active RAM allocation ~60MB)")
    print("  3. Study-Terminal   (interactive worker)")
    print("=" * 60)

    p1 = multiprocessing.Process(target=compute_worker, args=("Study-Compiler",), name="Study-Compiler")
    p2 = multiprocessing.Process(target=memory_worker, args=("Study-DocReader", 60), name="Study-DocReader")
    p3 = multiprocessing.Process(target=io_worker, args=("Study-Terminal",), name="Study-Terminal")

    p1.start()
    p2.start()
    p3.start()

    print(f"\nSpawned PIDs: {p1.pid}, {p2.pid}, {p3.pid}")
    print("\nIn ActivityOS:")
    print(f"  1. Click '+ Create Activity'")
    print(f"  2. Name it 'Study'")
    print(f"  3. Check PIDs: {p1.pid}, {p2.pid}, {p3.pid}")
    print(f"  4. Click 'Create Activity'")
    print(f"  5. Observe real CPU & Memory aggregated at Activity level!")
    print(f"  6. Click 'Pause' -> Watch OS suspend processes (CPU drops to 0%)")
    print(f"  7. Click 'Resume' -> Watch processes resume\n")
    print("Press Ctrl+C to terminate all demo worker processes.\n")

    try:
        p1.join()
        p2.join()
        p3.join()
    except KeyboardInterrupt:
        print("\nStopping demo worker processes...")
        p1.terminate()
        p2.terminate()
        p3.terminate()
        p1.join()
        p2.join()
        p3.join()
        print("Demo workers stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ActivityOS Demonstration Workload")
    parser.add_argument("--mode", choices=["compute", "memory", "io"], help="Run a single specific worker")
    args = parser.parse_args()

    if args.mode:
        run_single_worker(args.mode)
    else:
        run_all_workers()
