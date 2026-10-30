import json, ee
ee.Initialize(project="food-crisis-modeling-enso")
out = {}
for i in ("UCSB-CHC/CHIRPS/V3/DAILY_RNL", "NOAA/PERSIANN-CDR", "ECMWF/ERA5_LAND/DAILY_AGGR", "NOAA/CPC/Temperature",
          "NASA/GLDAS/V021/NOAH/G025/T3H", "MODIS/061/MOD13A3"):
    try:
        a = ee.data.getAsset(i); out[i] = {"ok": True, "type": a.get("type"), "endTime": a.get("endTime")}
    except Exception as e:
        out[i] = {"ok": False, "error": str(e)[:160]}
print(json.dumps(out, indent=1))
