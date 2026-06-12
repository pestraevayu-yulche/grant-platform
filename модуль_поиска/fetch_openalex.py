# fetch_openalex.py

import os
import json
import time
import requests


API_KEY = os.getenv("OPENALEX_API_KEY")

BASE_URL = "https://api.openalex.org/works"

HEADERS = {
    "User-Agent": "ScoutingAPI/1.0"
}

RESULTS_PER_PAGE = 50
PROJECTS_PER_TOPIC = 50


def get_abstract_from_index(inverted_index):
    """
    OpenAlex хранит abstract в inverted index.
    """

    if not inverted_index:
        return "Аннотация отсутствует"

    words = {}

    for word, positions in inverted_index.items():
        for position in positions:
            words[position] = word

    abstract = " ".join(
        words[i]
        for i in sorted(words.keys())
    )

    return abstract


def fetch_openalex_projects_by_topic(query, needed=50):
    projects = []

    page = 1

    print(f"\nТема: {query}")

    while len(projects) < needed:

        params = {
            "search": query,
            "sort": "relevance_score:desc",
            "per-page": RESULTS_PER_PAGE,
            "page": page
        }

        if API_KEY:
            params["api_key"] = API_KEY

        try:
            response = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                timeout=30
            )

            if response.status_code == 429:
                print("Rate limit. Ожидание...")
                time.sleep(20)
                continue

            response.raise_for_status()

            data = response.json()

            results = data.get("results", [])

            if not results:
                break

            for work in results:

                if len(projects) >= needed:
                    break

                authors = []
                contacts = []

                for authorship in work.get("authorships", []):

                    author = authorship.get("author", {})

                    author_name = author.get("display_name")

                    if author_name:
                        authors.append(author_name)

                        organization = None

                        institutions = authorship.get("institutions", [])

                        if institutions:
                            organization = institutions[0].get(
                                "display_name"
                            )

                        contacts.append({
                            "name": author_name,
                            "email": None,
                            "organization": organization
                        })

                abstract = get_abstract_from_index(
                    work.get("abstract_inverted_index")
                )

                if len(abstract) > 1500:
                    abstract = abstract[:1500] + "..."

                doi = work.get("doi")

                project = {
                    "id": work.get("id"),
                    "title": work.get(
                        "title",
                        "Без названия"
                    ),
                    "authors": authors,
                    "affiliations": [],
                    "abstract": abstract,
                    "source": "OpenAlex",
                    "url": doi or work.get("id"),
                    "contacts": contacts,
                    "relevance_score": work.get(
                        "relevance_score",
                        0
                    ),
                    "publication_year": work.get(
                        "publication_year"
                    )
                }

                projects.append(project)

            print(
                f"Страница {page}: "
                f"{len(results)} результатов"
            )

            page += 1

            time.sleep(1.5)

        except requests.exceptions.RequestException as e:
            print(f"Ошибка: {e}")
            break

    return projects


def save_projects(
    projects,
    output_file="data/openalex_projects.json"
):
    os.makedirs("data", exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            projects,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"\n✅ Сохранено "
        f"{len(projects)} проектов"
    )


def fetch_all_openalex_projects():

    topics = [
        "machine learning",
        "neural networks",
        "artificial intelligence",
        "computer vision",
        "natural language processing",
        "deep learning",
        "data science",
        "petroleum engineering",
        "oil refining",
        "catalysis",
        "materials science"
    ]

    all_projects = []

    for topic in topics:

        projects = fetch_openalex_projects_by_topic(
            topic,
            PROJECTS_PER_TOPIC
        )

        all_projects.extend(projects)

        time.sleep(2)

    return all_projects


if __name__ == "__main__":

    projects = fetch_all_openalex_projects()

    save_projects(projects)