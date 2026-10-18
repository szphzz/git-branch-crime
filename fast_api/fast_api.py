from fastapi import FastAPI
import requests
import os
import json

from dotenv import load_dotenv
from google.oauth2 import service_account
from google.cloud import storage
from datetime import datetime

from pydantic_settings.sources.providers import json

app = FastAPI()

@app.post("/tree-data")
def send_tree_data_to_bucket():
    #get the tree-data from data.sf.gov
    response = requests.get("https://data.sf.gov/api/v3/views/tkzw-k3nq/query.json")

    load_dotenv(".env_template")

    service_account_key = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
    project_id = os.getenv("GCP_PROJECT_ID")
    bucket_name = os.getenv("GCP_BUCKET_NAME")

    file_name = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_tree-data.json"
    # Log into Google Cloud using our service account
    credentials = service_account.Credentials.from_service_account_file(service_account_key)
    # This is how we are able to talk to Google Server
    client = storage.Client(project=project_id,
                            credentials=credentials)
    # Select the bucket we want to use
    bucket = client.bucket(bucket_name)
    # Create/select the file location inside the bucket
    file = bucket.blob(file_name)
    # upload
    file.upload_from_string(
        response.text,
        content_type="application/json")

    return {
        "message": "Tree data uploaded successfully",
        "file_name": file_name
    }

@app.post("/census-data")
def send_census_data_to_bucket():

    # Load environment variables FIRST
    load_dotenv(".env_template")

    # get census data for San Francisco County
    response = requests.get(
        "https://api.census.gov/data/2024/acs/acs5",
        params={
            "get": (
                "NAME,"
                "B01003_001E,"
                "B01002_001E,"
                "B19013_001E,"
                "B19301_001E,"
                "B17001_001E,"
                "B17001_002E,"
                "B23025_002E,"
                "B23025_004E,"
                "B23025_005E,"
                "B02001_002E,"
                "B02001_003E,"
                "B02001_004E,"
                "B02001_005E,"
                "B02001_006E,"
                "B02001_008E,"
                "B03003_003E,"
                "B15003_001E,"
                "B15003_017E,"
                "B15003_022E,"
                "B15003_023E,"
                "B15003_024E,"
                "B15003_025E,"
                "B25001_001E,"
                "B25003_001E,"
                "B25003_002E,"
                "B25003_003E,"
                "B25064_001E,"
                "B25077_001E"
            ),
            "for": "tract:*",
            "in": "state:06 county:075",
            "key": os.getenv("CENSUS_API_KEY")
        }
    )

    response.raise_for_status()

    # Make sure Census actually gave us valid data
    response.raise_for_status()

    service_account_key = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
    project_id = os.getenv("GCP_PROJECT_ID")
    bucket_name = os.getenv("GCP_BUCKET_NAME")

    file_name = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_census-data.json"

    # Log into Google Cloud using our service account
    credentials = service_account.Credentials.from_service_account_file(service_account_key)

    # This is how we are able to talk to Google Server
    client = storage.Client(project=project_id,
                            credentials=credentials)

    # Select the bucket we want to use
    bucket = client.bucket(bucket_name)

    # Create/select the file location inside the bucket
    file = bucket.blob(file_name)

    # upload
    file.upload_from_string(
        response.text,
        content_type="application/json"
    )

    return {
        "message": "Census data uploaded successfully",
        "file_name": file_name
    }