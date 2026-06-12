
import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])', re.I)
PHONE_RE = re.compile(r'(?:(?:\+7|8)[\s\-()]*)?(?:\d[\s\-()]*){10,}', re.I)
TG_RE = re.compile(r'(?:https?://t\.me/|t\.me/|telegram(?:\.me)?/|телеграм[:\s]*|telegram[:\s]*)([A-Za-z0-9_]{5,32})|(?<![\w])@([A-Za-z0-9_]{5,32})(?![\w])', re.I)
VK_RE = re.compile(r'(https?://(?:m\.)?vk\.com/[A-Za-z0-9_.-]+)|(?:vk\.com/)([A-Za-z0-9_.-]+)', re.I)

def normalize_phone(raw: str) -> str:
    digits = re.sub(r'\D+', '', raw or '')
    if len(digits) == 11 and digits.startswith('8'):
        return '+7' + digits[1:]
    if len(digits) == 11 and digits.startswith('7'):
        return '+' + digits
    if len(digits) == 10:
        return '+7' + digits
    return '+' + digits if digits else ''

def uniq(seq):
    out, seen = [], set()
    for x in seq:
        if not x:
            continue
        x = x.strip()
        key = x.lower()
        if key not in seen:
            out.append(x)
            seen.add(key)
    return out

def extract_contacts(text: str, links=None) -> dict:
    text = text or ''
    links = links or []
    emails = EMAIL_RE.findall(text)

    phones = []
    for match in PHONE_RE.findall(text):
        p = normalize_phone(match)
        if len(re.sub(r'\D+', '', p)) >= 10:
            phones.append(p)

    telegram = []
    for m in TG_RE.finditer(text):
        username = m.group(1) or m.group(2)
        if username and username.lower() not in {'project', 'university', 'contacts'}:
            telegram.append('@' + username.lstrip('@'))

    vk = []
    for m in VK_RE.finditer(text):
        url = m.group(1)
        handle = m.group(2)
        if url:
            vk.append(url)
        elif handle:
            vk.append('https://vk.com/' + handle)

    for href in links:
        href = href or ''
        low = href.lower()
        if 't.me/' in low or 'telegram.me/' in low:
            username = href.rstrip('/').split('/')[-1]
            if username:
                telegram.append('@' + username.lstrip('@'))
        if 'vk.com/' in low:
            vk.append(href)

    return {
        'email': uniq(emails),
        'phone': uniq(phones),
        'telegram': uniq(telegram),
        'vk': uniq(vk),
    }

def merge_contacts(auto_contacts: dict, manual_contacts: dict) -> dict:
    result = {}
    for key in ['email', 'phone', 'telegram', 'vk']:
        result[key] = uniq((auto_contacts or {}).get(key, []) + (manual_contacts or {}).get(key, []))
    return result

def has_any_contact(contacts: dict) -> bool:
    return any(contacts.get(k) for k in ['email', 'phone', 'telegram', 'vk'])
