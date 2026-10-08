"""
blob_uploader.py
Uploads the final rendered video to the configured Blob Storage container.
"""

import os
from azure.storage.blob import BlobServiceClient


def upload_video(local_path: str, blob_name: str) -> str:
    conn_str = os.environ["STORAGE_CONNECTION_STRING"]
    container_name = os.environ["STORAGE_CONTAINER_OUTPUT"]

    service_client = BlobServiceClient.from_connection_string(conn_str)
    container_client = service_client.get_container_client(container_name)

    if not container_client.exists():
        container_client.create_container()

    blob_client = container_client.get_blob_client(blob_name)
    with open(local_path, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)

    return blob_client.url