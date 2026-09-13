# Processes in Groups

A little experiment: what if you grouped OS processes by what you're actually *doing*, instead of by process name?

Basically — **the computer sees processes. I see activities.** This is just me poking at that mismatch.

---

## Why

My computer gets slow sometimes and Task Manager tells me `chrome.exe` is at 32%. Cool, but I don't care about that — I care about *why my study session is lagging*.

I usually think in terms of activities (studying, coding, gaming...) but the OS only knows about individual processes. So:

> what if I could just group processes around the activity they belong to?

That's it. That's the whole idea. No manifesto, just curiosity.

---

## The idea, roughly

Instead of seeing:

```
Chrome
VS Code
PDF Reader
Terminal
```

I want to see:

```
Study
 ├── Chrome
 ├── VS Code
 ├── PDF Reader
 └── Terminal
```

Same processes, just wrapped in a layer that says "these belong together."

---

## What it (tries to) do

- make a group, name it (`Study`, `Coding`, whatever)
- add processes to it
- see combined CPU/memory
- pause / resume the whole group at once
- change priority for everything in it
- keep a bit of history

So instead of managing 4 apps separately, I manage "Study."

---

## Tech Stack

- **OS:** Linux
- **Process Management:** OS process table / process interfaces
- **Process Monitoring:** CPU & memory usage from running processes
- **Process Control:** POSIX signals (`SIGSTOP`, `SIGCONT`)
- **Priority Control:** `nice` / `setpriority`
- **System Interaction:** Standard OS system calls / primitives
- **Storage:** Activity/group mappings and history
- **Interface:** Activity-grouped task manager / dashboard

Didn't want the build to be more complicated than the idea.

---

## Deliberate simplification

No auto-detecting what I'm doing. If I make a `Study` group, I manually add processes to it. Figuring out activity detection automatically is a whole different rabbit hole — not the point right now.

Just testing: **is grouping itself useful?**

---

## Not trying to prove anything

Not claiming processes are a bad abstraction, or that OSes need rethinking, or that this makes anything faster. Processes are fine — I'm just curious if they're the best way for *me* to look at what my computer is doing.

## If it goes somewhere

Maybe activity-aware resource management, scheduling, monitoring... or maybe not. It's an experiment, not a roadmap.
