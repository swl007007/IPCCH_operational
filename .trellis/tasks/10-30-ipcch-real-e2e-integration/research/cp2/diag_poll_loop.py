"""CP2 memory-incident diagnostic: the failed-sibling and timeout lifecycle scenarios with a hard poll cap.
Shows which task the sequential wait polls, whether the failing task T2 is ever reached, the growth of the test-only
WorldEE.events list, and whether the fake clock advances with poll_seconds=0. Never loops unbounded."""
import sys
import tracemalloc
from datetime import timedelta

sys.path.insert(0, ".")
from tests.cloud import test_ipcch_table_producers as T  # noqa: E402
from tests.cloud import ipcch_producer_world as pw  # noqa: E402

CAP = 200_000


class Capped(BaseException):          # BaseException: EETransport._wait retries ordinary Exceptions as STATUS_ERROR
    pass


class StatusError(Exception):           # an ordinary status failure: retried by _wait until its budget
    pass


def run(label, states, deadline=None, fake_clock=False, tmp=None, swallow_after=None):
    import pathlib
    import tempfile
    tmp = pathlib.Path(tempfile.mkdtemp())
    counts = {}

    def capped(task):
        counts[task.id] = counts.get(task.id, 0) + 1
        total = sum(counts.values())
        if total > CAP:
            raise Capped
        if swallow_after is not None and total > swallow_after:
            raise StatusError("injected status failure")
        return states(task) if callable(states) else states[min(task.polls, len(states) - 1)]
    producer, t, wee, tables = T.produce(tmp, ee_kw={"states": capped}, deadline=deadline)
    clock = {"t": T.NOW}
    if fake_clock:
        t.clock = lambda: clock["t"]
        t.monotonic = lambda: (clock["t"] - T.NOW).total_seconds()
        t.sleep = lambda s: clock.__setitem__("t", clock["t"] + timedelta(seconds=s))
    tracemalloc.start()
    try:
        producer.run(tables, origin="2026-09", windows=T.WINDOWS)
        outcome = "returned"
    except Capped:
        outcome = f"poll cap {CAP} reached"
    except Exception as exc:
        outcome = f"{type(exc).__name__}: {exc}"[:200]
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"[{label}] outcome={outcome}", flush=True)
    print(f"[{label}] poll_seconds={t.poll_seconds} polls_by_task={counts} events={len(wee.events)} "
          f"fake_clock_advanced_s={(clock['t'] - T.NOW).total_seconds()} traced_peak_MB={peak / 2**20:.1f}", flush=True)


run("failed-sibling", lambda task: "FAILED" if task.id == "T2" else "RUNNING")
run("timeout", ("RUNNING",), deadline=T.NOW + timedelta(seconds=905), fake_clock=True)
run("status-exception-retried", ("RUNNING",), swallow_after=1000)
