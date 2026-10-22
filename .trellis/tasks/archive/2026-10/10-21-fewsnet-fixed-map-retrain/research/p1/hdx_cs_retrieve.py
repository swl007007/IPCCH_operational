"""Freeze HDX-registered FEWS NET Current Situation resources for the 22 roster countries.

Dataset names are discovered from the public HDX CKAN catalog (organization `fewsnet`,
`*_current_situation_fewsnet_ipc_classification` whose registered CSV URL names the
country) and compared with the expected names below. For each country the registered CSV
and GeoJSON download URLs are followed and the raw bytes are written create-only with
retrieval timestamps, HTTP headers and SHA-256 hashes. A per-country receipt is written as
soon as that country finishes, and one failure never stops the remaining countries.
Short or interrupted streams are kept as `*.incomplete-<n>` files, recorded, and retried.
Content-Length counts encoded transfer bytes, so it is compared with the raw wire byte
count (urllib3 `tell()`), never with the decoded payload written to disk. Nothing is parsed or
altered here; content inspection is a separate step.

Usage: python hdx_cs_retrieve.py --out <staging>/hdx/<retrieval-id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

HDX_API = "https://data.humdata.org/api/3/action"
SEARCH_URL = (f"{HDX_API}/package_search?q=%22Current+Situation%22"
              "&fq=organization%3Afewsnet&rows=1000")
USER_AGENT = "ifpri-fewsnet-fixed-map-retrain/1.0 (public HDX read)"
SUFFIX = "_current_situation_fewsnet_ipc_classification"
# ISO2 -> expected HDX dataset name for the 22 FEWS production roster countries.
EXPECTED = {
    "AF": "afghanistan", "BF": "burkina_faso", "BI": "burundi",
    "CD": "congo__the_democratic_republic_of_the", "CM": "cameroon", "ET": "ethiopia",
    "GT": "guatemala", "HT": "haiti", "KE": "kenya", "MG": "madagascar", "ML": "mali",
    "MW": "malawi", "MZ": "mozambique", "NE": "niger", "NG": "nigeria", "SD": "sudan",
    "SO": "somalia", "SS": "south_sudan", "TD": "chad", "UG": "uganda", "YE": "yemen",
    "ZW": "zimbabwe",
}
FORMATS = {"CSV": "csv", "GeoJSON": "geojson"}
KEPT_HEADERS = ("content-type", "content-length", "content-encoding", "etag",
                "last-modified", "date", "content-disposition")
ATTEMPTS = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def download(session: requests.Session, url: str, dest: Path) -> dict[str, object]:
    """Stream `url` to `dest`; failed or short attempts are kept and recorded, then retried."""
    attempts: list[dict[str, object]] = []
    for attempt in range(1, ATTEMPTS + 1):
        started = utc_now()
        part = dest.with_name(f"{dest.name}.incomplete-{attempt}")
        digest, size, status, headers, final_url = hashlib.sha256(), 0, None, {}, None
        try:
            response = session.get(url, timeout=(30, 900), stream=True)
            status, final_url = response.status_code, response.url
            headers = {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers}
            response.raise_for_status()
            with part.open("xb") as handle:
                for chunk in response.iter_content(1 << 20):
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            wire = response.raw.tell()
            declared = headers.get("content-length")
            if declared is not None and int(declared) != wire:
                raise IOError(f"received {wire} transfer bytes, Content-Length {declared}")
            part.rename(dest)
            return {"requested_url": url, "final_url": final_url, "http_status": status,
                    "headers": headers, "retrieval_started_utc": started,
                    "retrieval_completed_utc": utc_now(), "local_file": dest.name,
                    "size_bytes": size, "transfer_bytes": wire,
                    "sha256": digest.hexdigest(), "complete": True,
                    "failed_attempts": attempts}
        except (requests.RequestException, IOError) as exc:
            attempts.append({"attempt": attempt, "started_utc": started, "http_status": status,
                             "error": f"{type(exc).__name__}: {exc}",
                             "kept_partial_file": part.name if part.exists() else None,
                             "partial_size_bytes": size,
                             "partial_sha256": digest.hexdigest() if size else None})
            if attempt < ATTEMPTS:
                time.sleep(5 * 2 ** (attempt - 1))
    return {"requested_url": url, "complete": False, "failed_attempts": attempts}


def discover(session: requests.Session, out: Path) -> tuple[dict[str, dict], dict]:
    """Map ISO2 -> catalog dataset by the country code in its registered CSV URL."""
    search = download(session, SEARCH_URL, out / "hdx_package_search.json")
    if not search["complete"]:
        return {}, search
    results = json.loads((out / "hdx_package_search.json").read_text("utf-8"))["result"]
    found: dict[str, list[dict]] = {}
    for dataset in results["results"]:
        if not dataset["name"].endswith(SUFFIX):
            continue
        for resource in dataset.get("resources", []):
            if resource.get("format") == "CSV":
                query = parse_qs(urlparse(resource["url"]).query)
                for iso2 in query.get("country", []):
                    found.setdefault(iso2, []).append(dataset)
    search["catalog_count"] = results["count"]
    search["catalog_results_read"] = len(results["results"])
    return {k: v[0] for k, v in found.items() if len(v) == 1}, search | {
        "ambiguous_countries": sorted(k for k, v in found.items() if len(v) > 1)}


def retrieve_country(session, iso2: str, dataset_name: str, country_dir: Path) -> dict:
    show_url = f"{HDX_API}/package_show?id={dataset_name}"
    show = download(session, show_url, country_dir / "hdx_package_show.json")
    entry: dict[str, object] = {"package_show": show, "resources": [], "errors": []}
    if not show["complete"]:
        entry["errors"].append("package_show download incomplete")
        return entry
    package = json.loads((country_dir / "hdx_package_show.json").read_text("utf-8"))
    if not package.get("success"):
        entry["errors"].append("package_show success=false")
        return entry
    dataset = package["result"]
    entry |= {
        "hdx_dataset_name": dataset["name"], "hdx_dataset_id": dataset["id"],
        "hdx_dataset_url": f"https://data.humdata.org/dataset/{dataset['name']}",
        "organization": dataset["organization"]["name"],
        "catalog_dataset_date": dataset.get("dataset_date"),
        "catalog_metadata_modified": dataset.get("metadata_modified"),
        "catalog_last_modified": dataset.get("last_modified"),
    }
    for resource in dataset["resources"]:
        fmt = resource.get("format")
        record = {"hdx_resource_id": resource["id"], "format": fmt, "name": resource.get("name"),
                  "registered_url": resource["url"],
                  "catalog_last_modified": resource.get("last_modified")}
        if fmt in FORMATS:
            record["download"] = download(
                session, resource["url"], country_dir / f"{resource['id']}.{FORMATS[fmt]}")
            if not record["download"]["complete"]:
                entry["errors"].append(f"{fmt} resource {resource['id']} incomplete")
        entry["resources"].append(record)
    if not any(r["format"] == "CSV" and r.get("download", {}).get("complete")
               for r in entry["resources"]):
        entry["errors"].append("no complete CSV resource")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    out: Path = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    receipt: dict[str, object] = {"retrieval_id": out.name, "started_utc": utc_now(),
                                  "hdx_api": HDX_API, "countries": {}}
    discovered, receipt["catalog_search"] = discover(session, out)
    for iso2, stem in EXPECTED.items():
        expected = stem + SUFFIX
        catalog = discovered.get(iso2)
        name = catalog["name"] if catalog else expected
        country_dir = out / iso2
        country_dir.mkdir()
        try:
            entry = retrieve_country(session, iso2, name, country_dir)
        except Exception as exc:  # keep going; the failure itself is evidence
            entry = {"errors": [f"{type(exc).__name__}: {exc}"],
                     "traceback": traceback.format_exc()}
        entry |= {"expected_dataset_name": expected,
                  "catalog_dataset_name": catalog["name"] if catalog else None,
                  "name_matches_catalog": bool(catalog) and catalog["name"] == expected,
                  "status": "complete" if not entry["errors"] else "failed"}
        write_json(country_dir / "country_receipt.json", entry)
        receipt["countries"][iso2] = entry
        print(iso2, entry["status"], entry["errors"], flush=True)
    receipt["completed_utc"] = utc_now()
    receipt["failed_countries"] = sorted(k for k, v in receipt["countries"].items()
                                         if v["status"] != "complete")
    write_json(out / "retrieval_receipt.json", receipt)


if __name__ == "__main__":
    main()
