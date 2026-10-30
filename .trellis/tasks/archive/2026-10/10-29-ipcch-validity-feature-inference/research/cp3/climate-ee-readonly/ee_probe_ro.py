"""Read-only getAsset probes of specific han-sandbox asset ids (metadata only)."""
import json, ee
ee.Initialize(project="food-crisis-modeling-enso")
R = "projects/han-sandbox-505315/assets/"
ids = [R + f"IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G{g:02d}" for g in (0, 24)]
ids += [R + f"STAGE2A_PRCP_BASELINE_1991_2020_{s}_M01" for s in ("CHIRPS", "PERSIANN", "ERA5LAND")]
ids += [R + f"STAGE2B_TEMP_BASELINE_1991_2020_{s}_M01" for s in ("CPC", "ERA5LAND")]
ids += [R + f"STAGE2D_SOIL_BASELINE_2001_2020_{s}_M01" for s in ("ERA5LAND", "GLDAS21")]
ids += [R + "S2E3_VI_BASE_ADMIN_2003_2020_TERRA_CMG_P01_V3", R + "S2E3_VI_CURRENT_ADMIN_TERRA_Y2026_CMG_V3",
        R + "S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2020_2026_V3", R + "S2C3_DROUGHT_ADMIN_ET0_FAO56_Y2020_2026_V3",
        R + "S2C3_ET0_PATCH32_Y2020_2026_V2"]
out = {}
for i in ids:
    try:
        a = ee.data.getAsset(i)
        out[i.split("/")[-1]] = {"ok": True, "type": a.get("type"), "updateTime": a.get("updateTime"), "sizeBytes": a.get("sizeBytes"),
                                 "properties_keys": sorted((a.get("properties") or {}).keys())[:20]}
    except Exception as e:
        out[i.split("/")[-1]] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
print(json.dumps(out, indent=1))
