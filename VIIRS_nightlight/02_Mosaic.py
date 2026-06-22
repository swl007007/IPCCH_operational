import arcpy
import os
import re
from collections import defaultdict
from tqdm import tqdm

# Set workspace environment
workspace = r"C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Processed_Dataset\Nightlight_update"
arcpy.env.workspace = workspace

# Set overwrite output to True
arcpy.env.overwriteOutput = True

# Get a list of all nightlight TIF files in the workspace
tif_files = arcpy.ListRasters("nightlight_VIIRS_*", "TIF")
print("Found {} VIIRS nightlight files".format(len(tif_files)))

# Group files by year and month
monthly_groups = defaultdict(list)

# Regular expression to extract year and month from filename
pattern = re.compile(r"nightlight_VIIRS_(\d{4})_(\d{2})")

# Group files by year and month with progress bar
print("Grouping files by year and month...")
for tif in tqdm(tif_files, desc="Grouping files"):
    match = pattern.search(tif)
    if match:
        year, month = match.groups()
        key = "{}_{}".format(year, month)
        monthly_groups[key].append(tif)

print("Found {} monthly groups".format(len(monthly_groups)))

# Process each monthly group with overall progress bar
for year_month in tqdm(monthly_groups.keys(), desc="Processing monthly mosaics"):
    year, month = year_month.split('_')
    files = monthly_groups[year_month]
    
    print("\nProcessing files for {}-{} ({} files):".format(year, month, len(files)))
    
    # Skip if no files found for this month
    if not files:
        print("No files found for {}-{}".format(year, month))
        continue
    
    # Get information about the first TIF file to determine properties
    sample_raster = arcpy.Raster(files[0])
    band_count = sample_raster.bandCount
    
    print("Pixel type: {}".format(sample_raster.pixelType))
    print("Number of bands: {}".format(band_count))
    
    # Define output mosaic dataset name
    output_name = "nightlight_VIIRS_{}_{}_mosaic.tif".format(year, month)
    output_mosaic = os.path.join(workspace, output_name)
    
    print("Mosaicking {} files...".format(len(files)))
    
    # Create mosaic using the Mosaic To New Raster tool
    arcpy.MosaicToNewRaster_management(
        input_rasters=files,
        output_location=workspace,
        raster_dataset_name_with_extension=output_name,
        coordinate_system_for_the_raster="",  # Will use the input raster's coordinate system
        pixel_type="32_BIT_FLOAT",  # Convert F32 to proper ArcGIS format
        cellsize="",  # Will use the input raster's cell size
        number_of_bands=band_count,  # Use detected band count
        mosaic_method="BLEND",  # Visually appealing seamless mosaic
        mosaic_colormap_mode="FIRST"
    )
    
    print("Mosaic completed for {}-{}!".format(year, month))
    print("Output saved to: {}".format(output_mosaic))

print("\nAll monthly mosaics have been processed successfully.")