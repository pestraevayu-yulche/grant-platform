# search_engine.py
import json
import os
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class SearchEngine:
    """Локальный семантический поиск по загруженной базе проектов.

    Исправления:
    1. Метод search() принимает competition_criteria и selected_directions.
    2. Релевантность всегда возвращается в поле relevance_percent.
    3. Фильтр направлений считается через embeddings, а не через грубое совпадение слов.
    4. Финальная формула не занижает локальные результаты до нуля, поэтому фильтр
       релевантности 0-100 работает предсказуемо.
    """

    def __init__(self, data_path: str = "data/all_projects.json"):
        self.data_path = data_path
        self.projects: List[Dict[str, Any]] = []
        self.embedding_model = SentenceTransformer(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.index = None
        self.embeddings: Optional[np.ndarray] = None
        self.project_texts: List[str] = []
        self._text_embedding_cache: Dict[str, np.ndarray] = {}
        self.load_projects()
        self.build_index()

    def load_projects(self) -> None:
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Файл с проектами не найден: {self.data_path}")
        with open(self.data_path, "r", encoding="utf-8") as f:
            self.projects = json.load(f)
        if not isinstance(self.projects, list):
            raise ValueError("data/all_projects.json должен содержать список проектов")

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return " ".join(str(x) for x in value if x is not None)
        if isinstance(value, dict):
            return " ".join(str(v) for v in value.values() if v is not None)
        return str(value)

    def _project_text(self, project: Dict[str, Any]) -> str:
        authors = self._clean_text(project.get("authors", []))
        contacts = self._clean_text(project.get("contacts", []))
        return " ".join([
            self._clean_text(project.get("title", "")),
            self._clean_text(project.get("abstract", "")),
            authors,
            contacts,
            self._clean_text(project.get("source", "")),
        ]).strip()

    def build_index(self) -> None:
        self.project_texts = [self._project_text(project) or "empty project" for project in self.projects]
        print("Создание embeddings...")
        self.embeddings = self.embedding_model.encode(self.project_texts, show_progress_bar=True)
        self.embeddings = np.array(self.embeddings, dtype=np.float32)
        dimension = self.embeddings.shape[1]
        faiss.normalize_L2(self.embeddings)
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(self.embeddings)
        print(f"FAISS index построен: {len(self.projects)} проектов")

    def _embed_text(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            text = "empty text"
        cached = self._text_embedding_cache.get(text)
        if cached is not None:
            return cached
        vec = self.embedding_model.encode([text])
        vec = np.array(vec, dtype=np.float32)
        faiss.normalize_L2(vec)
        self._text_embedding_cache[text] = vec
        return vec

    @staticmethod
    def _cosine_to_percent_scale(score: float) -> float:
        """Переводит cosine/IP в удобную шкалу 0..1.

        Для sentence-transformers даже хорошие совпадения часто имеют cosine около 0.45-0.75.
        Старый вариант напрямую умножал cosine на 100 и из-за этого нормальные результаты
        могли пропадать при фильтре релевантности. Здесь используется мягкая калибровка.
        """
        score = float(score or 0.0)
        if score < -1.0:
            score = -1.0
        if score > 1.0:
            score = 1.0
        calibrated = 0.5 + 0.5 * score
        return max(0.0, min(calibrated, 1.0))

    def semantic_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return []
        top_k = max(1, min(int(top_k), len(self.projects)))
        query_embedding = self._embed_text(query)
        scores, indices = self.index.search(query_embedding, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.projects):
                continue
            project = self.projects[idx].copy()
            project["semantic_raw"] = float(score)
            project["semantic_score"] = self._cosine_to_percent_scale(float(score))
            results.append(project)
        return results

    @staticmethod
    def keyword_score(query: str, text: str) -> float:
        try:
            if not query.strip() or not text.strip():
                return 0.0
            vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2))
            vectors = vectorizer.fit_transform([query, text])
            return float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0])
        except Exception:
            return 0.0

    @staticmethod
    def _criteria_text(competition_criteria: Optional[Dict[str, Any]]) -> str:
        if not competition_criteria:
            return ""
        parts = []
        for key in ["topic", "goal", "criteria", "problem", "expected_results", "priority_topics"]:
            parts.append(str(competition_criteria.get(key, "") or ""))
        nominations = competition_criteria.get("nominations", []) or []
        if isinstance(nominations, list):
            for nom in nominations:
                if isinstance(nom, dict):
                    parts.append(str(nom.get("name", "") or ""))
                    parts.append(str(nom.get("description", "") or ""))
                else:
                    parts.append(str(nom))
        return " ".join(parts).strip()

    def embedding_similarity(self, left_text: str, right_text: str) -> float:
        if not left_text.strip() or not right_text.strip():
            return 0.0
        left = self._embed_text(left_text)
        right = self._embed_text(right_text)
        raw = float(np.dot(left[0], right[0]))
        return self._cosine_to_percent_scale(raw)

    def direction_score(self, project: Dict[str, Any], selected_directions: Optional[List[str]]) -> float:
        if not selected_directions:
            return 0.0
        directions_text = " ; ".join(str(d) for d in selected_directions if str(d).strip())
        if not directions_text:
            return 0.0
        return self.embedding_similarity(directions_text, self._project_text(project))

    def criteria_score(self, project: Dict[str, Any], competition_criteria: Optional[Dict[str, Any]]) -> float:
        criteria_text = self._criteria_text(competition_criteria)
        if not criteria_text:
            return 0.0
        return self.embedding_similarity(criteria_text, self._project_text(project))

    def calculate_final_score(
        self,
        query: str,
        project: Dict[str, Any],
        competition_criteria: Optional[Dict[str, Any]] = None,
        selected_directions: Optional[List[str]] = None,
    ) -> float:
        semantic = float(project.get("semantic_score", 0) or 0)
        text = self._project_text(project)
        keyword = self.keyword_score(query, text)
        criteria = self.criteria_score(project, competition_criteria)
        direction = self.direction_score(project, selected_directions)

        source_weights = {
            "pt.2035.university": 1.00,
            "arXiv": 0.90,
            "OpenAlex": 0.88,
            "Роспатент": 0.84,
        }
        source_score = source_weights.get(project.get("source"), 0.78)

        if selected_directions:
            # Формула для поиска внутри конкретных направлений конкурса.
            # Главный вес остается у смысла запроса, но направление и описание конкурса
            # заметно влияют на ранжирование.
            final_score = (
                0.45 * semantic +
                0.12 * keyword +
                0.20 * criteria +
                0.18 * direction +
                0.05 * source_score
            )
        else:
            final_score = (
                0.55 * semantic +
                0.15 * keyword +
                0.20 * criteria +
                0.10 * source_score
            )

        title = str(project.get("title", "") or "").lower()
        query_l = query.lower().strip()
        if query_l and query_l in title:
            final_score = max(final_score, 0.99)

        project["criteria_score"] = round(criteria, 4)
        project["direction_score"] = round(direction, 4)
        project["keyword_score"] = round(keyword, 4)
        return max(0.0, min(round(final_score, 4), 1.0))

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 20,
        competition_criteria: Optional[Dict[str, Any]] = None,
        selected_directions: Optional[List[str]] = None,
        direction_threshold: float = 0.30,
    ) -> List[Dict[str, Any]]:
        semantic_results = self.semantic_search(query, top_k=top_k)
        ranked = []
        for project in semantic_results:
            score = self.calculate_final_score(query, project, competition_criteria, selected_directions)
            project["final_score"] = score
            project["relevance"] = score
            project["relevance_percent"] = round(score * 100, 1)
            project.setdefault("contacts", [])
            ranked.append(project)

        # Мягкий embedding-фильтр направлений.
        # Если выбранные направления есть, сначала оставляем проекты с достаточным
        # direction_score. Если фильтр слишком сузил выдачу, возвращаем ранжированную
        # выдачу без полного обнуления результатов, чтобы интерфейс не выглядел сломанным.
        if selected_directions:
            filtered = [p for p in ranked if float(p.get("direction_score", 0) or 0) >= direction_threshold]
            if len(filtered) >= 5:
                ranked = filtered

        ranked.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return ranked


_search_engine_instance = None


def get_search_engine():
    global _search_engine_instance
    if _search_engine_instance is None:
        print("Инициализация SearchEngine...")
        _search_engine_instance = SearchEngine()
    return _search_engine_instance
