# Converted from ACLED/00_add_ACLED_IPCCH.ipynb

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
acled_raw_file = require_file(
    resolve_path(CONFIG, 'tabular', 'acled_raw_file'),
    'ACLED raw input'
)
acled_scaffold_file = require_file(
    resolve_path(CONFIG, 'tabular', 'acled_scaffold_file'),
    'ACLED scaffold input'
)
acled_output_file = resolve_path(CONFIG, 'tabular', 'acled_output_file')

# %%
import pandas as pd
import numpy as np
import os
import datetime
#set wd


#read csv data
df_ACLED = pd.read_csv(acled_raw_file)
# keep there variables
var = ['event_date','event_type',
'year', 'country',
'admin1',
'admin2',
'admin3',
'location',
'latitude',
'longitude', 'fatalities']

# filter the data
df_ACLED = df_ACLED[var]
# convert event_date to datetime
df_ACLED['event_date'] = pd.to_datetime(df_ACLED['event_date'])
#drop year
df_ACLED = df_ACLED.drop(columns=['year'])
# extract month year from event_date
df_ACLED['month'] = df_ACLED['event_date'].dt.month
df_ACLED['year'] = df_ACLED['event_date'].dt.year
#drop event_date
df_ACLED = df_ACLED.drop(columns=['event_date'])
# for each event_type,country,admin1,admin2,admin3,location,latitude,longitude,year,month, sum fatalities and count the number of events
key_columns = [
        'event_type', 'country', 'admin1', 'admin2', 'admin3',
        'location', 'latitude', 'longitude', 'month', 'year'
    ]

    # Group by the key columns and aggregate
aggregated_df = df_ACLED.groupby(key_columns).agg(
    event_count=('event_type', 'count'),  # Count occurrences
    sum_fatalities=('fatalities', 'sum')  # Sum fatalities
).reset_index()

#replace Explosions/Remote violence as explosions,replace Battles as battles, replace Violence against civilians as violence
aggregated_df['event_type'] = aggregated_df['event_type'].replace({
    'Explosions/Remote violence': 'explosions',
    'Battles': 'battles',
    'Violence against civilians': 'violence'
})

# now cast into wide format on event_type
# pivot the dataframe
pivot_df = aggregated_df.pivot_table(
    index=['country', 'admin1', 'admin2', 'admin3', 'location', 'latitude', 'longitude', 'year', 'month'],
    columns='event_type',
    values=['event_count', 'sum_fatalities'],
    fill_value=0
)
# flatten the multi-level columns
pivot_df.columns = ['_'.join(col).strip() for col in pivot_df.columns.values]
# reset index to convert multi-index to columns
pivot_df.reset_index(inplace=True)

#does latitude, longitude, year and month uniquely combined
# check if latitude, longitude, year and month uniquely combined
#drop any duplicates in latitude, longitude, year and month
pivot_df = pivot_df.drop_duplicates(subset=['latitude', 'longitude', 'year', 'month','country','admin1','admin2','admin3','location'])
#rename latitude as lat, longitude as lon
pivot_df = pivot_df.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
# read scaffold
df_IPC = pd.read_csv(acled_scaffold_file)
#force year and month to be int
df_IPC['year'] = df_IPC['year'].astype(int)
df_IPC['month'] = df_IPC['month'].astype(int)
df_ACLED = pivot_df
df_ACLED
#drop duplicates of year month, lat lon in df_IPC
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'])
# df_ACLED sum at adm3 level, sum up the fatalities and event count
df_ACLED_adm3 = df_ACLED.groupby(['country', 'admin1', 'admin2', 'admin3','year', 'month']).agg(
    event_count_battles=('event_count_battles', 'sum'),
    event_count_explosions=('event_count_explosions', 'sum'),
    event_count_violence=('event_count_violence', 'sum'),
    sum_fatalities_battles=('sum_fatalities_battles', 'sum'),
    sum_fatalities_explosions=('sum_fatalities_explosions', 'sum'),
    sum_fatalities_violence=('sum_fatalities_violence', 'sum'),
    lat = ('lat', 'mean'),
    lon = ('lon', 'mean')
).reset_index()
df_ACLED_adm2 = df_ACLED.groupby(['country', 'admin1', 'admin2','year', 'month']).agg(
    event_count_battles_w5=('event_count_battles', 'sum'),
    event_count_explosions_w5=('event_count_explosions', 'sum'),
    event_count_violence_w5=('event_count_violence', 'sum'),
    sum_fatalities_battles_w5=('sum_fatalities_battles', 'sum'),
    sum_fatalities_explosions_w5=('sum_fatalities_explosions', 'sum'),
    sum_fatalities_violence_w5=('sum_fatalities_violence', 'sum'),
).reset_index()
df_ACLED_adm1 = df_ACLED.groupby(['country', 'admin1','year', 'month']).agg(
    event_count_battles_w10=('event_count_battles', 'sum'),
    event_count_explosions_w10=('event_count_explosions', 'sum'),
    event_count_violence_w10=('event_count_violence', 'sum'),
    sum_fatalities_battles_w10=('sum_fatalities_battles', 'sum'),
    sum_fatalities_explosions_w10=('sum_fatalities_explosions', 'sum'),
    sum_fatalities_violence_w10=('sum_fatalities_violence', 'sum'),
).reset_index()
# merge df_ACLED_adm3 and df_ACLED_adm2 on country, admin1, admin2, year, month
df_ACLED_adm = pd.merge(df_ACLED_adm3, df_ACLED_adm2, on=['country', 'admin1', 'admin2', 'year', 'month'], how='left')

# merge df_ACLED_adm and df_ACLED_adm1 on country, admin1, year, month
df_ACLED_adm = pd.merge(df_ACLED_adm, df_ACLED_adm1, on=['country', 'admin1', 'year', 'month'], how='left')
#drop country,admin1, admin2,admin3
df_ACLED_adm = df_ACLED_adm.drop(columns=['country', 'admin1', 'admin2','admin3'])

# %%
import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
import itertools
from tqdm import tqdm
import multiprocessing
from functools import partial

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

def create_location_index(df):
    """
    Create a simple spatial index for faster nearest neighbor queries

    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame containing lat and lon columns

    Returns:
    --------
    tuple
        (numpy array of lats, numpy array of lons, array of indices)
    """
    return (df['lat'].values, df['lon'].values, np.arange(len(df)))

def find_nearest_location(target_lat, target_lon, lats, lons, indices, max_distance=500):
    """
    Find the nearest location to the target coordinates

    Parameters:
    -----------
    target_lat, target_lon : float
        Target coordinates
    lats, lons : numpy arrays
        Arrays of latitudes and longitudes
    indices : numpy array
        Array of indices corresponding to the original DataFrame
    max_distance : float
        Maximum allowed distance in kilometers

    Returns:
    --------
    tuple
        (index of nearest point, distance to nearest point) or (None, None) if no point within max_distance
    """
    min_dist = float('inf')
    nearest_idx = None

    for i, (lat, lon) in enumerate(zip(lats, lons)):
        dist = haversine_distance(target_lat, target_lon, lat, lon)
        if dist < min_dist:
            min_dist = dist
            nearest_idx = indices[i]

    if min_dist <= max_distance:
        return nearest_idx, min_dist
    else:
        return None, None

def process_year_month(year, month, df_IPC, df_ACLED_adm, max_distance=500):
    """
    Process a single year-month combination

    Parameters:
    -----------
    year, month : int
        Year and month to process
    df_IPC, df_ACLED_adm : pandas DataFrame
        Full IPC and ACLED datasets
    max_distance : float
        Maximum allowed distance in kilometers

    Returns:
    --------
    pandas DataFrame
        Merged data for this year-month
    """
    # Filter data for current year-month
    ipc_subset = df_IPC[(df_IPC['year'] == year) & (df_IPC['month'] == month)]
    acled_subset = df_ACLED_adm[(df_ACLED_adm['year'] == year) & (df_ACLED_adm['month'] == month)]

    if len(ipc_subset) == 0 or len(acled_subset) == 0:
        # Return IPC subset with NaN values for ACLED metrics
        result = ipc_subset.copy()
        acled_columns = df_ACLED_adm.columns.drop(['year', 'month', 'lat', 'lon'], errors='ignore')
        for col in acled_columns:
            if col not in result.columns:
                result[col] = np.nan
        return result

    # Create spatial index for ACLED points
    acled_lats, acled_lons, acled_indices = create_location_index(acled_subset)

    # Create list to store results
    results = []

    # Process each IPC point
    for _, ipc_row in ipc_subset.iterrows():
        # Find nearest ACLED point
        nearest_idx, nearest_dist = find_nearest_location(
            ipc_row['lat'], ipc_row['lon'],
            acled_lats, acled_lons, acled_indices,
            max_distance
        )

        # Create result row with IPC data
        result_row = ipc_row.copy()

        # Add ACLED metrics if nearest point found
        if nearest_idx is not None:
            nearest_acled = acled_subset.iloc[nearest_idx]
            result_row['distance_to_nearest_acled'] = nearest_dist

            # Add ACLED metrics
            for col in acled_subset.columns:
                if col not in ['year', 'month', 'lat', 'lon']:
                    result_row[col] = nearest_acled[col]
        else:
            # No ACLED point within max distance
            result_row['distance_to_nearest_acled'] = np.nan
            for col in acled_subset.columns:
                if col not in ['year', 'month', 'lat', 'lon']:
                    result_row[col] = np.nan

        results.append(result_row)

    # Combine all results
    if results:
        return pd.DataFrame(results)
    else:
        return pd.DataFrame()

def process_year_month_wrapper(args):
    """Wrapper function for multiprocessing"""
    return process_year_month(*args)

def merge_ipc_with_acled(df_IPC, df_ACLED_adm, max_distance=500, n_processes=None):
    """
    Merge IPC data with ACLED data for all year-month combinations

    Parameters:
    -----------
    df_IPC : pandas DataFrame
        IPC data with lat, lon, year, month
    df_ACLED_adm : pandas DataFrame
        Pre-calculated ACLED metrics with lat, lon, year, month
    max_distance : float
        Maximum allowed distance in kilometers
    n_processes : int or None
        Number of processes to use (None = use all available cores)

    Returns:
    --------
    pandas DataFrame
        Merged data with ACLED metrics
    """
    # Get all unique year-month combinations that exist in both datasets
    ipc_year_months = set(zip(df_IPC['year'], df_IPC['month']))
    acled_year_months = set(zip(df_ACLED_adm['year'], df_ACLED_adm['month']))
    year_month_combinations = sorted(list(ipc_year_months.union(acled_year_months)))

    print(f"Processing {len(year_month_combinations)} year-month combinations...")

    # Determine number of processes to use
    if n_processes is None:
        n_processes = max(1, multiprocessing.cpu_count() - 1)

    # Prepare arguments for each year-month combination
    process_args = [
        (year, month, df_IPC, df_ACLED_adm, max_distance)
        for year, month in year_month_combinations
    ]

    # Process in parallel
    print(f"Using {n_processes} processes...")

    all_results = []

    with multiprocessing.Pool(processes=n_processes) as pool:
        # Process year-month combinations in parallel with progress bar
        for result in tqdm(
            pool.imap(process_year_month_wrapper, process_args),
            total=len(year_month_combinations),
            desc="Processing year-months"
        ):
            if len(result) > 0:
                all_results.append(result)

    # Combine all results
    if not all_results:
        print("No matching data found")
        return pd.DataFrame()

    final_result = pd.concat(all_results, ignore_index=True)

    # Calculate match statistics
    match_count = final_result['distance_to_nearest_acled'].notna().sum()
    total_count = len(final_result)
    match_rate = match_count / total_count * 100 if total_count > 0 else 0

    print(f"Match rate: {match_count}/{total_count} ({match_rate:.2f}%)")

    return final_result

def merge_ipc_with_acled_optimized(df_IPC, df_ACLED_adm, max_distance=500):
    """
    Optimized version that pre-groups the data by year and month

    Parameters:
    -----------
    df_IPC : pandas DataFrame
        IPC data with lat, lon, year, month
    df_ACLED_adm : pandas DataFrame
        Pre-calculated ACLED metrics with lat, lon, year, month
    max_distance : float
        Maximum allowed distance in kilometers

    Returns:
    --------
    pandas DataFrame
        Merged data with ACLED metrics
    """
    # Get all unique year-month combinations
    year_month_combinations = sorted(set([
        (year, month)
        for year, month in zip(df_IPC['year'], df_IPC['month'])
    ]))

    print(f"Processing {len(year_month_combinations)} year-month combinations...")

    # Group ACLED data by year and month for faster access
    acled_grouped = df_ACLED_adm.groupby(['year', 'month'])

    # Get all ACLED columns except the identifiers
    acled_columns = [col for col in df_ACLED_adm.columns
                    if col not in ['year', 'month', 'lat', 'lon']]

    # Initialize an empty DataFrame to store results
    results = []

    # Process each year-month combination
    for year, month in tqdm(year_month_combinations, desc="Processing year-months"):
        # Get IPC data for this year-month
        ipc_data = df_IPC[(df_IPC['year'] == year) & (df_IPC['month'] == month)].copy()

        # Skip if no IPC data for this year-month
        if len(ipc_data) == 0:
            continue

        # Get ACLED data for this year-month
        try:
            acled_data = acled_grouped.get_group((year, month))
        except KeyError:
            # No ACLED data for this year-month
            for col in acled_columns:
                ipc_data[col] = np.nan
            ipc_data['distance_to_nearest_acled'] = np.nan
            results.append(ipc_data)
            continue

        # Create arrays for faster distance calculation
        acled_lats = acled_data['lat'].values
        acled_lons = acled_data['lon'].values

        # Find nearest ACLED point for each IPC point
        distances = []
        nearest_indices = []

        for _, ipc_row in ipc_data.iterrows():
            min_dist = float('inf')
            nearest_idx = -1

            for i, (acled_lat, acled_lon) in enumerate(zip(acled_lats, acled_lons)):
                dist = haversine_distance(
                    ipc_row['lat'], ipc_row['lon'],
                    acled_lat, acled_lon
                )

                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = i

            if min_dist <= max_distance:
                distances.append(min_dist)
                nearest_indices.append(nearest_idx)
            else:
                distances.append(np.nan)
                nearest_indices.append(-1)

        # Add distance and nearest ACLED data to IPC data
        ipc_data['distance_to_nearest_acled'] = distances

        # Add ACLED metrics
        for col in acled_columns:
            ipc_data[col] = np.nan  # Initialize with NaN

        # Update only rows that have a match
        for i, (idx, dist) in enumerate(zip(nearest_indices, distances)):
            if not np.isnan(dist):
                nearest_acled = acled_data.iloc[idx]
                for col in acled_columns:
                    ipc_data.iloc[i, ipc_data.columns.get_loc(col)] = nearest_acled[col]

        # Add to results
        results.append(ipc_data)

    # Combine all results
    if not results:
        print("No data found")
        return pd.DataFrame()

    final_result = pd.concat(results, ignore_index=True)

    # Calculate match statistics
    match_count = final_result['distance_to_nearest_acled'].notna().sum()
    total_count = len(final_result)
    match_rate = match_count / total_count * 100 if total_count > 0 else 0

    print(f"Match rate: {match_count}/{total_count} ({match_rate:.2f}%)")

    return final_result

def main():
    """Main function to run the merging process"""
    # Load your datasets
    # Replace these with your actual file paths or data loading method

    # Optional: Preview data
    print("IPC data preview:")
    print(df_IPC.head())
    print(f"IPC data shape: {df_IPC.shape}")

    print("\nACLED_adm data preview:")
    print(df_ACLED_adm.head())
    print(f"ACLED_adm data shape: {df_ACLED_adm.shape}")

    # Set parameters
    max_distance = 500  # Maximum distance in kilometers

    # Choose the appropriate method based on dataset size
    # For this specific case (4,968 locations across 180 month-years),
    # the optimized single-process version will likely be faster
    use_optimized = True

    if use_optimized:
        # Use the optimized version for smaller datasets
        result = merge_ipc_with_acled_optimized(df_IPC, df_ACLED_adm, max_distance)
    else:
        # Use the parallel version for larger datasets
        n_processes = None  # Number of processes (None = use all available cores - 1)
        result = merge_ipc_with_acled(df_IPC, df_ACLED_adm, max_distance, n_processes)

    # Save the result
    ensure_dir(os.path.dirname(acled_output_file))
    result.to_csv(acled_output_file, index=False)
    print(f"Processing complete. Result saved with {len(result)} rows.")
    print(f"Output: {acled_output_file}")

    # Optional: Show the columns in the final dataset
    print("\nColumns in the final dataset:")
    print(result.columns.tolist())

    # Optional: Show summary statistics for the distance to nearest ACLED point
    if 'distance_to_nearest_acled' in result.columns:
        print("\nDistance to nearest ACLED point (km):")
        print(result['distance_to_nearest_acled'].describe())

if __name__ == "__main__":
    main()
