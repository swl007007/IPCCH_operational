# Converted from WFP_indicator/00_add_WFP_ch.ipynb

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
wfp_raw_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wfp_raw_file'),
    'WFP raw input'
)
wfp_scaffold_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wfp_scaffold_file'),
    'WFP scaffold input'
)
wfp_esa_lookup_file = require_file(
    resolve_path(CONFIG, 'tabular', 'wfp_esa_lookup_file'),
    'WFP ESA lookup input'
)
wfp_output_file = resolve_path(CONFIG, 'tabular', 'wfp_output_file')

# %%
import numpy as np
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import tqdm
import time
#set working directory
import os
import pycountry

# Define a proper function for requests with retry and custom headers
def requests_retry_session(retries=3, backoff_factor=0.3):
    session = requests.Session()
    # Set a proper user agent - THIS IS CRITICAL FOR NOMINATIM
    session.headers.update({
        'User-Agent': 'YourAppName/1.0 (your.email@example.com)',  # Use your actual info here
    })
    return session

def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def get_country_name(code):
    country = pycountry.countries.get(alpha_2=code)
    if country:
        return country.name
    else:
        return None
# read data
df = pd.read_csv(wfp_raw_file)
# format Price Date to datetime
df['Price Date'] = pd.to_datetime(df['Price Date'])
# keep only Country, Admin 1, Admin 2, Market Name, Commodity, Price Date, Trend

df = df[['Country', 'Admin 1', 'Admin 2', 'Market Name', 'Commodity', 'Price Date', 'Trend']]
# rename Country to country_name, Admin 1 to admin1, Admin 2 to admin2, Market Name to market_name, Commodity to commodity_name, Price Date to price_date, Trend to trend
df = df.rename(columns={
    'Country': 'country_name',
    'Admin 1': 'admin1',
    'Admin 2': 'admin2',
    'Market Name': 'market_name',
    'Commodity': 'commodity_name',
    'Price Date': 'price_date',
    'Trend': 'trend'
})
# extract year and month from price_date
df['year'] = df['price_date'].dt.year
df['month'] = df['price_date'].dt.month
#drop price_date
df = df.drop(columns=['price_date'])
#drop commodity_name
df = df.drop(columns=['commodity_name'])
# group by country_name, admin1, admin2, market_name, year, month, aggregate the mean and std of trend
df = df.groupby(['country_name','year', 'month']).agg(
    trend_mean=('trend', 'mean'),
    trend_std=('trend', 'std')
).reset_index()
# create an address column combining country_name, admin1, admin2, market_name (using , as separator)
#drop NAs in trend
df = df.dropna(subset=['trend_mean'])
#rename trend to WFP_Price
df = df.rename(columns={'trend_mean': 'WFP_Price', 'trend_std': 'WFP_Price_std'})

# %%
# convert country_name to three digit code
def convert_country_name_to_code(country_name):
    try:
        # Get the country object using the name
        country = pycountry.countries.lookup(country_name)
        # Return the alpha_3 code
        return country.alpha_3
    except LookupError:
        # If the country name is not found, return None or handle it as needed
        return None

# Apply the function to the 'country_name' column
df['country_code'] = df['country_name'].apply(convert_country_name_to_code)

# %%
# rename country_code to country_code_3
df = df.rename(columns={'country_code': 'country_code_3'})

# %%
#read scaffold
df_scaffold = pd.read_csv(wfp_scaffold_file)

# %%
# drop duplicates on lat, lon, year and month
df_scaffold = df_scaffold.drop_duplicates(subset=['lat', 'lon', 'year', 'month'])

# %%
# lat ad lon keep 12 digits, padding with 0
df_scaffold['lat'] = df_scaffold['lat'].apply(lambda x: '{:.12f}'.format(x))
df_scaffold['lon'] = df_scaffold['lon'].apply(lambda x: '{:.12f}'.format(x))

# %%
# read df_ESA
df_ESA = pd.read_csv(wfp_esa_lookup_file)

# %%
df_ESA['country'].unique()

# %%
# convert lat and lon to float and then padding to 12 digits
df_ESA['lat'] = df_ESA['lat'].astype(float).apply(lambda x: '{:.12f}'.format(x))
df_ESA['lon'] = df_ESA['lon'].astype(float).apply(lambda x: '{:.12f}'.format(x))

# %%
# for df_ESA, only keep ISO3, country, lat and lon
df_ESA = df_ESA[['ISO3', 'country', 'title', 'lat', 'lon']]

# drop duplicates
df_ESA = df_ESA.drop_duplicates(subset=['lat', 'lon'])

# %%
# merge on lat and lon
df_scaffold = df_scaffold.merge(df_ESA, on=['title'], how='left', suffixes=('', '_fixed'))

# %%
import pycountry
df_scaffold['country_code_3'] = df_scaffold['ISO3']

# %%
# convert year and month to integer
df_scaffold['year'] = df_scaffold['year'].astype(int)
df_scaffold['month'] = df_scaffold['month'].astype(int)

# %%
# merge df_scaffold and df on country_code_3, year and month
df_scaffold = df_scaffold.merge(df, on=['country_code_3', 'year', 'month'], how='left', indicator=True)

# %%
# see _merge
df_scaffold['_merge'].value_counts()

# %%
# drop _merge
df_scaffold = df_scaffold.drop(columns=['_merge'])

# %%
# drop country_code_3 and country_name
df_scaffold = df_scaffold.drop(columns=['country_code_3'])

# drop any duplicates in lat lon, year and month
df_scaffold = df_scaffold.drop_duplicates(subset=['lat', 'lon', 'year', 'month'])

# %%
df_scaffold.describe()

# %%
# location is the unique lat and lon
locations = df_scaffold[['lat', 'lon']].drop_duplicates()

# %%
len(locations)

# %%
# export
ensure_dir(os.path.dirname(wfp_output_file))
df_scaffold.to_csv(wfp_output_file, index=False)
print("Output: {0}".format(wfp_output_file))
