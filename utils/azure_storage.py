from azure.storage.blob import BlobServiceClient
from flask import current_app
import os
from werkzeug.utils import secure_filename

def get_blob_service_client():
    """Create and return a BlobServiceClient instance."""
    connection_string = current_app.config['AZURE_STORAGE_CONNECTION_STRING']
    return BlobServiceClient.from_connection_string(connection_string)

def upload_file(file, container_name=None):
    """
    Upload a file to Azure Blob Storage.
    Returns the URL of the uploaded file.
    """
    if not file:
        return None

    try:
        # Get container name from config or use default
        container_name = container_name or current_app.config['AZURE_STORAGE_CONTAINER']
        
        # Create blob service client
        blob_service_client = get_blob_service_client()
        
        # Get container client
        container_client = blob_service_client.get_container_client(container_name)
        
        # Create blob name from filename
        filename = secure_filename(file.filename)
        blob_name = f"{os.urandom(8).hex()}-{filename}"
        
        # Get blob client
        blob_client = container_client.get_blob_client(blob_name)
        
        # Upload file
        blob_client.upload_blob(file.read(), overwrite=True)
        
        # Return the URL
        return blob_client.url
        
    except Exception as e:
        current_app.logger.error(f"Error uploading file to Azure Storage: {str(e)}")
        return None

def delete_file(blob_url):
    """
    Delete a file from Azure Blob Storage.
    """
    try:
        # Get container name from config
        container_name = current_app.config['AZURE_STORAGE_CONTAINER']
        
        # Create blob service client
        blob_service_client = get_blob_service_client()
        
        # Get container client
        container_client = blob_service_client.get_container_client(container_name)
        
        # Extract blob name from URL
        blob_name = blob_url.split('/')[-1]
        
        # Get blob client
        blob_client = container_client.get_blob_client(blob_name)
        
        # Delete blob
        blob_client.delete_blob()
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Error deleting file from Azure Storage: {str(e)}")
        return False 