import logging
import azure.functions as func
import json
from math import ceil

from ..SharedCode import db_operations

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    page = req.params.get('page', '1')
    per_page = req.params.get('per_page', '10')

    try:
        page = int(page)
        per_page = int(per_page)
    except ValueError:
        return func.HttpResponse(
             "Invalid page or per_page parameter. Must be an integer.",
             status_code=400
        )

    allowed_per_page = [10, 20, 50, 100]
    if per_page not in allowed_per_page:
        per_page = 10

    continuation_token = req.headers.get('x-ms-continuation-token', None)

    try:
        articles_from_db, total_articles, new_continuation_token = db_operations.get_articles(page, per_page, continuation_token)
        
        total_pages = ceil(total_articles / per_page)

        response_data = {
            'articles': articles_from_db,
            'total_articles': total_articles,
            'total_pages': total_pages,
            'current_page': page,
            'per_page': per_page,
            'continuation_token': new_continuation_token
        }
        
        headers = {
            "Content-Type": "application/json",
            "x-ms-continuation-token": new_continuation_token if new_continuation_token else ""
        }

        return func.HttpResponse(
            json.dumps(response_data),
            headers=headers,
            status_code=200
        )
    except Exception as e:
        logging.error(f"Error fetching articles from Cosmos DB: {e}")
        return func.HttpResponse("Error fetching articles.", status_code=500)

    return func.HttpResponse(
        json.dumps(response_data),
        mimetype="application/json",
        status_code=200
    )
