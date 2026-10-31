# WSL terminal interruptions — evidence, 2026-10-31 UTC

User requested investigation of repeated `wsl.exe -d Ubuntu-24.04` exit code 1
and Conversation interrupted, followed by an unspecified PowerShell filesystem
error. The user subsequently restarted and reported current operation stable.
Investigation was read-only apart from this Supervisor evidence/ledger record;
no crash reproduction, runtime configuration change, or cloud operation.

## Confirmed chain

- 00:08:57: global OOM killed Python PID 522832, anonymous RSS 22,817,436 kB
  (21.76 GiB). The VM had about 24 GiB RAM and all 16 GiB swap was exhausted.
  Evidence: `/var/log/kern.log:44263-44265,44339-44340`.
- The victim belonged to `/init.scope`. systemd recorded its OOM at 00:08:57.125
  (`/var/log/syslog:473528`). Herdr received SIGTERM at 00:08:57.366569 and exited
  after cleanup (`~/.config/herdr/herdr-server.log:19725-19736`).
- At 00:10:27, systemd explicitly SIGKILLed init, SessionLeader, bash, Codex and
  Herdr in init.scope after its 90-second stop timeout, ending with `oom-kill`.
  Evidence: `/var/log/syslog:473657-473672`.
- Reopening the distro at 00:53:55, 00:56:07, 00:58:27 and 01:00:40 reused kernel
  boot ID `a7338a503f9c4be19129a3c0e7e29d29`. Each was followed by init.scope
  OOM/stop and another 90-second termination. Repeated kernel OOM messages have
  the same source monotonic timestamp 5245033448; they are not four independent
  new Python OOMs. The precise cgroup/systemd persistence mechanism is unproven.
- Effective init.scope policy is `OOMPolicy=stop`, `KillMode=control-group`,
  `TimeoutStopUSec=1min 30s`; no custom drop-in was found. The defaults appear
  in `/etc/systemd/system.conf:49,80`.
- A new kernel boot around 01:03:40 has ID
  `682d14c3-4beb-466f-b191-0309c53752fe`. Current init.scope OOM counters are zero.
  Supervisor verification: about 4.6 GiB RAM used, 18 GiB available, zero swap
  used; root and /mnt/c mounted read/write. Recovery is not a test-memory fix.

## Actions and attribution

The Claude transcript at
`~/.claude/projects/-mnt-c-Users-swl00-IFPRI-Dropbox-Weilun-Shi-IPCCH-monthly-operational/6a490ae1-ee00-43f9-bdfc-c887c9816c09.jsonl:12119`
starts the producer pytest at 00:02:57.827 using the pinned Python. Its output
was piped through grep/head, and no tool result survived. It is the outstanding
test invocation in that time window. No exact PID-to-command record was found;
do not assert the killed PID or individual test identity as proven.

The last completed Supervisor tool before OOM was a Herdr read at 00:05:59.
Neither target transcript contains an executed kill/pkill/shutdown/wsl-terminate
command before the event. At 00:10:25, AFTER the initial OOM/Herdr exit, Supervisor
backed up `session.json`, removed pane autolaunch metadata and started Herdr.
That new server was itself killed by the ongoing init.scope stop at 00:10:27.
The recovery was attempted before the wider systemd failure was understood.

Two later calls lost their return records during repeated exits: the 00:55:25
Herdr prompt and the 00:57:36 compound docs-patch/wait/read call. The latter's
file patch completed. `~/.codex/app-server-daemon/daemon.stderr.log:3-24`
reports these missing outputs on replay; it contains no corresponding crash
stacktrace. The user's 00:59:11 pause also explicitly interrupted a turn.

## Filesystem/Windows evidence and limits

- System/stornvme Event 129 at 00:08:37.286: NVMe RaidPort1 device reset.
- Microsoft-Windows-Ntfs/Operational Event 147, RecordId 234596 at
  01:03:17.893960: a C: WdiContextLog write took 44,457 ms. Ubuntu's VHD BasePath
  is also on C:. Storage latency is confirmed; causal relation and corruption
  are not established.
- WSLService Event 7011 at 01:03:45.051 reports a 30-second response timeout;
  Hyper-V VmSwitch records replacement of the WSL VM around 01:03:46.
- No matching EXT4 corruption/I/O-error/remount-read-only/panic was found.
  Journal warnings say corrupted OR unclean shutdown; /tmp/.X11-unix is a
  separate read-only tmpfs. Neither proves root/VHD corruption. Three Git SIGBUS
  events and 9p cache warnings after restart remain a separate filesystem lead.
- PowerShell's exact error is unavailable; Hyper-V-Compute event channels were
  not readable. Do not claim the filesystem issue resolved or disk healthy.

## Constraint before CP2 continuation

Do not rerun the full producer suite unbounded. First isolate the suspected test
invocation with a memory-limited scope outside init.scope, full logs, PID/exit
evidence, and peak-memory measurement. Identify the failing test/code path before
repair; do not change global OOM policy or increase memory as an assumed fix.
CP2 remains unaccepted; deployment and real E2E acceptance remain pending.
