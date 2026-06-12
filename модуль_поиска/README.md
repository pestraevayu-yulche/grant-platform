# PT2035 parser + AI analysis pack v2

Что делает пакет:
1. Парсит страницы проектов pt.2035.university по готовому списку URL.
2. Извлекает доступные публичные контакты: email, телефон, Telegram, VK.
3. Подмешивает ручные контакты из `manual_contacts.json`.
4. Добавляет AI-профиль проекта: технологические домены, бизнес-модель, зрелость, стратегическая связка.
5. Импортирует проекты в `data/all_projects.json`.

Важно:
На страницах pt.2035.university часть контактов может быть скрыта за кнопкой «Показать контакты команды» или доступна только авторизованным пользователям. Такие контакты парсер не сможет получить из публичного HTML. Для них используйте `manual_contacts.json`.

Команды:

```bash
pip install -r requirements_pt2035.txt
python pt2035_parser.py --urls pt2035_urls.txt --manual-contacts manual_contacts.json --output data/pt2035_projects.json --limit 3
```

Если первые 3 проекта спарсились нормально:

```bash
python pt2035_parser.py --urls pt2035_urls.txt --manual-contacts manual_contacts.json --output data/pt2035_projects.json
python import_pt2035_projects.py --input data/pt2035_projects.json --all data/all_projects.json --backup
```

После импорта нужно пересобрать FAISS-индекс тем скриптом, который используется в вашем проекте для индексации.
Если отдельного скрипта нет, можно временно удалить `data/all_projects.index`, чтобы индекс пересоздался при запуске, если это предусмотрено в `search_engine.py`.

Ручные контакты:
```json
{
  "https://pt.2035.university/project/example": {
    "email": ["mail@example.ru"],
    "telegram": ["@username"],
    "phone": ["+79991234567"],
    "vk": ["https://vk.com/example"]
  }
}
```
