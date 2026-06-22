# Converted from FAO_price/00_add_FAO_ipcch_update.ipynb

from __future__ import print_function

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, load_config, resolve_path, require_file

CONFIG = load_config()
source_data_root = resolve_path(CONFIG, "paths", "source_data_root")
output_root = ensure_dir(resolve_path(CONFIG, 'tabular', 'tabular_output_root'))
fao_raw_file_1 = require_file(
    resolve_path(CONFIG, 'tabular', 'fao_raw_file_1'),
    'FAO raw input 1'
)
fao_raw_file_2 = require_file(
    resolve_path(CONFIG, 'tabular', 'fao_raw_file_2'),
    'FAO raw input 2'
)
fao_scaffold_file = require_file(
    resolve_path(CONFIG, 'tabular', 'fao_scaffold_file'),
    'FAO scaffold input'
)
fao_output_file = resolve_path(CONFIG, 'tabular', 'fao_output_file')
fao_legacy_output_file = resolve_path(CONFIG, 'tabular', 'fao_legacy_output_file')

# %%
import pandas as pd
import numpy as np
import os
import datetime
#set wd

# %%
#read excel
df_1 = pd.read_excel(fao_raw_file_1)
df_2 = pd.read_excel(fao_raw_file_2)

# %%
#select only date,lat,lon, 'percentageChangeWRTReferencePrice'
df_1 = df_1[['date','lat','long','percentageChangeWRTReferencePrice']]
df_2 = df_2[['date','lat','long','percentageChangeWRTReferencePrice']]
# concat df_1 and df_2
df_FAO = pd.concat([df_1, df_2], ignore_index=True, axis=0)
#convert date to datetime
df_FAO['date'] = pd.to_datetime(df_FAO['date'])

#extract year and month from date
df_FAO['year'] = df_FAO['date'].dt.year
df_FAO['month'] = df_FAO['date'].dt.month
#drop date
df_FAO = df_FAO.drop(columns=['date'])
# rename percentageChangeWRTReferencePrice to FAO_price
df_FAO = df_FAO.rename(columns={'percentageChangeWRTReferencePrice': 'FAO_price'})

# +100
df_FAO['FAO_price'] = df_FAO['FAO_price'] + 100
# rename long as lon
df_FAO = df_FAO.rename(columns={'long': 'lon'})
# aggregate lat, lon, year, month, use the mean of FAO_price(ignore NaN)
df_FAO = df_FAO.groupby(['lat', 'lon', 'year', 'month'], as_index=False).agg({'FAO_price': 'mean'})
# drop NaN in FAO_price
df_FAO = df_FAO.dropna(subset=['FAO_price'])
# keep 12 digit lat and lon, pad 0
df_FAO['lat'] = df_FAO['lat'].apply(lambda x: '{:.12f}'.format(x))
df_FAO['lon'] = df_FAO['lon'].apply(lambda x: '{:.12f}'.format(x))
# read scaffold
df_IPC = pd.read_csv(fao_scaffold_file)

# force year and month to int, force lat and lon to 12f
df_IPC['year'] = df_IPC['year'].astype(int)
df_IPC['month'] = df_IPC['month'].astype(int)
df_IPC['lat'] = df_IPC['lat'].apply(lambda x: '{:.12f}'.format(x))
df_IPC['lon'] = df_IPC['lon'].apply(lambda x: '{:.12f}'.format(x))
#drop duplicates in lat, lon, year, month
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'])
df_FAO =    df_FAO.drop_duplicates(subset=['lat', 'lon', 'year', 'month'])
# convert lat and lon in df_IPC and df_FAO to real number with 12f
df_IPC['lat'] = df_IPC['lat'].astype(float)
df_IPC['lon'] = df_IPC['lon'].astype(float)
df_FAO['lat'] = df_FAO['lat'].astype(float)
df_FAO['lon'] = df_FAO['lon'].astype(float)
import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
import itertools

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

def match_nearest_markets(df_IPC, df_FAO, max_distance=100):
    """
    For each observation in df_IPC, find the nearest market in df_FAO
    for the same year and month, and merge the relevant information.

    Parameters:
    -----------
    df_IPC : pandas DataFrame
        DataFrame containing IPC data with lat, lon, year, and month columns
    df_FAO : pandas DataFrame
        DataFrame containing FAO data with lat, lon, year, month, and FAO_price columns
    max_distance : float, optional (default=100)
        Maximum allowed distance in kilometers between IPC point and FAO market

    Returns:
    --------
    pandas DataFrame
        df_IPC with added columns for market_distance and FAO_price
    """
    # Get all unique year-month combinations from 2010/1 to 2024/12
    years = range(2025, 2027)
    months = range(1, 13)
    year_month_combinations = list(itertools.product(years, months))

    # Filter out future dates if needed
    current_year = pd.Timestamp.now().year
    current_month = pd.Timestamp.now().month
    year_month_combinations = [
        (year, month) for year, month in year_month_combinations
        if (year < current_year) or (year == current_year and month <= current_month)
    ]

    # Initialize list to store results
    all_results = []

    total_combinations = len(year_month_combinations)
    print(f"Processing {total_combinations} year-month combinations...")

    # Process each year-month combination
    for i, (year, month) in enumerate(year_month_combinations):
        print(f"Processing {year}/{month} ({i+1}/{total_combinations})...")

        # Filter both datasets for the current year and month
        ipc_filtered = df_IPC[(df_IPC['year'] == year) & (df_IPC['month'] == month)]
        fao_filtered = df_FAO[(df_FAO['year'] == year) & (df_FAO['month'] == month)]

        if len(ipc_filtered) == 0 or len(fao_filtered) == 0:
            print(f"No data for {year}/{month} - skipping")
            continue

        # Create empty columns for results
        ipc_filtered = ipc_filtered.copy()
        ipc_filtered['market_distance'] = np.nan
        ipc_filtered['FAO_price'] = np.nan

        # For each IPC observation, find the nearest FAO market
        for idx, ipc_row in ipc_filtered.iterrows():
            min_distance = float('inf')
            nearest_market = None

            for _, fao_row in fao_filtered.iterrows():
                distance = haversine_distance(
                    ipc_row['lat'], ipc_row['lon'],
                    fao_row['lat'], fao_row['lon']
                )

                if distance < min_distance:
                    min_distance = distance
                    nearest_market = fao_row

            # Only merge if distance is within threshold
            if min_distance <= max_distance:
                ipc_filtered.at[idx, 'market_distance'] = min_distance
                ipc_filtered.at[idx, 'FAO_price'] = nearest_market['FAO_price']

        # Add to results
        all_results.append(ipc_filtered)

    # Combine all results
    if all_results:
        final_result = pd.concat(all_results, ignore_index=True)
        return final_result
    else:
        print("No matching data found")
        return pd.DataFrame()

def main():
    # Load your datasets
    # Replace these with your actual file paths or data loading method

    # Optional: Preview data
    print("IPC data preview:")
    print(df_IPC.head())
    print("\nFAO data preview:")
    print(df_FAO.head())

    # Set maximum distance (in km) for matching
    max_distance = 500  # Adjust this based on your needs

    # Process the data
    result = match_nearest_markets(df_IPC, df_FAO, max_distance)

    # Save the result to the configured handover outputs.
    ensure_dir(os.path.dirname(fao_output_file))
    ensure_dir(os.path.dirname(fao_legacy_output_file))
    result.to_csv(fao_output_file, index=False)
    result.to_csv(fao_legacy_output_file, index=False)
    print(f"Processing complete. Result saved with {len(result)} rows.")
    print(f"Primary output: {fao_output_file}")
    print(f"Legacy alias: {fao_legacy_output_file}")

    # Summary of matches
    matched = result['market_distance'].notna().sum()
    total = len(result)
    match_rate = matched / total * 100 if total > 0 else 0
    print(f"Match rate: {matched}/{total} ({match_rate:.2f}%)")

if __name__ == "__main__":
    main()
