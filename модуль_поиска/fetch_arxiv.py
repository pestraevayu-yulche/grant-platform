import requests
import xml.etree.ElementTree as ET
import json
import time
import os


ARXIV_API_URL = "http://export.arxiv.org/api/query"


def fetch_arxiv_papers(query, max_results=100, sort_by="relevance"):
    """
    Загрузка статей из arXiv по ключевому слову
    """

    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending"
    }

    print(f"\nЗапрос к arXiv: {query}")

    try:
        response = requests.get(ARXIV_API_URL, params=params, timeout=30)

        if response.status_code != 200:
            print(f"Ошибка arXiv API: {response.status_code}")
            return []

        root = ET.fromstring(response.content)

    except Exception as e:
        print(f"Ошибка запроса arXiv: {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}

    papers = []

    for entry in root.findall("atom:entry", ns):

        title_elem = entry.find("atom:title", ns)
        title = (
            title_elem.text.strip().replace("\n", " ")
            if title_elem is not None else "Без названия"
        )

        abstract_elem = entry.find("atom:summary", ns)
        abstract = (
            abstract_elem.text.strip().replace("\n", " ")
            if abstract_elem is not None else "Аннотация отсутствует"
        )

        authors = []

        for author in entry.findall("atom:author", ns):
            name_elem = author.find("atom:name", ns)

            if name_elem is not None:
                authors.append(name_elem.text)

        id_elem = entry.find("atom:id", ns)
        paper_id = id_elem.text if id_elem is not None else ""

        published_elem = entry.find("atom:published", ns)
        published = published_elem.text if published_elem is not None else ""

        pdf_url = None

        for link in entry.findall("atom:link", ns):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
                break

        contacts = []

        for author_name in authors:
            contacts.append({
                "name": author_name,
                "email": None,
                "organization": None
            })

        paper = {
            "id": paper_id,
            "title": title,
            "authors": authors,
            "affiliations": [],
            "abstract": abstract[:1500],
            "published": published,
            "url": paper_id,
            "pdf_url": pdf_url,
            "source": "arXiv",
            "source_type": "article",
            "contacts": contacts,
            "language": "en",
            "relevance_score": 0
        }

        papers.append(paper)

    return papers


def save_papers_to_json(papers, filename="data/arxiv_projects.json"):

    os.makedirs("data", exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Сохранено {len(papers)} статей")


if __name__ == "__main__":

    topics = [
        "machine learning",
        "neural networks",
        "catalysis",
        "oil refining",
        "materials science",
        "artificial intelligence",
        "computer vision",
        "natural language processing",
        "computer science",
        "software engineering",
        "data science",
        "robotics",
        "cybersecurity"
    ]

    all_papers = []

    for topic in topics:

        print("=" * 60)
        print(f"Тема: {topic}")
        print("=" * 60)

        papers = fetch_arxiv_papers(topic, max_results=50)

        all_papers.extend(papers)

        print(f"Загружено: {len(papers)}")
        print(f"Всего: {len(all_papers)}")

        time.sleep(3)

    save_papers_to_json(all_papers)

    print(f"\n✅ Готово! Всего статей: {len(all_papers)}")