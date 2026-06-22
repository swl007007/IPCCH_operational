import os
import requests
from concurrent.futures import ThreadPoolExecutor

def download_file(url, destination_folder):
    filename = os.path.join(destination_folder, url.split("/")[-1])
    response = requests.get(url)

    if response.status_code == 200:
        with open(filename, "wb") as file:
            file.write(response.content)
        print(f"Downloaded: {url}")
    else:
        print(f"Failed to download: {url}")

def download_multiple_files(urls, destination_folder, num_threads=5):
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        tasks = [executor.submit(download_file, url, destination_folder) for url in urls]
        for task in tasks:
            task.result()

def generate_urls(base_url, start_year, start_month, end_year, end_month):
    urls = []
    for year in range(start_year, end_year + 1):
        start = start_month if year == start_year else 1
        end = end_month if year == end_year else 12
        for month in range(start, end + 1):
            url = f"{base_url}/GOSIF_GPP_{year}.M{month:02d}_SD.tif.gz"
            urls.append(url)
    return urls

if __name__ == "__main__":
    base_url = "http://data.globalecology.unh.edu/data/GOSIF-GPP_v2/Monthly/SD"
    start_year, start_month = 2016, 1
    end_year, end_month = 2023, 12
    destination_folder = "downloads"
    num_threads = 5

    urls = generate_urls(base_url, start_year, start_month, end_year, end_month)
    download_multiple_files(urls, destination_folder, num_threads)
