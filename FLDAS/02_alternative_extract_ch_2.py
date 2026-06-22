import arcpy
import os
import pandas as pd
from arcpy.sa import *
from tqdm import tqdm
import multiprocessing
import time
import numpy as np
import gc  # Add garbage collection module

arcpy.env.outputCodePage = ""  # Disables code page conversion for output
arcpy.env.inputCodePage = ""   # Disables code page conversion for input

# Function to process a single TIF file (will be run in parallel)
def process_tif_file(args):
    tif_file, shapefile, id_field = args
    
    # Initialize results dictionaries for this file
    file_mean_results = {}
    file_std_results = {}
    
    # Get month and year from filename
    filename = os.path.basename(tif_file)
    parts = filename.split("_")
    if len(parts) >= 3:
        year = parts[1]
        month = parts[2]
        date_key = "{}_{}".format(year, month)
    else:
        date_key = filename.replace('.tif', '')
    
    print("\nProcessing {} ({})".format(filename, date_key))
    
    try:
        # Check out Spatial Analyst extension for this process
        arcpy.CheckOutExtension("Spatial")
        
        # Create a Raster object for the file
        raster_obj = arcpy.Raster(tif_file)
        band_count = raster_obj.bandCount
        print("Number of bands: {}".format(band_count))
        
        # Process each band separately
        for band_num in range(1, band_count + 1):
            band_key = date_key + "_B{}".format(band_num)
            print("  Processing band {}...".format(band_num))
            
            # Create unique names for this process
            process_id = os.getpid()
            band_layer_name = "band_layer_{}_{}".format(process_id, band_num)
            mean_table = "in_memory\\mean_{}_{}".format(process_id, band_num)
            std_table = "in_memory\\std_{}_{}".format(process_id, band_num)
            
            # Extract band using Make Raster Layer
            arcpy.MakeRasterLayer_management(tif_file, band_layer_name, "", "", band_num)
            
            # Calculate zonal statistics
            arcpy.gp.ZonalStatisticsAsTable_sa(shapefile, id_field, band_layer_name, mean_table, "DATA", "MEAN")
            arcpy.gp.ZonalStatisticsAsTable_sa(shapefile, id_field, band_layer_name, std_table, "DATA", "STD")
            
            # Process mean results
            mean_values = {}
            with arcpy.da.SearchCursor(mean_table, [id_field, "MEAN"]) as cursor:
                for row in cursor:
                    region_id = row[0]
                    mean_value = row[1]
                    mean_values[region_id] = mean_value
            
            # Process std results
            std_values = {}
            with arcpy.da.SearchCursor(std_table, [id_field, "STD"]) as cursor:
                for row in cursor:
                    region_id = row[0]
                    std_value = row[1]
                    std_values[region_id] = std_value
            
            # Add to file results
            for region_id, value in mean_values.items():
                if region_id not in file_mean_results:
                    file_mean_results[region_id] = {}
                file_mean_results[region_id][band_key] = value
                
            for region_id, value in std_values.items():
                if region_id not in file_std_results:
                    file_std_results[region_id] = {}
                file_std_results[region_id][band_key] = value
            
            # Clean up
            try:
                arcpy.Delete_management(mean_table)
                arcpy.Delete_management(std_table)
                arcpy.Delete_management(band_layer_name)
            except:
                pass
        
        # Check in Spatial Analyst extension
        arcpy.CheckInExtension("Spatial")
        
        return (file_mean_results, file_std_results)
        
    except Exception as e:
        print("Error processing {}: {}".format(filename, str(e)))
        # Check in Spatial Analyst extension even if error
        arcpy.CheckInExtension("Spatial")
        return ({}, {})

# Function to write dataframe in chunks
def save_dataframe_in_chunks(data_dict, output_file, chunk_size=500):
    """Save a large dictionary to CSV in chunks to avoid memory issues"""
    region_ids = list(data_dict.keys())
    total_regions = len(region_ids)
    
    # Discover all possible column names
    all_columns = set(['region_id'])
    for region_id, values in data_dict.items():
        all_columns.update(values.keys())
    
    # Convert to list and sort for consistent order
    columns = sorted(list(all_columns))
    
    # Write header
    with open(output_file, 'w') as f:
        f.write(','.join(columns) + '\n')
    
    # Process in chunks
    for chunk_start in range(0, total_regions, chunk_size):
        chunk_end = min(chunk_start + chunk_size, total_regions)
        current_regions = region_ids[chunk_start:chunk_end]
        
        rows = []
        for region_id in current_regions:
            row = {'region_id': region_id}
            row.update(data_dict[region_id])
            rows.append(row)
        
        # Create small dataframe for this chunk
        chunk_df = pd.DataFrame(rows)
        
        # Ensure all columns are present
        for col in columns:
            if col not in chunk_df.columns:
                chunk_df[col] = None
        
        # Reorder columns to match header
        chunk_df = chunk_df[columns]
        
        # Append to file
        chunk_df.to_csv(output_file, mode='a', header=False, index=False)
        
        # Clean up to free memory
        del chunk_df
        del rows
        gc.collect()
        
    print("Successfully saved data to {}".format(output_file))

# Main script
if __name__ == "__main__":
    # Check out the Spatial Analyst extension for the main process
    arcpy.CheckOutExtension("Spatial")
    
    # Set environment settings
    arcpy.env.overwriteOutput = True
    
    # Input parameters
    tif_folder = r"C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Processed_Dataset\FLDAS_Monthly\Part2"
    shapefile = r"C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\Outcome\ch_scaffold_fixed.shp"
    output_folder = r"C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\FEWSNET_predictors\output_ch"
    id_field = "fid"
    
    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Create a list of all TIF files
    tif_files = [os.path.join(tif_folder, f) for f in os.listdir(tif_folder) 
                 if f.endswith('_all_bands.tif') and "FLDAS" in f]
    
    print("Found {} FLDAS files to process".format(len(tif_files)))
    
    # Prepare arguments for multiprocessing
    args_list = [(tif_file, shapefile, id_field) for tif_file in tif_files]
    
    # Determine number of processes (use fewer than CPU count to avoid memory issues)
    num_cpus = multiprocessing.cpu_count()
    num_processes = max(1, min(num_cpus - 1, 8))  # Reduced from 8 to 4 to save memory
    print("Using {} parallel processes".format(num_processes))
    
    # Create a pool of worker processes
    pool = multiprocessing.Pool(processes=num_processes)
    
    # Process files in parallel and get results
    start_time = time.time()
    results = list(tqdm(pool.imap(process_tif_file, args_list), total=len(args_list), desc="Processing files"))
    pool.close()
    pool.join()
    
    # Combine results from all processes
    mean_results = {}
    std_results = {}
    
    for file_mean, file_std in results:
        # Merge file mean results
        for region_id, values in file_mean.items():
            if region_id not in mean_results:
                mean_results[region_id] = {}
            mean_results[region_id].update(values)
        
        # Merge file std results
        for region_id, values in file_std.items():
            if region_id not in std_results:
                std_results[region_id] = {}
            std_results[region_id].update(values)
    
    # Total processing time
    elapsed_time = time.time() - start_time
    print("\nParallel processing completed in {:.2f} minutes".format(elapsed_time / 60.0))
    
    print("\nCreating final datasets...")
    
    # Define output files
    mean_output_csv = os.path.join(output_folder, "FLDAS_mean_extraction_results_p2.csv")
    std_output_csv = os.path.join(output_folder, "FLDAS_std_extraction_results_p2.csv")
    
    # Save results to CSV in chunks to avoid memory issues
    print("Saving mean results to {}".format(mean_output_csv))
    save_dataframe_in_chunks(mean_results, mean_output_csv)
    
    print("Saving std results to {}".format(std_output_csv))
    save_dataframe_in_chunks(std_results, std_output_csv)
    
    print("Extraction complete! Results saved to:")
    print("- Mean values: " + mean_output_csv)
    print("- Standard deviations: " + std_output_csv)
    
    # Check in the Spatial Analyst extension for the main process
    arcpy.CheckInExtension("Spatial")