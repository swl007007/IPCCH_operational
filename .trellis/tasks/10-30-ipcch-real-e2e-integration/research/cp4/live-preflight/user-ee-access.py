import json,ee
from pathlib import Path
out={"credential_source":"existing earthengine persistent user credentials","compute_project":"feisty-flames-511718-d4","reads":{}}
try:
 ee.Initialize(project=out["compute_project"])
 ee.data.setDeadline(60000)
 ee.data.setMaxRetries(0)
 out["initialize"]="ok"
except Exception as exc:
 out["initialize_error"]=type(exc).__name__+": "+str(exc)
if out.get("initialize")=="ok":
 for name in ["IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G00","STAGE2A_PRCP_BASELINE_1991_2020_CHIRPS_M01"]:
  asset="projects/han-sandbox-505315/assets/"+name
  result={}
  for operation,fn in [("metadata",ee.data.getAsset),("acl",ee.data.getAssetAcl)]:
   try:
    value=fn(asset)
    result[operation]={k:v for k,v in value.items() if k in ("name","type","sizeBytes","owners","writers","readers","all_users_can_read")}
   except Exception as exc: result[operation+"_error"]=type(exc).__name__+": "+str(exc)
  out["reads"][name]=result
path=Path(__file__).with_name("user-ee-access.json")
path.write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out))
