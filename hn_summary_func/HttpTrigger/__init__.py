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

    # TODO: Replace with Cosmos DB call
    # articles_from_db, total_articles = db_operations.get_articles(page, per_page)
    articles_from_db = []
    total_articles = 0
    
    total_pages = ceil(total_articles / per_page)

    response_data = {
        'articles': articles_from_db,
        'total_articles': total_articles,
        'total_pages': total_pages,
        'current_page': page,
        'per_page': per_page
    }

    return func.HttpResponse(
        json.dumps(response_data),
        mimetype="application/json",
        status_code=200
    )
