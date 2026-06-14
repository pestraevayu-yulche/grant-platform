# search_engine.py - ОБЛЕГЧЕННАЯ ВЕРСИЯ С ИСПОЛЬЗОВАНИЕМ HF SPACE API
import json
import os
import requests
import numpy as np
from typing import Any, Dict, List, Optional

# URL Hugging Face Space
HF_SPACE_URL = os.environ.get('HF_SPACE_URL', 'https://YuYulche-grant-platform-ai.hf.space')

def get_embedding(text: str) -> Optional[List[float]]:
    """Получить эмбеддинг через Hugging Face API"""
    try:
        response = requests.post(
            f'{HF_SPACE_URL}/embed',
            json={'text': text[:512]},
            timeout=30
        )
        if response.status_code == 200:
            return response.json()['embedding']
    except Exception as e:
        print(f"Ошибка API эмбеддинга: {e}")
    return None

def batch_get_embeddings(texts: List[str]) -> Optional[List[List[float]]]:
    """Массовое получение эмбеддингов"""
    try:
        response = requests.post(
            f'{HF_SPACE_URL}/batch_embed',
            json={'texts': [t[:512] for t in texts]},
            timeout=60
        )
        if response.status_code == 200:
            return response.json()['embeddings']
    except Exception as e:
        print(f"Ошибка массового API: {e}")
    return None

class SimpleInMemoryIndex:
    """Простой индекс для косинусного поиска без FAISS"""
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.embeddings = []
        self.documents = []
    
    def add(self, embeddings: np.ndarray):
        self.embeddings = embeddings
    
    def search(self, query_emb: np.ndarray, k: int) -> tuple:
        # Косинусное сходство
        similarities = np.dot(self.embeddings, query_emb.T).flatten()
        indices = np.argsort(similarities)[-k:][::-1]
        return similarities[indices], indices

class SearchEngine:
    """Поисковый движок через HF Space API (без FAISS и sentence-transformers локально)"""

    def __init__(self, data_path: str = "data/all_projects.json"):
        self.data_path = data_path
        self.projects: List[Dict[str, Any]] = []
        self.index = None
        self.embeddings: Optional[np.ndarray] = None
        self.project_texts: List[str] = []
        self.load_projects()
        if self.projects:
            self.build_index()

    def load_projects(self) -> None:
        if not os.path.exists(self.data_path):
            print(f"Файл с проектами не найден: {self.data_path}")
            return
        with open(self.data_path, "r", encoding="utf-8") as f:
            self.projects = json.load(f)
        if not isinstance(self.projects, list):
            raise ValueError("data/all_projects.json должен содержать список проектов")
        print(f"Загружено {len(self.projects)} проектов")

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
        return " ".join([
            self._clean_text(project.get("title", "")),
            self._clean_text(project.get("abstract", "")),
            self._clean_text(project.get("authors", [])),
            self._clean_text(project.get("description", "")),
        ]).strip()[:1000]

    def build_index(self) -> None:
        self.project_texts = [self._project_text(project) or "empty" for project in self.projects]
        print("Получение эмбеддингов через Hugging Face API...")
        
        # Получаем эмбеддинги для всех текстов
        all_embeddings = batch_get_embeddings(self.project_texts)
        if all_embeddings:
            self.embeddings = np.array(all_embeddings, dtype=np.float32)
        else:
            # Fallback: получаем по одному
            embeddings_list = []
            for text in self.project_texts:
                emb = get_embedding(text)
                if emb:
                    embeddings_list.append(emb)
                else:
                    embeddings_list.append([0.0] * 384)
            self.embeddings = np.array(embeddings_list, dtype=np.float32)
        
        # Нормализуем для косинусного сходства
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.embeddings = self.embeddings / (norms + 1e-8)
        
        # Создаем простой индекс
        self.index = SimpleInMemoryIndex(dimension=self.embeddings.shape[1])
        self.index.add(self.embeddings)
        print(f"Индекс построен: {len(self.projects)} проектов")

    def _embed_text(self, text: str) -> np.ndarray:
        emb = get_embedding(text[:512])
        if emb is None:
            emb = [0.0] * 384
        vec = np.array([emb], dtype=np.float32)
        # Нормализуем
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    @staticmethod
    def _cosine_to_percent_scale(score: float) -> float:
        score = float(score or 0.0)
        score = max(-1.0, min(score, 1.0))
        calibrated = 0.5 + 0.5 * score
        return max(0.0, min(calibrated, 1.0))

    def semantic_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        if not query or not query.strip() or not self.index or self.index.embeddings is None:
            return []
        top_k = max(1, min(int(top_k), len(self.projects)))
        query_embedding = self._embed_text(query)
        scores, indices = self.index.search(query_embedding, top_k)
        results = []
        for score, idx in zip(scores, indices[0] if len(indices.shape) > 1 else indices):
            if idx < 0 or idx >= len(self.projects):
                continue
            project = self.projects[idx].copy()
            project["semantic_raw"] = float(score)
            project["semantic_score"] = self._cosine_to_percent_scale(float(score))
            results.append(project)
        return results

    @staticmethod
    def keyword_score(query: str, text: str) -> float:
        # Упрощенная версия (без sklearn)
        if not query.strip() or not text.strip():
            return 0.0
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())
        if not query_words:
            return 0.0
        intersection = query_words.intersection(text_words)
        return len(intersection) / len(query_words)

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
        
        source_weights = {
            "pt.2035.university": 1.00,
            "arXiv": 0.90,
            "OpenAlex": 0.88,
            "Роспатент": 0.84,
        }
        source_score = source_weights.get(project.get("source"), 0.78)

        final_score = 0.7 * semantic + 0.15 * keyword + 0.15 * source_score

        title = str(project.get("title", "") or "").lower()
        query_l = query.lower().strip()
        if query_l and query_l in title:
            final_score = max(final_score, 0.85)

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

        ranked.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return ranked

_search_engine_instance = None

def get_search_engine():
    global _search_engine_instance
    if _search_engine_instance is None:
        print("Инициализация SearchEngine (через Hugging Face API)...")
        _search_engine_instance = SearchEngine()
    return _search_engine_instance
