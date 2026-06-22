"""Download IPC data year-by-year and assemble combined files.

Run: pip install requests (requests is the only runtime dependency).
Set IPCINFO_API_KEY in the environment before running.
"""

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

API_KEY = os.environ.get("IPCINFO_API_KEY")
if not API_KEY:
    raise RuntimeError("Set IPCINFO_API_KEY in the environment before running.")
BASE_URL = "https://api.ipcinfo.org"
START_YEAR = 2017
END_YEAR = 2026  # inclusive
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
RETRIEVE_DATE = date.today().isoformat()
REQUEST_DELAY_SEC = 1.0
MAX_RETRIES = 4
RETRY_BASE_SLEEP_SEC = 3.0
REQUEST_TIMEOUT_SEC = 180

ENDPOINTS: dict[str, dict[str, Any]] = {
    "areas": {
        "path": "/areas",
        "params": {"format": "geojson", "type": "A","period":"C"},
        "accept": "application/geo+json",
        "ext": "geojson",
    },
    "analyses": {
        "path": "/analyses",
        "params": {"type": "A"},
        "accept": "application/json",
        "ext": "json",
    },
}


def fetch_year(endpoint: str, year: int) -> Any:
    cfg = ENDPOINTS[endpoint]
    url = BASE_URL + cfg["path"]
    params = {**cfg["params"], "key": API_KEY, "year": year}
    headers = {"accept": cfg["accept"]}

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SEC
            )
            if resp.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(
                    f"transient {resp.status_code} from {endpoint} year={year}"
                )
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_err = exc
            sleep_for = RETRY_BASE_SLEEP_SEC * attempt
            print(
                f"  [{endpoint} {year}] attempt {attempt}/{MAX_RETRIES} failed: "
                f"{exc!s}. retrying in {sleep_for:.0f}s"
            )
            time.sleep(sleep_for)
    raise RuntimeError(
        f"giving up on {endpoint} year={year} after {MAX_RETRIES} attempts: {last_err}"
    )


def per_year_path(endpoint: str, year: int) -> Path:
    cfg = ENDPOINTS[endpoint]
    return OUTPUT_DIR / f"{endpoint}_{year}.{cfg['ext']}"


def save_per_year(data: Any, endpoint: str, year: int) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = per_year_path(endpoint, year)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def download_all_years(endpoint: str) -> dict[int, Any]:
    yearly: dict[int, Any] = {}
    for year in range(START_YEAR, END_YEAR + 1):
        print(f"[{endpoint}] fetching year={year}")
        data = fetch_year(endpoint, year)
        save_per_year(data, endpoint, year)
        yearly[year] = data
        time.sleep(REQUEST_DELAY_SEC)
    return yearly


def combine_yearly(endpoint: str, yearly: dict[int, Any]) -> Path:
    cfg = ENDPOINTS[endpoint]
    metadata = {
        "endpoint": endpoint,
        "endpoint_path": cfg["path"],
        "retrieved_date": RETRIEVE_DATE,
        "years": sorted(yearly.keys()),
        "type_filter": cfg["params"].get("type"),
    }

    sample = next(iter(yearly.values()))
    if isinstance(sample, dict) and sample.get("type") == "FeatureCollection":
        features: list[Any] = []
        for year, fc in yearly.items():
            for feat in fc.get("features", []) or []:
                if isinstance(feat, dict):
                    feat.setdefault("properties", {})
                    if isinstance(feat["properties"], dict):
                        feat["properties"].setdefault("source_year", year)
                features.append(feat)
        combined: Any = {
            "type": "FeatureCollection",
            "metadata": metadata,
            "features": features,
        }
    elif isinstance(sample, list):
        records: list[Any] = []
        for year, recs in yearly.items():
            for rec in recs or []:
                if isinstance(rec, dict):
                    rec.setdefault("source_year", year)
                records.append(rec)
        combined = {"metadata": metadata, "records": records}
    else:
        combined = {"metadata": metadata, "data": yearly}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{endpoint}_combined_{RETRIEVE_DATE}.{cfg['ext']}"
    out_path.write_text(json.dumps(combined, ensure_ascii=False), encoding="utf-8")
    return out_path


def run_endpoint(endpoint: str) -> Path:
    yearly = download_all_years(endpoint)
    combined = combine_yearly(endpoint, yearly)
    print(f"[{endpoint}] combined -> {combined}")
    return combined


def main() -> None:
    for endpoint in ("areas", "analyses"):
        run_endpoint(endpoint)


if __name__ == "__main__":
    main()
