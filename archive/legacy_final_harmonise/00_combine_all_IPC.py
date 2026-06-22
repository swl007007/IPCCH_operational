# Converted from Final_harmonise/00_combine_all_IPC.ipynb

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


df_ACLED = pd.read_csv(r'ACLED\ipc_with_merged_acled_metrics.csv')
df_AEZ = pd.read_csv(r'AEZ\IPC_aez_completed.csv')
df_ASAP = pd.read_csv(r'ASAP_land_cover\IPC_ASAP_completed.csv')
df_rivers = pd.read_csv(r'Distance_to_rivers\IPC_distance_to_river_completed.csv')
df_nightlight = pd.read_csv(r'DMSP_OLS\old_methods\IPC_nightlight_completed_final.csv')
df_elevation = pd.read_csv(r'Elevation\IPC_elevation_completed.csv')
df_ESA = pd.read_csv(r'ESA\IPC_ESA_completed.csv')
df_EVI = pd.read_csv(r'EVI\old_methods\IPC_EVI_completed_final.csv')
df_FAO = pd.read_csv(r'FAO\IPC_with_matched_markets.csv')
df_FEWSNET = pd.read_csv(r'FEWSNET_predictors\old_methods\IPC_fldas_fewsnet_completed.csv')
df_GPP = pd.read_csv(r'GOSIF_GPP\old_methods\IPC_GPP_complete.csv')
df_soil = pd.read_csv(r'ISRIC\IPC_soilgrids_completed.csv')
df_market_access = pd.read_csv(r'Market_access\IPC_market_access_completed.csv')
df_ruggedness = pd.read_csv(r'Ruggedness\IPC_ruggedness_completed.csv')
df_slope =  pd.read_csv(r'Slope\IPC_slope_completed.csv')
df_wbg = pd.read_csv(r'WBG\IPC_WBG_completed.csv')
df_wfp = pd.read_csv(r'WFP\IPC_WFP_prices.csv')



IPC_geoidentifier = pd.read_csv(r'Outcome\IPC_2017_2025\geoidentifier.csv')


# pad df_ESA with 12 decimal places
df_ESA['lat'] = df_ESA['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ESA['lon'] = df_ESA['lon'].apply(lambda x: '{:.12f}'.format(x))
df_ACLED['lat'] = df_ACLED['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ACLED['lon'] = df_ACLED['lon'].apply(lambda x: '{:.12f}'.format(x))
# merge df_ACLED with df_ESA
df_IPC = pd.merge(df_ACLED, df_ESA, on=['lat', 'lon'], how='left', indicator=True)
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

#df_AEZ drop lat and lon, then append df_ESA[['lat', 'lon']] to df_AEZ
df_AEZ = df_AEZ.drop(columns=['lat', 'lon'])
df_AEZ = pd.concat([df_AEZ, df_ESA[['lat', 'lon']]], axis=1)
# merge df_IPC with df_AEZ
df_IPC = pd.merge(df_IPC, df_AEZ, on=['lat', 'lon'], how='left', indicator=True)
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
# pad lat and lon in df_ASAP with 12 decimal places
df_ASAP['lat'] = df_ASAP['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ASAP['lon'] = df_ASAP['lon'].apply(lambda x: '{:.12f}'.format(x))
# merge df_IPC with df_ASAP
df_IPC = pd.merge(df_IPC, df_ASAP, on=['lat', 'lon'], how='left', indicator=True)
# drop duplicates in lat lon year month, keep first
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')
df_IPC = df_IPC.drop(columns=['_merge'])
#pad lat and lon in df_rivers with 12 decimal places
df_rivers['lat'] = df_rivers['lat'].apply(lambda x: '{:.12f}'.format(x))
df_rivers['lon'] = df_rivers['lon'].apply(lambda x: '{:.12f}'.format(x))

# merge df_IPC with df_rivers
df_IPC = pd.merge(df_IPC, df_rivers, on=['lat', 'lon'], how='left', indicator=True)
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
# drop duplcicates in lat lon year month, keep first
df_IPC = df_IPC.drop_duplicates(subset=['lat', 'lon', 'year', 'month'], keep='first')
# for df_nigthtlight, drop lat lon row_id
df_nightlight = df_nightlight.drop(columns=['lat', 'lon', 'row_id'])
# drop duplicates in area_id, year, month, keep first
df_nightlight = df_nightlight.drop_duplicates(subset=['area_id', 'year', 'month'], keep='first')
# merge df_IPC with df_nightlight on area_id, year, month
df_IPC = pd.merge(df_IPC, df_nightlight, on=['area_id', 'year', 'month'], how='left', indicator=True)
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
#pad lat and lon in df_elevation with 12 decimal places
df_elevation['lat'] = df_elevation['lat'].apply(lambda x: '{:.12f}'.format(x))
df_elevation['lon'] = df_elevation['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_elevation, keep first
df_elevation = df_elevation.drop_duplicates(subset=['lat', 'lon'], keep='first')

# merge df_IPC with df_elevation
df_IPC = pd.merge(df_IPC, df_elevation, on=['lat', 'lon'], how='left', indicator=True)
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
# drop lat lon row_id for df_EVI
df_EVI = df_EVI.drop(columns=['lat', 'lon', 'row_id'])
# drop duplicates in area_id, year, month, keep first
df_EVI = df_EVI.drop_duplicates(subset=['area_id', 'year', 'month'], keep='first')
# merge df_IPC with df_EVI on area_id, year, month
df_IPC = pd.merge(df_IPC, df_EVI, on=['area_id', 'year', 'month'], how='left', indicator=True)
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
#drop lat lon row_id for df_FAO
df_FAO = df_FAO.drop(columns=['lat', 'lon', 'row_id'])
# drop duplicates in area_id, year, month, keep first
df_FAO = df_FAO.drop_duplicates(subset=['area_id', 'year', 'month'], keep='first')
# merge df_IPC with df_FAO on area_id, year, month
df_IPC = pd.merge(df_IPC, df_FAO, on=['area_id', 'year', 'month'], how='left', indicator=True)
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
#df_FEWSNET drop lat lon
df_FEWSNET = df_FEWSNET.drop(columns = ['lat','lon'])

df_FEWSNET = df_FEWSNET.drop_duplicates(subset=['area_id', 'year', 'month'], keep='first')

df_IPC = pd.merge(df_IPC, df_FEWSNET, on=['area_id', 'year', 'month'], how='left', indicator=True)
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
#pad lat and lon in df_GPP with 12 decimal places
df_GPP['lat'] = df_GPP['lat'].apply(lambda x: '{:.12f}'.format(x))
df_GPP['lon'] = df_GPP['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_elevation, keep first
df_GPP= df_GPP.drop_duplicates(subset=['lat', 'lon','year','month'], keep='first')

# merge df_IPC with df_elevation
df_IPC = pd.merge(df_IPC, df_GPP, on=['lat', 'lon','year','month'], how='left', indicator=True)
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
#pad lat and lon in df_soil with 12 decimal places
df_soil['lat'] = df_soil['lat'].apply(lambda x: '{:.12f}'.format(x))
df_soil['lon'] = df_soil['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_soil, keep first
df_soil= df_soil.drop_duplicates(subset=['lat', 'lon'], keep='first')

# merge df_IPC with df_soil
df_IPC = pd.merge(df_IPC, df_soil, on=['lat', 'lon'], how='left', indicator=True)


#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])
#pad lat and lon in df_market_access with 12 decimal places
df_market_access['lat'] = df_market_access['lat'].apply(lambda x: '{:.12f}'.format(x))
df_market_access['lon'] = df_market_access['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_market_access, keep first
df_market_access= df_market_access.drop_duplicates(subset=['lat', 'lon'], keep='first')

# merge df_IPC with df_market_access
df_IPC = pd.merge(df_IPC, df_market_access, on=['lat', 'lon'], how='left', indicator=True)
# drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# pad lat and lon in df_ruggedness with 12 decimal places
df_ruggedness['lat'] = df_ruggedness['lat'].apply(lambda x: '{:.12f}'.format(x))
df_ruggedness['lon'] = df_ruggedness['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_ruggedness, keep first
df_ruggedness= df_ruggedness.drop_duplicates(subset=['lat', 'lon'], keep='first')

# merge df_IPC with df_ruggedness
df_IPC = pd.merge(df_IPC, df_ruggedness, on=['lat', 'lon'], how='left', indicator=True)

# %%
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# pad lat and lon in df_slope with 12 decimal places
df_slope['lat'] = df_slope['lat'].apply(lambda x: '{:.12f}'.format(x))
df_slope['lon'] = df_slope['lon'].apply(lambda x: '{:.12f}'.format(x))

# drop duplicates in lat lon in df_slope, keep first
df_slope= df_slope.drop_duplicates(subset=['lat', 'lon'], keep='first')

# merge df_IPC with df_slope
df_IPC = pd.merge(df_IPC, df_slope, on=['lat', 'lon'], how='left', indicator=True)

# %%
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# for df_wbg, drop lat lon row_id country_code_3
df_wbg = df_wbg.drop(columns=['lat', 'lon', 'row_id','country_code_3'])
# drop duplicates in area_id, year, month, keep first
df_wbg = df_wbg.drop_duplicates(subset=['area_id', 'year', 'month'], keep='first')

# merge df_IPC with df_wbg on area_id, year, month
df_IPC = pd.merge(df_IPC, df_wbg, on=['area_id', 'year', 'month'], how='left', indicator=True)

# %%
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
# for df_wbg, drop lat lon row_id
df_wfp = df_wfp.drop(columns=['lat', 'lon', 'row_id'])
# drop duplicates in area_id, year, month, keep first
df_wfp = df_wfp.drop_duplicates(subset=['area_id', 'year', 'month'], keep='first')
# merge df_IPC with df_wfp on area_id, year, month
df_IPC = pd.merge(df_IPC, df_wfp, on=['area_id', 'year', 'month'], how='left', indicator=True)

# %%
#drop _merge
df_IPC = df_IPC.drop(columns=['_merge'])

# %%
#order column by lat lon year month
df_IPC = df_IPC[['lat', 'lon', 'year', 'month'] + [col for col in df_IPC.columns if col not in ['lat', 'lon', 'year', 'month']]]

# %%
# sort value  by lat lon year month
df_IPC = df_IPC.sort_values(by=['lat', 'lon', 'year', 'month'], ascending=[True, True, True, True])

# %%
import polars

# covert df_IPC to polars dataframe
df_IPC_polars = polars.from_pandas(df_IPC)

# %%
# see df_IPC_polars columns
df_IPC_polars.columns

# %%
# impute 'distance_to_nearest_acled', 'event_count_battles', 'event_count_explosions', 'event_count_violence', 'sum_fatalities_battles', 'sum_fatalities_explosions', 'sum_fatalities_violence', 'event_count_battles_w5', 'event_count_explosions_w5', 'event_count_violence_w5',
#'sum_fatalities_battles_w5', 'sum_fatalities_explosions_w5', 'sum_fatalities_violence_w5', 'event_count_battles_w10', 'event_count_explosions_w10', 'event_count_violence_w10', 'sum_fatalities_battles_w10', 'sum_fatalities_explosions_w10', 'sum_fatalities_violence_w10' by backward fill

df_IPC_polars = df_IPC_polars.with_columns(
    [polars.col('distance_to_nearest_acled').fill_null(strategy='backward'),
     polars.col('event_count_battles').fill_null(strategy='backward'),
        polars.col('event_count_explosions').fill_null(strategy='backward'),
        polars.col('event_count_violence').fill_null(strategy='backward'),
        polars.col('sum_fatalities_battles').fill_null(strategy='backward'),
        polars.col('sum_fatalities_explosions').fill_null(strategy='backward'),
        polars.col('sum_fatalities_violence').fill_null(strategy='backward'),
        polars.col('event_count_battles_w5').fill_null(strategy='backward'),
        polars.col('event_count_explosions_w5').fill_null(strategy='backward'),
        polars.col('event_count_violence_w5').fill_null(strategy='backward'),
        polars.col('sum_fatalities_battles_w5').fill_null(strategy='backward'),
        polars.col('sum_fatalities_explosions_w5').fill_null(strategy='backward'),
        polars.col('sum_fatalities_violence_w5').fill_null(strategy='backward'),
        polars.col('event_count_battles_w10').fill_null(strategy='backward'),
        polars.col('event_count_explosions_w10').fill_null(strategy='backward'),
        polars.col('event_count_violence_w10').fill_null(strategy='backward'),
        polars.col('sum_fatalities_battles_w10').fill_null(strategy='backward'),
        polars.col('sum_fatalities_explosions_w10').fill_null(strategy='backward'),
        polars.col('sum_fatalities_violence_w10').fill_null(strategy='backward')]
)

# %%

# impute distance_to_river,nightlight,nightlight_sd,'Evap_tavg_mean','Evap_tavg_stdDev','LWdown_f_tavg_mean','LWdown_f_tavg_stdDev','Lwnet_tavg_mean','Lwnet_tavg_stdDev','Psurf_f_tavg_mean','Psurf_f_tavg_stdDev','Qair_f_tavg_mean',
#'Qair_f_tavg_stdDev','Qg_tavg_mean','Qg_tavg_stdDev','Qh_tavg_mean','Qh_tavg_stdDev','Qle_tavg_mean','Qle_tavg_stdDev','Qs_tavg_mean','Qs_tavg_stdDev','Qsb_tavg_mean','Qsb_tavg_stdDev','RadT_tavg_mean','RadT_tavg_stdDev','Rainf_f_tavg_mean',
#'Rainf_f_tavg_stdDev','SnowCover_inst_mean','SnowCover_inst_stdDev','SnowDepth_inst_mean','SnowDepth_inst_stdDev','Snowf_tavg_mean','Snowf_tavg_stdDev','SoilMoi00_10cm_tavg_mean','SoilMoi00_10cm_tavg_stdDev','SoilMoi10_40cm_tavg_mean','SoilMoi10_40cm_tavg_stdDev',
# 'SoilMoi100_200cm_tavg_mean','SoilMoi100_200cm_tavg_stdDev','SoilMoi40_100cm_tavg_mean','SoilMoi40_100cm_tavg_stdDev','SoilTemp00_10cm_tavg_mean','SoilTemp00_10cm_tavg_stdDev','SoilTemp10_40cm_tavg_mean','SoilTemp10_40cm_tavg_stdDev','SoilTemp100_200cm_tavg_mean','SoilTemp100_200cm_tavg_stdDev','SoilTemp40_100cm_tavg_mean',
#'SoilTemp40_100cm_tavg_stdDev','SWdown_f_tavg_mean','SWdown_f_tavg_stdDev','SWE_inst_mean','SWE_inst_stdDev','Swnet_tavg_mean','Swnet_tavg_stdDev','Tair_f_tavg_mean','Tair_f_tavg_stdDev','Wind_f_tavg_mean','Wind_f_tavg_stdDev','nitrogen_5-15cm_mean',
#'phh2o_5-15cm_mean','cec_5-15cm_mean','cfvo_5-15cm_mean','soc_5-15cm_mean' with linear interpolation

df_IPC_polars = df_IPC_polars.with_columns(
    [polars.col('distance_to_river').interpolate(),
     polars.col('nightlight').interpolate(),
        polars.col('nightlight_sd').interpolate(),
        polars.col('Evap_tavg_mean').interpolate(),
        polars.col('Evap_tavg_stdDev').interpolate(),
        polars.col('LWdown_f_tavg_mean').interpolate(),
        polars.col('LWdown_f_tavg_stdDev').interpolate(),
        polars.col('Lwnet_tavg_mean').interpolate(),
        polars.col('Lwnet_tavg_stdDev').interpolate(),
        polars.col('Psurf_f_tavg_mean').interpolate(),
        polars.col('Psurf_f_tavg_stdDev').interpolate(),
        polars.col('Qair_f_tavg_mean').interpolate(),
        polars.col('Qair_f_tavg_stdDev').interpolate(),
        polars.col('Qg_tavg_mean').interpolate(),
        polars.col('Qg_tavg_stdDev').interpolate(),
        polars.col('Qh_tavg_mean').interpolate(),
        polars.col('Qh_tavg_stdDev').interpolate(),
        polars.col('Qle_tavg_mean').interpolate(),
        polars.col('Qle_tavg_stdDev').interpolate(),
        polars.col('Qs_tavg_mean').interpolate(),
        polars.col('Qs_tavg_stdDev').interpolate(),
        polars.col('Qsb_tavg_mean').interpolate(),
        polars.col('Qsb_tavg_stdDev').interpolate(),
        polars.col('RadT_tavg_mean').interpolate(),
        polars.col('RadT_tavg_stdDev').interpolate(),
        polars.col('Rainf_f_tavg_mean').interpolate(),
        polars.col('Rainf_f_tavg_stdDev').interpolate(),
        polars.col('SnowCover_inst_mean').interpolate(),
        polars.col('SnowCover_inst_stdDev').interpolate(),
        polars.col('SnowDepth_inst_mean').interpolate(),
        polars.col('SnowDepth_inst_stdDev').interpolate(),
        polars.col('Snowf_tavg_mean').interpolate(),
        polars.col('Snowf_tavg_stdDev').interpolate(),
        polars.col('SoilMoi00_10cm_tavg_mean').interpolate(), 
        polars.col('SoilMoi00_10cm_tavg_stdDev').interpolate(),
        polars.col('SoilMoi10_40cm_tavg_mean').interpolate(),
        polars.col('SoilMoi10_40cm_tavg_stdDev').interpolate(),
        polars.col('SoilMoi100_200cm_tavg_mean').interpolate(),
        polars.col('SoilMoi100_200cm_tavg_stdDev').interpolate(),
        polars.col('SoilMoi40_100cm_tavg_mean').interpolate(),
        polars.col('SoilMoi40_100cm_tavg_stdDev').interpolate(),
        polars.col('SoilTemp00_10cm_tavg_mean').interpolate(),
        polars.col('SoilTemp00_10cm_tavg_stdDev').interpolate(),
        polars.col('SoilTemp10_40cm_tavg_mean').interpolate(),
        polars.col('SoilTemp10_40cm_tavg_stdDev').interpolate(),
        polars.col('SoilTemp100_200cm_tavg_mean').interpolate(),
        polars.col('SoilTemp100_200cm_tavg_stdDev').interpolate(),
        polars.col('SoilTemp40_100cm_tavg_mean').interpolate(),
        polars.col('SoilTemp40_100cm_tavg_stdDev').interpolate(),
        polars.col('SWdown_f_tavg_mean').interpolate(),
        polars.col('SWdown_f_tavg_stdDev').interpolate(),
        polars.col('SWE_inst_mean').interpolate(),
        polars.col('SWE_inst_stdDev').interpolate(),
        polars.col('Swnet_tavg_mean').interpolate(),
        polars.col('Swnet_tavg_stdDev').interpolate(),
        polars.col('Tair_f_tavg_mean').interpolate(),
        polars.col('Tair_f_tavg_stdDev').interpolate(),
        polars.col('Wind_f_tavg_mean').interpolate(),
        polars.col('Wind_f_tavg_stdDev').interpolate(),
        polars.col('nitrogen_5-15cm_mean').interpolate(),
        polars.col('phh2o_5-15cm_mean').interpolate(),
        polars.col('cec_5-15cm_mean').interpolate(),
        polars.col('cfvo_5-15cm_mean').interpolate(),
        polars.col('soc_5-15cm_mean').interpolate()]
    
)

# %%
#save to csv
df_IPC_polars.write_csv(r'IPC_2017_2025_assembled.csv')
