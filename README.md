# ActivityOS — Review 2 Prototype (60% Core MVP)

> **Assessment 6 — Proposed Methodology and 60% of Code Implementation**  
> University Operating Systems Project

---

## 1. Project Overview & Philosophy

Modern desktop operating systems present running software to the user as flat, fragmented, and disconnected processes. When a laptop experiences lag or high resource pressure, opening a conventional Task Manager confronts the user with hundreds of isolated PIDs (`chrome`, `code`, `node`, `docker`, `python`) rather than what the user is actually doing: **Studying**, **Coding**, **Researching**, or **Gaming**.

**ActivityOS** introduces an experimental, higher-level **Activity-centric abstraction layer** above an unmodified Linux operating system:

```
                            HUMAN
                              ↓
                          ACTIVITY
                              ↓
                          PROCESSES
                              ↓
                            LINUX
```

Target OS: **Linux** (Kernel 3.x / 4.x / 5.x / 6.x, unmodified).  
ActivityOS interacts with the system strictly through standard Linux primitives:
- Reading process accounting via the Linux `/proc` pseudo-filesystem (`/proc/<pid>/stat`, `/proc/<pid>/status`, `/proc/stat`, `/proc/meminfo`).
- Controlling process execution via standard POSIX signals (`kill(pid, SIGSTOP)`, `kill(pid, SIGCONT)`, `kill(pid, SIGTERM)`).
- Adjusting priority via `setpriority(PRIO_PROCESS, pid, nice)`.
- No kernel patches, no custom scheduler, no cgroups, and no non-Linux fallbacks for this prototype. Instead, it maintains an application-level Activity representation and translates Activity-level operations down into standard, unmodified Linux process mechanisms (`/proc`, `SIGSTOP`, `SIGCONT`, `SIGTERM`, `setpriority()`).

---

## 2. 100% Planned Architecture vs. 60% Core MVP Implementation

As required by Assessment 6, this prototype delivers approximately **60% of the functional code implementation** of the complete planned 100% ActivityOS system. The core functional path is implemented with real Linux mechanisms; the remaining ~40% is clearly scoped for future milestones.

### Functional Scope Matrix

| System Capability | Complete 100% Vision | Review 2 Core MVP (60%) | Milestone Status |
|---|---|---|---|
| **Activity Data Model** | Full persistent schema + session history + priority rules | Complete schema: `activity_id`, `name`, `member_processes[]`, `state`, `priority_level`, `resource_snapshot`, `event_log[]` | **Implemented (60% Core)** |
| **Process Grouper** | Manual selection + heuristic rule matching | Real Linux process discovery via `/proc` + PID validation + multi-select grouping | **Implemented (60% Core)** |
| **Activity Manager** | Multi-session lifecycle + persistent registry | Owns Activity records, authoritative PID mappings, and state transitions (`ACTIVE`, `PAUSED`, `STOPPED`) | **Implemented (60% Core)** |
| **Application Launcher** | Desktop shortcut integration & sandboxing | Spawns configured application commands, resolves launched parent PIDs and descendant child process trees | **Implemented (60% Core)** |
| **Resource Monitor** | Per-process accounting + system attribution | Real Linux `/proc/<pid>/stat` CPU jiffies & `/proc/<pid>/status` RSS memory reader | **Implemented (60% Core)** |
| **Resource Aggregation** | Activity-level totals & system percentages | Computes aggregate CPU % and Memory (MB/GB) across all member processes | **Implemented (60% Core)** |
| **Process Drill-Down** | Interactive hierarchy with thread breakdown | Drill-down view displaying each member process's PID, command, CPU %, Memory, and status | **Implemented (60% Core)** |
| **Activity Pause** | State freeze with dependency ordering | Translates 1 Activity command into `kill(pid, SIGSTOP)` for each member PID | **Implemented (60% Core)** |
| **Activity Resume** | Wake scheduling and priority restoration | Translates 1 Activity command into `kill(pid, SIGCONT)` for each member PID | **Implemented (60% Core)** |
| **Activity Stop** | Graceful termination + session archival | Translates 1 Activity command into `kill(pid, SIGTERM)` for member processes; finalizes session | **Implemented (60% Core)** |
| **Process Failure Handling** | Automatic re-attachment & fault recovery | Catches dead/unavailable PIDs and permission errors individually without crashing | **Implemented (60% Core)** |
| **Timeline Logger** | Searchable audit trail + event analytics | Records timestamped ActivityOS actions (`create`, `start`, `pause`, `resume`, `stop`, `unavailable`) | **Implemented (60% Core)** |
| **Local Persistence** | SQLite query engine + data migrations | Atomic JSON storage (`~/.activityos/activities.json`), handles ephemeral PID safety on reload | **Implemented (60% Core)** |
| **Desktop Application** | Multi-window desktop GUI + custom widgets | Standalone desktop application window with Overview, Activities, Drill-down, and Creator | **Implemented (60% Core)** |
| *System Resource Attribution* | System pie attribution (Activities vs Background) | Overview shows System CPU/RAM; full attribution breakdown scoped for final review | *Remaining 40% (Future)* |
| *Session History & Analytics* | Post-session duration, peak/avg curves, export | Basic timeline log included; historical analytical reports scoped for final review | *Remaining 40% (Future)* |
| *Dynamic Priority Tuning* | Dynamic renicing policies based on focus | Field exists in model and control engine; automated priority adjustment scoped for later | *Remaining 40% (Future)* |
| *In-Flight Activity Editing* | Add/remove processes dynamically to running activity | Activity re-creation supported; dynamic in-flight PID mutation scoped for final review | *Remaining 40% (Future)* |
| *Automatic Activity Detection* | Machine-learning/window heuristic inference | Explicitly out of scope per methodology (Review 1 & 2) | *Future Research* |

---

## 3. Modular Architecture

The codebase strictly follows the component chain established in the Proposed Methodology:

```
                            USER
                              ↓
                       PROCESS GROUPER
                              ↓
                      ACTIVITY MANAGER
                       ├──────────────→ RESOURCE MONITOR
                       │
                       ├──────────────→ ACTIVITY CONTROL ENGINE
                       │                         ↓
                       │                  OS SYSTEM CALLS (kill, /proc)
                       │                         ↓
                       │                  OPERATING SYSTEM (unmodified Linux)
                       │
                       └──────────────→ TIMELINE LOGGER

                     RESOURCE MONITOR ─────→ DASHBOARD
                     TIMELINE LOGGER ───────→ DASHBOARD
```

- **`activityos/grouper.py` (`ProcessGrouper`)**: Discovers running system processes, filters candidate PIDs, and validates process existence before association.
- **`activityos/manager.py` (`ActivityManager`)**: Single authoritative owner of Activity records and the `Activity ↔ PID` membership mapping.
- **`activityos/monitor.py` (`ResourceMonitor`)**: Reads `/proc/<pid>/stat` (utime + stime) and `/proc/<pid>/status` (`VmRSS`), computing per-process CPU % and aggregating totals.
- **`activityos/control.py` (`ActivityControlEngine`)**: Translates Activity commands into POSIX signals (`SIGSTOP`, `SIGCONT`, `SIGTERM`) per PID with granular outcome tracking.
- **`activityos/launcher.py` (`ApplicationLauncher`)**: Spawns configured applications and discovers spawned child process trees.
- **`activityos/logger.py` (`TimelineLogger`)**: Records ActivityOS actions into each Activity's `event_log[]`.
- **`activityos/storage.py` (`ActivityStorage`)**: Manages atomic local persistence in `~/.activityos/activities.json`.
- **`activityos/ui/` (`Desktop UI`)**: Standalone desktop window (via `pywebview` or zero-dependency native `tkinter/ttk` fallback).

---

## 4. Real Linux Mechanisms Used

| Capability | Linux Kernel / OS Mechanism | How ActivityOS Implements It |
|---|---|---|
| **Process Discovery** | Linux `/proc` pseudo-filesystem | Enumerates integer directories in `/proc`, parses `comm` and `cmdline`. |
| **CPU Monitoring** | `/proc/<pid>/stat` & `/proc/stat` | Samples `utime` + `stime` across $\Delta t$, derives: $\frac{\Delta (\text{utime}+\text{stime})}{\Delta \text{sys\_jiffies}} \times 100 \times N_{\text{cpus}}$. |
| **Memory Monitoring**| `/proc/<pid>/status` | Parses `VmRSS` (Resident Set Size in physical RAM) in kB. |
| **System Overview** | `/proc/meminfo` & `/proc/stat` | Reads `MemTotal`, `MemAvailable` and total CPU jiffies. |
| **Pause Activity** | `kill(pid, SIGSTOP)` (Signal 19) | OS kernel stops scheduling member processes immediately; CPU drops to 0%. |
| **Resume Activity**| `kill(pid, SIGCONT)` (Signal 18) | OS kernel resumes scheduling member processes. |
| **Stop Activity**  | `kill(pid, SIGTERM)` (Signal 15) | OS delivers graceful termination signal to member processes. |
| **Priority Control**| `setpriority(PRIO_PROCESS, pid, nice)` | Translates activity-level priority to per-process nice value (-20 to 19). |

---

## 5. Live Demonstration Guide (Review 2 Flow)

Follow these steps to conduct a live evaluation demonstration:

### Step 1: Launch the Demo Workload (or Real Applications)
Open a terminal and run the provided realistic multi-process workload:
```bash
python3 demo_workload.py
```
This spawns 3 real Linux worker processes simulating a **Study** session:
- `Study-Compiler`: Computes active CPU tasks (~20-30% CPU load).
- `Study-DocReader`: Allocates ~60 MB physical RSS RAM.
- `Study-Terminal`: Interactive worker process.

*(Alternatively, you can use any real Linux applications such as Chrome, VS Code, or bash terminals).*

### Step 2: Launch ActivityOS
In another terminal, run:
```bash
python3 main.py
```
*(Or execute `./run.sh` on Linux).*

### Step 3: Create Activity "Study"
1. Click the **+ Create Activity** button.
2. Enter the name: `Study`.
3. Locate the worker processes (or type `Study` in the filter box).
4. Select the checkboxes for the 3 worker PIDs.
5. Click **Create Activity**.

### Step 4: Observe Real-Time Activity Monitoring
- On the dashboard, observe the **Study** activity card:
  - **State**: `ACTIVE` (green badge).
  - **CPU Total**: Displays aggregate CPU (e.g. `24.8%`).
  - **Memory Total**: Displays aggregate RAM (e.g. `82.4 MB`).
  - **Processes**: `3 PIDs`.

### Step 5: Drill Down Into Contributing Processes
- Click **Inspect** on the Study activity card.
- The right panel shows the conceptual contrast:
  - **Activity Context**: Shows the unified Study activity.
  - **Contributing Processes Table**: Lists each real PID, process name, individual CPU %, and individual RSS memory.

### Step 6: Pause Activity (SIGSTOP)
- Click the **Pause** button on Study.
- Observe:
  1. The activity state changes to `PAUSED` (orange badge).
  2. ActivityOS translates this single command into `kill(pid, SIGSTOP)` for each member PID.
  3. The Linux kernel immediately suspends scheduling of those processes.
  4. Aggregate CPU usage on the dashboard drops to **0.0%**.
  5. The Timeline Log records: `[PAUSE] All 3 member processes paused successfully (SIGSTOP)`.

### Step 7: Resume Activity (SIGCONT)
- Click the **Resume** button on Study.
- Observe:
  1. The activity state changes to `ACTIVE` (green badge).
  2. ActivityOS translates this to `kill(pid, SIGCONT)` for each PID.
  3. The processes resume execution and their active CPU utilization immediately returns.
  4. The Timeline Log records: `[RESUME] All 3 member processes resumed successfully (SIGCONT)`.

### Step 8: Stop Activity (SIGTERM)
- Click **Stop**.
- Member processes are signaled with `SIGTERM` and terminated.
- The session concludes and the state updates to `STOPPED`.

---

## 6. Running Automated Tests

A comprehensive test suite verifies the models, Linux `/proc` parsing, signal translation, and lifecycle:

```bash
python3 run_tests.py
```

All unit tests run in < 0.1 seconds and validate:
- Serialization of Activity, Session, ProcessDetail, and ResourceSnapshot.
- Correct parsing of `/proc/<pid>/stat` and `/proc/<pid>/status` with mock fixtures.
- Aggregation mathematics across member processes.
- Fault tolerance when a process dies between grouping and control.
- Atomic persistence and reload from disk.

---

## 7. Known Limitations & Future Scope (~40%)

The following features are deliberately reserved for the final implementation phase:
1. **Dynamic In-Flight Membership Editing**: Adding or removing PIDs to an activity while it is actively running without recreation.
2. **System-Wide Activity Attribution**: Pie charts and total system percentage breakdown (Activities vs. Background Unassigned processes).
3. **Session Analytics & Export**: Historical peak/average charts, session duration reports, and JSON/CSV export.
4. **Automated Priority Policies**: Dynamically altering nice values based on active window focus.
5. **Cgroups Resource Guarantees**: Hard CPU/Memory limits using Linux cgroups (explicitly out of scope for Review 2 per methodology).
