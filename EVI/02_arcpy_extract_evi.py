import arcpy
import fnmatch
import os
import pandas as pd
import sys
from arcpy.sa import *
from tqdm import tqdm

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, get_value, load_config, resolve_path, require_dir, require_file

# --- SCRIPT OVERVIEW ---
# This script extracts zonal statistics (both MEAN and Standard Deviation) for
# each polygon in a shapefile from a series of time-stamped EVI raster files.
# It improves efficiency by calculating all statistics in a single pass per raster.
# The results are saved into two separate CSV files: one for mean values and
# one for standard deviation values.

# --- DEBUGGING NOTES ---
# Original Issue: The script was likely failing with an "ERROR 010167: Could not open workspace"
#   because it was writing temporary tables to arcpy.env.scratchGDB.
# Solution:
#   1. In-Memory Workspace: All temporary tables are now created in the "in_memory"
#      workspace to avoid file path and permission issues.
#   2. Efficiency Improvement: Instead of calling ZonalStatisticsAsTable twice per file,
#      this version calls it only ONCE using the "ALL" statistics_type. This calculates
#      all possible statistics (MEAN, STD, MIN, MAX, etc.) in a single operation,
#      reducing processing time. The required MEAN and STD values are then read from
#      the resulting table.

try:
    # Check out the Spatial Analyst extension
    arcpy.CheckOutExtension("Spatial")

    # Set environment settings
    arcpy.env.overwriteOutput = True

    # Input parameters
    config = load_config()
    tif_folder = require_dir(resolve_path(config, "evi", "raw_raster_folder"), "EVI raw_raster_folder")
    shapefile = require_file(resolve_path(config, "paths", "polygon_input"), "paths polygon_input")
    output_folder = ensure_dir(resolve_path(config, "evi", "output_folder"))
    id_field = get_value(config, "evi", "zone_field", get_value(config, "identifiers", "ch_admin_code", "admin_code"))
    filename_pattern = get_value(config, "evi", "filename_pattern", "MOD13A3_*.tif")

    # Create a list of all TIF files to be processed
    print("Finding TIF files...")
    tif_files = [os.path.join(tif_folder, f) for f in os.listdir(tif_folder)
                 if f.endswith('.tif') and fnmatch.fnmatch(f, filename_pattern)]
    print("Found {} TIF files to process.".format(len(tif_files)))


    # Create dictionaries to store results for mean and standard deviation
    mean_results = {}
    std_results = {}

    # Process each TIF file with a tqdm progress bar
    for tif_file in tqdm(tif_files, desc="Processing TIF files", unit="file"):
        filename = os.path.basename(tif_file)
        # Extract year and month from a filename like "MOD13A3_2010_01.tif"
        try:
            parts = filename.replace('.tif', '').split("_")
            date_key = "{}_{}".format(parts[1], parts[2])
        except IndexError:
            # Fallback for unexpected filenames, skips the file
            print("\nWarning: Could not parse date from filename: {}. Skipping.".format(filename))
            continue

        # --- MODIFIED FOR STABILITY AND EFFICIENCY ---
        # Define a temporary table name for the in_memory workspace
        temp_table_name = "temp_zonal_" + date_key
        temp_table_path = "in_memory/" + temp_table_name

        # Calculate ALL zonal statistics in a single pass for efficiency
        # This creates a table with columns for MEAN, STD, MIN, MAX, etc.
        ZonalStatisticsAsTable(shapefile, id_field, tif_file, temp_table_path, "DATA", "ALL")

        # Convert the in-memory table to a NumPy array, requesting the ID, MEAN, and STD fields
        arr = arcpy.da.TableToNumPyArray(temp_table_path, [id_field, "MEAN", "STD"])

        # Add results to both dictionaries from the single array
        for row in arr:
            region_id, mean_value, std_value = row[0], row[1], row[2]

            # Initialize nested dictionary for the region if it's the first time we've seen it
            if region_id not in mean_results:
                mean_results[region_id] = {}
                std_results[region_id] = {}

            # Store the mean and std values for the current region and date
            mean_results[region_id][date_key] = mean_value
            std_results[region_id][date_key] = std_value
            
        # Clean up the in-memory table to free RAM
        arcpy.Delete_management(temp_table_path)


    print("\nCreating final datasets...")

    # --- Function to convert dictionary to sorted DataFrame ---
    def create_sorted_df(results_dict, progress_desc):
        """Converts a results dictionary to a pandas DataFrame and sorts columns chronologically."""
        df_rows = []
        for region_id, values in tqdm(results_dict.items(), desc=progress_desc, unit="region"):
            row = {'region_id': region_id}
            row.update(values)
            df_rows.append(row)
        
        df = pd.DataFrame(df_rows)
        
        # Sort date columns chronologically
        date_cols = [col for col in df.columns if col != 'region_id']
        date_cols.sort() # Sorts YYYY_MM format correctly
        df = df[['region_id'] + date_cols]
        return df

    # Create and sort DataFrames for both mean and std
    mean_df = create_sorted_df(mean_results, "Building Mean DataFrame")
    std_df = create_sorted_df(std_results, "Building Std DataFrame")

    # Save results to CSV files
    mean_output_csv = os.path.join(output_folder, "EVI_mean_extraction_results.csv")
    std_output_csv = os.path.join(output_folder, "EVI_std_extraction_results.csv")

    mean_df.to_csv(mean_output_csv, index=False, encoding='utf-8')
    std_df.to_csv(std_output_csv, index=False, encoding='utf-8')

    print("\nExtraction complete! Results saved to:")
    print("- Mean values: " + mean_output_csv)
    print("- Standard deviations: " + std_output_csv)

finally:
    # This block ensures that resources are cleaned up even if the script fails
    print("Checking in Spatial Analyst extension.")
    arcpy.CheckInExtension("Spatial")

    # Clean up the entire in_memory workspace
    print("Cleaning up in-memory workspace.")
    arcpy.Delete_management("in_memory")

