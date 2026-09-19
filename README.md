````markdown
# Processes in Groups

A small experiment: what if you grouped OS processes by what you're actually doing, instead of by process name?

Basically, the computer sees processes. I see activities.

## Why

My computer gets slow sometimes and Task Manager tells me `chrome.exe` is at 32%.

Cool, but I don't really care about `chrome.exe` being at 32%. I care about why my study session is lagging.

I usually think in terms of activities:

- Studying
- Coding
- Gaming
- Writing
- Research

The OS thinks in terms of:

- `chrome.exe`
- `Code.exe`
- `python.exe`
- `terminal.exe`

So I started wondering:

> What if processes could be grouped around the activity they belong to?

## The idea

Instead of seeing:

```text
Chrome
VS Code
PDF Reader
Terminal
````

I want to see:

```text
Study
├── Chrome
├── VS Code
├── PDF Reader
└── Terminal
```

The underlying processes don't change. This is simply another layer of organization around them.

## What it does

The current prototype can:

* Create activities and give them names
* Associate real Linux processes with activities
* Launch configured applications as part of an activity
* Discover and track their real PIDs
* Monitor CPU and memory usage
* Aggregate resource usage across an activity
* Show the processes contributing to an activity
* Pause and resume an entire activity
* Stop an activity and its processes
* Detect processes that exit unexpectedly
* Record activity events over time
* Persist activities and session information

Instead of managing several processes individually, the idea is to manage the activity they belong to.

## How it works

The operating system still manages normal Linux processes. This project adds an activity layer above them.

```text
Activity
   |
   +-- Resource Monitoring
   |
   +-- Activity Control
   |
   +-- Event History
   |
   +-- Persistence
   |
   +-- Linux Processes
          |
          +-- Chrome
          +-- VS Code
          +-- Terminal
```

Activities are application-level objects. They don't replace processes or require changes to the Linux kernel.

## Implementation

The prototype uses existing Linux interfaces for process monitoring and control.

* CPU: `/proc/<pid>/stat`
* Memory: `/proc/<pid>/status`
* Pause / Resume: `SIGSTOP` / `SIGCONT`
* Stopping: `SIGTERM`
* Process discovery: Linux PID and process information
* Persistence: JSON
* Event history: application-level timeline logging
* Priority: Linux `setpriority()` / `nice` infrastructure

The project currently runs on Linux.

## What I'm exploring

The interesting part isn't really the dashboard. It's the abstraction.

Processes are useful execution units, but they aren't necessarily how people think about the work happening on a computer.

An activity might contain one process, several processes, or several applications.

The question I'm exploring is whether this higher-level relationship can be made useful without changing the underlying process model.

## Current limitations

This is still an experiment.

* Activities are manually defined
* Processes are manually associated with activities
* Linux is the only supported OS
* Automatic activity detection isn't implemented
* Rich historical analytics are still limited
* Dynamic process membership is not fully implemented
* Activity-level priority policies are not yet fully wired into the lifecycle

## Tech

* Python
* Linux
* `/proc`
* POSIX signals
* subprocesses
* JSON persistence
* Tkinter / web-based interface
* Automated tests
* Real-process end-to-end testing

## Why I'm building this

I don't know yet whether this abstraction is actually useful.

That's kind of the point.

I'm interested in what happens when you stop looking at a computer as a collection of applications and processes, and instead look at it through the things you're actually trying to do.

The computer sees processes. I see activities.

```
```