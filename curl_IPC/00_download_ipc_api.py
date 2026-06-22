"""Download IPC data year-by-year and assemble combined files.

Run: pip install requests (requests is the only runtime dependency).
Set IPCINFO_API_KEY in the environment before running.
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

try:
    from urllib.parse import quote, quote_plus
except ImportError:
    from urllib import quote, quote_plus

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflow_config import get_value, load_config, resolve_path

BASE_URL = "https://api.ipcinfo.org"
DEFAULT_START_YEAR = 2017
DEFAULT_END_YEAR = 2026
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
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


def parse_year(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(
            "Invalid {0}: {1}. Expected integer year.".format(label, value)
        )


def load_runtime_settings() -> dict[str, Any]:
    config = load_config()
    api_key_env_var = get_value(config, "ipc_api", "api_key_env_var", "IPCINFO_API_KEY")
    api_key = os.environ.get(api_key_env_var)
    if not api_key:
        raise RuntimeError("Set {0} in the environment before running.".format(api_key_env_var))
    start_year = parse_year(
        get_value(config, "ipc_api", "start_year", str(DEFAULT_START_YEAR)),
        "ipc_api.start_year",
    )
    end_year = parse_year(
        get_value(config, "ipc_api", "end_year", str(DEFAULT_END_YEAR)),
        "ipc_api.end_year",
    )
    if start_year > end_year:
        raise RuntimeError(
            "ipc_api.start_year must be <= ipc_api.end_year: {0} > {1}".format(
                start_year, end_year
            )
        )
    return {
        "api_key": api_key,
        "start_year": start_year,
        "end_year": end_year,
        "output_dir": Path(
            resolve_path(config, "ipc_api", "output_folder", str(DEFAULT_OUTPUT_DIR))
        ),
        "retrieve_date": date.today().isoformat(),
    }


def safe_error_message(exc: Exception, settings: dict[str, Any]) -> str:
    message = str(exc)
    api_key = settings.get("api_key")
    if api_key:
        for key_variant in set(
            [api_key, quote(api_key, safe=""), quote_plus(api_key, safe="")]
        ):
            if key_variant:
                message = message.replace(key_variant, "<redacted>")
    return message


def fetch_year(endpoint: str, year: int, settings: dict[str, Any]) -> Any:
    cfg = ENDPOINTS[endpoint]
    url = BASE_URL + cfg["path"]
    params = {**cfg["params"], "key": settings["api_key"], "year": year}
    headers = {"accept": cfg["accept"]}

    last_err_message = ""
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
            last_err_message = safe_error_message(exc, settings)
            sleep_for = RETRY_BASE_SLEEP_SEC * attempt
            print(
                f"  [{endpoint} {year}] attempt {attempt}/{MAX_RETRIES} failed: "
                f"{last_err_message}. retrying in {sleep_for:.0f}s"
            )
            time.sleep(sleep_for)
    raise RuntimeError(
        f"giving up on {endpoint} year={year} after {MAX_RETRIES} attempts: "
        f"{last_err_message}"
    )


def per_year_path(endpoint: str, year: int, settings: dict[str, Any]) -> Path:
    cfg = ENDPOINTS[endpoint]
    return settings["output_dir"] / f"{endpoint}_{year}.{cfg['ext']}"


def save_per_year(data: Any, endpoint: str, year: int, settings: dict[str, Any]) -> Path:
    settings["output_dir"].mkdir(parents=True, exist_ok=True)
    path = per_year_path(endpoint, year, settings)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def download_all_years(endpoint: str, settings: dict[str, Any]) -> dict[int, Any]:
    yearly: dict[int, Any] = {}
    for year in range(settings["start_year"], settings["end_year"] + 1):
        print(f"[{endpoint}] fetching year={year}")
        data = fetch_year(endpoint, year, settings)
        save_per_year(data, endpoint, year, settings)
        yearly[year] = data
        time.sleep(REQUEST_DELAY_SEC)
    return yearly


def combine_yearly(endpoint: str, yearly: dict[int, Any], settings: dict[str, Any]) -> Path:
    cfg = ENDPOINTS[endpoint]
    metadata = {
        "endpoint": endpoint,
        "endpoint_path": cfg["path"],
        "retrieved_date": settings["retrieve_date"],
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

    settings["output_dir"].mkdir(parents=True, exist_ok=True)
    out_path = (
        settings["output_dir"]
        / f"{endpoint}_combined_{settings['retrieve_date']}.{cfg['ext']}"
    )
    out_path.write_text(json.dumps(combined, ensure_ascii=False), encoding="utf-8")
    return out_path


def run_endpoint(endpoint: str, settings: dict[str, Any]) -> Path:
    yearly = download_all_years(endpoint, settings)
    combined = combine_yearly(endpoint, yearly, settings)
    print(f"[{endpoint}] combined -> {combined}")
    return combined


def main() -> None:
    settings = load_runtime_settings()
    for endpoint in ("areas", "analyses"):
        run_endpoint(endpoint, settings)


if __name__ == "__main__":
    main()
