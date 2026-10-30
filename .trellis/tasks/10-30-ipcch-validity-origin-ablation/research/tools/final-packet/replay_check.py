"""Bind a package replay receipt to the CURRENT harvested package (task 10-30; local only): the receipt must have passed
with no integrity problems, name exactly this package directory and carry the sha256 of its current package.json. Used by
run_final.sh (holdout ``package`` and ``gcs-only/annual-package`` of every horizon) and cleanup_annual_weights.py.

  python3 -B replay_check.py RECEIPT PACKAGE_DIR   # exit 0 only when bound and passed
"""
import hashlib, json, os, sys


def problems(receipt, package_dir):
    try:
        r = json.load(open(receipt))
        pj = os.path.join(package_dir, "package.json")
        cur = hashlib.sha256(open(pj, "rb").read()).hexdigest()
    except (OSError, ValueError) as e:
        return [f"{type(e).__name__}: {e}"]
    out = []
    if r.get("passed") is not True or r.get("integrity_problems"):
        out.append("replay did not pass cleanly")
    if os.path.realpath(r.get("package") or "") != os.path.realpath(package_dir):
        out.append(f"replay is of {r.get('package')}, not {package_dir}")
    if r.get("package_json_sha256") != cur:
        out.append("replay package.json sha256 differs from the current harvested package")
    return out


if __name__ == "__main__":
    p = problems(sys.argv[1], sys.argv[2])
    print(json.dumps({"receipt": sys.argv[1], "package": sys.argv[2], "problems": p}))
    sys.exit(1 if p else 0)
