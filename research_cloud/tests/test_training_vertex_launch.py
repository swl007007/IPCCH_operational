"""The launcher's per-trial cap: its own header code (IPCCH_TRIAL_TIMEOUT_S -> SIGALRM) terminates an over-running
trial with SIGALRM, so the trial fails visibly; without the variable nothing is armed."""
import os
import signal
import subprocess
import sys
import unittest

from research_cloud.training.vertex_launch import LAUNCHER


class Cap(unittest.TestCase):
    def header(self):
        lines = LAUNCHER.split("\n")
        end = next(i for i, line in enumerate(lines) if line.startswith("import google.auth"))
        return "\n".join(lines[:end]) + "\nimport time\ntime.sleep(5)\n"

    def run_with(self, cap):
        env = {**os.environ, **({"IPCCH_TRIAL_TIMEOUT_S": cap} if cap else {})}
        env.pop("IPCCH_TRIAL_TIMEOUT_S", None) if cap is None else None
        return subprocess.run([sys.executable, "-c", self.header()], env=env, timeout=30).returncode

    def test_alarm_terminates_and_absent_cap_does_not(self):
        self.assertEqual(self.run_with("1"), -signal.SIGALRM)
        self.assertEqual(self.run_with(None), 0)


if __name__ == "__main__":
    unittest.main()
