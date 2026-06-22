import gzip
import os
import shutil
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, get_value, load_config, resolve_path, require_dir, require_file


def unzip_tif_gz_files(input_folder):
    tif_files = [name for name in os.listdir(input_folder) if name.endswith('.tif.gz')]
    for name in tif_files:
        input_path = os.path.join(input_folder, name)
        output_path = os.path.join(input_folder, name.replace('.gz', ''))
        with gzip.open(input_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    print('Unzipped {} files in {}'.format(len(tif_files), input_folder))


if __name__ == "__main__":
    config = load_config()
    input_folder = require_dir(resolve_path(config, "gosif_gpp", "download_folder_mean"), "GOSIF mean download folder")
    unzip_tif_gz_files(input_folder)
