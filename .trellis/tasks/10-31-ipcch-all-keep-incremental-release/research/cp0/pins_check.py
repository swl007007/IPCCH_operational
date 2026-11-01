"""Task 10-31 CP0: READ-ONLY pins. Live generation + streamed sha256 of the shared v2 objects named by the normal config,
and local rehash of the prepared ACLED input and selections (must equal the PRD pins)."""
import hashlib, json, sys
from google.cloud import storage
cfg = json.load(open("/home/swl007007/ipcch-operator/food-crisis-test/project.json"))["v2"]
c = storage.Client(); out = {"shared": {}, "local": {}}
for key in ("envelope", "environment_manifest"):
    uri = cfg[key]; b, _, n = uri.removeprefix("gs://").partition("/"); blob = c.bucket(b).get_blob(n)
    out["shared"][key] = {"uri": uri, "generation": str(blob.generation), "size": blob.size,
                          "sha256": hashlib.sha256(blob.download_as_bytes(if_generation_match=blob.generation)).hexdigest()}
uri = cfg["country_reference"]["real"]; b, _, n = uri.removeprefix("gs://").partition("/"); blob = c.bucket(b).get_blob(n)
out["shared"]["country_reference_real"] = {"uri": uri, "generation": str(blob.generation), "size": blob.size,
    "sha256": hashlib.sha256(blob.download_as_bytes(if_generation_match=blob.generation)).hexdigest()}
P = "/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/incremental-20261101/prepared/"
for f in ("selections.json", "acled_regional_aggregate_20261017_20261023.csv"):
    out["local"][f] = hashlib.sha256(open(P + f, "rb").read()).hexdigest()
expect = {"envelope": "03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596",
          "environment_manifest": "2f0a7251e0436d900ddb91d0a783421b205094ffdb26ba52ccbdfb7f9bb31e3d",
          "country_reference_real": "0823e418f0fe361db00b701f5737033ee860159e9d21ca2f6167cfe2d54e2f0b",
          "selections.json": "7ab733d8c0e22bc866ae0ddb8cdfce63b3c5621e749b6ec2316f8fdaf58af4a7",
          "acled_regional_aggregate_20261017_20261023.csv": "e660c7e8eb126c102145069441805bf55314914cb6297601bd5a150a87e47e8a"}
out["match"] = {k: (out["shared"].get(k) or {}).get("sha256", out["local"].get(k)) == v for k, v in expect.items()}
json.dump(out, open(sys.argv[1], "x"), indent=1, sort_keys=True); print(json.dumps(out, indent=1))
