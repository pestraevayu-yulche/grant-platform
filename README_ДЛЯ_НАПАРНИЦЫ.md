# Финальная чистка и стабилизация связки модулей

Этот пакет не содержит patch-скриптов. В нем лежат полные готовые файлы для замены.

## Что заменить

### Модуль автоматизации
- `app.py`
- `templates/admin_dashboard.html`
- `templates/admin_contest_form.html`

### Модуль поиска
- `app.py`
- `automation_integration.py`
- `templates/results.html`
- `templates/index.html`
- `templates/select_competition.html`

### Корень `grant_platform`
- `run_all.ps1`
- `run_all.py`
- `.gitignore`

## Что удалить

Удалить из `модуль_поиска` все старые patch/fix-файлы:
- `fix_search_final.py`
- `fix_search_filters_page.py`
- `fix_search_filters_page_v2.py`
- `fix_search_module.py`
- `apply_search_module_patch.py`
- `apply_search_patch.py`
- `apply_search_patch_safe.py`
- `check_search_integration.py`

Удалить из `модуль_автоматизации`:
- `apply_automation_admin_contests_patch.py`
- `apply_automation_patch.py`
- `fix_automation_contests.py`

Можно оставить backup-файлы локально, но в общий репозиторий их не добавлять.

## Проверка

1. Запустить модуль автоматизации:
`cd D:\grant_platform\модуль_автоматизации && python app.py`

2. Проверить API:
- `http://127.0.0.1:8000/api/scouting/health`
- `http://127.0.0.1:8000/api/scouting/contests`

3. Запустить модуль поиска:
`cd D:\grant_platform\модуль_поиска && python app.py`

4. Открыть:
`http://127.0.0.1:5000/`

5. Выбрать конкурс. Страница результатов должна открыться только с `external_competition_id`.
