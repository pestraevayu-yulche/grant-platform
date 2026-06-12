# vk_hunter.py
import requests
from urllib.parse import quote

try:
    from transliterate import translit
except Exception:
    translit = None


class VKHunter:
    """Безопасный VK-поиск.

    Если VK_TOKEN не задан, класс не обращается к API и возвращает None.
    Интерфейс при этом может открывать обычную страницу поиска VK по ФИО автора.
    """

    def __init__(self, access_token=''):
        self.access_token = (access_token or '').strip()
        self.api_url = 'https://api.vk.com/method/'
        self.api_version = '5.131'

    @staticmethod
    def vk_search_url(name: str) -> str:
        return f'https://vk.com/search?c[q]={quote(name or "")}&c[section]=people'

    def transliterate_name(self, name):
        if not name:
            return {'latin': '', 'cyrillic': ''}
        if translit is None:
            return {'latin': name, 'cyrillic': name}
        try:
            cyrillic = translit(name, 'ru', reversed=True)
            return {'latin': name, 'cyrillic': cyrillic}
        except Exception:
            return {'latin': name, 'cyrillic': name}

    @staticmethod
    def extract_city_from_affiliation(affiliation):
        cities = {
            'Москва': ['Москва', 'Moscow', 'МГУ', 'МФТИ', 'МИФИ', 'ВШЭ', 'HSE'],
            'Санкт-Петербург': ['Санкт-Петербург', 'St. Petersburg', 'СПб', 'ИТМО', 'СПбГУ', 'Политех'],
            'Новосибирск': ['Новосибирск', 'Novosibirsk', 'НГУ'],
            'Екатеринбург': ['Екатеринбург', 'УрФУ'],
            'Уфа': ['Уфа', 'Ufa', 'УГНТУ'],
            'Казань': ['Казань', 'Kazan', 'КФУ'],
            'Томск': ['Томск', 'Tomsk', 'ТГУ', 'ТПУ'],
        }
        if not affiliation:
            return None
        low = affiliation.lower()
        for city, keywords in cities.items():
            if any(k.lower() in low for k in keywords):
                return city
        return None

    def search_person_cascaded(self, author_info):
        if not self.access_token:
            return None

        full_name = (author_info.get('full_name') or '').strip()
        affiliation = (author_info.get('affiliation') or '').strip()
        if not full_name:
            return None

        name_parts = full_name.split()
        first_name = name_parts[0] if len(name_parts) > 0 else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        first_name_cyr = self.transliterate_name(first_name)['cyrillic']
        last_name_cyr = self.transliterate_name(last_name)['cyrillic']
        full_name_cyr = f'{first_name_cyr} {last_name_cyr}'.strip() or full_name
        city = self.extract_city_from_affiliation(affiliation)

        attempts = []
        if full_name_cyr:
            attempts.append({'q': full_name_cyr, 'type': 'only_name'})
        if city and full_name_cyr:
            attempts.append({'q': full_name_cyr, 'city_name': city, 'type': 'fullname+city'})
        if city and last_name_cyr:
            attempts.append({'q': last_name_cyr, 'city_name': city, 'type': 'lastname+city'})
        attempts.append({'q': full_name, 'type': 'latin_name'})

        for attempt in attempts:
            found = self._search_vk(attempt)
            if found and len(found) == 1:
                return self._extract_user_info(found[0], attempt['type'])
            if found and len(found) > 1:
                return [self._get_short_user_info(u) for u in found]
        return None

    def _search_vk(self, params):
        search_params = {
            'count': 5,
            'fields': 'contacts,universities,city,country,education,about,activities,interests,status,last_seen,screen_name',
            'access_token': self.access_token,
            'v': self.api_version,
            'q': params.get('q', ''),
        }
        try:
            response = requests.get(self.api_url + 'users.search', params=search_params, timeout=10)
            data = response.json()
            if 'error' in data:
                print(f"VK API ошибка: {data['error'].get('error_msg')}")
                return None
            items = data.get('response', {}).get('items', [])
            return [item for item in items if not item.get('deactivated')]
        except Exception as e:
            print(f'Ошибка запроса к VK: {e}')
            return None

    @staticmethod
    def _profile_url(user_data):
        screen_name = user_data.get('screen_name')
        if screen_name:
            return f'https://vk.com/{screen_name}'
        return f"https://vk.com/id{user_data.get('id')}"

    def _extract_user_info(self, user_data, search_type):
        return {
            'id': user_data.get('id'),
            'first_name': user_data.get('first_name'),
            'last_name': user_data.get('last_name'),
            'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
            'profile_url': self._profile_url(user_data),
            'search_type': search_type,
            'contacts': {
                'mobile_phone': user_data.get('mobile_phone'),
                'home_phone': user_data.get('home_phone'),
            },
            'university': user_data.get('university_name'),
            'city': (user_data.get('city') or {}).get('title') if isinstance(user_data.get('city'), dict) else None,
            'about': user_data.get('about'),
            'status': user_data.get('status'),
            'relevance_score': self._calculate_relevance(user_data),
        }

    def _get_short_user_info(self, user_data):
        return {
            'id': user_data.get('id'),
            'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
            'profile_url': self._profile_url(user_data),
            'city': (user_data.get('city') or {}).get('title') if isinstance(user_data.get('city'), dict) else None,
            'university': user_data.get('university_name'),
        }

    @staticmethod
    def _calculate_relevance(user_data):
        score = 0
        if user_data.get('university_name'):
            score += 30
        if user_data.get('city'):
            score += 15
        if user_data.get('about') or user_data.get('activities') or user_data.get('interests'):
            score += 20
        if user_data.get('mobile_phone') or user_data.get('home_phone'):
            score += 10
        return min(score, 100)
