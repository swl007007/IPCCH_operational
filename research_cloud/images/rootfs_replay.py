"""Replay packages inside a pulled image's filesystem in a bubblewrap sandbox (no container daemon on the workstation).

The image filesystem is a ``crane export`` of the image pulled by digest; the run is bound to that pull by the saved
manifest (its sha256 must equal the digest) and config (its sha256 must equal the manifest's config digest). Each
replay runs as::

    bwrap --unshare-all --uid 65534 --gid 65534 --tmpfs / (--ro-bind ROOT/X /X for each image entry) --proc /proc --dev /dev --tmpfs /tmp
          --tmpfs HOME --ro-bind PACKAGES /packages --bind OUT /out --chdir /out --clearenv --setenv (image Env) ...
          /usr/local/bin/python -m research_cloud.packages.replay /packages/NAME --report /out/NAME.json

i.e. the image's entries make up ``/`` (read-only), with the image's own interpreter, libraries, loader and baked
``/app/research_cloud``; the image's ``Env`` from its config (``PYTHONDONTWRITEBYTECODE=1`` included); runtime user
65534; no network, IPC or PID sharing; and only the packages (read-only) and the output directory bound in. Host
paths such as ``/mnt/c`` (Dropbox) and the native workspace do not exist inside. A probe in the same sandbox checks
it: module files under ``/usr/local`` and ``/app``, the mapped loader/libc are the image's, ``/mnt`` and the host
home are absent (the image's own ``/mnt`` is empty), ``/packages`` is not writable, and a network connection fails. The host kernel is shared (a
namespace sandbox, not a VM).

Package-to-image mapping is the frozen runtime coverage (cloud-deployment-plan / S44-S46), by the package's recorded
Linux runtime env: rt-geoxgb-x300 -> training-ipcch (28); rt-fews-x300, rt-popv1-x300 -> training-fews (29 + 24);
rt-ipcchgeo-x320, rt-alphaearth-x320 -> replay-x320 (70 + 16); rt-forecast-x320 -> replay-forecast-x320 (56).

  python -m research_cloud.images.rootfs_replay --rootfs DIR --image NAME --digest sha256:... --manifest FILE
      --config FILE --packages DIR --expect-packages N --out DIR
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

IMAGE_FOR_ENV = {"rt-geoxgb-x300": "training-ipcch", "rt-fews-x300": "training-fews", "rt-popv1-x300": "training-fews",
                 "rt-ipcchgeo-x320": "replay-x320", "rt-alphaearth-x320": "replay-x320",
                 "rt-forecast-x320": "replay-forecast-x320"}
PROBE = """
import json, os, socket, sys, numpy, pandas, xgboost, research_cloud
mapped = sorted({l.split()[-1] for l in open('/proc/self/maps') if 'ld-linux' in l or 'libc.so' in l or 'libpython' in l})
try:
    socket.create_connection(('8.8.8.8', 53), timeout=3); net = 'reachable'
except OSError as e:
    net = type(e).__name__
print(json.dumps({'executable': sys.executable, 'uid': os.getuid(), 'version': sys.version.split()[0],
    'numpy': [numpy.__version__, numpy.__file__], 'pandas': [pandas.__version__, pandas.__file__],
    'xgboost': [xgboost.__version__, xgboost.__file__], 'research_cloud': research_cloud.__file__, 'mapped': mapped,
    'host_mnt_c_exists': os.path.exists('/mnt/c'), 'mnt_entries': sorted(os.listdir('/mnt')) if os.path.isdir('/mnt') else [], 'host_home_exists': os.path.exists(HOST_HOME), 'network': net,
    'packages_writable': os.access('/packages', os.W_OK)}))
"""


def package_env(package_dir):
    runtime = json.load(open(os.path.join(package_dir, "package.json")))["runtime"]
    for key in ("linux", "linux_loader_tested"):
        if isinstance(runtime.get(key), dict) and runtime[key].get("env"):
            return runtime[key]["env"]
    raise SystemExit(f"{package_dir}: no recorded Linux runtime env")


def sandbox(root, config, packages, out):
    env = dict(e.split("=", 1) for e in config["config"].get("Env", []))
    home = env.get("HOME", "/tmp/home")
    # a tmpfs root holding the image's top-level entries read-only (directories and files bound, symlinks recreated),
    # so the mount points below need no change to the extracted image
    argv = ["bwrap", "--unshare-all", "--die-with-parent", "--uid", "65534", "--gid", "65534", "--tmpfs", "/"]
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.islink(path):
            argv += ["--symlink", os.readlink(path), f"/{name}"]
        elif name not in ("proc", "dev", "tmp"):
            argv += ["--ro-bind", path, f"/{name}"]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", home,
             "--ro-bind", packages, "/packages", "--bind", out, "/out", "--chdir", "/out", "--clearenv"]
    for k, v in sorted(env.items()):
        argv += ["--setenv", k, v]
    return argv


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rootfs", required=True)
    ap.add_argument("--image", required=True, choices=sorted(set(IMAGE_FOR_ENV.values())))
    ap.add_argument("--digest", required=True)
    ap.add_argument("--manifest", required=True, help="the manifest saved at pull time (crane manifest IMAGE@DIGEST)")
    ap.add_argument("--config", required=True, help="the image config saved at pull time (crane config)")
    ap.add_argument("--packages", required=True)
    ap.add_argument("--expect-packages", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    manifest_sha = "sha256:" + hashlib.sha256(open(args.manifest, "rb").read()).hexdigest()
    if manifest_sha != args.digest:
        raise SystemExit(f"manifest {manifest_sha} is not the image digest {args.digest}")
    manifest = json.load(open(args.manifest))
    config_bytes = open(args.config, "rb").read()
    if "sha256:" + hashlib.sha256(config_bytes).hexdigest() != manifest["config"]["digest"]:
        raise SystemExit("image config does not match the manifest's config digest")
    root, packages = os.path.realpath(args.rootfs), os.path.realpath(args.packages)
    os.makedirs(args.out, exist_ok=True)
    out = os.path.realpath(args.out)
    base = sandbox(root, json.loads(config_bytes), packages, out)
    python = "/usr/local/bin/python"
    probe = subprocess.run(base + [python, "-c", PROBE.replace("HOST_HOME", repr(os.path.expanduser("~")))],
                           capture_output=True, text=True, timeout=300)
    if probe.returncode != 0:
        raise SystemExit(f"probe failed: {probe.stderr[-2000:]}")
    info = json.loads(probe.stdout.strip().splitlines()[-1])
    problems = [k for k in ("numpy", "pandas", "xgboost") if not info[k][1].startswith("/usr/local/lib/python3.12/")]
    problems += [] if info["research_cloud"].startswith("/app/") else ["research_cloud"]
    problems += [] if info["mapped"] and all(m.startswith(("/usr/", "/lib/")) for m in info["mapped"]) else ["mapped"]
    problems += [k for k in ("host_mnt_c_exists", "mnt_entries", "host_home_exists", "packages_writable") if info[k]]
    problems += [] if info["network"] != "reachable" else ["network"]
    problems += [] if info["uid"] == 65534 else ["uid"]
    if problems:
        raise SystemExit(f"sandbox probe failed: {problems} {info}")
    names = sorted(n for n in os.listdir(packages)
                   if IMAGE_FOR_ENV.get(package_env(os.path.join(packages, n))) == args.image)
    if len(names) != args.expect_packages:
        raise SystemExit(f"coverage: {len(names)} packages map to {args.image}, expected {args.expect_packages}")
    summary = {"image": args.image, "digest": args.digest, "manifest_sha256": manifest_sha,
               "config_digest": manifest["config"]["digest"], "rootfs": root, "sandbox": base, "probe": info,
               "packages": len(names), "results": {}, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    for n in names:
        t0 = time.time()
        r = subprocess.run(base + [python, "-m", "research_cloud.packages.replay", f"/packages/{n}",
                                   "--report", f"/out/{n}.json"], capture_output=True, text=True, timeout=3600)
        rec = {"rc": r.returncode, "seconds": round(time.time() - t0, 1)}
        report = os.path.join(out, f"{n}.json")
        if os.path.exists(report):
            rep = json.load(open(report))
            rec.update({k: rep.get(k) for k in ("passed", "rows", "package_json_sha256", "runtime", "error") if k in rep})
        else:
            rec["stderr_tail"] = r.stderr[-600:]
        summary["results"][n] = rec
        print(json.dumps({"package": n, **{k: rec.get(k) for k in ("rc", "passed", "rows", "seconds")}}), flush=True)
    summary["passed"] = sum(1 for v in summary["results"].values() if v["rc"] == 0 and v.get("passed") is True)
    summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print(json.dumps({k: summary[k] for k in ("image", "digest", "packages", "passed")}))
    return 0 if summary["passed"] == summary["packages"] else 1


if __name__ == "__main__":
    sys.exit(main())
