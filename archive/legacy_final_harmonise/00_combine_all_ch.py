# Converted from Final_harmonise/00_combine_all_ch.ipynb

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

#set working directory
os.chdir(source_data_root)


df_ACLED = pd.read_csv(r'ACLED\ch_with_merged_acled_metrics.csv')
df_AEZ = pd.read_csv(r'AEZ\ch_aez_completed.csv')
df_ASAP = pd.read_csv(r'ASAP_land_cover\ch_ASAP_completed_sampled.csv')
df_rivers = pd.read_csv(r'Distance_to_rivers\ch_distance_to_river_completed.csv')
df_nightlight_std = pd.read_csv(r'DMSP_OLS\output_ch\nightlight_std_extraction_results.csv')
df_nightlight = pd.read_csv(r'DMSP_OLS\output_ch\nightlight_sum_extraction_results.csv')
df_elevation = pd.read_csv(r'Elevation\ch_elevation_completed_FINAL.csv')
df_ESA = pd.read_csv(r'ESA\ch_ESA_completed.csv')
df_EVI = pd.read_csv(r'EVI\output_ch\EVI_mean_extraction_results.csv')
df_EVI_std = pd.read_csv(r'EVI\output_ch\EVI_std_extraction_results.csv')
df_FAO = pd.read_csv(r'FAO\ch_with_matched_markets.csv')
df_FEWSNET_p1 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_mean_extraction_results_p1.csv')
df_FEWSNET_p2 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_mean_extraction_results_p2.csv')
df_FEWSNET_p3 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_mean_extraction_results_p3.csv')
df_FEWSNET_p4 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_mean_extraction_results_p4.csv')
df_FEWSNET_std_p1 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_std_extraction_results_p1.csv')
df_FEWSNET_std_p2 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_std_extraction_results_p2.csv')
df_FEWSNET_std_p3 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_std_extraction_results_p3.csv')
df_FEWSNET_std_p4 = pd.read_csv(r'FEWSNET_predictors\output_ch\FLDAS_std_extraction_results_p4.csv')
df_GPP = pd.read_csv(r'GOSIF_GPP\output_ch\GOSIF_GPP_extraction_results_ch.csv')
df_GPP_std = pd.read_csv(r'GOSIF_GPP\output_ch\GOSIF_GPP_extraction_results_SD.csv')
df_market_access = pd.read_csv(r'Market_access\ch_market_access_completed_batched.csv')
df_ruggedness = pd.read_csv(r'Ruggedness\ch_ruggedness_percentile_completed.csv')
df_slope =  pd.read_csv(r'Slope\ch_slope_completed_batched.csv')
df_wbg = pd.read_csv(r'WBG\ch_WBG_completed.csv')
df_wfp = pd.read_csv(r'WFP\ch_WFP_prices.csv')
df_soil = pd.read_csv(r'ISRIC\ch_soilgrids_completed_batched.csv')


ch_geoidentifier = pd.read_csv(r'Outcome\geoidentifier_ch.csv')

# %%
# convert df_ESA lat and lon to float type
df_ESA['lat'] = df_ESA['lat'].astype(float)
df_ESA['lon'] = df_ESA['lon'].astype(float)

# %%

# pad df_ESA with 12 decimal places
df_ESA['lat'] = df_ESA['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ESA['lon'] = df_ESA['lon'].apply(lambda x: '{:.12f}'.format(x))

# %%
# CONVERT df_ACLED lat and lon to float type
df_ACLED['lat'] = df_ACLED['lat'].astype(float)
df_ACLED['lon'] = df_ACLED['lon'].astype(float)

# %%

df_ACLED['lat'] = df_ACLED['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ACLED['lon'] = df_ACLED['lon'].apply(lambda x: '{:.12f}'.format(x))

# %%

# merge df_ACLED with df_ESA
df_IPC = pd.merge(df_ACLED, df_ESA, on=['title'], how='left', indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# see df_IPC columns
print(df_IPC.columns)

# %%
# rename lat_x, lat_y  as lat, lon, country_x as country, drop country_y, rename lat_y, lon_y as lon_fixed, lon_x as lon_fixed
df_IPC = df_IPC.rename(columns={'lat_x': 'lat', 'lon_x': 'lon', 'country_x': 'country'})
df_IPC = df_IPC.drop(columns=['country_y'])
df_IPC = df_IPC.rename(columns={'lat_y': 'lat_fixed', 'lon_y': 'lon_fixed'})

# %%

# drop duplicates in lat,lon,year and month
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'])

# %%
#read ch_scaffold_fixed
ch_geoidentifier = pd.read_csv(os.path.join(source_data_root, "Outcome", "ch_scaffold_fixed.csv"))

# %%
# create index for ch_geoidentifier
ch_geoidentifier['index'] = ch_geoidentifier.index

# keep only index and title
ch_geoidentifier = ch_geoidentifier[['index', 'lat', 'lon']]

# convert lat and lon to string to float
ch_geoidentifier['lat'] = ch_geoidentifier['lat'].astype(float)
ch_geoidentifier['lon'] = ch_geoidentifier['lon'].astype(float)

# convert to 12 decimal places
ch_geoidentifier['lat'] = ch_geoidentifier['lat'].apply(lambda x: '{:.12f}'.format(x))
ch_geoidentifier['lon'] = ch_geoidentifier['lon'].apply(lambda x: '{:.12f}'.format(x))

# merge df_IPC with ch_geoidentifier on lat and lon
df_IPC = pd.merge(df_IPC, ch_geoidentifier, on=['lat', 'lon'], how='left', indicator=True)

# %%
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# drop duplicates in lat, lon, year and month
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'])

# %%
# drop index
df_IPC = df_IPC.drop(columns=['index'])

# %%
# in df_AEZ, drop duplicates in lat and lon
df_AEZ = df_AEZ.drop_duplicates(subset=['lat', 'lon'])

# %%

# drop ISO2, ISO3, title, country
df_AEZ = df_AEZ.drop(columns=['ISO2', 'ISO3', 'title', 'country'])

# convert df_AEZ lat and lon to float type
df_AEZ['lat'] = df_AEZ['lat'].astype(float)
df_AEZ['lon'] = df_AEZ['lon'].astype(float)

# pad df_AEZ with 12 decimal places
df_AEZ['lat'] = df_AEZ['lat'].apply(lambda x: '{:.12f}'.format(x))
df_AEZ['lon'] = df_AEZ['lon'].apply(lambda x: '{:.12f}'.format(x))

# rename as lat_fixed and lon_fixed
df_AEZ = df_AEZ.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})

# merge df_IPC with df_AEZ
df_IPC = pd.merge(df_IPC, df_AEZ, on=['lat_fixed', 'lon_fixed'], how='left', indicator=True)

# %%

#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# convert df_ASAP lat and lon to float type
df_ASAP['lat'] = df_ASAP['lat'].astype(float)
df_ASAP['lon'] = df_ASAP['lon'].astype(float)



# pad lat and lon in df_ASAP with 12 decimal places
df_ASAP['lat'] = df_ASAP['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ASAP['lon'] = df_ASAP['lon'].apply(lambda x: '{:.12f}'.format(x))


# drop ISO2, ISO3, title, country
df_ASAP = df_ASAP.drop(columns=['ISO2', 'ISO3', 'title', 'country'])

# drop duplicates in lat and lon in df_ASAP
df_ASAP = df_ASAP.drop_duplicates(subset=['lat', 'lon'])

# rename as lat_fixed and lon_fixed
df_ASAP = df_ASAP.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})


# merge df_IPC with df_ASAP
df_IPC = pd.merge(df_IPC, df_ASAP, on=['lat_fixed', 'lon_fixed'], how='left', indicator=True)
# drop duplicates in lat lon year month, keep first
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')

# %%

df_IPC = df_IPC.drop(columns=['_merge','.geo','system:index'])

# %%
# in df_rivers, drop _merge
df_rivers = df_rivers.drop(columns=['_merge'])

# %%
# convert df_rivers lat and lon to float type
df_rivers['lat'] = df_rivers['lat'].astype(float)
df_rivers['lon'] = df_rivers['lon'].astype(float)
#pad lat and lon in df_rivers with 12 decimal places
df_rivers['lat'] = df_rivers['lat'].apply(lambda x: '{:.12f}'.format(x))
df_rivers['lon'] = df_rivers['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat and lon in df_rivers
df_rivers = df_rivers.drop_duplicates(subset=['lat', 'lon'])

# rename as lat_fixed and lon_fixed
df_rivers = df_rivers.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})

# %%

# merge df_IPC with df_rivers
df_IPC = pd.merge(df_IPC, df_rivers, on=['lat_fixed', 'lon_fixed'], how='left', indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%

# drop duplcicates in lat lon year month, keep first
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')

# %%
# recast df_nightlight_mean into long format
df_nightlight = df_nightlight.melt(id_vars=['region_id'], var_name='year_month', value_name='nightlight_mean')
# split year_month into year and month
df_nightlight[['year', 'month']] = df_nightlight['year_month'].str.split('_', expand=True)
# drop year_month
df_nightlight = df_nightlight.drop(columns=['year_month'])
# convert year and month to int
df_nightlight['year'] = df_nightlight['year'].astype(int)
df_nightlight['month'] = df_nightlight['month'].astype(int)

# sort by region_id, year, month
df_nightlight = df_nightlight.sort_values(by=['region_id', 'year', 'month'], ascending=[True, True, True])
# impute forward for df_nightlight_mean, column nightlight_mean
df_nightlight.loc[:, 'nightlight_mean'] = df_nightlight.loc[:, 'nightlight_mean'].ffill(axis=0)
# fill the rest with 0
df_nightlight.loc[:, 'nightlight_mean'] = df_nightlight.loc[:, 'nightlight_mean'].fillna(0)
# drop duplicates in df_nightlight_mean
df_nightlight = df_nightlight.drop_duplicates(subset=['region_id', 'year', 'month'], keep='first')

# %%

# for nightlight_mean<0, set to 0
df_nightlight.loc[df_nightlight['nightlight_mean'] < 0, 'nightlight_mean'] = 0
# rename region_id to admin_code
df_nightlight = df_nightlight.rename(columns={'region_id': 'admin_code'})

# %%
# rename index in ch_geoidentifier to admin_code
ch_geoidentifier = ch_geoidentifier.rename(columns={'index': 'admin_code'})
# merge df_nightlight with ch_geoidentifier
df_nightlight = pd.merge(df_nightlight, ch_geoidentifier, on='admin_code', how='left', indicator=True)

# %%
# drop _merge
df_nightlight = df_nightlight.drop(columns=['_merge'])
# convert lat and lon to float type
df_nightlight['lat'] = df_nightlight['lat'].astype(float)
df_nightlight['lon'] = df_nightlight['lon'].astype(float)

# pad with 12 decimal places
df_nightlight['lat'] = df_nightlight['lat'].apply(lambda x: '{:.12f}'.format(x))
df_nightlight['lon'] = df_nightlight['lon'].apply(lambda x: '{:.12f}'.format(x))

# %%

# merge df_IPC with df_nightlight
df_IPC = pd.merge(df_IPC, df_nightlight, on=['lat', 'lon', 'year', 'month'], how='left', indicator=True)

# %%
# drop _merge in df_IPC
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# see df_IPC columns
print(df_IPC.columns)

# %%
# drop country_y, title_y, ISO2_y, ISO3_y ,rename country_x as country, title_x as title, ISO2_x as ISO2, ISO3_x as ISO3
df_IPC = df_IPC.drop(columns=['country_y', 'title_y', 'ISO2_y', 'ISO3_y'])
df_IPC = df_IPC.rename(columns={'country_x': 'country', 'title_x': 'title', 'ISO2_x': 'ISO2', 'ISO3_x': 'ISO3'})

# %%
# for df_nightlight_std, recast into long format
df_nightlight_std = df_nightlight_std.melt(id_vars=['region_id'], var_name='year_month', value_name='nightlight_std')
# split year_month into year and month
df_nightlight_std[['year', 'month']] = df_nightlight_std['year_month'].str.split('_', expand=True)
# drop year_month
df_nightlight_std = df_nightlight_std.drop(columns=['year_month'])
# convert year and month to int
df_nightlight_std['year'] = df_nightlight_std['year'].astype(int)
df_nightlight_std['month'] = df_nightlight_std['month'].astype(int)
# sort by region_id, year, month
df_nightlight_std = df_nightlight_std.sort_values(by=['region_id', 'year', 'month'], ascending=[True, True, True])
# impute forward for df_nightlight_std, column nightlight_std
df_nightlight_std.loc[:, 'nightlight_std'] = df_nightlight_std.loc[:, 'nightlight_std'].ffill(axis=0)
# fill the rest with 0
df_nightlight_std.loc[:, 'nightlight_std'] = df_nightlight_std.loc[:, 'nightlight_std'].fillna(0)
# drop duplicates in df_nightlight_std
df_nightlight_std = df_nightlight_std.drop_duplicates(subset=['region_id', 'year', 'month'], keep='first')
# for nightlight_std<0, set to 0
df_nightlight_std.loc[df_nightlight_std['nightlight_std'] < 0, 'nightlight_std'] = 0
# rename region_id to admin_code
df_nightlight_std = df_nightlight_std.rename(columns={'region_id': 'admin_code'})

# merge df_IPC and df_nightlight_std on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_nightlight_std, how='left', on=['admin_code', 'year', 'month'], indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%

# convert df_elevation lat and lon to float type
df_elevation['lat'] = df_elevation['lat'].astype(float)
df_elevation['lon'] = df_elevation['lon'].astype(float)

#pad lat and lon in df_elevation with 12 decimal places
df_elevation['lat'] = df_elevation['lat'].apply(lambda x: '{:.12f}'.format(x))
df_elevation['lon'] = df_elevation['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_elevation, keep first
df_elevation = df_elevation.drop_duplicates(subset=['lat', 'lon'], keep='first')

# rename as lat_fixed and lon_fixed
df_elevation = df_elevation.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})

# drop title, country, ISO2, ISO3 from df_elevation
df_elevation = df_elevation.drop(columns=['title', 'country', 'ISO2', 'ISO3'])
# merge df_IPC with df_elevation
df_IPC = pd.merge(df_IPC, df_elevation, on=['lat_fixed', 'lon_fixed'], how='left', indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
df_EVI_mean = df_EVI.copy()
# for df_EVI_mean, recast into long format
df_EVI_mean = df_EVI_mean.melt(id_vars=['region_id'], var_name='year_month', value_name='EVI_mean')
# split year_month into year and month
df_EVI_mean[['year', 'month']] = df_EVI_mean['year_month'].str.split('_', expand=True)
# drop year_month
df_EVI_mean = df_EVI_mean.drop(columns=['year_month'])
# convert year and month to int
df_EVI_mean['year'] = df_EVI_mean['year'].astype(int)
df_EVI_mean['month'] = df_EVI_mean['month'].astype(int)
# sort by region_id, year, month
df_EVI_mean = df_EVI_mean.sort_values(by=['region_id', 'year', 'month'], ascending=[True, True, True])
# impute forward for df_EVI_mean, column EVI_mean
df_EVI_mean.loc[:, 'EVI_mean'] = df_EVI_mean.loc[:, 'EVI_mean'].ffill(axis=0)
# fill the rest with 0
df_EVI_mean.loc[:, 'EVI_mean'] = df_EVI_mean.loc[:, 'EVI_mean'].fillna(0)
# drop duplicates in df_EVI_mean
df_EVI_mean = df_EVI_mean.drop_duplicates(subset=['region_id', 'year', 'month'], keep='first')
# for EVI_mean<0, set to 0
df_EVI_mean.loc[df_EVI_mean['EVI_mean'] < 0, 'EVI_mean'] = 0
# rename region_id to admin_code
df_EVI_mean = df_EVI_mean.rename(columns={'region_id': 'admin_code'})




# merge df_IPC and df_EVI_mean on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_EVI_mean, how='left', on=['admin_code', 'year', 'month'], indicator=True)

# %%
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
df_IPC = df_IPC.sort_values(by=['admin_code', 'year', 'month'], ascending=[True, True, True])

# fill the rest with 0
df_IPC.loc[:, 'EVI_mean'] = df_IPC.loc[:, 'EVI_mean'].fillna(0)
# recast df_EVI_std into long format
df_EVI_std = df_EVI_std.melt(id_vars=['region_id'], var_name='year_month', value_name='EVI_std')
# split year_month into year and month
df_EVI_std[['year', 'month']] = df_EVI_std['year_month'].str.split('_', expand=True)
# drop year_month
df_EVI_std = df_EVI_std.drop(columns=['year_month'])
# convert year and month to int
df_EVI_std['year'] = df_EVI_std['year'].astype(int)
df_EVI_std['month'] = df_EVI_std['month'].astype(int)
# sort by region_id, year, month
df_EVI_std = df_EVI_std.sort_values(by=['region_id', 'year', 'month'], ascending=[True, True, True])
# impute forward for df_EVI_std, column EVI_std
df_EVI_std.loc[:, 'EVI_std'] = df_EVI_std.loc[:, 'EVI_std'].ffill(axis=0)
# fill the rest with 0
df_EVI_std.loc[:, 'EVI_std'] = df_EVI_std.loc[:, 'EVI_std'].fillna(0)
# drop duplicates in df_EVI_std
df_EVI_std = df_EVI_std.drop_duplicates(subset=['region_id', 'year', 'month'], keep='first')
# for EVI_std<0, set to 0
df_EVI_std.loc[df_EVI_std['EVI_std'] < 0, 'EVI_std'] = 0
# rename region_id to admin_code
df_EVI_std = df_EVI_std.rename(columns={'region_id': 'admin_code'})
# merge df_IPC and df_EVI_std on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_EVI_std, how='left', on=['admin_code', 'year', 'month'], indicator=True)
# sort by admin_code, year, month
df_IPC = df_IPC.sort_values(by=['admin_code', 'year', 'month'], ascending=[True, True, True])
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
# fill the rest with 0
df_IPC.loc[:, 'EVI_std'] = df_IPC.loc[:, 'EVI_std'].fillna(0)

# %%
# for df_FAO, keep only lat, lon, year, month, market_distance, FAO_price
df_FAO = df_FAO[['lat','lon', 'year', 'month', 'market_distance', 'FAO_price']]

# convert df_FAO lat and lon to float type
df_FAO['lat'] = df_FAO['lat'].astype(float)
df_FAO['lon'] = df_FAO['lon'].astype(float)

# pad lat and lon in df_FAO with 12 decimal places
df_FAO['lat'] = df_FAO['lat'].apply(lambda x: '{:.12f}'.format(x))
df_FAO['lon'] = df_FAO['lon'].apply(lambda x: '{:.12f}'.format(x))

# sort by admin_code, year, month
df_FAO = df_FAO.sort_values(by=['lat','lon', 'year', 'month'], ascending=[True, True, True,True])

# merge df_IPC and df_FAO on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_FAO, how='left', on=['lat','lon', 'year', 'month'], indicator=True)

# %%

# drop _merge
df_IPC= df_IPC.drop(columns=['_merge'])

# foir FAO_price, if it is >1000, set to 1000
df_IPC.loc[df_IPC['FAO_price'] > 1000, 'FAO_price'] = 1000

# %%
#del merged dataframe
del df_FAO, df_EVI_mean, df_EVI_std, df_nightlight, df_nightlight_std, df_elevation, df_ASAP, df_rivers, df_AEZ, df_ACLED, df_ESA

# %%
df_FEWSNET_mean_1 = df_FEWSNET_p1.copy()
df_FEWSNET_mean_2 = df_FEWSNET_p2.copy()
df_FEWSNET_mean_3 = df_FEWSNET_p3.copy()
df_FEWSNET_mean_4 = df_FEWSNET_p4.copy()
df_FEWSNET_std_1 = df_FEWSNET_std_p1.copy()
df_FEWSNET_std_2 = df_FEWSNET_std_p2.copy()
df_FEWSNET_std_3 = df_FEWSNET_std_p3.copy()
df_FEWSNET_std_4 = df_FEWSNET_std_p4.copy()
# recsat df_FEWS_mean_1 into long format
df_FEWSNET_mean_1 = df_FEWSNET_mean_1.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_mean')
# find split year_month, use band as column name
df_FEWSNET_mean_1[['year', 'month', 'band']] = df_FEWSNET_mean_1['year_month_band'].str.split('_', expand=True)

# recast into wide format, use band as column name
df_FEWSNET_mean_1 = df_FEWSNET_mean_1.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_mean').reset_index()
# recast df_FEWSNET_mean_2 into long format
df_FEWSNET_mean_2 = df_FEWSNET_mean_2.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_mean')
# find split year_month, use band as column name
df_FEWSNET_mean_2[['year', 'month', 'band']] = df_FEWSNET_mean_2['year_month_band'].str.split('_', expand=True)
# recast into wide format, use band as column name
df_FEWSNET_mean_2 = df_FEWSNET_mean_2.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_mean').reset_index()

# recast df_FEWSNET_mean_3 into long format
df_FEWSNET_mean_3 = df_FEWSNET_mean_3.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_mean')
# find split year_month, use band as column name
df_FEWSNET_mean_3[['year', 'month', 'band']] = df_FEWSNET_mean_3['year_month_band'].str.split('_', expand=True)
# recast into wide format, use band as column name
df_FEWSNET_mean_3 = df_FEWSNET_mean_3.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_mean').reset_index()

# recast df_FEWSNET_mean_4 into long format
df_FEWSNET_mean_4 = df_FEWSNET_mean_4.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_mean')
# find split year_month, use band as column name
df_FEWSNET_mean_4[['year', 'month', 'band']] = df_FEWSNET_mean_4['year_month_band'].str.split('_', expand=True)
# recast into wide format, use band as column name
df_FEWSNET_mean_4 = df_FEWSNET_mean_4.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_mean').reset_index()


# concatenate df_FEWSNET_mean_1, df_FEWSNET_mean_2, df_FEWSNET_mean_3, df_FEWSNET_mean_4
df_FEWSNET_mean = pd.concat([df_FEWSNET_mean_1, df_FEWSNET_mean_2, df_FEWSNET_mean_3, df_FEWSNET_mean_4], axis=0)
# convert region_id, year, monnth to int
df_FEWSNET_mean['region_id'] = df_FEWSNET_mean['region_id'].astype(int)
df_FEWSNET_mean['year'] = df_FEWSNET_mean['year'].astype(int)
df_FEWSNET_mean['month'] = df_FEWSNET_mean['month'].astype(int)

# rename region_id to admin_code
df_FEWSNET_mean = df_FEWSNET_mean.rename(columns={'region_id': 'admin_code'})

# for B1:B28, impute forward
df_FEWSNET_mean.loc[:, 'B1':'B28'] = df_FEWSNET_mean.loc[:, 'B1':'B28'].ffill(axis=0)

# fill the rest with 0
df_FEWSNET_mean.loc[:, 'B1':'B28'] = df_FEWSNET_mean.loc[:, 'B1':'B28'].fillna(0)
# drop duplicates in df_FEWSNET_mean
df_FEWSNET_mean = df_FEWSNET_mean.drop_duplicates(subset=['admin_code', 'year', 'month'], keep='first')
# merge df_IPC and df_FEWSNET_mean on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_FEWSNET_mean, how='left', on=['admin_code', 'year', 'month'], indicator=True)

# %%

# for df_IPC, sort by admin_code, year, month, drop _merge, drop duplicates
df_IPC = df_IPC.sort_values(by=['admin_code', 'year', 'month'], ascending=[True, True, True])
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%


# impute forward for df_IPC, column B1:B28
df_IPC.loc[:, 'B1':'B28'] = df_IPC.loc[:, 'B1':'B28'].ffill(axis=0)
# fill the rest with 0
df_IPC.loc[:, 'B1':'B28'] = df_IPC.loc[:, 'B1':'B28'].fillna(0)
# for df_IPC, B1:B28, fill missing with 0
df_IPC.loc[:, 'B3':'B9'] = df_IPC.loc[:, 'B3':'B9'].fillna(0)
# recast df_FEWSNET_std_1 into long format
df_FEWSNET_std_1 = df_FEWSNET_std_1.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_std')
# find split year_month, use band as column name
df_FEWSNET_std_1[['year', 'month', 'band']] = df_FEWSNET_std_1['year_month_band'].str.split('_', expand=True)
# recast into wide format, use band as column name
df_FEWSNET_std_1 = df_FEWSNET_std_1.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_std').reset_index()
# recast df_FEWSNET_std_2 into long format
df_FEWSNET_std_2 = df_FEWSNET_std_2.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_std')
# find split year_month, use band as column name
df_FEWSNET_std_2[['year', 'month', 'band']] = df_FEWSNET_std_2['year_month_band'].str.split('_', expand=True)
# recast into wide format, use band as column name
df_FEWSNET_std_2 = df_FEWSNET_std_2.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_std').reset_index()
# recast df_FEWSNET_std_3 into long format
df_FEWSNET_std_3 = df_FEWSNET_std_3.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_std')
# find split year_month, use band as column name
df_FEWSNET_std_3[['year', 'month', 'band']] = df_FEWSNET_std_3['year_month_band'].str.split('_', expand=True)
# recast into wide format, use band as column name
df_FEWSNET_std_3 = df_FEWSNET_std_3.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_std').reset_index()
# recast df_FEWSNET_std_4 into long format
df_FEWSNET_std_4 = df_FEWSNET_std_4.melt(id_vars=['region_id'], var_name='year_month_band', value_name='FEWSNET_value_std')
# find split year_month, use band as column name
df_FEWSNET_std_4[['year', 'month', 'band']] = df_FEWSNET_std_4['year_month_band'].str.split('_', expand=True)
# recast into wide format, use band as column name
df_FEWSNET_std_4 = df_FEWSNET_std_4.pivot(index=['region_id', 'year', 'month'], columns='band', values='FEWSNET_value_std').reset_index()
# concatenate df_FEWSNET_std_1, df_FEWSNET_std_2, df_FEWSNET_std_3, df_FEWSNET_std_4
df_FEWSNET_std = pd.concat([df_FEWSNET_std_1, df_FEWSNET_std_2, df_FEWSNET_std_3, df_FEWSNET_std_4], axis=0)
# convert region_id, year, month to int
df_FEWSNET_std['region_id'] = df_FEWSNET_std['region_id'].astype(int)
df_FEWSNET_std['year'] = df_FEWSNET_std['year'].astype(int)
df_FEWSNET_std['month'] = df_FEWSNET_std['month'].astype(int)
# rename region_id to admin_code
df_FEWSNET_std = df_FEWSNET_std.rename(columns={'region_id': 'admin_code'})
# for B1:B28, impute forward
df_FEWSNET_std.loc[:, 'B1':'B28'] = df_FEWSNET_std.loc[:, 'B1':'B28'].ffill(axis=0)
# fill the rest with 0
df_FEWSNET_std.loc[:, 'B1':'B28'] = df_FEWSNET_std.loc[:, 'B1':'B28'].fillna(0)

# merge df_IPC and df_FEWSNET_std on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_FEWSNET_std, how='left', on=['admin_code', 'year', 'month'], indicator=True)
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# for B1_y:B9_y, fill missing with 0
df_IPC.loc[:, 'B1_y':'B9_y'] = df_IPC.loc[:, 'B1_y':'B9_y'].fillna(0)
# release memory
del df_FEWSNET_mean_1, df_FEWSNET_mean_2, df_FEWSNET_mean_3, df_FEWSNET_mean_4, df_FEWSNET_std_1, df_FEWSNET_std_2, df_FEWSNET_std_3, df_FEWSNET_std_4,df_FEWSNET_mean, df_FEWSNET_std

# %%
df_GPP_mean = df_GPP.copy()
# recast df_GPP_mean into long format
df_GPP_mean = df_GPP_mean.melt(id_vars=['region_id'], var_name='year_month', value_name='GPP_mean')
# split year_month into year and month
df_GPP_mean[['year', 'month']] = df_GPP_mean['year_month'].str.split('.M', expand=True)\
# drop year_month
df_GPP_mean = df_GPP_mean.drop(columns=['year_month'])


import re

# Clean month column to keep only numeric part
df_GPP_mean['month'] = df_GPP_mean['month'].astype(str).str.extract(r'(\d+)')[0]

# convert year and month to int
df_GPP_mean['year'] = df_GPP_mean['year'].astype(int)
df_GPP_mean['month'] = df_GPP_mean['month'].astype(int)
# sort by region_id, year, month
df_GPP_mean = df_GPP_mean.sort_values(by=['region_id', 'year', 'month'], ascending=[True, True, True])
# impute forward for df_GPP_mean, column GPP_mean
df_GPP_mean.loc[:, 'GPP_mean'] = df_GPP_mean.loc[:, 'GPP_mean'].ffill(axis=0)
# fill the rest with 0
df_GPP_mean.loc[:, 'GPP_mean'] = df_GPP_mean.loc[:, 'GPP_mean'].fillna(0)
# drop duplicates in df_GPP_mean
df_GPP_mean = df_GPP_mean.drop_duplicates(subset=['region_id', 'year', 'month'], keep='first')
# for GPP_mean<0, set to 0
df_GPP_mean.loc[df_GPP_mean['GPP_mean'] < 0, 'GPP_mean'] = 0
# rename region_id to admin_code
df_GPP_mean = df_GPP_mean.rename(columns={'region_id': 'admin_code'})
# merge df_IPC and df_GPP_mean on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_GPP_mean, how='left', on=['admin_code', 'year', 'month'], indicator=True)

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# for df_IPC, sort by admin_code, year, month, drop _merge, drop duplicates
df_IPC = df_IPC.sort_values(by=['admin_code', 'year', 'month'], ascending=[True, True, True])


# impute forward for df_IPC, column GPP_mean
df_IPC.loc[:, 'GPP_mean'] = df_IPC.loc[:, 'GPP_mean'].ffill(axis=0)
# fill the rest with 0
df_IPC.loc[:, 'GPP_mean'] = df_IPC.loc[:, 'GPP_mean'].fillna(0)

# recast df_GPP_std into long format
df_GPP_std = df_GPP_std.melt(id_vars=['region_id'], var_name='year_month', value_name='GPP_std')
# split year_month into year and month
df_GPP_std[['year', 'month']] = df_GPP_std['year_month'].str.split('.M', expand=True)
# drop year_month
df_GPP_std = df_GPP_std.drop(columns=['year_month'])
# Clean month column to keep only numeric part
df_GPP_std['month'] = df_GPP_std['month'].astype(str).str.extract(r'(\d+)')[0]
# convert year and month to int
df_GPP_std['year'] = df_GPP_std['year'].astype(int)
df_GPP_std['month'] = df_GPP_std['month'].astype(int)
# sort by region_id, year, month
df_GPP_std = df_GPP_std.sort_values(by=['region_id', 'year', 'month'], ascending=[True, True, True])
# impute forward for df_GPP_std, column GPP_std
df_GPP_std.loc[:, 'GPP_std'] = df_GPP_std.loc[:, 'GPP_std'].ffill(axis=0)
# fill the rest with 0
df_GPP_std.loc[:, 'GPP_std'] = df_GPP_std.loc[:, 'GPP_std'].fillna(0)
# drop duplicates in df_GPP_std
df_GPP_std = df_GPP_std.drop_duplicates(subset=['region_id', 'year', 'month'], keep='first')
# for GPP_std<0, set to 0
df_GPP_std.loc[df_GPP_std['GPP_std'] < 0, 'GPP_std'] = 0
# rename region_id to admin_code
df_GPP_std = df_GPP_std.rename(columns={'region_id': 'admin_code'})
# merge df_IPC and df_GPP_std on admin_code, year, month
df_IPC = pd.merge(df_IPC, df_GPP_std, how='left', on=['admin_code', 'year', 'month'], indicator=True)
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
# for df_IPC, sort by admin_code, year, month, drop _merge, drop duplicates
df_IPC = df_IPC.sort_values(by=['admin_code', 'year', 'month'], ascending=[True, True, True])
# impute forward for df_IPC, column GPP_std
df_IPC.loc[:, 'GPP_std'] = df_IPC.loc[:, 'GPP_std'].ffill(axis=0)
# fill the rest with 0
df_IPC.loc[:, 'GPP_std'] = df_IPC.loc[:, 'GPP_std'].fillna(0)

del df_GPP_mean, df_GPP_std

# %%

# keep only admin_code and soil columns from sg_cec_5-15cm to sg_soc_5-15cm
soil_cols = df_soil.columns.tolist()
start = soil_cols.index('sg_cec_5-15cm')
end = soil_cols.index('sg_soc_5-15cm') + 1

# %%
#drop columns title, country, ISO2, ISO3
df_soil = df_soil.drop(columns=['title', 'country', 'ISO2', 'ISO3'])
#convert df_soil lat and lon to float type
df_soil['lat'] = df_soil['lat'].astype(float)
df_soil['lon'] = df_soil['lon'].astype(float)


# pad lat and lon in df_soil with 12 decimal places
df_soil['lat'] = df_soil['lat'].apply(lambda x: '{:.12f}'.format(x))
df_soil['lon'] = df_soil['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_soil
df_soil = df_soil.drop_duplicates(subset=['lat', 'lon'])
# rename as lat_fixed and lon_fixed
df_soil = df_soil.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})
# merge df_IPC and df_soil on admin_code
df_IPC = pd.merge(df_IPC, df_soil, how='left', on=['lat_fixed','lon_fixed'], indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# drop country,title, ISO2, ISO3 from df_market_access
df_market_access = df_market_access.drop(columns=['country', 'title', 'ISO2', 'ISO3'])

# convert df_market_access lat and lon to float type
df_market_access['lat'] = df_market_access['lat'].astype(float)
df_market_access['lon'] = df_market_access['lon'].astype(float)
# pad lat and lon in df_market_access with 12 decimal places
df_market_access['lat'] = df_market_access['lat'].apply(lambda x: '{:.12f}'.format(x))
df_market_access['lon'] = df_market_access['lon'].apply(lambda x: '{:.12f}'.format(x))
# impute forward for df_market_access, column market_access
df_market_access.loc[:, 'market_access'] = df_market_access.loc[:, 'market_access'].ffill(axis=0)
# fill the rest with 0
df_market_access.loc[:, 'market_access'] = df_market_access.loc[:, 'market_access'].fillna(0)
# drop duplicates in df_market_access
df_market_access = df_market_access.drop_duplicates(subset=['lat', 'lon'], keep='first')
# rename as lat_fixed and lon_fixed
df_market_access = df_market_access.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})
# merge df_IPC and df_market_access on admin_code
df_IPC = pd.merge(df_IPC, df_market_access, how='left', on=['lat_fixed','lon_fixed'], indicator=True)

# %%

df_IPC = df_IPC.drop(columns=['_merge'])

# %%


# sort by admin_code, year, month
df_IPC = df_IPC.sort_values(by=['lat','lon', 'year', 'month'], ascending=[True, True, True,True])

# drop duplicates in df_IPC
df_IPC = df_IPC.drop_duplicates(subset=['lat','lon', 'year', 'month'], keep='first')

# impute forward for df_IPC, column sg_soc_5-15cm
df_IPC.loc[:, 'sg_soc_5-15cm'] = df_IPC.loc[:, 'sg_soc_5-15cm'].ffill(axis=0)
# fill the rest with 0
df_IPC.loc[:, 'sg_soc_5-15cm'] = df_IPC.loc[:, 'sg_soc_5-15cm'].fillna(0)
del df_market_access

# %%
del df_FEWSNET_p1, df_FEWSNET_p2, df_FEWSNET_p3, df_FEWSNET_p4, df_FEWSNET_std_p1, df_FEWSNET_std_p2, df_FEWSNET_std_p3, df_FEWSNET_std_p4, df_EVI, df_GPP,

# %%
del df_soil, end, start, soil_cols

# %%

# keep only admin_code, ruggedness from df_ruggedness
df_ruggedness = df_ruggedness[['lat','lon', 'ruggedness']]
# convert df_ruggedness lat and lon to float type
df_ruggedness['lat'] = df_ruggedness['lat'].astype(float)
df_ruggedness['lon'] = df_ruggedness['lon'].astype(float)

# pad lat and lon in df_ruggedness with 12 decimal places
df_ruggedness['lat'] = df_ruggedness['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ruggedness['lon'] = df_ruggedness['lon'].apply(lambda x: '{:.12f}'.format(x))
# sort by admin_code
df_ruggedness = df_ruggedness.sort_values(by=['lat','lon'], ascending=[True,True])
# impute forward for df_ruggedness, column ruggedness
df_ruggedness.loc[:, 'ruggedness'] = df_ruggedness.loc[:, 'ruggedness'].ffill(axis=0)
# fill the rest with 0
df_ruggedness.loc[:, 'ruggedness'] = df_ruggedness.loc[:, 'ruggedness'].fillna(0)
# drop duplicates in df_ruggedness
df_ruggedness = df_ruggedness.drop_duplicates(subset=['lat','lon'], keep='first')

# rename as lat_fixed and lon_fixed
df_ruggedness = df_ruggedness.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})


# merge df_IPC and df_ruggedness on lat, lon
df_IPC = pd.merge(df_IPC, df_ruggedness, how='left', on=['lat_fixed','lon_fixed'], indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# del df_ruggedness
del df_ruggedness

# %%

# for df_slope, keep only lat, lon, slope
df_slope = df_slope[['lat','lon', 'slope']]
# convert lat and lon to float type
df_slope['lat'] = df_slope['lat'].astype(float)
df_slope['lon'] = df_slope['lon'].astype(float)

# sort by lat, lon
df_slope = df_slope.sort_values(by=['lat','lon'], ascending=[True,True])
# impute forward for df_slope, column slope
df_slope.loc[:, 'slope'] = df_slope.loc[:, 'slope'].ffill(axis=0)
# fill the rest with 0
df_slope.loc[:, 'slope'] = df_slope.loc[:, 'slope'].fillna(0)
# drop duplicates in df_slope
df_slope = df_slope.drop_duplicates(subset=['lat','lon'], keep='first')

# pad lat and lon in df_slope with 12 decimal places
df_slope['lat'] = df_slope['lat'].apply(lambda x: '{:.12f}'.format(x))
df_slope['lon'] = df_slope['lon'].apply(lambda x: '{:.12f}'.format(x))

# rename as lat_fixed and lon_fixed
df_slope = df_slope.rename(columns={'lat': 'lat_fixed', 'lon': 'lon_fixed'})

# %%


# merge df_IPC and df_slope on lat, lon
df_IPC = pd.merge(df_IPC, df_slope, how='left', on=['lat_fixed','lon_fixed'], indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%

# del df_slope
del df_slope

# %%

# keep only lat, lon, year, month, CPI, GDP, CC, gini from df_wbg
df_wbg = df_wbg[['lat','lon', 'year', 'month', 'CPI', 'GDP', 'CC', 'gini']]
# sort by lat, lon, year, month
df_wbg = df_wbg.sort_values(by=['lat', 'lon', 'year', 'month'], ascending=[True, True, True, True])
# drop duplicates in df_wbg
df_wbg = df_wbg.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')

# %%
#convert lat and lon to float type
df_wbg['lat'] = df_wbg['lat'].astype(float)
df_wbg['lon'] = df_wbg['lon'].astype(float)

# %%
# pad lat and lon in df_wbg with 12 decimal places
df_wbg['lat'] = df_wbg['lat'].apply(lambda x: '{:.12f}'.format(x))
df_wbg['lon'] = df_wbg['lon'].apply(lambda x: '{:.12f}'.format(x))
# merge df_IPC and df_wbg on lat, lon, year, month
df_IPC = pd.merge(df_IPC, df_wbg, how='left', on=['lat', 'lon', 'year', 'month'], indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# drop duplicates in df_IPC
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')
# del df_wbg
del df_wbg

# %%

# for df_wfp, keep only lat, lon, year, month, WFP_Price, WFP_Price_std
df_wfp = df_wfp[['lat', 'lon', 'year', 'month', 'WFP_Price', 'WFP_Price_std']]

# convert lat and lon to float type
df_wfp['lat'] = df_wfp['lat'].astype(float)
df_wfp['lon'] = df_wfp['lon'].astype(float)
# sort by lat, lon, year, month
df_wfp = df_wfp.sort_values(by=['lat', 'lon', 'year', 'month'], ascending=[True, True, True, True])
# drop duplicates in df_wfp
df_wfp = df_wfp.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')
# pad lat and lon in df_wfp with 12 decimal places
df_wfp['lat'] = df_wfp['lat'].apply(lambda x: '{:.12f}'.format(x))
df_wfp['lon'] = df_wfp['lon'].apply(lambda x: '{:.12f}'.format(x))
# merge df_IPC and df_wfp on lat, lon, year, month
df_IPC = pd.merge(df_IPC, df_wfp, how='left', on=['lat', 'lon', 'year', 'month'], indicator=True)

# %%

# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# drop duplicates in df_IPC
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')

# %%
del df_wfp

# %%

# rename b1_x:b28_x
colnames = ['B1_x','B1_y','B2_x','B2_y','B3_x','B3_y','B4_x','B4_y','B5_x','B5_y','B6_x','B6_y','B7_x','B7_y','B8_x','B8_y','B9_x','B9_y','B10_x','B10_y','B11_x','B11_y','B12_x','B12_y','B13_x','B13_y','B14_x','B14_y','B15_x','B15_y','B16_x','B16_y','B17_x','B17_y', 'B18_x', 'B18_y', 'B19_x', 'B19_y', 'B20_x', 'B20_y', 'B21_x', 'B21_y', 'B22_x', 'B22_y', 'B23_x', 'B23_y', 'B24_x', 'B24_y', 'B25_x', 'B25_y', 'B26_x', 'B26_y', 'B27_x', 'B27_y', 'B28_x', 'B28_y']

new_colnames = ['Evap_tavg_mean', 'Evap_tavg_stdDev', 'LWdown_f_tavg_mean', 'LWdown_f_tavg_stdDev', 'Lwnet_tavg_mean', 'Lwnet_tavg_stdDev', 'Psurf_f_tavg_mean', 'Psurf_f_tavg_stdDev', 'Qair_f_tavg_mean', 'Qair_f_tavg_stdDev', 'Qg_tavg_mean', 'Qg_tavg_stdDev', 'Qh_tavg_mean', 'Qh_tavg_stdDev', 'Qle_tavg_mean', 'Qle_tavg_stdDev', 'Qs_tavg_mean', 'Qs_tavg_stdDev', 'Qsb_tavg_mean', 'Qsb_tavg_stdDev', 'RadT_tavg_mean', 'RadT_tavg_stdDev', 'Rainf_f_tavg_mean', 'Rainf_f_tavg_stdDev', 'SnowCover_inst_mean', 'SnowCover_inst_stdDev', 'SnowDepth_inst_mean', 'SnowDepth_inst_stdDev', 'Snowf_tavg_mean', 'Snowf_tavg_stdDev', 'SoilMoi00_10cm_tavg_mean', 'SoilMoi00_10cm_tavg_stdDev', 'SoilMoi10_40cm_tavg_mean', 'SoilMoi10_40cm_tavg_stdDev', 'SoilMoi100_200cm_tavg_mean', 'SoilMoi100_200cm_tavg_stdDev', 'SoilMoi40_100cm_tavg_mean', 'SoilMoi40_100cm_tavg_stdDev', 'SoilTemp00_10cm_tavg_mean', 'SoilTemp00_10cm_tavg_stdDev', 'SoilTemp10_40cm_tavg_mean', 'SoilTemp10_40cm_tavg_stdDev', 'SoilTemp100_200cm_tavg_mean', 'SoilTemp100_200cm_tavg_stdDev', 'SoilTemp40_100cm_tavg_mean', 'SoilTemp40_100cm_tavg_stdDev', 'SWdown_f_tavg_mean', 'SWdown_f_tavg_stdDev', 'SWE_inst_mean', 'SWE_inst_stdDev', 'Swnet_tavg_mean', 'Swnet_tavg_stdDev', 'Tair_f_tavg_mean', 'Tair_f_tavg_stdDev', 'Wind_f_tavg_mean', 'Wind_f_tavg_stdDev']


# rename columns in df_IPC
for i in range(len(colnames)):
    df_IPC = df_IPC.rename(columns={colnames[i]: new_colnames[i]})

# %%
del colnames, i, new_colnames, ch_geoidentifier

# %%
# from distance_to_nearest_acled to sum_fatalities_violence_w10, impute with 0
df_IPC.loc[:, 'distance_to_nearest_acled':'sum_fatalities_violence_w10'] = df_IPC.loc[:, 'distance_to_nearest_acled':'sum_fatalities_violence_w10'].fillna(0)

# %%
# from AEZ_10000 to AEZ_9000, replace value ,True=1, False=0, missing=0
for col in df_IPC.columns:
    if col.startswith('AEZ_'):
        df_IPC[col] = df_IPC[col].replace({True: 1, False: 0, np.nan: 0})

# %%
# imput crop, range missing with 0
df_IPC.loc[:, 'crop'] = df_IPC.loc[:, 'crop'].fillna(0)
df_IPC.loc[:, 'range'] = df_IPC.loc[:, 'range'].fillna(0)

# %%
# impute forward for distance_to_river,nightlight_mean, nightlight_std
df_IPC.loc[:, 'distance_to_river'] = df_IPC.loc[:, 'distance_to_river'].ffill(axis=0)
df_IPC.loc[:, 'nightlight_mean'] = df_IPC.loc[:, 'nightlight_mean'].ffill(axis=0)
df_IPC.loc[:, 'nightlight_std'] = df_IPC.loc[:, 'nightlight_std'].ffill(axis=0)

# %%
# for sg_cec_5-15cm to sg_phh2o_5-15cm, impute forward
df_IPC.loc[:, 'sg_cec_5-15cm':'sg_phh2o_5-15cm'] = df_IPC.loc[:, 'sg_cec_5-15cm':'sg_phh2o_5-15cm'].ffill(axis=0)

# %%
# the maximum value of admin_code
df_IPC['admin_code'].max()

# %%
missing_admin_code = df_IPC[df_IPC['admin_code'].isnull()]

# %%
# extract rows where admin_code is missing

# filter rows where admin_code is not null
df_IPC = df_IPC[df_IPC['admin_code'].notnull()]




# for missing admin_code, group by lat and lon, assign an admin_code starting from the maximum value + 1
max_admin_code = int(df_IPC['admin_code'].max()+100000)
missing_admin_code['admin_code'] = missing_admin_code.groupby(['lat','lon']).ngroup() + max_admin_code

# concatenate df_IPC and missing_admin_code
df_IPC = pd.concat([df_IPC, missing_admin_code], axis=0)

# %%
# export the final df_IPC to a csv file
df_IPC.to_csv('chcountries_final_v12022025.csv', index=False)
