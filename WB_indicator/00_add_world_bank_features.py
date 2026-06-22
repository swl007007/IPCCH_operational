# Converted from WB_indicator/00_add_WBG_ch.ipynb

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
wb_cpi_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wb_cpi_file'),
    'World Bank CPI input'
)
wb_gdp_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wb_gdp_file'),
    'World Bank GDP input'
)
wb_cc_percentile_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wb_cc_percentile_file'),
    'World Bank control-of-corruption input'
)
wb_scaffold_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wb_scaffold_file'),
    'World Bank scaffold input'
)
wb_pip_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wb_pip_file'),
    'World Bank PIP input'
)
wb_esa_completed_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wb_esa_completed_file'),
    'World Bank ESA completed input'
)
wb_country_lookup_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wb_country_lookup_file'),
    'World Bank country lookup input'
)
wb_output_file = resolve_path(CONFIG, 'tabular', 'wb_output_file')

# %%
import pandas as pd
import numpy as np
import os
import datetime
#set wd

# %%
#read csv data
df_CPI = pd.read_csv(wb_cpi_file)
df_GDP = pd.read_csv(wb_gdp_file)
df_CC = pd.read_csv(wb_cc_percentile_file)
df_IPC = pd.read_csv(wb_scaffold_file)
df_gini = pd.read_csv(wb_pip_file)
df_ESA = pd.read_csv(wb_esa_completed_file)

# %%
# drop Country Name, Indicator Name, and Indicator Code
df_CPI.drop(columns=['Country Name', 'Indicator Name', 'Indicator Code'], inplace=True)
# recast wide format as long format
df_CPI = pd.melt(df_CPI, id_vars=['Country Code'], var_name='Year', value_name='CPI')
# drop where CPI is NaN
df_CPI.dropna(subset=['CPI'], inplace=True)

# rename Country Code to country_code_3, Year to year
df_CPI.rename(columns={'Country Code': 'country_code_3', 'Year': 'year'}, inplace=True)

# %%
df_GDP.drop(columns=['Country Name', 'Indicator Name', 'Indicator Code'], inplace=True)
# recast wide format as long format
df_GDP = pd.melt(df_GDP, id_vars=['Country Code'], var_name='Year', value_name='GDP')
# drop where GDP is NaN
df_GDP.dropna(subset=['GDP'], inplace=True)
# rename Country Code to country_code_3, Year to year
df_GDP.rename(columns={'Country Code': 'country_code_3', 'Year': 'year'}, inplace=True)

# %%
df_CC.drop(columns=['Country Name', 'Series Name', 'Series Code'], inplace=True)
# recast wide format as long format
df_CC = pd.melt(df_CC, id_vars=['Country Code'], var_name='Year', value_name='CC')
# drop where CC is NaN
df_CC.dropna(subset=['CC'], inplace=True)
# rename Country Code to country_code_3, Year to year
df_CC.rename(columns={'Country Code': 'country_code_3', 'Year': 'year'}, inplace=True)
#extract the first four letter of df_CC['year']
df_CC['year'] = df_CC['year'].str.split(' ').str[0]

# %%
# drop Unnamed: 0 for df_IPC
# force year and month to integer
df_IPC['year'] = df_IPC['year'].astype(int)
df_IPC['month'] = df_IPC['month'].astype(int)

# %%
# convert 2 letter country code to 3 letter country code in df_ESA using pycountry
import pycountry


# for df_ESA,drop country_y, rename country_x to country
df_ESA.drop(columns=['country_y'], inplace=True)
df_ESA.rename(columns={'country_x': 'country'}, inplace=True)

# %%
df_country = pd.read_csv(wb_country_lookup_file)

# %%
# keep only country lat lon
df_country = df_country[['country','ISO3','lat', 'lon']]

# %%
# convert lat and lon to float, pad with 12 decimal places
df_country['lat'] = df_country['lat'].astype(float).map('{:.12f}'.format)
df_country['lon'] = df_country['lon'].astype(float).map('{:.12f}'.format)


# convert lat and lon to float, pad with 12 decimal places
df_IPC['lat'] = df_IPC['lat'].astype(float).map('{:.12f}'.format)
df_IPC['lon'] = df_IPC['lon'].astype(float).map('{:.12f}'.format)

# merge df_country with df_IPC on lat and lon
df_IPC = pd.merge(df_IPC, df_country, on=['lat', 'lon'], how='left', indicator=True)

# %%
# drop _merge
df_IPC.drop(columns=['_merge'], inplace=True)

# %%

df_IPC['country_code_3'] = df_IPC['ISO3']

# %%
# keep lat lon country_code_3 for df_ESA
df_ESA = df_ESA[['country_code_3', 'lat', 'lon']]

# convert lat and lon to float, padding 12 digits
df_ESA['lat'] = df_ESA['lat'].astype(float).map('{:.12f}'.format)
df_ESA['lon'] = df_ESA['lon'].astype(float).map('{:.12f}'.format)

# %%
# df_IPC lat and lon convert to float, padding 12 digits
df_IPC['lat'] = df_IPC['lat'].astype(float).map('{:.12f}'.format)
df_IPC['lon'] = df_IPC['lon'].astype(float).map('{:.12f}'.format)

# %%
# drop duplicate sin lat,lon,year and month
df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], inplace=True)

# %%
# convert df_IPC['year'] to integer
df_IPC['year'] = df_IPC['year'].astype(int)
# convert df_CPI['year'] to integer
df_CPI['year'] = df_CPI['year'].astype(int)
# convert df_GDP['year'] to integer
df_GDP['year'] = df_GDP['year'].astype(int)
# convert df_CC['year'] to integer
df_CC['year'] = df_CC['year'].astype(int)

# %%
# merge df_IPC and df_CPI on country_code_3 and year, add indicator
df_IPC = pd.merge(df_IPC, df_CPI, how='left', on=['country_code_3', 'year'], indicator=True)

# %%
# drop _merge
df_IPC.drop(columns=['_merge'], inplace=True)

# %%
# merge df_IPC and df_GDP on country_code_3 and year, add indicator
df_IPC = pd.merge(df_IPC, df_GDP, how='left', on=['country_code_3', 'year'], indicator=True)

# %%
# see _merge
print(df_IPC['_merge'].value_counts())

# %%
# drop _merge
df_IPC.drop(columns=['_merge'], inplace=True)

# %%
# merge df_IPC and df_CC on country_code_3 and year, add indicator
df_IPC = pd.merge(df_IPC, df_CC, how='left', on=['country_code_3', 'year'], indicator=True)
# see _merge
print(df_IPC['_merge'].value_counts())

# %%
# drop _merge
df_IPC.drop(columns=['_merge'], inplace=True)

# %%
# for df_gini, keep only country_code, reporting_year, and gini
df_gini = df_gini[['country_code', 'reporting_year', 'gini']]

# %%
# rename country_code to country_code_3, reporting_year to year
df_gini.rename(columns={'country_code': 'country_code_3', 'reporting_year': 'year'}, inplace=True)

# %%
# df_gini sort by country_code_3 and year
df_gini.sort_values(by=['country_code_3', 'year'], inplace=True)

# %%
# Handle duplicate years by averaging gini values
df_gini = df_gini.groupby(['country_code_3', 'year']).agg({'gini': 'mean'}).reset_index()

# Function to interpolate missing years for a country
def interpolate_country(country_df):
    # Sort by year
    country_df = country_df.sort_values('year')

    # Get the min and max years
    min_year = country_df['year'].min()
    max_year = country_df['year'].max()

    # Create a complete range of years
    full_years = pd.DataFrame({'year': range(min_year, max_year + 1)})

    # Merge with existing data
    merged = pd.merge(full_years, country_df, on='year', how='left')

    # Add country code for missing years
    merged['country_code_3'] = country_df['country_code_3'].iloc[0]

    # Linear interpolation for gini values
    merged['gini'] = merged['gini'].interpolate(method='linear')

    return merged

# Apply interpolation for each country
countries = df_gini['country_code_3'].unique()
interpolated_dfs = []

for country in countries:
    country_df = df_gini[df_gini['country_code_3'] == country]
    interpolated_df = interpolate_country(country_df)
    interpolated_dfs.append(interpolated_df)

# Combine all interpolated data
result = pd.concat(interpolated_dfs)

# Sort by country and year
result = result.sort_values(['country_code_3', 'year'])

# %%
#convert year to integer
result['year'] = result['year'].astype(int)

# %%
# merge df_IPC and result on country_code_3 and year, add indicator
df_IPC = pd.merge(df_IPC, result, how='left', on=['country_code_3', 'year'], indicator=True)

# %%
# see _merge
print(df_IPC['_merge'].value_counts())

# %%
# drop _merge
df_IPC.drop(columns=['_merge'], inplace=True)

# %%
# save results
ensure_dir(os.path.dirname(wb_output_file))
df_IPC.to_csv(wb_output_file, index=False)
print("Output: {0}".format(wb_output_file))
