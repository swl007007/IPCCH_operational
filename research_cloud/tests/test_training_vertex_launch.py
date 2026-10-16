"""The per-trial cap command (cloud_job.cap_command, coreutils timeout) ends an over-running trial even when the
wrapper is the container's PID 1 - checked inside the pinned training-ipcch image (bwrap --as-pid-1, the exact
train-entry -> timeout -> python chain of the Vertex spec) when its rootfs is available, else with the host's
coreutils. (An in-process SIGALRM is not a cap: PID 1 ignores signals it has no handler for.)"""
import json
import os
import shutil
import subprocess
import time
import unittest

from research_cloud.training import vertex_submit as vs
from research_cloud.training.cloud_job import cap_command

ROOTFS = "/home/swl007007/projects/food-crisis-research/scratch/image-pulls/training-ipcch-fdbe6d1.rootfs"
CONFIG = "/home/swl007007/projects/food-crisis-research/scratch/image-pulls/training-ipcch-fdbe6d1.config.json"
SLEEP = "import os, time; print(os.getpid(), os.getppid(), flush=True); time.sleep(10)"
STUBBORN = "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print(os.getpid(), os.getppid(), flush=True); time.sleep(10)"


def short(cap_s):                       # the production wrapper with a 2 s kill grace instead of 30 s
    return [c.replace("--kill-after=30s", "--kill-after=2s") for c in cap_command(cap_s)]


class Cap(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(ROOTFS) and shutil.which("bwrap"), "pinned image rootfs or bwrap not available")
    def test_cap_in_image_as_pid1(self):
        from research_cloud.images.rootfs_replay import sandbox
        out = os.path.join("/tmp", f"cap-test-{os.getpid()}")
        os.makedirs(out, exist_ok=True)
        base = sandbox(ROOTFS, json.load(open(CONFIG)), out, out)
        i = base.index("--clearenv")
        base[i:i] = ["--as-pid-1"]
        cases = [  # (command, expected rc, max seconds, (trial is PID 1, trial's parent pid))
            # TERM at the cap -> 124; a TERM-ignoring trial gets KILL after the grace -> 137; the last case shows why a
            # signal-only cap fails: an unwrapped python PID 1 survives SIGALRM and SIGTERM (exits 0 on its own)
            (["/usr/local/bin/train-entry"] + short(1) + ["python", "-c", SLEEP], 124, 6, (False, "1")),
            (["/usr/local/bin/train-entry"] + short(1) + ["python", "-c", STUBBORN], 137, 8, (False, "1")),
            (["python", "-c", "import os, signal, time; print(os.getpid(), os.getppid(), flush=True); "
              "os.kill(1, signal.SIGALRM); os.kill(1, signal.SIGTERM); time.sleep(1)"], 0, 6, (True, "0")),
        ]
        for cmd, rc_want, max_s, ids in cases:
            t0 = time.time()
            r = subprocess.run(base + cmd, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, rc_want, (cmd, r.stderr[-500:]))
            self.assertLess(time.time() - t0, max_s)
            pid, ppid = r.stdout.split()[:2]
            self.assertEqual((pid == "1", ppid), ids)           # wrapped: the trial is not PID 1, its parent is

    def test_admission_requires_the_cap_at_the_command_prefix(self):
        detail = {"timeout_s": 900, "hpt_trials": 2}
        cap = cap_command(900)

        def problems(cmd):
            job = {"maxTrialCount": 2, "parallelTrialCount": 1, "trialJobSpec": {
                "workerPoolSpecs": [{"machineSpec": {"machineType": "n1-highmem-4"}, "replicaCount": "1",
                                     "containerSpec": {"imageUri": "i@sha256:x", "command": cmd}}],
                "scheduling": {"timeout": "3000s", "disableRetries": True}}}
            return [p for p in vs.within_reservation(job, "hpt", detail) if "per-trial cap" in p]
        entry = "/usr/local/bin/train-entry"
        from research_cloud.training import cloud_job as cj
        made = cj.spec("m", "repo/img@sha256:" + "b" * 64, "n1-highmem-4", "/gcs/a", "/gcs/b", "ipcch", 900, 2,
                       "crisis_f1", {"rounds": {"type": "int", "min": 50, "max": 100}},
                       mlflow_uri="https://svc.run.app", experiment="e", entry=entry)
        self.assertEqual(problems(made["trialJobSpec"]["workerPoolSpecs"][0]["containerSpec"]["command"]), [])
        self.assertEqual(problems([entry] + cap + ["python", "-c", "x"]), [])
        self.assertEqual(problems(cap + ["python", "-c", "x"]), [])
        for bad in ([entry, "python", "-c", "x"] + cap,                     # cap present but not the prefix
                    ["sh", "-c", "x"] + cap + ["python"],                   # something runs before the cap
                    [entry, entry] + cap + ["python"],                      # entry twice
                    [entry] + cap + ["sh", "-c", "python"],                 # cap does not run python directly
                    [entry] + cap,                                          # no python at all
                    [entry] + cap_command(1800) + ["python"],               # cap above the reservation
                    [entry, "/usr/bin/timeout", "900s", "python"],          # no KILL escalation
                    ["python", "-c", "x"], []):
            self.assertTrue(problems(bad), bad)

    def test_cap_on_host(self):
        t0 = time.time()
        rc = subprocess.run([shutil.which("timeout")] + short(1)[1:] + ["sleep", "10"], timeout=60).returncode
        self.assertEqual(rc, 124)
        self.assertLess(time.time() - t0, 6)


if __name__ == "__main__":
    unittest.main()
