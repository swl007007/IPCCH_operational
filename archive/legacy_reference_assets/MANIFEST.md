# Legacy Reference Asset Archive

These files were moved out of `polygons_and_identifier/` because their names
look like current IPCCH production references but their contract is legacy or
ambiguous. Keep them only for traceability.

| Archived file | Previous live path | Reason |
| --- | --- | --- |
| `polygons_and_identifier/IPC_scaffold_example.csv` | `polygons_and_identifier/IPC_scaffold_example.csv` | Example IPC scaffold, not the unified production IPCCH scaffold. |
| `polygons_and_identifier/geoidentifier_ipcch.csv` | `polygons_and_identifier/geoidentifier_ipcch.csv` | Partial lat/lon geometry reference; replaced by `Outcome/ipcch_unified/spatial/unique_area_id_lat_lon.csv` and `ipcch_admin_geometry.*`. |
| `polygons_and_identifier/gdf_ipc_ch_final.geojson` | `polygons_and_identifier/gdf_ipc_ch_final.geojson` | Combined IPC/CH geometry reference with unclear production contract; replaced by unified IPCCH shapefile. |
| `polygons_and_identifier/gdf_ipc_ch_final_country_count.csv` | `polygons_and_identifier/gdf_ipc_ch_final_country_count.csv` | Companion summary for archived `gdf_ipc_ch_final.geojson`. |

The active G-02 handover package is `Outcome/ipcch_unified/`.
