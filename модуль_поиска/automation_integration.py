import os
from urllib.parse import quote_plus

import requests

AUTOMATION_API_URL = os.getenv("AUTOMATION_API_URL", "http://127.0.0.1:8000")
AUTOMATION_ADMIN_URL = os.getenv("AUTOMATION_ADMIN_URL", "http://127.0.0.1:8000/admin/dashboard")
INTEGRATION_API_TOKEN = os.getenv("INTEGRATION_API_TOKEN", "")

DEFAULT_CRITERIA = [
    "Актуальность",
    "Новизна",
    "Практическая значимость",
    "Реализуемость",
    "Соответствие направлениям конкурса",
    "Потенциал масштабирования",
]


def _headers():
    headers = {"Accept": "application/json"}
    if INTEGRATION_API_TOKEN:
        headers["X-Integration-Token"] = INTEGRATION_API_TOKEN
    return headers


def _safe_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        parts, current, in_quotes = [], [], False
        for char in raw:
            if char == '"':
                in_quotes = not in_quotes
                continue
            if char == "," and not in_quotes:
                item = "".join(current).strip()
                if item:
                    parts.append(item)
                current = []
            else:
                current.append(char)
        item = "".join(current).strip()
        if item:
            parts.append(item)
        return [p.strip().strip('"').strip("'") for p in parts if p.strip()]
    return [str(value).strip()]


def build_external_search_text(competition_or_id=None, extra_query=""):
    if competition_or_id is None:
        competition = {}
    elif isinstance(competition_or_id, dict):
        competition = competition_or_id
    else:
        competition = load_external_contest(competition_or_id)

    title = competition.get("title") or competition.get("name") or ""
    description = competition.get("description") or ""
    goal = competition.get("goal") or ""
    topic = competition.get("topic") or ""
    directions = _safe_list(competition.get("directions"))
    criteria = _safe_list(competition.get("criteria"))
    priority_topics = _safe_list(competition.get("priority_topics"))

    parts = []
    if title:
        parts.append(f"Название конкурса: {title}")
    if description:
        parts.append(f"Описание конкурса: {description}")
    if goal and goal != description:
        parts.append(f"Цель конкурса: {goal}")
    if topic and topic not in [description, goal]:
        parts.append(f"Тематика конкурса: {topic}")
    if directions:
        parts.append("Направления конкурса: " + ", ".join(directions))
    if priority_topics:
        parts.append("Приоритетные тематики: " + ", ".join(priority_topics))
    if criteria:
        parts.append("Критерии оценки: " + ", ".join(criteria))
    if extra_query:
        parts.append(f"Дополнительное уточнение поиска: {extra_query}")
    return "\n".join([p for p in parts if p.strip()])


def normalize_external_contest(contest):
    if contest is None:
        contest = {}
    directions = _safe_list(contest.get("directions"))
    criteria = _safe_list(contest.get("criteria")) or DEFAULT_CRITERIA
    priority_topics = _safe_list(contest.get("priority_topics")) or directions
    title = contest.get("title") or contest.get("name") or contest.get("contest_name") or ""
    description = contest.get("description") or ""
    goal = contest.get("goal") or description
    topic = contest.get("topic") or " ".join([description, " ".join(directions)]).strip()

    normalized = {
        "id": f"external_{contest.get('id')}" if contest.get("id") is not None else "external_unknown",
        "external_id": contest.get("id"),
        "title": title,
        "name": title,
        "topic": topic,
        "goal": goal,
        "description": description,
        "directions": directions,
        "criteria": criteria,
        "priority_topics": priority_topics,
        "max_grant": contest.get("max_grant") or contest.get("max_amount"),
        "max_amount": contest.get("max_amount") or contest.get("max_grant"),
        "budget": contest.get("budget") or contest.get("max_amount") or contest.get("max_grant"),
        "duration_months": contest.get("duration_months"),
        "region": contest.get("region"),
        "application_deadline": contest.get("application_deadline"),
        "status": contest.get("status"),
        "is_external": True,
        "source_module": "automation",
    }
    normalized["search_text"] = build_external_search_text(normalized)
    return normalized


def get_external_contests():
    url = f"{AUTOMATION_API_URL.rstrip('/')}/api/scouting/contests"
    response = requests.get(url, headers=_headers(), timeout=10)
    response.raise_for_status()
    data = response.json()
    raw_contests = data.get("contests") or data.get("competitions") or data.get("items") or []
    return [normalize_external_contest(item) for item in raw_contests]


def load_external_contest(external_contest_id):
    url = f"{AUTOMATION_API_URL.rstrip('/')}/api/scouting/contests/{external_contest_id}"
    response = requests.get(url, headers=_headers(), timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("success") is False:
        raise ValueError(data.get("error", "Не удалось получить конкурс из модуля автоматизации"))
    contest = data.get("contest") or data.get("competition") or data.get("item") or data
    return normalize_external_contest(contest)


def load_external_competition(external_competition_id):
    return load_external_contest(external_competition_id)


def get_external_competition(external_competition_id):
    return load_external_contest(external_competition_id)


def get_external_contest(external_contest_id):
    return load_external_contest(external_contest_id)


def get_external_competition_criteria(competition_or_id):
    if isinstance(competition_or_id, dict):
        competition = normalize_external_contest(competition_or_id)
    else:
        competition = load_external_contest(competition_or_id)
    return _safe_list(competition.get("criteria")) or DEFAULT_CRITERIA


def build_competition_search_text(competition_or_id=None, extra_query=""):
    return build_external_search_text(competition_or_id, extra_query)


def make_admin_return_url(external_competition_id=None, return_url=None):
    if return_url:
        return return_url
    base = AUTOMATION_ADMIN_URL.rstrip("/")
    if external_competition_id:
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}contest_id={quote_plus(str(external_competition_id))}"
    return base


def build_admin_return_url(external_competition_id=None, return_url=None):
    return make_admin_return_url(external_competition_id, return_url)


def check_automation_connection():
    url = f"{AUTOMATION_API_URL.rstrip('/')}/api/scouting/health"
    response = requests.get(url, headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.json()
