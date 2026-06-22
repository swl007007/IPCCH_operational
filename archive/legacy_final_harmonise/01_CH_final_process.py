# Converted from Final_harmonise/01_CH_final_process.ipynb

from __future__ import print_function

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, load_config, resolve_path, require_file

CONFIG = load_config()
source_data_root = resolve_path(CONFIG, "paths", "source_data_root")
output_root = ensure_dir(resolve_path(CONFIG, 'paths', 'output_root'))

# %%
import pandas as pd
import numpy as np
import os
import polars as pl
#set working directory
os.chdir(source_data_root)

# %%
# read csv using polars
df = pl.read_csv('chcountries_final_v12022025.csv')

# %%
# output column names
print(df.columns)

# %%
time_variants = ['event_count_battles', 'event_count_explosions', 'event_count_violence', 'sum_fatalities_battles', 'sum_fatalities_explosions', 'sum_fatalities_violence', 'event_count_battles_w5', 'event_count_explosions_w5', 'event_count_violence_w5', 'sum_fatalities_battles_w5', 'sum_fatalities_explosions_w5', 'sum_fatalities_violence_w5', 'event_count_battles_w10', 'event_count_explosions_w10', 'event_count_violence_w10', 'sum_fatalities_battles_w10', 'sum_fatalities_explosions_w10', 'sum_fatalities_violence_w10', 'nightlight_mean', 'nightlight_std', 'EVI_mean', 'EVI_std',  'FAO_price', 'Evap_tavg_mean', 'Evap_tavg_stdDev', 'LWdown_f_tavg_mean', 'LWdown_f_tavg_stdDev', 'Lwnet_tavg_mean', 'Lwnet_tavg_stdDev', 'Psurf_f_tavg_mean', 'Psurf_f_tavg_stdDev', 'Qair_f_tavg_mean', 'Qair_f_tavg_stdDev', 'Qg_tavg_mean', 'Qg_tavg_stdDev', 'Qh_tavg_mean', 'Qh_tavg_stdDev', 'Qle_tavg_mean', 'Qle_tavg_stdDev', 'Qs_tavg_mean', 'Qs_tavg_stdDev', 'Qsb_tavg_mean', 'Qsb_tavg_stdDev', 'RadT_tavg_mean', 'RadT_tavg_stdDev', 'Rainf_f_tavg_mean', 'Rainf_f_tavg_stdDev', 'SnowCover_inst_mean', 'SnowCover_inst_stdDev', 'SnowDepth_inst_mean', 'SnowDepth_inst_stdDev', 'Snowf_tavg_mean', 'Snowf_tavg_stdDev', 'SoilMoi00_10cm_tavg_mean', 'SoilMoi00_10cm_tavg_stdDev', 'SoilMoi10_40cm_tavg_mean', 'SoilMoi10_40cm_tavg_stdDev', 'SoilMoi100_200cm_tavg_mean', 'SoilMoi100_200cm_tavg_stdDev', 'SoilMoi40_100cm_tavg_mean', 'SoilMoi40_100cm_tavg_stdDev', 'SoilTemp00_10cm_tavg_mean', 'SoilTemp00_10cm_tavg_stdDev', 'SoilTemp10_40cm_tavg_mean', 'SoilTemp10_40cm_tavg_stdDev', 'SoilTemp100_200cm_tavg_mean', 'SoilTemp100_200cm_tavg_stdDev', 'SoilTemp40_100cm_tavg_mean', 'SoilTemp40_100cm_tavg_stdDev', 'SWdown_f_tavg_mean', 'SWdown_f_tavg_stdDev', 'SWE_inst_mean', 'SWE_inst_stdDev', 'Swnet_tavg_mean', 'Swnet_tavg_stdDev', 'Tair_f_tavg_mean', 'Tair_f_tavg_stdDev', 'Wind_f_tavg_mean', 'Wind_f_tavg_stdDev', 'GPP_std', 'GPP_mean', 'CPI', 'GDP', 'CC', 'gini', 'WFP_Price', 'WFP_Price_std']

# %%
# for each time variant, create a new column with the same name but with "_l12" suffix, which is the lagged value of the column by 12 months
for variant in time_variants:
    df = df.with_columns(
        pl.col(variant).shift(12).alias(f"{variant}_l12")
    )

# for each time variant, create a new column with the same name but with "_m12" suffix, which is the moving average of the column by 12 months
for variant in time_variants:
    df = df.with_columns(
        pl.col(variant).rolling_mean(window_size=12, min_periods=1).alias(f"{variant}_m12")
    )
    
# for each time variant, create a new column with the same name but with "_v12" suffix, which is the lagged 12 months value of moving average of the column by 12 months
for variant in time_variants:
    df = df.with_columns(
        pl.col(variant).rolling_mean(window_size=12, min_periods=1).shift(12).alias(f"{variant}_v12")
    )

# %%
import geopandas as gpd
# read shapefile
shapefile_path = r'Outcome/gdf_ch.geojson'
gdf_shapefile = gpd.read_file(shapefile_path)

# %%
gdf_shapefile.columns

# %%
#drop population, to, geometry
gdf_shapefile = gdf_shapefile.drop(columns=['population', 'to', 'geometry'])

# %%
# convert from to datetime, extract the first three letter and convert to month
gdf_shapefile['month'] = pd.to_datetime(gdf_shapefile['from']).dt.strftime('%b')

# %%
# convert month to only number
gdf_shapefile['month'] = pd.to_datetime(gdf_shapefile['month'], format='%b').dt.month

# %%
#drop from
gdf_shapefile = gdf_shapefile.drop(columns=['from'])

# %%
df_outcome = gdf_shapefile.copy()

# %%
#use unique method in polars to drop duplicates in year month and title
df_outcome = pl.from_pandas(df_outcome)
df_outcome = df_outcome.unique(subset=['year', 'month', 'title'])
df = df.unique(subset=['year', 'month', 'title'])

# %%
# convert year and month columns to integer
df_outcome = df_outcome.with_columns(
    pl.col('year').cast(pl.Int32),
    pl.col('month').cast(pl.Int32)
)

# do the same for df
df = df.with_columns(
    pl.col('year').cast(pl.Int32),
    pl.col('month').cast(pl.Int32)
)

# merge df and df_outcome on year, month, and area_id
df_final = df.join(df_outcome, on=['year', 'month', 'title'], how='left')

# %%
#drop any column with _right
cols_to_drop = [col for col in df_final.columns if col.endswith('_right')]
df_final = df_final.drop(cols_to_drop)

# %%
# -----------------------------------------------------------------------------
# Script Start
# -----------------------------------------------------------------------------

import polars as pl
import polars.selectors as cs # Selector functions (like cs.numeric())
import numpy as np           # For handling NaN/Inf, using abs()

# Get current time for potential logging or reference
from datetime import datetime
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"Script execution started at: {current_time}")


# Check if data loading was successful (basic check)
if 'df_final' not in locals() or not isinstance(df_final, pl.DataFrame):
    print("Error: df_final DataFrame not loaded correctly. Exiting.")
    exit()
elif df_final.is_empty():
    print("Warning: df_final DataFrame is empty. Analysis may yield no results.")
else:
     print(f"Data loaded successfully. DataFrame shape: {df_final.shape}")


# =============================================================================
# --- 2. Missing Data Analysis (Corrected) ---
# =============================================================================
print("\n--- 2. Missing Data Analysis ---")

# Calculate null counts per column and reshape using melt
null_info = df_final.null_count().melt(
    variable_name="feature",  # Name for the column holding original column names
    value_name="null_count"    # Name for the column holding the null counts
)

# Check if df_final is empty to avoid division by zero
if df_final.height > 0:
    # Calculate null percentage and sort
    null_info = null_info.with_columns(
        (pl.col("null_count") / df_final.height * 100).round(2).alias("null_percentage")
    ).sort("null_percentage", descending=True)
else:
    # Handle empty DataFrame case: create the percentage column with zeros
    null_info = null_info.with_columns(
        pl.lit(0.0, dtype=pl.Float64).alias("null_percentage")
    ).sort("feature") # Sort by feature name

# Calculate total nulls efficiently from null_info
total_nulls = null_info['null_count'].sum()

print(f"Total null values in DataFrame: {total_nulls}")
print("Missing data summary per feature (Top 10 or all if less):")
print(null_info.head(10)) # Show top N missing features

# Optional: Filter to show only columns that *do* have missing values
missing_features = null_info.filter(pl.col("null_count") > 0)
if not missing_features.is_empty():
    print(f"\n{missing_features.height} features have missing values.")
    # print(missing_features) # Uncomment to see all features with missing data
else:
    print("\nNo missing values found in the DataFrame.")


# =============================================================================
# --- 3. Generate Summary Statistics ---
# =============================================================================
# This needs to be done *before* checking for constant columns.
# We only describe numeric columns to avoid errors/warnings on non-numeric data.
print("\n--- 3. Generating Numerical Summary ---")
numerical_summary = pl.DataFrame() # Initialize as empty

try:
    # Select only numeric columns for describe
    numeric_cols_for_describe = df_final.select(cs.numeric()).columns
    if numeric_cols_for_describe: # Proceed only if there are numeric columns
         print(f"Describing {len(numeric_cols_for_describe)} numeric columns...")
         numerical_summary = df_final.select(numeric_cols_for_describe).describe()
         print("Numerical summary generated.")
         # print(numerical_summary) # Uncomment to view the summary table
    else:
         print("No numeric columns found to generate summary statistics.")

except Exception as e:
    print(f"Error generating numerical summary: {e}")
    # Ensure numerical_summary remains an empty DF on error


# =============================================================================
# --- 4. Constant Feature Analysis (Corrected) ---
# =============================================================================
print("\n--- 4. Constant Feature Analysis ---")
constant_cols = []
std_dev_threshold = 1e-9 # Threshold for standard deviation to be considered zero
value_range_threshold = 1e-9 # Threshold for min/max difference

# Check if numerical_summary was generated successfully and is not empty
if not numerical_summary.is_empty() and "statistic" in numerical_summary.columns:
    # Get the list of numeric columns present in the summary (excluding the 'statistic' column)
    numeric_cols_in_summary = [c for c in numerical_summary.columns if c != "statistic"]

    # Pre-filter rows for efficiency
    try:
        std_dev_row = numerical_summary.filter(pl.col("statistic") == "std")
        min_val_row = numerical_summary.filter(pl.col("statistic") == "min")
        max_val_row = numerical_summary.filter(pl.col("statistic") == "max")
    except pl.ColumnNotFoundError:
         print("Error: 'statistic' column unexpectedly missing from numerical_summary. Skipping constant check.")
         std_dev_row, min_val_row, max_val_row = pl.DataFrame(), pl.DataFrame(), pl.DataFrame() # Assign empty DFs

    # Proceed only if we successfully filtered the statistic rows
    if not std_dev_row.is_empty() and not min_val_row.is_empty() and not max_val_row.is_empty():
        print(f"Checking {len(numeric_cols_in_summary)} numeric features for constant values...")
        for col_name in numeric_cols_in_summary:
            try:
                # Extract values using .item()
                std_dev = std_dev_row.select(pl.col(col_name)).item()
                min_val = min_val_row.select(pl.col(col_name)).item()
                max_val = max_val_row.select(pl.col(col_name)).item()

                # Check for None or NaN/Inf before comparison
                # If a column is all Nulls, its describe() stats might be null.
                # We handle all-null columns in missing data analysis. Skip here.
                if (std_dev is None or np.isnan(std_dev) or np.isinf(std_dev)) and \
                   (min_val is None or np.isnan(min_val) or np.isinf(min_val)) and \
                   (max_val is None or np.isnan(max_val) or np.isinf(max_val)):
                    continue # Skip columns where all stats are invalid/null

                # --- Check 1: Standard Deviation (handle potential None for std) ---
                is_constant_std = False
                if std_dev is not None and not np.isnan(std_dev) and not np.isinf(std_dev):
                    if abs(std_dev) < std_dev_threshold:
                        is_constant_std = True

                # --- Check 2: Min == Max (handle potential None for min/max) ---
                is_constant_minmax = False
                if min_val is not None and not np.isnan(min_val) and not np.isinf(min_val) and \
                   max_val is not None and not np.isnan(max_val) and not np.isinf(max_val):
                    if abs(min_val - max_val) < value_range_threshold:
                         is_constant_minmax = True

                # --- Combine checks ---
                if is_constant_std or is_constant_minmax:
                    if col_name not in constant_cols:
                         constant_cols.append(col_name)
                         # print(f"  - Column '{col_name}' identified as constant.")

            except pl.ColumnNotFoundError:
                print(f"Warning: Column '{col_name}' unexpectedly not found during constant check iteration.")
            except ValueError as ve:
                 print(f"Warning: ValueError during constant check for column '{col_name}': {ve}")
            except Exception as e:
                print(f"Warning: Error processing column '{col_name}' for constant check: {type(e).__name__} - {e}")
    else:
        print("Could not find 'std', 'min', or 'max' rows in numerical_summary. Skipping constant value check.")

else:
    print("Skipping constant feature analysis as numerical summary is empty or missing 'statistic' column.")


print(f"\nConstant numeric columns identified ({len(constant_cols)}): {constant_cols}")


# =============================================================================
# --- 5. Optional: Remove Constant Columns ---
# =============================================================================
print("\n--- 5. Removing Constant Columns ---")

if constant_cols:
    print(f"Removing {len(constant_cols)} constant columns...")
    try:
        df_final = df_final.drop(constant_cols)
        print("Constant columns removed. New DataFrame shape:", df_final.shape)
    except Exception as e:
        print(f"Error removing constant columns: {e}")
else:
    print("No constant columns to remove.")


# =============================================================================
# End of Analysis Script
# Your subsequent modeling or analysis steps would go here, using the cleaned df_final
# =============================================================================

print("\n---------------------------------------------")
print("Data analysis script finished.")
print(f"Final DataFrame shape: {df_final.shape}")
print("---------------------------------------------")

# You can now use the processed 'df_final' for further steps.

# %%
numerical_summary

# %%
# save df_final to csv
df_final.write_csv('CH_final_v12102025.csv')

# %%
# write numerical_summary to csv
numerical_summary.write_csv('IPC_numerical_summary.csv')
