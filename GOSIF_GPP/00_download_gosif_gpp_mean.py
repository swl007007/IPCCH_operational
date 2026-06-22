import os
import requests
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, get_value, load_config, resolve_path, require_dir, require_file

REQUEST_TIMEOUT_SEC = 180
CHUNK_SIZE = 1024 * 1024


def download_file(url, destination_folder):
    filename = os.path.join(destination_folder, url.split("/")[-1])
    response = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT_SEC)

    if response.status_code == 200:
        with open(filename, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    file_obj.write(chunk)
        print("Downloaded: {0}".format(url))
    else:
        print("Failed to download: {0} status={1}".format(url, response.status_code))


def download_multiple_files(urls, destination_folder, num_threads=1):
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    for url in urls:
        download_file(url, destination_folder)

def generate_urls(base_url, start_year, start_month, end_year, end_month):
    urls = []
    for year in range(start_year, end_year + 1):
        start = start_month if year == start_year else 1
        end = end_month if year == end_year else 12
        for month in range(start, end + 1):
            url = "{0}/GOSIF_GPP_{1}.M{2:02d}_Mean.tif.gz".format(base_url, year, month)
            urls.append(url)
    return urls

if __name__ == "__main__":
    base_url = "http://data.globalecology.unh.edu/data/GOSIF-GPP_v2/Monthly/Mean"
    start_year, start_month = 2016, 1
    end_year, end_month = 2023, 12
    config = load_config()
    destination_folder = ensure_dir(resolve_path(config, "gosif_gpp", "download_folder_mean"))
    num_threads = 5

    urls = generate_urls(base_url, start_year, start_month, end_year, end_month)
    download_multiple_files(urls, destination_folder, num_threads)
