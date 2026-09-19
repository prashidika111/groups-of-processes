"""
ActivityOS Tkinter Native Desktop GUI
Zero-dependency desktop GUI fallback built using standard Python tkinter/ttk.
Ensures ActivityOS can be launched and demonstrated on ANY Linux installation
without requiring WebKitGTK or third-party web engines.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import time
from typing import Dict, List, Optional, Any
from ..manager import ActivityManager
from ..models import ActivityState


class ActivityOSTkApp:
    """
    Tkinter desktop application window for ActivityOS.
    """

    def __init__(self, root: tk.Tk, manager: ActivityManager):
        self.root = root
        self.manager = manager
        self.selected_act_id: Optional[str] = None

        self.root.title("ActivityOS — Activity-Centric Resource Manager")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        # Style configuration
        self._configure_styles()

        # Build UI layout
        self._build_header()
        self._build_system_ribbon()
        self._build_main_layout()

        # Start periodic polling (every 1.5 seconds)
        self._poll_heartbeat()

    def _configure_styles(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Dark technical color palette
        self.bg_dark = "#121315"
        self.bg_panel = "#1a1c1f"
        self.bg_card = "#23262b"
        self.fg_main = "#e8e6e3"
        self.accent = "#4e7865"

        self.root.configure(bg=self.bg_dark)
        self.style.configure(".", background=self.bg_dark, foreground=self.fg_main)
        self.style.configure("Treeview", background=self.bg_card, foreground=self.fg_main, fieldbackground=self.bg_card, rowheight=24)
        self.style.configure("Treeview.Heading", background=self.bg_panel, foreground=self.fg_main, font=("Helvetica", 9, "bold"))
        self.style.map("Treeview", background=[("selected", self.accent)])

    def _build_header(self):
        header_frame = tk.Frame(self.root, bg=self.bg_panel, padx=16, pady=10, relief="groove", bd=1)
        header_frame.pack(fill="x")

        title_lbl = tk.Label(
            header_frame,
            text="ACTIVITYOS  [Review 2 Core MVP]",
            font=("Courier", 14, "bold"),
            bg=self.bg_panel,
            fg="#ffffff"
        )
        title_lbl.pack(side="left")

        sub_lbl = tk.Label(
            header_frame,
            text="— Manage your work as activities, not isolated processes.",
            font=("Helvetica", 10),
            bg=self.bg_panel,
            fg="#8c887b"
        )
        sub_lbl.pack(side="left", padx=10)

        create_btn = tk.Button(
            header_frame,
            text="+ Create Activity",
            bg=self.accent,
            fg="#ffffff",
            font=("Helvetica", 9, "bold"),
            padx=12,
            pady=4,
            relief="flat",
            cursor="hand2",
            command=self._open_create_dialog
        )
        create_btn.pack(side="right")

    def _build_system_ribbon(self):
        ribbon = tk.Frame(self.root, bg=self.bg_panel, padx=16, pady=8, bd=1, relief="ridge")
        ribbon.pack(fill="x", padx=14, pady=8)

        self.sys_cpu_var = tk.StringVar(value="CPU: 0.0%")
        self.sys_mem_var = tk.StringVar(value="Memory: 0.0% (0 / 0 MB)")
        self.act_count_var = tk.StringVar(value="Activities: 0")
        self.proc_count_var = tk.StringVar(value="Managed PIDs: 0")

        tk.Label(ribbon, textvariable=self.sys_cpu_var, font=("Courier", 11, "bold"), bg=self.bg_panel, fg="#ffffff").pack(side="left", padx=14)
        tk.Label(ribbon, textvariable=self.sys_mem_var, font=("Courier", 11, "bold"), bg=self.bg_panel, fg="#ffffff").pack(side="left", padx=14)
        tk.Label(ribbon, textvariable=self.act_count_var, font=("Courier", 11), bg=self.bg_panel, fg="#b0bec5").pack(side="left", padx=14)
        tk.Label(ribbon, textvariable=self.proc_count_var, font=("Courier", 11), bg=self.bg_panel, fg="#b0bec5").pack(side="left", padx=14)

    def _build_main_layout(self):
        paned = tk.PanedWindow(self.root, orient="horizontal", bg=self.bg_dark, bd=0, sashwidth=4)
        paned.pack(fill="both", expand=True, padx=14, pady=4)

        # Left panel: Activities
        left_frame = tk.Frame(paned, bg=self.bg_panel, bd=1, relief="ridge", padx=10, pady=10)
        paned.add(left_frame, width=540)

        lbl_acts = tk.Label(left_frame, text="MY ACTIVITIES", font=("Helvetica", 11, "bold"), bg=self.bg_panel, fg="#ffffff")
        lbl_acts.pack(anchor="w", pady=(0, 8))

        columns = ("name", "state", "cpu", "memory", "pids")
        self.tree_activities = ttk.Treeview(left_frame, columns=columns, show="headings", selectmode="browse")
        self.tree_activities.heading("name", text="Activity")
        self.tree_activities.heading("state", text="State")
        self.tree_activities.heading("cpu", text="CPU %")
        self.tree_activities.heading("memory", text="Memory")
        self.tree_activities.heading("pids", text="PIDs")

        self.tree_activities.column("name", width=120)
        self.tree_activities.column("state", width=75, anchor="center")
        self.tree_activities.column("cpu", width=65, anchor="e")
        self.tree_activities.column("memory", width=80, anchor="e")
        self.tree_activities.column("pids", width=55, anchor="center")

        self.tree_activities.pack(fill="both", expand=True)
        self.tree_activities.bind("<<TreeviewSelect>>", self._on_activity_select)

        # Action Buttons under activities list
        btn_box = tk.Frame(left_frame, bg=self.bg_panel, pady=8)
        btn_box.pack(fill="x")

        tk.Button(btn_box, text="Start", bg="#388e3c", fg="white", font=("Helvetica", 9, "bold"), padx=10, command=self._start_selected).pack(side="left", padx=4)
        tk.Button(btn_box, text="Pause (SIGSTOP)", bg="#f57c00", fg="white", font=("Helvetica", 9, "bold"), padx=10, command=self._pause_selected).pack(side="left", padx=4)
        tk.Button(btn_box, text="Resume (SIGCONT)", bg="#2e7d32", fg="white", font=("Helvetica", 9, "bold"), padx=10, command=self._resume_selected).pack(side="left", padx=4)
        tk.Button(btn_box, text="Stop", bg="#c62828", fg="white", font=("Helvetica", 9, "bold"), padx=10, command=self._stop_selected).pack(side="left", padx=4)
        tk.Button(btn_box, text="Delete", bg="#424242", fg="white", padx=8, command=self._delete_selected).pack(side="right", padx=4)

        # Right panel: Drill-down & Timeline
        right_frame = tk.Frame(paned, bg=self.bg_panel, bd=1, relief="ridge", padx=10, pady=10)
        paned.add(right_frame)

        self.drill_title_var = tk.StringVar(value="ACTIVITY DRILL-DOWN (Select an activity)")
        lbl_drill = tk.Label(right_frame, textvariable=self.drill_title_var, font=("Helvetica", 11, "bold"), bg=self.bg_panel, fg="#ffffff")
        lbl_drill.pack(anchor="w", pady=(0, 4))

        # Conceptual info label
        info_lbl = tk.Label(
            right_frame,
            text="ActivityOS aggregates underlying Linux processes into one Activity context.",
            font=("Helvetica", 9, "italic"),
            bg=self.bg_panel,
            fg="#8c887b"
        )
        info_lbl.pack(anchor="w", pady=(0, 8))

        # Drilldown processes treeview
        proc_columns = ("pid", "name", "cpu", "memory", "status")
        self.tree_procs = ttk.Treeview(right_frame, columns=proc_columns, show="headings", height=8)
        self.tree_procs.heading("pid", text="PID")
        self.tree_procs.heading("name", text="Process Name")
        self.tree_procs.heading("cpu", text="CPU %")
        self.tree_procs.heading("memory", text="Memory RSS")
        self.tree_procs.heading("status", text="Status")

        self.tree_procs.column("pid", width=65, anchor="center")
        self.tree_procs.column("name", width=140)
        self.tree_procs.column("cpu", width=65, anchor="e")
        self.tree_procs.column("memory", width=85, anchor="e")
        self.tree_procs.column("status", width=75, anchor="center")

        self.tree_procs.pack(fill="both", expand=True)

        # Activity Event History Timeline
        lbl_timeline = tk.Label(right_frame, text="ACTIVITY TIMELINE LOG", font=("Helvetica", 10, "bold"), bg=self.bg_panel, fg="#ffffff")
        lbl_timeline.pack(anchor="w", pady=(12, 4))

        self.timeline_listbox = tk.Listbox(right_frame, bg=self.bg_card, fg=self.fg_main, font=("Courier", 9), height=7, bd=0)
        self.timeline_listbox.pack(fill="both", expand=True)

    def _poll_heartbeat(self):
        """Periodic background refresh."""
        try:
            data = self.manager.poll_all_resources()
            sys_data = data.get("system", {})
            self.sys_cpu_var.set(f"CPU: {sys_data.get('cpu_percent', 0.0):.1f}%")
            self.sys_mem_var.set(f"Memory: {sys_data.get('memory_percent', 0.0):.1f}% ({sys_data.get('memory_used_mb', 0):.0f}/{sys_data.get('memory_total_mb', 0):.0f} MB)")

            activities = self.manager.get_all_activities()
            self.act_count_var.set(f"Activities: {len(activities)}")

            active_pids = sum(len(a.member_processes) for a in activities if a.state in (ActivityState.ACTIVE, ActivityState.PAUSED))
            self.proc_count_var.set(f"Managed PIDs: {active_pids}")

            # Refresh activities treeview
            curr_selected = self.tree_activities.selection()
            self.tree_activities.delete(*self.tree_activities.get_children())

            for act in activities:
                snap = act.resource_snapshot
                mem_str = f"{snap.memory_mb:.1f} MB" if snap.memory_mb < 1024 else f"{(snap.memory_mb/1024):.2f} GB"
                item_id = self.tree_activities.insert(
                    "", "end", iid=act.activity_id,
                    values=(act.name, act.state.value, f"{snap.cpu_percent:.1f}%", mem_str, len(act.member_processes))
                )

            # Re-select
            if self.selected_act_id and self.selected_act_id in [a.activity_id for a in activities]:
                self.tree_activities.selection_set(self.selected_act_id)
                self._update_drilldown_view(self.selected_act_id)

        except Exception as e:
            print(f"[TkApp] Poll error: {e}")

        self.root.after(1500, self._poll_heartbeat)

    def _on_activity_select(self, event):
        sel = self.tree_activities.selection()
        if sel:
            self.selected_act_id = sel[0]
            self._update_drilldown_view(self.selected_act_id)

    def _update_drilldown_view(self, act_id: str):
        drill = self.manager.get_drilldown(act_id)
        if not drill:
            return

        self.drill_title_var.set(f"ACTIVITY: {drill['name'].upper()} [{drill['state']}]")

        # Update contributing processes
        self.tree_procs.delete(*self.tree_procs.get_children())
        summary = drill.get("summary", {})
        processes = summary.get("contributing_processes", [])
        for p in processes:
            mem_str = f"{p['memory_mb']:.1f} MB" if p.get('memory_mb') else "0 MB"
            self.tree_procs.insert("", "end", values=(p["pid"], p["name"], f"{p['cpu_percent']:.1f}%", mem_str, p["status"]))

        # Update timeline events
        self.timeline_listbox.delete(0, "end")
        events = drill.get("event_log", [])
        for e in reversed(events):
            self.timeline_listbox.insert("end", f"[{e['iso_time']}] [{e['action'].upper()}] {e['details']}")

    def _start_selected(self):
        if not self.selected_act_id:
            messagebox.showinfo("Select Activity", "Please select an activity from the list.")
            return
        ok, msg = self.manager.start_activity(self.selected_act_id)
        messagebox.showinfo("Start Activity", msg)

    def _pause_selected(self):
        if not self.selected_act_id:
            messagebox.showinfo("Select Activity", "Please select an activity from the list.")
            return
        res = self.manager.pause_activity(self.selected_act_id)
        messagebox.showinfo("Pause Activity", res.summary)

    def _resume_selected(self):
        if not self.selected_act_id:
            messagebox.showinfo("Select Activity", "Please select an activity from the list.")
            return
        res = self.manager.resume_activity(self.selected_act_id)
        messagebox.showinfo("Resume Activity", res.summary)

    def _stop_selected(self):
        if not self.selected_act_id:
            messagebox.showinfo("Select Activity", "Please select an activity from the list.")
            return
        res = self.manager.stop_activity(self.selected_act_id)
        messagebox.showinfo("Stop Activity", res.summary)

    def _delete_selected(self):
        if not self.selected_act_id:
            return
        if messagebox.askyesno("Delete Activity", "Are you sure you want to delete this activity?"):
            self.manager.delete_activity(self.selected_act_id)
            self.selected_act_id = None

    def _open_create_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Create Activity")
        dialog.geometry("640x500")
        dialog.configure(bg=self.bg_panel)

        tk.Label(dialog, text="Activity Name:", bg=self.bg_panel, fg="#ffffff", font=("Helvetica", 10, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        name_entry = tk.Entry(dialog, font=("Helvetica", 11), bg=self.bg_card, fg="#ffffff", insertbackground="white")
        name_entry.pack(fill="x", padx=16, pady=(0, 10))

        tk.Label(dialog, text="Optional Launch Command (e.g. 'code', 'python demo_workload.py'):", bg=self.bg_panel, fg="#ffffff", font=("Helvetica", 9, "bold")).pack(anchor="w", padx=16, pady=(0, 2))
        cmd_entry = tk.Entry(dialog, font=("Courier", 10), bg=self.bg_card, fg="#ffffff", insertbackground="white")
        cmd_entry.pack(fill="x", padx=16, pady=(0, 10))

        tk.Label(dialog, text="Associate Running Processes (Select PIDs):", bg=self.bg_panel, fg="#ffffff", font=("Helvetica", 9, "bold")).pack(anchor="w", padx=16, pady=(0, 4))

        # Process select listbox with multiple select
        p_frame = tk.Frame(dialog, bg=self.bg_card)
        p_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        scrollbar = tk.Scrollbar(p_frame)
        scrollbar.pack(side="right", fill="y")

        proc_listbox = tk.Listbox(p_frame, selectmode="multiple", bg=self.bg_card, fg=self.fg_main, font=("Courier", 9), yscrollcommand=scrollbar.set)
        proc_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=proc_listbox.yview)

        # Scan processes
        procs = self.manager.grouper.discover_available_processes()
        pid_map = []
        for p in procs[:80]:
            pid_map.append(p["pid"])
            proc_listbox.insert("end", f"PID {p['pid']:<6} | {p['name']:<18} | {p['memory_mb']:>6.1f} MB | {p['status']}")

        def on_create():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Error", "Please enter an activity name.")
                return

            sel_indices = proc_listbox.curselection()
            selected_pids = [pid_map[i] for i in sel_indices]

            app_cmd = cmd_entry.get().strip()
            configured_apps = [{"name": name, "command": app_cmd}] if app_cmd else []

            act = self.manager.create_activity(name, selected_pids, configured_apps)
            self.selected_act_id = act.activity_id
            dialog.destroy()

        btn_row = tk.Frame(dialog, bg=self.bg_panel)
        btn_row.pack(fill="x", padx=16, pady=10)
        tk.Button(btn_row, text="Cancel", bg="#424242", fg="white", padx=12, command=dialog.destroy).pack(side="right", padx=6)
        tk.Button(btn_row, text="Create Activity", bg=self.accent, fg="white", font=("Helvetica", 9, "bold"), padx=14, command=on_create).pack(side="right")


def launch_tk_gui(manager: ActivityManager):
    root = tk.Tk()
    app = ActivityOSTkApp(root, manager)
    root.mainloop()
