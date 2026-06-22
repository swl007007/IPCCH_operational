import arcpy
import os
import pandas as pd
import sys
from arcpy.sa import *
from tqdm import tqdm

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, get_value, load_config, resolve_path, require_dir, require_file

# Check out the Spatial Analyst extension
arcpy.CheckOutExtension("Spatial")

# Set environment settings
arcpy.env.overwriteOutput = True

# Input parameters
config = load_config()
tif_folder = require_dir(resolve_path(config, "viirs", "mosaic_folder"), "VIIRS mosaic_folder")
shapefile = require_file(resolve_path(config, "paths", "polygon_input"), "paths polygon_input")
output_folder = ensure_dir(resolve_path(config, "viirs", "output_folder"))
id_field = get_value(config, "viirs", "zone_field", get_value(config, "identifiers", "arcpy_zone_field", "fid"))

# Create a list of all DMSP-OLS TIF files
tif_files = []
for f in os.listdir(tif_folder):
    if f.endswith('.tif') and f.startswith('nightlight_VIIRS'):
        tif_files.append(os.path.join(tif_folder, f))

print("Found {} DMSP-OLS nightlight files".format(len(tif_files)))
if not tif_files:
    raise RuntimeError("No VIIRS nightlight mosaic TIF files found in {}".format(tif_folder))

# Create dictionaries to store results
sum_results = {}
std_results = {}

# Process each TIF file with tqdm progress bar
for tif_file in tqdm(tif_files, desc="Processing TIF files", unit="file"):
    # Get month and year from filename
    filename = os.path.basename(tif_file)
    parts = filename.split("_")
    
    # Extract year and month from filename
    if len(parts) >= 4:
        year = parts[2]
        month = parts[3]
        if month.endswith("_mosaic.tif"):
            month = month.replace("_mosaic.tif", "")
        elif month.endswith(".tif"):
            month = month.replace(".tif", "")
        date_key = "{}_{}".format(year, month)
    else:
        date_key = filename.replace('.tif', '')
    
    print("\nProcessing {} ({})".format(filename, date_key))
    
    try:
        # Set up the output tables
        sum_table = os.path.join("in_memory", "sum_" + date_key)
        std_table = os.path.join("in_memory", "std_" + date_key)
        
        # Calculate zonal sum (this will skip NoData values automatically)
        arcpy.gp.ZonalStatisticsAsTable_sa(shapefile, id_field, tif_file, sum_table, "DATA", "SUM")
        
        # Calculate zonal standard deviation
        arcpy.gp.ZonalStatisticsAsTable_sa(shapefile, id_field, tif_file, std_table, "DATA", "STD")
        
        # Process sum results
        with arcpy.da.SearchCursor(sum_table, [id_field, "SUM"]) as cursor:
            for row in cursor:
                region_id = row[0]
                sum_value = row[1]
                
                if region_id not in sum_results:
                    sum_results[region_id] = {}
                
                sum_results[region_id][date_key] = sum_value
        
        # Process std results
        with arcpy.da.SearchCursor(std_table, [id_field, "STD"]) as cursor:
            for row in cursor:
                region_id = row[0]
                std_value = row[1]
                
                if region_id not in std_results:
                    std_results[region_id] = {}
                
                std_results[region_id][date_key] = std_value
        
        # Clean up
        arcpy.Delete_management(sum_table)
        arcpy.Delete_management(std_table)
        
    except Exception as e:
        print("Error processing {}: {}".format(filename, str(e)))

print("\nCreating final datasets...")

# Convert sum results to DataFrame
sum_df_rows = []
for region_id, values in tqdm(sum_results.items(), desc="Building Sum DataFrame", unit="region"):
    row = {'region_id': region_id}
    row.update(values)
    sum_df_rows.append(row)

sum_df = pd.DataFrame(sum_df_rows)

# Convert std results to DataFrame
std_df_rows = []
for region_id, values in tqdm(std_results.items(), desc="Building Std DataFrame", unit="region"):
    row = {'region_id': region_id}
    row.update(values)
    std_df_rows.append(row)

std_df = pd.DataFrame(std_df_rows)

# Save results to CSV
sum_output_csv = os.path.join(output_folder, "nightlight_sum_extraction_results.csv")
std_output_csv = os.path.join(output_folder, "nightlight_std_extraction_results.csv")

sum_df.to_csv(sum_output_csv, index=False)
std_df.to_csv(std_output_csv, index=False)

print("Extraction complete! Results saved to:")
print("- Sum values: " + sum_output_csv)
print("- Standard deviations: " + std_output_csv)

# Check in the Spatial Analyst extension
arcpy.CheckInExtension("Spatial")
