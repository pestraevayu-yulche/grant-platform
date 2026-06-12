
from __future__ import annotations
import argparse, json, re, time
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from contact_utils import extract_contacts, merge_contacts, has_any_contact
from project_profiler import profile_project

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ScoutingMVP/1.0; +https://example.org)"
}

def load_urls(path: str) -> list[str]:
    urls = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line == "-":
            continue
        urls.append(line)
    return urls

def load_manual_contacts(path: str | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def parse_project_page(url: str, manual_contacts_by_url: dict | None = None, timeout: int = 25) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    h1 = soup.find("h1")
    h2 = soup.find("h2")
    if h1:
        title = clean_text(h1.get_text(" "))
    elif h2:
        title = clean_text(h2.get_text(" "))
    elif soup.title:
        title = clean_text(soup.title.get_text(" "))

    # Берем описание после заголовка "Описание проекта", если возможно.
    full_text = clean_text(soup.get_text(" "))
    description = ""
    marker = "Описание проекта"
    if marker in full_text:
        description = full_text.split(marker, 1)[1]
        for stop in ["Выбрать тип", "Пульс", "Достижения", "Команда", "Кого вы ищете?"]:
            if stop in description:
                description = description.split(stop, 1)[0]
        description = clean_text(description)
    if not description:
        # fallback: первые содержательные 2000 символов после заголовка
        description = full_text[:3000]

    links = [a.get("href") for a in soup.find_all("a") if a.get("href")]
    auto_contacts = extract_contacts(full_text, links=links)
    manual = (manual_contacts_by_url or {}).get(url, {})
    contacts = merge_contacts(auto_contacts, manual)

    team = []
    if "Команда" in full_text:
        tail = full_text.split("Команда", 1)[1]
        tail = tail.split("Наставники", 1)[0] if "Наставники" in tail else tail[:500]
        team = [x.strip() for x in re.split(r"\s{2,}|,|;", tail) if 2 <= len(x.strip()) <= 80]

    project = {
        "id": "pt2035_" + urlparse(url).path.rstrip("/").split("/")[-1],
        "source": "pt2035",
        "title": title,
        "authors": team,
        "description": description,
        "abstract": description,
        "url": url,
        "contacts": contacts,
        "email": contacts.get("email", [None])[0] if contacts.get("email") else "",
        "has_contacts": has_any_contact(contacts),
        "available_channels": [k for k, v in contacts.items() if v],
    }
    project["ai_profile"] = profile_project(project)
    return project

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", default="pt2035_urls.txt", help="TXT-файл со ссылками на проекты")
    ap.add_argument("--manual-contacts", default="manual_contacts.json", help="JSON с ручными контактами")
    ap.add_argument("--output", default="data/pt2035_projects.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.7)
    args = ap.parse_args()

    urls = load_urls(args.urls)
    if args.limit:
        urls = urls[:args.limit]
    manual = load_manual_contacts(args.manual_contacts)

    results = []
    errors = []
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    for i, url in enumerate(urls, start=1):
        try:
            print(f"[{i}/{len(urls)}] parsing {url}")
            results.append(parse_project_page(url, manual))
        except Exception as e:
            errors.append({"url": url, "error": str(e)})
            print(f"ERROR: {url}: {e}")
        time.sleep(args.delay)

    Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.output + ".errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {args.output}; projects={len(results)}; errors={len(errors)}")

if __name__ == "__main__":
    main()
