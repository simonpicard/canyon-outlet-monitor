# canyon-outlet-monitor

A script to monitor bikes in [Canyon\'s outlet](https://www.canyon.com/en-be/outlet-bikes/), featured in [my blog post](https://www.simonmyway.com/blog/swapping-my-company-car-for-a-bike-1000-km-later).

## Approach

1. request all bikes on the outlet
2. scrap them,
3. save them in a CSV table
4. send me a daily email with new bikes matching search criteria

Disclaimer: storing password on a YML file is not good practice and was done for this toy project as it is not expected to be in production with sensible data.

## Script set up

You need to fill in the `conf.yaml` file:

- mail:
  - sender: the email of the sender, must be Gmail
  - pw: the password of the sender
  - receiver: the email of the daily notification received

- bikes_df:
  - gcs: `true` if stored on GCS, false if local
  - path: path to the CSV file which will be used as database, if on GCS then start with `gs://`
  - cloud_function: if `true` then the script is assumed to be trigger from a Google Cloud Function and will use its service account, `false` otherwise
  - sa_path: path to service account JSON with GCS permission when not running from a Cloud Function, useful for local development

- search:
  - product field: regex to match

Search example:
- search:
  - product_name: "pathlite:on"
    product_size: ^(L|multi|M)$
  - product_name: endurace
    product_size: (^L|multi)

## CD set up

This repo contains an automated deployment to Google Cloud Function, to use it you must set up the following GitHub secrets:
- GCP_SA_JSON: service account with cloud function permission
- GCP_PID: GCP project ID on which to deploy the script
- GCP_PUB_SUB_TOPIC: The pub sub topic which should trigger the cloud function

Then you should set up a Cloud Scheduler triggering a pub sub message on the `GCP_PUB_SUB_TOPIC`, if you feel like making a Terraform script to automate this then please make a PR!