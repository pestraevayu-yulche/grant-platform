# fetch_rospatent.py

import os
import json
import time
import requests


API_KEY = os.getenv("ROSPATENT_API_KEY")

BASE_URL = "https://searchplatform.rospatent.gov.ru/patsearch/v0.2"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def clean_html(text):
    import re

    if not text:
        return ""

    text = re.sub(r"<.*?>", "", text)

    return text.strip()


def fetch_rospatent_patents(
    query,
    limit=20,
    dataset="ru_since_1994"
):

    url = f"{BASE_URL}/search"

    payload = {
        "q": f"ALLTEXT:{query}",
        "datasets": [dataset],
        "limit": limit,
        "offset": 0,
        "sort": "publication_date:desc"
    }

    try:

        response = requests.post(
            url,
            headers=HEADERS,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        return data.get("hits", [])

    except Exception as e:
        print(f"Ошибка: {e}")
        return []


def convert_patent_to_project(patent):

    common = patent.get("common", {})
    biblio_ru = patent.get("biblio", {}).get("ru", {})
    snippet = patent.get("snippet", {})

    inventors = biblio_ru.get("inventor", [])

    authors = [
        inv.get("name")
        for inv in inventors
        if inv.get("name")
    ]

    contacts = []

    for author in authors:
        contacts.append({
            "name": author,
            "email": None,
            "organization": None
        })

    abstract = clean_html(
        snippet.get("description", "")
    )

    if not abstract:
        abstract = (
            f"Патент "
            f"{common.get('document_number', '')}"
        )

    patent_id = patent.get("id")

    project = {
        "id": patent_id,
        "title": clean_html(
            snippet.get(
                "title",
                biblio_ru.get(
                    "title",
                    "Без названия"
                )
            )
        ),
        "authors": authors,
        "affiliations": [],
        "abstract": abstract[:1500],
        "source": "Роспатент",
        "url": None,
        "contacts": contacts,
        "relevance_score": patent.get(
            "similarity",
            0
        ),
        "publication_date": common.get(
            "publication_date"
        )
    }

    return project