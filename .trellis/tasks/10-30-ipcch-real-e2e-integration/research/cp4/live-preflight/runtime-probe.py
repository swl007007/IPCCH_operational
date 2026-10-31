import json,google.auth,ee
from google.cloud import storage
result={"identity":"monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com","checks":{}}
def check(name,fn):
 try: result["checks"][name]={"ok":True,"result":fn()}
 except Exception as exc: result["checks"][name]={"ok":False,"error":type(exc).__name__+": "+str(exc)}
def initialize():
 credentials,_=google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform","https://www.googleapis.com/auth/earthengine"])
 ee.Initialize(credentials=credentials,project="feisty-flames-511718-d4")
 ee.data.setDeadline(60000)
 ee.data.setMaxRetries(0)
 return "initialized"
check("ee_initialize",initialize)
if result["checks"]["ee_initialize"]["ok"]:
 for name in ["IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G00","STAGE2A_PRCP_BASELINE_1991_2020_CHIRPS_M01"]:
  check(name,lambda name=name: {k:v for k,v in ee.data.getAsset("projects/han-sandbox-505315/assets/"+name).items() if k in ("name","type","sizeBytes","bands")})
client=storage.Client(project="feisty-flames-511718-d4")
permissions=["storage.objects.get","storage.objects.create","storage.objects.delete","storage.objects.list"]
for name in ["food-crisis-test-ipcch-data","food-crisis-test-ipcch-requests"]:
 check(name,lambda name=name: client.bucket(name).test_iam_permissions(permissions,timeout=30,retry=None))
def current():
 blob=client.bucket("food-crisis-test-ipcch-data").blob("monthly-staging/current.json")
 blob.reload(timeout=30,retry=None)
 return {"generation":str(blob.generation),"size":blob.size}
check("current_metadata",current)
print("IPCCH_RUNTIME_PREFLIGHT "+json.dumps(result,sort_keys=True),flush=True)
raise SystemExit(0 if all(v["ok"] for v in result["checks"].values()) else 2)
