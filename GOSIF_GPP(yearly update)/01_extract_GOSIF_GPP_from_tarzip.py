import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask
from rasterio.merge import merge
import gzip
import shutil
import os

# set the working directory
os.chdir(r'C:\Users\WeilunShi\Dropbox (IFPRI)\monitoring-food-crises\Weilun_workspace\0.external_data\2016')

# list all files in the folder
files = os.listdir()
def extract_unique_polygons(input):
    # create a list of all the tif files
    for file in files:
        if file.endswith('.tif.gz'):
            tif_files = [file for file in files if file.endswith('.tif.gz')]


    # unzip the files
    for file in tif_files:
        with gzip.open(file, 'rb') as f_in:
            with open(file.replace('.gz', ''), 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out) 


extract_unique_polygons(files)



