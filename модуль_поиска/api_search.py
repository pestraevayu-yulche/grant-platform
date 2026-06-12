# api_search.py

from flask import Blueprint
from flask import request
from flask import jsonify

from search_engine import SearchEngine


search_api = Blueprint(
    "search_api",
    __name__
)

engine = SearchEngine()


@search_api.route(
    "/api/search",
    methods=["POST"]
)
def search_projects():

    data = request.json

    query = data.get("query", "")

    filters = data.get("filters", {})

    limit = data.get("limit", 20)

    results = engine.search(
        query=query,
        top_k=limit
    )

    min_relevance = filters.get(
        "min_relevance",
        0
    )

    filtered = []

    for project in results:

        score_percent = (
            project["final_score"] * 100
        )

        if score_percent >= min_relevance:
            filtered.append(project)

    return jsonify(filtered)