import json
import os


DATA_FOLDER = "data"


def normalize_text(text):
    """
    Нормализация текста для дедупликации
    """
    if not text:
        return ""

    return (
        text.strip()
        .lower()
        .replace("\n", " ")
        .replace("  ", " ")
    )


def make_project_key(project):
    """
    Создание ключа проекта для поиска дублей
    """

    title = normalize_text(project.get("title", ""))

    authors = tuple(
        sorted([
            normalize_text(a)
            for a in project.get("authors", [])
            if a
        ])
    )

    return (title, authors)


def merge_unique_lists(list1, list2):
    """
    Объединение списков без дублей
    """

    result = []

    for item in list1 + list2:
        if item not in result:
            result.append(item)

    return result


def merge_contacts(existing_contacts, new_contacts):
    """
    Объединение контактов
    """

    if not existing_contacts:
        return new_contacts

    if not new_contacts:
        return existing_contacts

    merged = []
    seen = set()

    for contact in existing_contacts + new_contacts:

        key = (
            normalize_text(contact.get("name", "")),
            normalize_text(contact.get("email", ""))
        )

        if key not in seen:
            seen.add(key)
            merged.append(contact)

    return merged


def choose_best_url(project1, project2):
    """
    Выбор лучшего URL
    Предпочитаем DOI/OpenAlex вместо arXiv ID
    """

    url1 = project1.get("url")
    url2 = project2.get("url")

    if url2 and "doi.org" in str(url2):
        return url2

    if url1 and "doi.org" in str(url1):
        return url1

    return url1 or url2


def choose_best_abstract(project1, project2):
    """
    Выбор более качественной аннотации
    """

    abs1 = project1.get("abstract", "")
    abs2 = project2.get("abstract", "")

    if not abs1:
        return abs2

    if not abs2:
        return abs1

    if abs1 == "Аннотация отсутствует":
        return abs2

    if abs2 == "Аннотация отсутствует":
        return abs1

    return abs1 if len(abs1) >= len(abs2) else abs2


def merge_project_metadata(existing, new_project):
    """
    Объединение metadata проектов
    """

    # Источники
    existing_sources = existing.get("sources", [])
    if not existing_sources:
        existing_sources = [existing.get("source")]

    new_sources = new_project.get("sources", [])
    if not new_sources:
        new_sources = [new_project.get("source")]

    existing["sources"] = merge_unique_lists(
        existing_sources,
        new_sources
    )

    # Главный source
    priority_sources = [
        "OpenAlex",
        "arXiv",
        "Роспатент",
        "pt.2035.university"
    ]

    for source in priority_sources:
        if source in existing["sources"]:
            existing["source"] = source
            break

    # Авторы
    existing["authors"] = merge_unique_lists(
        existing.get("authors", []),
        new_project.get("authors", [])
    )

    # Организации
    existing["affiliations"] = merge_unique_lists(
        existing.get("affiliations", []),
        new_project.get("affiliations", [])
    )

    # Контакты
    existing["contacts"] = merge_contacts(
        existing.get("contacts", []),
        new_project.get("contacts", [])
    )

    # Аннотация
    existing["abstract"] = choose_best_abstract(
        existing,
        new_project
    )

    # URL
    existing["url"] = choose_best_url(
        existing,
        new_project
    )

    # PDF
    if not existing.get("pdf_url") and new_project.get("pdf_url"):
        existing["pdf_url"] = new_project.get("pdf_url")

    # Published
    if not existing.get("published") and new_project.get("published"):
        existing["published"] = new_project.get("published")

    # relevance_score
    existing["relevance_score"] = max(
        existing.get("relevance_score", 0),
        new_project.get("relevance_score", 0)
    )

    return existing


def remove_duplicates(projects):
    """
    Удаление дублей с merge metadata
    """

    unique_projects = []
    seen_projects = {}

    duplicates_count = 0

    for project in projects:

        key = make_project_key(project)

        if key not in seen_projects:

            seen_projects[key] = project
            unique_projects.append(project)

        else:

            duplicates_count += 1

            existing_project = seen_projects[key]

            merged_project = merge_project_metadata(
                existing_project,
                project
            )

            seen_projects[key] = merged_project

    print(f"\n🧹 Удалено дубликатов: {duplicates_count}")

    return unique_projects


def load_projects(filepath):
    """
    Загрузка JSON файла
    """

    try:

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:

        print(f"Ошибка чтения {filepath}: {e}")
        return []


def save_projects(projects, output_path):
    """
    Сохранение проектов
    """

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            projects,
            f,
            ensure_ascii=False,
            indent=2
        )


def print_statistics(projects):
    """
    Статистика
    """

    print("\n" + "=" * 70)
    print("СТАТИСТИКА")
    print("=" * 70)

    source_stats = {}

    for project in projects:

        sources = project.get("sources", [])

        if not sources:
            sources = [project.get("source", "Unknown")]

        for source in sources:
            source_stats[source] = source_stats.get(source, 0) + 1

    for source, count in sorted(source_stats.items()):
        print(f"{source}: {count}")

    print("\nКАЧЕСТВО ДАННЫХ")
    print("-" * 40)

    with_abstract = sum(
        1 for p in projects
        if p.get("abstract")
        and p["abstract"] != "Аннотация отсутствует"
    )

    with_authors = sum(
        1 for p in projects
        if p.get("authors")
    )

    with_contacts = sum(
        1 for p in projects
        if p.get("contacts")
    )

    with_multiple_sources = sum(
        1 for p in projects
        if len(p.get("sources", [])) > 1
    )

    print(f"С аннотациями: {with_abstract}/{len(projects)}")
    print(f"С авторами: {with_authors}/{len(projects)}")
    print(f"С контактами: {with_contacts}/{len(projects)}")
    print(f"Объединённых дублей: {with_multiple_sources}")


def merge_all_projects():

    files_to_merge = [
        ("arxiv_projects.json", "arXiv"),
        ("openalex_projects.json", "OpenAlex"),
        ("russian_projects.json", "pt.2035"),
        ("rospatent_projects.json", "Роспатент")
    ]

    all_projects = []

    print("=" * 70)
    print("ОБЪЕДИНЕНИЕ ПРОЕКТОВ")
    print("=" * 70)

    for filename, source_name in files_to_merge:

        filepath = os.path.join(DATA_FOLDER, filename)

        if not os.path.exists(filepath):

            print(f"✗ Файл не найден: {filename}")
            continue

        projects = load_projects(filepath)

        print(f"✓ {source_name}: {len(projects)} проектов")

        all_projects.extend(projects)

    print(f"\nДо дедупликации: {len(all_projects)} проектов")

    unique_projects = remove_duplicates(all_projects)

    print(f"После дедупликации: {len(unique_projects)} проектов")

    output_path = os.path.join(
        DATA_FOLDER,
        "all_projects.json"
    )

    save_projects(unique_projects, output_path)

    print("\n✅ Файл успешно сохранён")
    print(f"📁 {output_path}")

    print_statistics(unique_projects)


if __name__ == "__main__":
    merge_all_projects()