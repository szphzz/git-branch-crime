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