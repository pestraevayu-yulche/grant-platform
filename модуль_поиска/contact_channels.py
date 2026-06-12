"""Utilities for normalizing project contacts and preparing invitation links.

Supports both legacy format:
    contacts = [{"name": "...", "email": "...", "phone": "..."}]
and new pt.2035 format:
    contacts = {"email": [...], "phone": [...], "telegram": [...], "vk": [...]}
"""
from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import quote_plus

EMPTY_VALUES = {"", "-", "—", "none", "null", "не указан", "не указано", "nan"}


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple) or isinstance(value, set):
        raw = list(value)
    else:
        raw = [value]
    out: List[str] = []
    for item in raw:
        s = str(item).strip()
        if s and s.lower() not in EMPTY_VALUES:
            out.append(s)
    return out


def normalize_phone(phone: str) -> str:
    """Normalize Russian-style phone numbers for tel/search links."""
    raw = str(phone or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D+", "", raw)
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) >= 10:
        return "+" + digits
    return raw


def normalize_telegram(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    s = s.replace("https://t.me/", "").replace("http://t.me/", "")
    s = s.replace("t.me/", "").strip("/")
    if s.startswith("telegram:"):
        s = s.split(":", 1)[1].strip()
    if s.startswith("@"):
        return s
    # Telegram invite hashes often start with + and are opened as https://t.me/+hash
    if s.startswith("+"):
        return s
    return "@" + s


def phone_digits_for_messenger(phone: str) -> str:
    return re.sub(r"\D+", "", normalize_phone(phone))


def whatsapp_url(phone: str, text: str = "") -> str:
    """Build a WhatsApp Web direct-chat URL.

    The URL opens the chat immediately only if the user is already signed in
    to WhatsApp Web in the browser. If the browser is not paired with a
    WhatsApp account, WhatsApp will show the QR/login screen first.
    """
    digits = phone_digits_for_messenger(phone)
    if not digits:
        return ""
    suffix = f"&text={quote_plus(text)}" if text else ""
    return f"https://web.whatsapp.com/send?phone={digits}{suffix}"


def sms_url(phone: str, text: str = "") -> str:
    normalized = normalize_phone(phone)
    if not normalized:
        return ""
    suffix = f"?body={quote_plus(text)}" if text else ""
    return f"sms:{normalized}{suffix}"


def telegram_url(handle: str) -> str:
    h = normalize_telegram(handle)
    if not h:
        return ""
    if h.startswith("@"):
        return "https://t.me/" + h[1:]
    if h.startswith("+"):
        return "https://t.me/" + h
    return "https://t.me/" + h


def normalize_vk(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("vk.com/"):
        return "https://" + s
    return "https://vk.com/" + s.lstrip("@")


def normalize_contacts(project: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return flat list of contact entries with type/value/url/search fields."""
    contacts = project.get("contacts") or {}
    result: List[Dict[str, str]] = []

    def add(kind: str, value: str, name: str = "") -> None:
        v = str(value or "").strip()
        if not v or v.lower() in EMPTY_VALUES:
            return
        if kind == "phone":
            v = normalize_phone(v)
            url = f"tel:{v}" if v else ""
        elif kind == "telegram":
            v = normalize_telegram(v)
            url = telegram_url(v)
        elif kind == "vk":
            v = normalize_vk(v)
            url = v
        elif kind == "email":
            url = f"mailto:{v}"
        else:
            url = ""
        if not any(c.get("type") == kind and c.get("value") == v for c in result):
            result.append({"type": kind, "value": v, "name": name, "url": url})

    if isinstance(contacts, dict):
        for email in _as_list(contacts.get("email")):
            add("email", email)
        for phone in _as_list(contacts.get("phone")):
            add("phone", phone)
        for tg in _as_list(contacts.get("telegram")):
            add("telegram", tg)
        for vk in _as_list(contacts.get("vk")):
            add("vk", vk)
    elif isinstance(contacts, list):
        for item in contacts:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("fullname") or "").strip()
                for email in _as_list(item.get("email")):
                    add("email", email, name)
                for phone in _as_list(item.get("phone")):
                    add("phone", phone, name)
                for tg in _as_list(item.get("telegram")):
                    add("telegram", tg, name)
                for vk in _as_list(item.get("vk")):
                    add("vk", vk, name)
            elif isinstance(item, str):
                s = item.strip()
                if "@" in s and "." in s:
                    add("email", s)
                elif s.startswith("@") or "t.me/" in s:
                    add("telegram", s)
                elif re.search(r"\d{10,}", s):
                    add("phone", s)

    legacy_email = str(project.get("email") or "").strip()
    if legacy_email and legacy_email.lower() not in EMPTY_VALUES:
        add("email", legacy_email)

    return result


def project_channels(project: Dict[str, Any]) -> List[str]:
    return sorted({c["type"] for c in normalize_contacts(project)})


def enrich_project_contacts(project: Dict[str, Any]) -> Dict[str, Any]:
    """Update project has_contacts/available_channels using normalized contacts."""
    channels = project_channels(project)
    project["has_contacts"] = bool(channels)
    project["available_channels"] = channels
    return project


def invitation_text(competition: Dict[str, Any] | None = None) -> Dict[str, str]:
    competition = competition or {}
    title = competition.get("title") or competition.get("name") or "конкурсе"
    topic = competition.get("topic") or competition.get("description") or ""
    comp_id = competition.get("id") or "demo"
    link = competition.get("public_url") or f"https://example.org/competitions/{comp_id}"
    subject = f"Приглашение к участию в конкурсе {title}".strip()
    body = (
        "Здравствуйте!\n\n"
        f"Приглашаем вас принять участие в конкурсе \"{title}\".\n\n"
        f"Тематика конкурса: {topic}\n\n"
        "Ваш проект был найден системой Scouting API как потенциально релевантный направлению конкурса. "
        "При заинтересованности просим ознакомиться с условиями и подать заявку.\n\n"
        f"Ссылка на конкурс: {link}\n\n"
        "С уважением,\nОрганизаторы конкурса"
    )
    tg_text = (
        f"Здравствуйте! Приглашаем вас принять участие в конкурсе \"{title}\". "
        f"Ваш проект найден как релевантный тематике конкурса. Ссылка: {link}"
    )
    return {"subject": subject, "body": body, "telegram": tg_text, "link": link}


def build_invite_actions(project: Dict[str, Any], competition: Dict[str, Any] | None = None) -> List[Dict[str, str]]:
    texts = invitation_text(competition)
    actions: List[Dict[str, str]] = []
    for c in normalize_contacts(project):
        kind = c["type"]
        value = c["value"]
        if kind == "email":
            url = f"https://mail.google.com/mail/?view=cm&fs=1&to={quote_plus(value)}&su={quote_plus(texts['subject'])}&body={quote_plus(texts['body'])}"
            label = "Email"
        elif kind == "telegram":
            url = telegram_url(value)
            label = "Telegram"
        elif kind == "vk":
            url = c.get("url") or normalize_vk(value)
            label = "VK"
        elif kind == "phone":
            actions.append({
                "type": "phone_sms",
                "label": "SMS",
                "value": value,
                "url": sms_url(value, texts["body"]),
            })
            actions.append({
                "type": "phone_whatsapp",
                "label": "WhatsApp",
                "value": value,
                "url": whatsapp_url(value, texts["body"]),
            })
            continue
        else:
            continue
        actions.append({"type": kind, "label": label, "value": value, "url": url})
    return actions
