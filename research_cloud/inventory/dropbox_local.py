"""Classify DrvFS paths as locally available or cloud-only Dropbox placeholders.

Reading an online-only placeholder makes Dropbox download it, so callers must
check here before opening a file under /mnt/c. Attributes are read in one
PowerShell call per batch; nothing is opened.

Statuses: ``local``, ``cloud_only``, ``missing`` (PowerShell reported
ItemNotFound) or ``inspection_error`` (any other per-path failure). A failed
or malformed batch raises InspectionError; it is never reported as missing.

Usage: python3 dropbox_local.py PATH...   (or paths on stdin) -> JSON lines
Exit status 2 if any path is ``inspection_error`` or the batch failed.
"""
import json
import subprocess
import sys

OFFLINE = 0x1000
RECALL_ON_OPEN = 0x40000
RECALL_ON_DATA_ACCESS = 0x400000
NOT_LOCAL = OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS

ROW = (
    "try{$i=Get-Item -LiteralPath '%s' -Force -ErrorAction Stop; "
    "'R|%d|ok|'+[int64]$i.Attributes+'|'+$i.Length}"
    "catch [System.Management.Automation.ItemNotFoundException]{'R|%d|missing||'}"
    "catch{'R|%d|error||'+($_.Exception.GetType().FullName)}\n"
)


class InspectionError(RuntimeError):
    pass


def to_windows(path):
    if not path.startswith("/mnt/") or len(path) < 7 or path[6] != "/":
        raise ValueError(f"not a DrvFS path: {path}")
    return path[5].upper() + ":\\" + path[7:].replace("/", "\\")


def run_powershell(script):
    """Run via a UTF-8 (BOM) .ps1 in Windows %TEMP%: no command-line length limit, no codepage loss."""
    import os
    import tempfile
    temp_dir = "/mnt/c/Users/swl00/AppData/Local/Temp"
    fd, path = tempfile.mkstemp(prefix="dropbox_local_", suffix=".ps1", dir=temp_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(b"\xef\xbb\xbf" + script.encode("utf-8"))
        return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", to_windows(path)], capture_output=True, timeout=1800, cwd="/mnt/c")
    finally:
        os.unlink(path)


def parse_rows(stdout, count):
    """Return one parsed row per index 0..count-1, or raise on any gap/duplicate/garbage."""
    rows = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("R|"):
            continue
        parts = line.split("|", 4)
        if len(parts) != 5 or not parts[1].isdigit():
            raise InspectionError(f"malformed row: {line!r}")
        index = int(parts[1])
        if index >= count or index in rows:
            raise InspectionError(f"unexpected or duplicate row index {index}")
        rows[index] = parts[2:]
    if len(rows) != count:
        raise InspectionError(f"expected {count} rows, got {len(rows)}")
    return rows


def classify(paths, batch=400, runner=run_powershell):
    out = []
    for start in range(0, len(paths), batch):
        chunk = paths[start:start + batch]
        script = "$ErrorActionPreference='Stop'\n" + "".join(
            ROW % (to_windows(p).replace("'", "''"), n, n, n) for n, p in enumerate(chunk))
        res = runner(script)
        if res.returncode != 0:
            raise InspectionError(f"powershell exit {res.returncode}: "
                                  f"{res.stderr.decode('utf-8', 'replace')[:500]}")
        rows = parse_rows(res.stdout.decode("utf-8", "replace"), len(chunk))
        for n, path in enumerate(chunk):
            state, attr, detail = rows[n]
            if state == "missing":
                out.append({"path": path, "status": "missing"})
            elif state == "error":
                out.append({"path": path, "status": "inspection_error", "error": detail})
            elif state == "ok" and attr.isdigit():
                out.append({"path": path, "status": "cloud_only" if int(attr) & NOT_LOCAL else "local",
                            "attributes": int(attr), "bytes": int(detail) if detail.isdigit() else None})
            else:
                raise InspectionError(f"unparseable row for index {n}: {rows[n]!r}")
    return out


if __name__ == "__main__":
    items = sys.argv[1:] or [l.rstrip("\n") for l in sys.stdin if l.strip()]
    try:
        records = classify(items)
    except InspectionError as exc:
        print(json.dumps({"status": "batch_inspection_error", "error": str(exc)}))
        sys.exit(2)
    for rec in records:
        print(json.dumps(rec))
    sys.exit(2 if any(r["status"] == "inspection_error" for r in records) else 0)
