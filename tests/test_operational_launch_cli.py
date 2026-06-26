import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import model_pipeline.run_operational_launch_inference as cli
from model_pipeline.ipcch_launch_runtime import outputs


class OperationalLaunchCliTests(unittest.TestCase):
    def test_no_map_writes_three_prediction_csvs_and_passed_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = self._write_input(root / "input.csv")
            model_package = root / "package"
            model_package.mkdir()
            output_dir = root / "out"
            calls = []

            def fake_run_scope(*, monthly_rows, feature_month, scope_months, **kwargs):
                calls.append((scope_months, feature_month, kwargs["target_month"]))
                self.assertEqual(["001", "002"], monthly_rows["area_id"].tolist())
                self.assertEqual(["001", "002"], monthly_rows["admin_code"].tolist())
                predictions = pd.DataFrame(
                    {
                        "area_id": monthly_rows["area_id"],
                        "overall_phase_pred": [3, 2],
                        "scope_months": scope_months,
                    }
                )
                summary = {
                    "status": "passed",
                    "scope_months": scope_months,
                    "target_month": kwargs["target_month"],
                    "row_count": len(predictions),
                }
                return predictions, summary

            with mock.patch.object(cli, "run_scope", side_effect=fake_run_scope):
                exit_code = cli.main(
                    [
                        "--input",
                        str(input_path),
                        "--model-package",
                        str(model_package),
                        "--output-dir",
                        str(output_dir),
                        "--feature-month",
                        "2026-04",
                        "--no-map",
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertEqual(
                [
                    (0, "2026-04", "2026-04"),
                    (6, "2026-04", "2026-10"),
                    (12, "2026-04", "2027-04"),
                ],
                calls,
            )
            for scope in (0, 6, 12):
                csv_path = output_dir / (
                    "ipcch_launch_202604_scope_{0}m_predictions.csv".format(scope)
                )
                map_path = output_dir / (
                    "ipcch_launch_202604_scope_{0}m_map.png".format(scope)
                )
                self.assertTrue(csv_path.exists())
                self.assertFalse(map_path.exists())

            summary = self._read_summary(output_dir)
            self.assertEqual("passed", summary["status"])
            self.assertEqual([0, 6, 12], summary["scopes_completed"])
            self.assertTrue(summary["map_generation_disabled"])
            self.assertEqual("2026-04", summary["feature_month"])
            self.assertEqual(str(input_path), summary["input"]["path"])
            self.assertIn("sha256", summary["input"])
            self.assertEqual("passed", summary["input_report"]["status"])
            self.assertEqual(
                str(output_dir / "ipcch_launch_202604_scope_0m_predictions.csv"),
                summary["planned_outputs"]["0"]["predictions_csv"],
            )
            self.assertEqual(
                str(output_dir / "ipcch_launch_202604_scope_0m_predictions.csv"),
                summary["written_outputs"]["0"]["predictions_csv"],
            )
            self.assertNotIn("map_png", summary["planned_outputs"]["0"])
            self.assertNotIn("map_png", summary["written_outputs"]["0"])

    def test_existing_output_without_overwrite_fails_before_scoring_or_mixing_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = self._write_input(root / "input.csv")
            model_package = root / "package"
            model_package.mkdir()
            output_dir = root / "out"
            output_dir.mkdir()
            existing = output_dir / "ipcch_launch_202604_scope_0m_predictions.csv"
            existing.write_text("sentinel\n", encoding="utf-8")

            with mock.patch.object(cli, "run_scope") as run_scope:
                exit_code = cli.main(
                    [
                        "--input",
                        str(input_path),
                        "--model-package",
                        str(model_package),
                        "--output-dir",
                        str(output_dir),
                        "--feature-month",
                        "2026-04",
                        "--no-map",
                    ]
                )

            self.assertNotEqual(0, exit_code)
            run_scope.assert_not_called()
            self.assertEqual("sentinel\n", existing.read_text(encoding="utf-8"))
            self.assertFalse(
                (output_dir / "ipcch_launch_202604_scope_6m_predictions.csv").exists()
            )
            summary = self._read_summary(output_dir)
            self.assertEqual("failed", summary["status"])
            self.assertEqual([], summary["scopes_completed"])
            self.assertEqual({}, summary["written_outputs"])

    def test_validate_only_writes_summary_but_no_primary_predictions_or_maps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = self._write_input(root / "input.csv")
            model_package = root / "package"
            model_package.mkdir()
            output_dir = root / "out"

            with mock.patch.object(cli, "run_scope") as run_scope:
                exit_code = cli.main(
                    [
                        "--input",
                        str(input_path),
                        "--model-package",
                        str(model_package),
                        "--output-dir",
                        str(output_dir),
                        "--feature-month",
                        "2026-04",
                        "--validate-only",
                    ]
                )

            self.assertEqual(0, exit_code)
            run_scope.assert_not_called()
            self.assertEqual([], list(output_dir.glob("*_predictions.csv")))
            self.assertEqual([], list(output_dir.glob("*_map.png")))
            summary = self._read_summary(output_dir)
            self.assertEqual("passed", summary["status"])
            self.assertTrue(summary["validate_only"])
            self.assertEqual([], summary["scopes_completed"])
            self.assertEqual({}, summary["planned_outputs"])
            self.assertEqual({}, summary["written_outputs"])

    def test_input_validation_failure_writes_failed_summary_and_no_primary_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "input.csv"
            pd.DataFrame({"admin_code": ["001"], "year": [2026], "month": [5]}).to_csv(
                input_path,
                index=False,
            )
            model_package = root / "package"
            model_package.mkdir()
            output_dir = root / "out"

            with mock.patch.object(cli, "run_scope") as run_scope:
                exit_code = cli.main(
                    [
                        "--input",
                        str(input_path),
                        "--model-package",
                        str(model_package),
                        "--output-dir",
                        str(output_dir),
                        "--feature-month",
                        "2026-04",
                        "--no-map",
                    ]
                )

            self.assertNotEqual(0, exit_code)
            run_scope.assert_not_called()
            self.assertEqual([], list(output_dir.glob("*_predictions.csv")))
            self.assertEqual([], list(output_dir.glob("*_map.png")))
            summary = self._read_summary(output_dir)
            self.assertEqual("failed", summary["status"])
            self.assertIn("feature_month", summary["error"]["message"])
            self.assertEqual({}, summary["planned_outputs"])
            self.assertEqual({}, summary["written_outputs"])

    def test_missing_spatial_path_when_maps_enabled_fails_before_primary_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = self._write_input(root / "input.csv")
            model_package = root / "package"
            model_package.mkdir()
            output_dir = root / "out"

            with mock.patch.object(cli, "run_scope") as run_scope:
                exit_code = cli.main(
                    [
                        "--input",
                        str(input_path),
                        "--model-package",
                        str(model_package),
                        "--output-dir",
                        str(output_dir),
                        "--feature-month",
                        "2026-04",
                    ]
                )

            self.assertNotEqual(0, exit_code)
            run_scope.assert_not_called()
            self.assertEqual([], list(output_dir.glob("*_predictions.csv")))
            summary = self._read_summary(output_dir)
            self.assertEqual("failed", summary["status"])
            self.assertIn("spatial-path", summary["error"]["message"])
            self.assertEqual({}, summary["planned_outputs"])
            self.assertEqual({}, summary["written_outputs"])

    def test_missing_input_path_returns_nonzero_and_writes_failed_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_input = root / "missing.csv"
            model_package = root / "package"
            model_package.mkdir()
            output_dir = root / "out"

            with mock.patch.object(cli, "run_scope") as run_scope:
                exit_code = cli.main(
                    [
                        "--input",
                        str(missing_input),
                        "--model-package",
                        str(model_package),
                        "--output-dir",
                        str(output_dir),
                        "--feature-month",
                        "2026-04",
                        "--no-map",
                    ]
                )

            self.assertNotEqual(0, exit_code)
            run_scope.assert_not_called()
            self.assertEqual([], list(output_dir.glob("*_predictions.csv")))
            summary = self._read_summary(output_dir)
            self.assertEqual("failed", summary["status"])
            self.assertEqual(str(missing_input), summary["input"]["path"])
            self.assertIsNone(summary["input"]["sha256"])
            self.assertIn("input CSV", summary["error"]["message"])
            self.assertEqual({}, summary["planned_outputs"])
            self.assertEqual({}, summary["written_outputs"])

    def test_script_path_help_from_repo_root_succeeds(self):
        script_path = Path("model_pipeline/run_operational_launch_inference.py")

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertIn("--feature-month", result.stdout)

    def test_commit_temp_outputs_rolls_back_old_and_new_outputs_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_path = root / "old.csv"
            new_path = root / "new.csv"
            old_path.write_text("old committed\n", encoding="utf-8")
            temp_old = root / ".old.tmp"
            temp_new = root / ".new.tmp"
            temp_old.write_text("new replacement\n", encoding="utf-8")
            temp_new.write_text("new primary\n", encoding="utf-8")
            calls = []
            real_replace = outputs.os.replace

            def fail_on_third_replace(src, dst):
                calls.append((Path(src).name, Path(dst).name))
                if len(calls) == 3:
                    raise OSError("simulated commit failure")
                real_replace(src, dst)

            with mock.patch.object(outputs.os, "replace", side_effect=fail_on_third_replace):
                with self.assertRaisesRegex(outputs.OutputError, "commit.*failed"):
                    outputs.commit_temp_outputs(
                        [
                            (temp_old, old_path),
                            (temp_new, new_path),
                        ]
                    )

            self.assertEqual("old committed\n", old_path.read_text(encoding="utf-8"))
            self.assertFalse(new_path.exists())
            self.assertEqual([], list(root.glob("*.backup-*")))

    def _write_input(self, path):
        pd.DataFrame(
            {
                "admin_code": ["001", "002"],
                "year": [2026, 2026],
                "month": [4, 4],
                "feature": [1.0, 2.0],
            }
        ).to_csv(path, index=False)
        return path

    def _read_summary(self, output_dir):
        with (output_dir / "run_summary.json").open("r", encoding="utf-8") as handle:
            return json.load(handle)


if __name__ == "__main__":
    unittest.main()
