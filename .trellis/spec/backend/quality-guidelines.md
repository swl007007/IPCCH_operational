# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

<!--
Document your project's quality standards here.

Questions to answer:
- What patterns are forbidden?
- What linting rules do you enforce?
- What are your testing requirements?
- What code review standards apply?
-->

(To be filled by the team)

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

(To be filled by the team)

---

## Required Patterns

<!-- Patterns that must always be used -->

(To be filled by the team)

---

## Testing Requirements

Run IPCCH local tests sequentially in an independent user service outside WSL
`init.scope`, using the active E2E task's `research/cp2/guarded.sh` (or the same
limits): `MemoryMax=4G`, `MemorySwapMax=0`, `RuntimeMaxSec=600`, address space
3 GiB, BLAS/OMP threads 1. Keep `/usr/bin/time -v`, full logs and the child's exit
marker. A missing marker is INTERRUPTED, even when systemd-run returns zero.

Polling test clocks must advance: `poll_seconds=1` with a fake sleep that advances
time. For sequential waits, script earlier siblings to complete before testing
a later failed sibling. Cap test-only event recording/polls; a runaway guard
must escape the waiter's intentional `Exception` retry (use a dedicated
`BaseException` subclass). Zero-delay/no-op clocks can produce unbounded loops
and event growth. Assert sibling cancellation and timeout receipts, not just an
exception. See `tests/cloud/ipcch_producer_world.py` and producer lifecycle tests.

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)
