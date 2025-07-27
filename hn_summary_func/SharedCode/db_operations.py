import os
from azure.cosmos import CosmosClient, PartitionKey

# Get Cosmos DB connection details from environment variables
endpoint = os.environ.get("COSMOS_DB_ENDPOINT")
key = os.environ.get("COSMOS_DB_KEY")
database_name = os.environ.get("COSMOS_DB_DATABASE_NAME", "HNSummariesDB")
container_name = os.environ.get("COSMOS_DB_CONTAINER_NAME", "Articles")

def get_cosmos_client():
    """Initializes and returns a Cosmos DB client."""
    if not all([endpoint, key]):
        raise ValueError("Cosmos DB connection details (ENDPOINT and KEY) are not set in environment variables.")
    return CosmosClient(endpoint, key)

def initialize_database_and_container():
    """Creates the database and container if they don't exist."""
    client = get_cosmos_client()
    database = client.create_database_if_not_exists(id=database_name)
    partition_key = PartitionKey(path="/id")
    container = database.create_container_if_not_exists(
        id=container_name,
        partition_key=partition_key,
        offer_throughput=400
    )
    print(f"Database '{database_name}' and container '{container_name}' are ready.")
    return container

def save_article(article_data):
    """Saves a single article to the Cosmos DB container."""
    container = initialize_database_and_container()
    container.upsert_item(body=article_data)
    print(f"Saved article {article_data['id']} to Cosmos DB.")

def get_articles(page, per_page, continuation_token=None):
    """
    Retrieves a paginated list of articles from Cosmos DB using continuation tokens.
    """
    container = initialize_database_and_container()

    # Set query options for pagination
    query_options = {
        'max_item_count': per_page,
        'continuation_token': continuation_token
    }

    query = "SELECT * FROM c ORDER BY c.timestamp DESC"
    
    # Execute the query
    results_iterator = container.query_items(
        query=query,
        enable_cross_partition_query=True,
        **query_options
    )

    # Fetch the items and the new continuation token
    items = list(results_iterator)
    new_continuation_token = results_iterator.continuation_token

    # To get the total count, a separate query is needed.
    # This can be expensive, so consider if it's truly necessary for your application.
    count_query = "SELECT VALUE COUNT(1) FROM c"
    total_articles = list(container.query_items(count_query, enable_cross_partition_query=True))[0]

    return items, total_articles, new_continuation_token
