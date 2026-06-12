
from urllib.parse import quote

def build_invitation_text(competition: dict, project: dict) -> str:
    name = project.get("title", "ваш проект")
    comp_title = competition.get("title") or competition.get("name") or "конкурс проектных инициатив"
    comp_url = competition.get("public_url") or f"https://example.org/competitions/{competition.get('id', 'demo')}"
    return (
        f"Здравствуйте!\n\n"
        f"Мы нашли ваш проект «{name}» и считаем, что он может быть релевантен конкурсу «{comp_title}».\n\n"
        f"Ссылка на конкурс: {comp_url}\n\n"
        f"Будем рады, если вы рассмотрите возможность участия.\n\n"
        f"С уважением,\nорганизационный комитет"
    )

def build_channel_actions(project: dict, competition: dict) -> list[dict]:
    contacts = project.get("contacts") or {}
    text = build_invitation_text(competition, project)
    subject = f"Приглашение к участию в конкурсе: {competition.get('title') or competition.get('name') or ''}".strip()
    actions = []

    for email in contacts.get("email", []):
        actions.append({
            "channel": "email",
            "label": email,
            "url": f"mailto:{email}?subject={quote(subject)}&body={quote(text)}"
        })

    for tg in contacts.get("telegram", []):
        username = tg.lstrip("@")
        actions.append({
            "channel": "telegram",
            "label": "@" + username,
            "url": f"https://t.me/{username}"
        })

    for phone in contacts.get("phone", []):
        actions.append({
            "channel": "phone",
            "label": phone,
            "url": f"tel:{phone}"
        })

    for vk in contacts.get("vk", []):
        actions.append({
            "channel": "vk",
            "label": vk,
            "url": vk if vk.startswith("http") else f"https://vk.com/{vk}"
        })

    # Если контактов нет, остается поиск по названию/команде
    if not actions:
        query = quote(" ".join([project.get("title", ""), " ".join(project.get("authors", []))]))
        actions.append({
            "channel": "vk_search",
            "label": "Поиск VK",
            "url": f"https://vk.com/search?c%5Bq%5D={query}&c%5Bsection%5D=auto"
        })

    return actions
