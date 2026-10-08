# Operator quickstart

Run commands from this directory. This is the monthly FEWSNET/IPCCH pipeline, including migration to your own Google Cloud project. Predictions target the selected month O, O+6 and O+12. September's independent manual handover is a separate entrypoint.

1. Install Python 3.12.3, Google Cloud CLI and the pinned Python dependencies in an isolated environment:

   ```bash
   python -m venv /private/operator-venv
   source /private/operator-venv/bin/activate
   python -m pip install --no-deps -r requirements.lock.txt
   python -m pip check
   ```

2. Copy `project.example.json` to `/private/project.json`. Fill every destination field. Follow [one-time setup](OPERATIONS.md#one-time-destination-setup) for buckets, image transfer, identities, APIs and deployment. Keep the config and its `work_dir` durable and outside this package.
3. Validate the local baseline, then upload it once:

   ```bash
   python pipeline.py init --config /private/project.json --baseline bootstrap
   python pipeline.py init --config /private/project.json --baseline bootstrap --execute
   ```

4. Preview the month's request, then repeat with `--execute`:

   ```bash
   python pipeline.py run --config /private/project.json      --month 2026-11 --cutoff 2026-11-08T00:00:00Z      --deadline 2026-11-09T00:00:00Z --run-id nov-2026-a      --acled keep --wfp keep
   ```

   Replace the example dates. `--cutoff` fixes the discovery vintage; `--deadline` is the preparation deadline and latest allowed local submission time. Allow several hours for provider extraction. It does not cancel a delivery job already submitted; delivery has its configured four-hour task timeout. Remote sensing is refreshed through the latest eligible published period. A selected origin does not imply every provider has already published that month's observations; gaps/staleness retain the accepted fill and disclosure behavior.

   Replace either source choice with `--acled refresh --acled-raw /private/acled.csv` or `--wfp refresh --wfp-raw /private/wfp.csv`. See [compatible raw formats](OPERATIONS.md#compatible-raw-formats). These choices are independent. Fixed variables and the initial history are reused.

5. The run command waits up to one hour by default. If it returns while preparation is running, repeat the **same complete command, dates and run ID with `--execute`** to finish submission. `status` alone never submits the delivery manifest. Track and download:

   ```bash
   python pipeline.py status --config /private/project.json --run-id nov-2026-a
   python pipeline.py download --config /private/project.json      --run-id nov-2026-a --output /private/november-delivery --execute
   ```

Only durable `succeeded` means delivery completed. Download verifies the release inventory without replaying the models. Failed attempts retain evidence and need a new run ID.

Use [model updates](OPERATIONS.md#replace-compatible-models) for already-trained replacements. The accepted October fallback is in `fallback/october_2026/`; it does not need another scoring/replay run. The several-GB `bootstrap/` is a **one-time migration baseline**, not data downloaded from providers every month.

This handover was checked locally with fake cloud services and relocated files. Destination deployment and live provider access remain operator actions.
