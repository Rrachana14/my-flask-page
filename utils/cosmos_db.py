from azure.cosmos import CosmosClient
from flask import current_app

def get_cosmos_client():
    """Get or create a Cosmos DB client."""
    endpoint = current_app.config['COSMOS_ENDPOINT']
    key = current_app.config['COSMOS_KEY']
    return CosmosClient(endpoint, key)

def get_database():
    """Get or create the database."""
    client = get_cosmos_client()
    database_name = current_app.config['COSMOS_DATABASE']
    
    # Create database if it doesn't exist
    try:
        database = client.create_database_if_not_exists(id=database_name)
    except Exception as e:
        current_app.logger.error(f"Error creating database: {str(e)}")
        raise
    
    return database

def get_container(container_name):
    """Get or create a container."""
    database = get_database()
    
    # Create container if it doesn't exist
    try:
        container = database.create_container_if_not_exists(
            id=container_name,
            partition_key='/id'
        )
    except Exception as e:
        current_app.logger.error(f"Error creating container: {str(e)}")
        raise
    
    return container

def create_item(container_name, item):
    """Create a new item in the specified container."""
    container = get_container(container_name)
    try:
        return container.create_item(body=item)
    except Exception as e:
        current_app.logger.error(f"Error creating item: {str(e)}")
        raise

def get_item(container_name, item_id, partition_key):
    """Get an item by ID and partition key."""
    container = get_container(container_name)
    try:
        return container.read_item(item=item_id, partition_key=partition_key)
    except Exception as e:
        current_app.logger.error(f"Error reading item: {str(e)}")
        raise

def query_items(container_name, query, parameters=None):
    """Query items in the specified container."""
    container = get_container(container_name)
    try:
        return list(container.query_items(
            query=query,
            parameters=parameters or [],
            enable_cross_partition_query=True
        ))
    except Exception as e:
        current_app.logger.error(f"Error querying items: {str(e)}")
        raise

def update_item(container_name, item_id, partition_key, item):
    """Update an existing item."""
    container = get_container(container_name)
    try:
        return container.replace_item(item=item_id, body=item)
    except Exception as e:
        current_app.logger.error(f"Error updating item: {str(e)}")
        raise

def delete_item(container_name, item_id, partition_key):
    """Delete an item by ID and partition key."""
    container = get_container(container_name)
    try:
        container.delete_item(item=item_id, partition_key=partition_key)
    except Exception as e:
        current_app.logger.error(f"Error deleting item: {str(e)}")
        raise 