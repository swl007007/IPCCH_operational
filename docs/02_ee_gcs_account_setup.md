# Earth Engine and Google Cloud Account Setup

The new operator account is not assumed to exist yet. Complete this checklist before any production remote-sensing export.

## Account Checklist

1. Create or identify the new Google account.
2. Register or authorize the account for Google Earth Engine.
3. Create or identify the GCP project used for exports.
4. Create or identify the GCS bucket used for raster exports.
5. Grant the operator account permission to write Earth Engine exports to the bucket and read bucket contents with `gsutil`.
6. Install Google Cloud SDK on the operator's Windows machine.
7. Run `gcloud auth login`.
8. For the cloud monthly E2E smoke, set project `food-crisis-modeling` and
   region `us-central1`.
9. Confirm `earthengine.googleapis.com` and `storage.googleapis.com` are enabled
   before treating export failures as IAM or script failures.
10. Run `gsutil ls gs://operator-bucket-name`.
11. Run one small Earth Engine test export using the date range in `config/ee_gcs_template.ini`.
12. Download the small test export with `gsutil -m cp`.

## Production Rule

Do not start a full EVI, FLDAS, or VIIRS export until one small test export has reached GCS and downloaded locally.
