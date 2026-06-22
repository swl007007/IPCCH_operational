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

# --- SCRIPT OVERVIEW ---
# This script automates the process of extracting mean raster values (e.g., Gross Primary Productivity)
# for each polygon in a shapefile over a series of time-stamped TIF files.
# It then compiles all the data into a single, wide-format CSV file where each
# row corresponds to a polygon and each column corresponds to a time period.

# --- DEBUGGING NOTES ---
# Original Error: arcgisscripting.ExecuteError: ERROR 010167: Could not open workspace %1.
# Cause: This error typically occurs when ArcPy cannot access the location for an output file.
#   In the original script, it was likely due to an issue with arcpy.env.scratchGDB, which can be
#   unreliable depending on the execution environment.
# Solution: The script has been modified to use the "in_memory" workspace for temporary data.
#   This is a more stable and efficient method, as it writes temporary tables to RAM,
#   avoiding file path conflicts and improving performance.

try:
    # Check out the Spatial Analyst extension
    arcpy.CheckOutExtension("Spatial")

    # Set environment settings
    arcpy.env.overwriteOutput = True

    # Input parameters
    config = load_config()
    tif_folder = require_dir(resolve_path(config, "gosif_gpp", "raw_raster_folder_sd"), "GOSIF SD raster folder")
    shapefile = require_file(resolve_path(config, "paths", "polygon_input"), "paths polygon_input")
    output_folder = ensure_dir(resolve_path(config, "gosif_gpp", "output_folder"))
    id_field = get_value(config, "gosif_gpp", "zone_field", get_value(config, "identifiers", "arcpy_zone_field", "fid"))

    # Create a list of all TIF files to be processed
    print("Finding TIF files...")
    tif_files = [os.path.join(tif_folder, f) for f in os.listdir(tif_folder)
                 if f.endswith('.tif') and "GOSIF_GPP" in f]
    print("Found {} TIF files to process.".format(len(tif_files)))

    # Create a dictionary to store results in the format: {region_id: {date: value, ...}}
    results = {}

    # Process each TIF file with a tqdm progress bar
    for tif_file in tqdm(tif_files, desc="Processing TIF files", unit="file"):
        # Extract month and year from the filename
        # Assumes the filename format is like "GOSIF_GPP_YYYY.MXX_Mean.tif"
        filename = os.path.basename(tif_file)
        year_month = filename.split("GOSIF_GPP_")[1].split("_SD")[0]

        # --- MODIFIED FOR STABILITY ---
        # Define a temporary table in the "in_memory" workspace.
        # This is more robust than using a path to a geodatabase on disk.
        # Note: Table names in memory cannot contain periods, so they are replaced.
        temp_table_name = "temp_zonal_" + year_month.replace('.', '_')
        temp_table_path = "in_memory/" + temp_table_name

        # Calculate zonal statistics, writing the output table to memory
        ZonalStatisticsAsTable(shapefile, id_field, tif_file, temp_table_path, "DATA", "MEAN")

        # Convert the in-memory table to a NumPy array to access the data
        # Fields requested: the polygon ID and the calculated MEAN value
        arr = arcpy.da.TableToNumPyArray(temp_table_path, [id_field, "MEAN"])

        # Add the results to our main results dictionary
        for row in arr:
            region_id = row[0]
            mean_value = row[1]

            # If the region isn't in our dictionary yet, add it
            if region_id not in results:
                results[region_id] = {}

            # Store the mean value for the current region and date
            results[region_id][year_month] = mean_value
        
        # Clean up the in-memory table to free RAM, important in long loops
        arcpy.Delete_management(temp_table_path)


    print("\nCreating final dataset...")

    # Convert the nested dictionary of results to a list of flat dictionaries
    df_rows = []
    for region_id, values in tqdm(results.items(), desc="Building DataFrame", unit="region"):
        row = {'region_id': region_id}
        row.update(values)
        df_rows.append(row)

    # Create a pandas DataFrame from the list of rows
    df = pd.DataFrame(df_rows)

    # --- ADDED FOR BETTER OUTPUT ---
    # Sort the date columns chronologically for a clean, ordered output file.
    # Get all column names except for the region identifier
    date_cols = [col for col in df.columns if col != 'region_id']
    # A simple string sort works here because the format is YYYY.MXX
    date_cols.sort()
    # Reorder the DataFrame to have the ID first, followed by sorted dates
    df = df[['region_id'] + date_cols]


    # Save the final DataFrame to a CSV file
    output_csv = os.path.join(output_folder, "GOSIF_GPP_extraction_results_SD.csv")
    df.to_csv(output_csv, index=False, encoding='utf-8')

    print("\nExtraction complete! Results saved to " + output_csv)

finally:
    # This block will run whether the script succeeds or fails
    print("Checking in Spatial Analyst extension.")
    arcpy.CheckInExtension("Spatial")

    # Clean up the entire in_memory workspace
    print("Cleaning up in-memory workspace.")
    arcpy.Delete_management("in_memory")

