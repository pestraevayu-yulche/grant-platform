# app.py
from flask import Flask, render_template, request, jsonify, make_response, session, redirect, url_for
from functools import wraps
from search_engine import get_search_engine
from live_search import get_live_search
from competitions_db import competitions_db
from vk_hunter import VKHunter
from contact_channels import normalize_contacts as normalize_project_contacts, build_invite_actions
from automation_integration import get_external_contests, load_external_competition, build_external_search_text, make_admin_return_url, get_external_competition_criteria

import csv
import io
import json
import os
import re
import sqlite3
import traceback
from datetime import datetime
from typing import Any, Dict, List

import requests
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if load_dotenv is not None:
    load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
app.secret_key = os.environ.get('SCOUTING_SECRET_KEY', 'dev-secret-change-me')

DATA_DIR = os.path.join(BASE_DIR, 'data')
USERS_DB_PATH = os.path.join(DATA_DIR, 'users.sqlite3')
AUTOMATION_API_URL = os.environ.get('AUTOMATION_API_URL', 'http://127.0.0.1:8000')
AUTOMATION_ADMIN_URL = os.environ.get('AUTOMATION_ADMIN_URL', 'http://127.0.0.1:8000/admin/dashboard')


def get_db_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_users_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT UNIQUE,
            fullname TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()

    defaults = [
        (
            os.environ.get('SCOUTING_ADMIN_USERNAME', 'admin'),
            os.environ.get('SCOUTING_ADMIN_EMAIL', 'admin@example.local'),
            os.environ.get('SCOUTING_ADMIN_FULLNAME', 'Администратор'),
            os.environ.get('SCOUTING_ADMIN_PASSWORD', 'admin123'),
            'admin',
        ),
        (
            os.environ.get('SCOUTING_ORGANIZER_USERNAME', 'organizer'),
            os.environ.get('SCOUTING_ORGANIZER_EMAIL', 'organizer@example.local'),
            os.environ.get('SCOUTING_ORGANIZER_FULLNAME', 'Организатор конкурсов'),
            os.environ.get('SCOUTING_ORGANIZER_PASSWORD', 'org123'),
            'organizer',
        ),
    ]
    reset_passwords = os.environ.get('SCOUTING_RESET_DEFAULT_PASSWORDS', 'false').lower() == 'true'
    for username, email, fullname, password, role in defaults:
        exists = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not exists:
            conn.execute(
                'INSERT INTO users (username, email, fullname, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (username, email, fullname, generate_password_hash(password), role, datetime.now().isoformat())
            )
        elif reset_passwords:
            conn.execute(
                'UPDATE users SET email = ?, fullname = ?, password_hash = ?, role = ? WHERE username = ?',
                (email, fullname, generate_password_hash(password), role, username)
            )
    conn.commit()
    conn.close()


def get_user_by_username(username: str):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user


def normalize_min_relevance(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 100.0))
    except Exception:
        return 0.0


def normalize_contacts(project: Dict[str, Any]) -> List[Dict[str, str]]:
    """Normalize legacy and new contact formats to a flat list.

    Supports:
    - legacy list of dicts with email/phone;
    - pt.2035 dict: {email: [], phone: [], telegram: [], vk: []}.
    """
    return normalize_project_contacts(project)


def enrich_contacts_for_response(project: Dict[str, Any]) -> Dict[str, Any]:
    contacts = normalize_contacts(project)
    project['contacts_normalized'] = contacts
    project['available_channels'] = sorted({c.get('type') for c in contacts if c.get('type')})
    project['has_contacts'] = bool(project['available_channels'])
    return project

def normalize_competition(competition: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Приводит конкурс к безопасной структуре для шаблонов и JSON API.

    Нужна для старых конкурсов, созданных до появления полей directions/nominations.
    Jinja не умеет сериализовать Undefined через tojson, поэтому все поля должны
    существовать и иметь JSON-совместимые значения.
    """
    if not competition:
        return None

    c = dict(competition)

    text_defaults = {
        'id': '',
        'title': '',
        'name': '',
        'topic': '',
        'description': '',
        'goal': '',
        'geography': '',
        'fund': '',
        'duration': '',
        'conditions': '',
        'start_date': '',
        'end_date': '',
        'max_grant': '',
        'own_contribution': '',
        'budget_limits': '',
        'criteria': '',
        'problem': '',
        'expected_results': '',
        'priority_topics': '',
        'created_at': '',
        'updated_at': '',
    }
    for key, default in text_defaults.items():
        if c.get(key) is None:
            c[key] = default

    directions = c.get('directions')
    if not isinstance(directions, list):
        directions = []
    c['directions'] = directions

    nominations = c.get('nominations')
    if not isinstance(nominations, list):
        nominations = []

    normalized_nominations = []
    for item in nominations:
        if isinstance(item, dict):
            normalized_nominations.append({
                'name': str(item.get('name') or item.get('title') or ''),
                'description': str(item.get('description') or ''),
                'minAmount': str(item.get('minAmount') or item.get('min_amount') or item.get('min_grant') or ''),
                'maxAmount': str(item.get('maxAmount') or item.get('max_amount') or item.get('max_grant') or ''),
            })
        elif isinstance(item, str):
            normalized_nominations.append({
                'name': item,
                'description': '',
                'minAmount': '',
                'maxAmount': '',
            })

    if not normalized_nominations and directions:
        normalized_nominations = [
            {'name': str(direction), 'description': '', 'minAmount': '', 'maxAmount': ''}
            for direction in directions
        ]

    c['nominations'] = normalized_nominations
    return c

def source_filter(results: List[Dict[str, Any]], sources: Dict[str, bool]) -> List[Dict[str, Any]]:
    if not sources:
        return results
    mapping = {
        'arxiv': 'arXiv',
        'openalex': 'OpenAlex',
        'rospatent': 'Роспатент',
        'pt2035': 'pt.2035.university',
    }
    enabled = [label for key, label in mapping.items() if sources.get(key)]
    if not enabled:
        return []
    return [r for r in results if r.get('source') in enabled]


def direction_filter(results: List[Dict[str, Any]], directions: List[str]) -> List[Dict[str, Any]]:
    if not directions:
        return results
    keywords = []
    for d in directions:
        clean = re.sub(r'^Н\d\.\s*', '', str(d)).lower()
        keywords.extend([w for w in re.split(r'[^a-zа-яё0-9]+', clean) if len(w) > 3])
    if not keywords:
        return results
    filtered = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('abstract', '')}".lower()
        if any(word in text for word in keywords):
            filtered.append(r)
    return filtered


def get_competition_criteria(competition_id: str):
    if not competition_id:
        return None
    competition = normalize_competition(competitions_db.get_by_id(competition_id))
    if not competition:
        return None
    return {
        'nominations': competition.get('nominations', []),
        'criteria': competition.get('criteria', ''),
        'problem': competition.get('problem', ''),
        'expected_results': competition.get('expected_results', ''),
        'priority_topics': competition.get('priority_topics', ''),
        'topic': competition.get('topic', ''),
        'goal': competition.get('goal', ''),
    }


def login_required(f):
    # Авторизация выполняется в модуле автоматизации.
    # Модуль поиска работает как внутренний сервис и не требует отдельного входа.
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


@app.route('/favicon.ico')
def favicon():
    # Браузер автоматически запрашивает favicon.ico.
    # Если файла нет, это не должно превращаться в 500-ошибку приложения.
    return ('', 204)


@app.errorhandler(Exception)
def handle_exception(e):
    # 404/405 и другие HTTP-исключения Flask/Werkzeug не являются падением системы.
    # Раньше общий обработчик превращал запрос /favicon.ico в 500.
    if isinstance(e, HTTPException):
        if request.path.startswith('/api/') or request.path in ['/export', '/send_to_review']:
            return jsonify({'success': False, 'error': e.description}), e.code
        return e

    traceback.print_exc()
    if request.path.startswith('/api/') or request.path in ['/export', '/send_to_review']:
        return jsonify({'success': False, 'error': str(e)}), 500
    raise e


init_users_db()

print('Загрузка поискового движка...')
engine = get_search_engine()
print('Поисковый движок готов!')

print('Загрузка live search...')
live_engine = get_live_search()
print('Live search готов!')

vk_hunter = VKHunter(os.environ.get('VK_TOKEN', ''))


@app.route('/login')
def login_page():
    return redirect('/')


@app.route('/register')
def register_page():
    return redirect('/')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/create_competition')
@login_required
def create_competition():
    return redirect(f"{AUTOMATION_ADMIN_URL.rstrip('/')}/admin/contests/create")


@app.route('/edit_competition/<competition_id>')
@login_required
def edit_competition_page(competition_id):
    clean_id = str(competition_id).replace('external_', '')
    return redirect(f"{AUTOMATION_ADMIN_URL.rstrip('/')}/admin/contests/{clean_id}/edit")


@app.route('/results')
@login_required
def results_page():
    external_competition_id = request.args.get('external_competition_id')
    competition_id = request.args.get('competition_id')
    return_url = request.args.get('return_url', '')

    # Без конкурса страница результатов не имеет смысла: поиск строится по профилю конкурса.
    # Поэтому /results без параметров всегда возвращает на страницу выбора конкурса.
    if not external_competition_id and not competition_id:
        return redirect(url_for('index'))

    if external_competition_id and not return_url:
        return_url = make_admin_return_url(external_competition_id)

    return render_template(
        'results.html',
        automation_admin_url=AUTOMATION_ADMIN_URL,
        integration_mode=bool(external_competition_id),
        external_competition_id=external_competition_id,
        competition_id=competition_id,
        return_url=return_url,
    )


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))

    if not username or not password:
        return jsonify({'success': False, 'error': 'Введите логин и пароль'}), 400

    user = get_user_by_username(username)
    if user and check_password_hash(user['password_hash'], password):
        session['logged_in'] = True
        session['username'] = user['username']
        session['role'] = user['role']
        session['fullname'] = user['fullname'] or user['username']
        return jsonify({'success': True, 'role': user['role'], 'fullname': session['fullname']})

    return jsonify({'success': False, 'error': 'Неверный логин или пароль'}), 401


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    fullname = str(data.get('fullname', '')).strip()
    email = str(data.get('email', '')).strip().lower()

    if not username or not password:
        return jsonify({'success': False, 'error': 'Заполните логин и пароль'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'error': 'Пароль должен быть не короче 6 символов'}), 400

    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO users (username, email, fullname, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (username, email or None, fullname, generate_password_hash(password), 'user', datetime.now().isoformat())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'error': 'Пользователь с таким логином или email уже существует'}), 409
    conn.close()

    return jsonify({'success': True, 'message': 'Регистрация успешна'})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))




@app.route('/api/external_competitions/<external_competition_id>', methods=['GET'])
@login_required
def api_get_external_competition(external_competition_id):
    """Получение конкурса из модуля автоматизации для интеграционного режима."""
    try:
        competition = load_external_competition(external_competition_id)
        return jsonify(competition)
    except Exception as e:
        return jsonify({'error': str(e)}), 502

@app.route('/api/competitions', methods=['GET'])
def api_get_competitions():
    try:
        return jsonify(get_external_contests())
    except Exception as e:
        print('Ошибка загрузки конкурсов из модуля автоматизации:', e)
        return jsonify([])


@app.route('/api/competitions', methods=['POST'])
@login_required
def api_create_competition():
    return jsonify({'error': 'Создание конкурса перенесено в модуль автоматизации'}), 410


@app.route('/api/competitions/<competition_id>', methods=['GET'])
def api_get_competition(competition_id):
    try:
        return jsonify(load_external_competition(competition_id))
    except Exception as e:
        print('Ошибка загрузки конкурса из модуля автоматизации:', e)
        return jsonify({'error': 'Competition not found'}), 404


@app.route('/api/competitions/<competition_id>', methods=['PUT'])
@login_required
def api_update_competition(competition_id):
    return jsonify({'error': 'Редактирование конкурса перенесено в модуль автоматизации'}), 410


@app.route('/api/competitions/<competition_id>', methods=['DELETE'])
@login_required
def api_delete_competition(competition_id):
    return jsonify({'error': 'Удаление конкурса перенесено в модуль автоматизации'}), 410


@app.route('/api/search_with_filters', methods=['POST'])
def api_search_with_filters():
    data = request.get_json(silent=True) or {}
    query = str(data.get('query', '')).strip()
    min_relevance = normalize_min_relevance(data.get('min_relevance', 0))
    sources = data.get('sources') or {}
    competition_id = data.get('external_competition_id') or data.get('competition_id')
    directions = data.get('directions') or []

    competition_criteria = None
    if competition_id:
        try:
            competition = load_external_competition(competition_id)
            if not query:
                query = build_external_search_text(competition)
            competition_criteria = {
                'nominations': [],
                'criteria': ', '.join(competition.get('criteria', [])),
                'problem': competition.get('description', ''),
                'expected_results': '',
                'priority_topics': ', '.join(competition.get('priority_topics', [])),
                'topic': competition.get('topic', ''),
                'goal': competition.get('goal', ''),
            }
            if not directions:
                directions = competition.get('directions') or []
        except Exception as e:
            print('Не удалось получить внешний конкурс:', e)

    if not query:
        return jsonify({'error': 'Не удалось сформировать поисковый профиль конкурса'}), 400

    results = engine.search(
        query,
        top_k=300,
        competition_criteria=competition_criteria,
        selected_directions=directions,
    )

    print('=== ОТЛАДКА ПОИСКА ===')
    print(f'Запрос сформирован по конкурсу: {query[:300]}')
    print(f'min_relevance: {min_relevance}')
    print(f'competition_id/external_competition_id: {competition_id}')
    print(f'Найдено проектов до фильтрации: {len(results)}')

    results = source_filter(results, sources)
    results = [r for r in results if float(r.get('relevance_percent', 0) or 0) >= min_relevance]

    for r in results:
        enrich_contacts_for_response(r)

    results = results[:100]
    print(f'Найдено проектов после фильтров: {len(results)}')
    print('=== КОНЕЦ ОТЛАДКИ ===')

    return jsonify({'query': query, 'results_count': len(results), 'results': results})


@app.route('/api/search', methods=['POST'])
@login_required
def api_search():
    data = request.get_json(silent=True) or {}
    query = str(data.get('query', '')).strip()
    if not query:
        return jsonify({'error': 'Пустой поисковый запрос'}), 400
    limit = int(data.get('top_k', 20) or 20)
    results = engine.search(query=query, filters=data.get('filters', {}), top_k=limit)
    return jsonify({'query': query, 'results_count': len(results), 'results': results})


@app.route('/api/search_live', methods=['POST'])
@login_required
def api_search_live():
    data = request.get_json(silent=True) or {}
    query = str(data.get('query', '')).strip()
    min_relevance = normalize_min_relevance(data.get('min_relevance', 0))
    sources = data.get('sources') or {}
    limit = int(data.get('limit', 25) or 25)
    if not query:
        return jsonify({'error': 'Запрос не может быть пустым'}), 400
    results = live_engine.search_combined(query, sources, min_relevance, limit)
    return jsonify({'query': query, 'results_count': len(results), 'results': results, 'source': 'live_api'})


@app.route('/api/search_hybrid', methods=['POST'])
@login_required
def api_search_hybrid():
    data = request.get_json(silent=True) or {}
    query = str(data.get('query', '')).strip()
    min_relevance = normalize_min_relevance(data.get('min_relevance', 0))
    sources = data.get('sources') or {}
    if not query:
        return jsonify({'error': 'Запрос не может быть пустым'}), 400
    local_results = engine.search(query, top_k=100)
    local_results = [r for r in local_results if float(r.get('relevance_percent', 0) or 0) >= min_relevance]
    local_results = source_filter(local_results, sources)
    live_results = live_engine.search_combined(query, sources, min_relevance, 20)
    titles = {str(r.get('title', '')).lower() for r in local_results}
    for r in live_results:
        if str(r.get('title', '')).lower() not in titles:
            local_results.append(r)
    local_results.sort(key=lambda x: x.get('relevance_percent', 0), reverse=True)
    return jsonify({'query': query, 'results_count': len(local_results), 'results': local_results[:100], 'source': 'hybrid'})


@app.route('/api/search_vk_cascaded', methods=['POST'])
@login_required
def api_search_vk_cascaded():
    data = request.get_json(silent=True) or {}
    author_name = str(data.get('author_name', '')).strip()
    affiliation = str(data.get('affiliation', '')).strip()
    if not author_name:
        return jsonify({'error': 'Имя автора не указано'}), 400
    result = vk_hunter.search_person_cascaded({'full_name': author_name, 'affiliation': affiliation})
    if result is None:
        return jsonify({'type': 'none', 'vk_search_url': f'https://vk.com/search?c[q]={author_name}&c[section]=people'})
    if isinstance(result, list):
        return jsonify({'type': 'multiple', 'users': result})
    return jsonify({'type': 'single', 'user': result})


@app.route('/api/invite_actions', methods=['POST'])
@login_required
def api_invite_actions():
    data = request.get_json(silent=True) or {}
    projects = data.get('projects') or []
    competition_id = data.get('competition_id')
    external_competition_id = data.get('external_competition_id')
    if external_competition_id:
        try:
            competition = load_external_competition(external_competition_id)
        except Exception:
            competition = None
    else:
        competition = normalize_competition(competitions_db.get_by_id(competition_id)) if competition_id else None

    enriched = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        item = dict(project)
        enrich_contacts_for_response(item)
        item['invite_actions'] = build_invite_actions(item, competition)
        enriched.append(item)

    return jsonify({'success': True, 'projects': enriched})


@app.route('/export', methods=['POST'])
@login_required
def export():
    data = request.get_json(silent=True) or {}
    results = data.get('results', [])
    if not results:
        return jsonify({'error': 'Нет результатов для экспорта'}), 400

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Название проекта', 'Авторы', 'Источник', 'Релевантность', 'Email', 'Telegram', 'Телефон', 'VK', 'Каналы', 'Ссылка', 'Аннотация'])
    for res in results:
        contacts = normalize_contacts(res)
        by_type = {'email': [], 'telegram': [], 'phone': [], 'vk': []}
        for contact in contacts:
            ctype = contact.get('type')
            value = contact.get('value')
            if ctype in by_type and value:
                by_type[ctype].append(value)
        authors = res.get('authors', [])
        if isinstance(authors, list):
            authors = ', '.join(str(a) for a in authors)
        channels = ', '.join(k for k, values in by_type.items() if values)
        writer.writerow([
            res.get('title', ''),
            authors,
            res.get('source', ''),
            f"{res.get('relevance_percent', 0)}%",
            ' | '.join(by_type['email']),
            ' | '.join(by_type['telegram']),
            ' | '.join(by_type['phone']),
            ' | '.join(by_type['vk']),
            channels,
            res.get('url', ''),
            str(res.get('abstract', ''))[:1000],
        ])

    content = output.getvalue()
    response = make_response('\uFEFF' + content)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=projects_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return response


@app.route('/send_to_review', methods=['POST'])
@login_required
def send_to_review():
    data = request.get_json(silent=True) or {}
    selected_projects = data.get('projects', [])
    competition_info = data.get('competition_info', {})
    if not selected_projects:
        return jsonify({'error': 'Нет выбранных проектов'}), 400

    sent_results = []
    for project in selected_projects:
        authors = project.get('authors', [])
        if isinstance(authors, list):
            authors = ', '.join(str(a) for a in authors)
        application = {
            'title': project.get('title', ''),
            'description': (
                f"Авторы: {authors}\n\n"
                f"{project.get('abstract', '')}\n\n"
                f"Конкурс: {competition_info.get('title', '')}\n"
                f"Тематика: {competition_info.get('topic', '')}"
            )
        }
        try:
            response = requests.post(f'{AUTOMATION_API_URL}/applications', json=application, timeout=10)
            if 200 <= response.status_code < 300:
                sent_results.append({'title': project.get('title', ''), 'status': 'sent'})
            else:
                sent_results.append({'title': project.get('title', ''), 'status': 'error', 'code': response.status_code})
        except Exception as e:
            sent_results.append({'title': project.get('title', ''), 'status': 'error', 'message': str(e)})

    return jsonify({'message': f'Обработано {len(sent_results)} проектов', 'results': sent_results})


@app.route('/status')
def status():
    automation_status = 'offline'
    try:
        response = requests.get(f'{AUTOMATION_API_URL}/health', timeout=5)
        automation_status = 'online' if response.status_code == 200 else 'unknown'
    except Exception:
        pass
    return jsonify({
        'search_engine': 'online',
        'automation_module': automation_status,
        'automation_url': AUTOMATION_API_URL,
        'automation_admin_url': AUTOMATION_ADMIN_URL,
        'users_db': USERS_DB_PATH,
    })


if __name__ == '__main__':
    cert_file = os.path.join(BASE_DIR, 'cert.pem')
    key_file = os.path.join(BASE_DIR, 'key.pem')
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print('Запуск с HTTPS (SSL)')
        app.run(debug=True, host='0.0.0.0', port=5000, ssl_context=(cert_file, key_file))
    else:
        print('SSL-сертификаты не найдены. Запуск без HTTPS.')
        app.run(debug=True, host='127.0.0.1', port=5000)


@app.route('/api/admin_return_url')
@login_required
def api_admin_return_url():
    contest_id = request.args.get('contest_id')
    return_url = request.args.get('return_url')
    return jsonify({"url": return_url or make_admin_return_url(contest_id)})
