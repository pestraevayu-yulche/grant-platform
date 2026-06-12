# live_search.py
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

import requests


class LiveSearchEngine:
    def __init__(self):
        self.last_request_time = 0.0
        self.request_interval = 0.5

    def _rate_limit(self) -> None:
        current_time = time.time()
        diff = current_time - self.last_request_time
        if diff < self.request_interval:
            time.sleep(self.request_interval - diff)
        self.last_request_time = time.time()

    @staticmethod
    def _openalex_abstract(work: Dict[str, Any]) -> str:
        plain = work.get("abstract")
        if plain:
            return str(plain)
        inverted = work.get("abstract_inverted_index")
        if not inverted:
            return "Аннотация отсутствует"
        words = []
        for word, positions in inverted.items():
            for pos in positions:
                words.append((pos, word))
        return " ".join(word for _, word in sorted(words))

    def search_arxiv(self, query: str, min_relevance: float = 0, limit: int = 25) -> List[Dict[str, Any]]:
        self._rate_limit()
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
        }
        try:
            response = requests.get("http://export.arxiv.org/api/query", params=params, timeout=15)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            ns = {"arxiv": "http://www.w3.org/2005/Atom"}
            results = []
            for idx, entry in enumerate(root.findall("arxiv:entry", ns)):
                title = entry.find("arxiv:title", ns)
                abstract = entry.find("arxiv:summary", ns)
                arxiv_id = entry.find("arxiv:id", ns)
                authors = []
                for author in entry.findall("arxiv:author", ns):
                    name = author.find("arxiv:name", ns)
                    if name is not None and name.text:
                        authors.append(name.text.strip())
                relevance = 1.0 - (idx / max(limit, 1)) * 0.5
                relevance_percent = round(relevance * 100, 1)
                if relevance_percent < float(min_relevance):
                    continue
                results.append({
                    "id": arxiv_id.text if arxiv_id is not None else "",
                    "title": title.text.strip().replace("\n", " ") if title is not None and title.text else "Без названия",
                    "authors": authors,
                    "abstract": abstract.text.strip().replace("\n", " ")[:1200] if abstract is not None and abstract.text else "",
                    "source": "arXiv",
                    "url": arxiv_id.text if arxiv_id is not None else "",
                    "contacts": [],
                    "relevance": relevance,
                    "relevance_percent": relevance_percent,
                })
            return results
        except Exception as e:
            print(f"arXiv ошибка: {e}")
            return []

    def search_openalex(self, query: str, min_relevance: float = 0, limit: int = 25) -> List[Dict[str, Any]]:
        self._rate_limit()
        params = {"search": query, "sort": "relevance_score:desc", "per-page": limit}
        try:
            response = requests.get("https://api.openalex.org/works", params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            results = []
            raw_scores = [float(w.get("relevance_score") or 0) for w in data.get("results", [])]
            max_score = max(raw_scores) if raw_scores else 1.0
            for work in data.get("results", []):
                raw_score = float(work.get("relevance_score") or 0)
                relevance = raw_score / max_score if max_score else 0.0
                relevance_percent = round(relevance * 100, 1)
                if relevance_percent < float(min_relevance):
                    continue
                authors = []
                for authorship in work.get("authorships", []):
                    author = authorship.get("author") or {}
                    name = author.get("display_name")
                    if name:
                        authors.append(name)
                doi = work.get("doi")
                results.append({
                    "id": work.get("id"),
                    "title": work.get("title") or "Без названия",
                    "authors": authors,
                    "abstract": self._openalex_abstract(work)[:1200],
                    "source": "OpenAlex",
                    "url": doi or work.get("id") or "",
                    "contacts": [],
                    "relevance": relevance,
                    "relevance_percent": relevance_percent,
                })
            return results
        except Exception as e:
            print(f"OpenAlex ошибка: {e}")
            return []

    def search_combined(self, query: str, sources: Dict[str, bool], min_relevance: float = 0, limit: int = 25) -> List[Dict[str, Any]]:
        all_results = []
        if not sources or sources.get("arxiv"):
            all_results.extend(self.search_arxiv(query, min_relevance, limit))
        if not sources or sources.get("openalex"):
            all_results.extend(self.search_openalex(query, min_relevance, limit))
        all_results.sort(key=lambda x: x.get("relevance_percent", 0), reverse=True)
        return all_results


_live_search = None


def get_live_search():
    global _live_search
    if _live_search is None:
        _live_search = LiveSearchEngine()
    return _live_search
