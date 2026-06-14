# ai_services.py - ОБЛЕГЧЕННАЯ ВЕРСИЯ ДЛЯ RENDER
import nltk
import json
import os
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.probability import FreqDist
import numpy as np

# Скачиваем данные NLTK (один раз)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('punkt_tab')
    nltk.download('stopwords')
    nltk.download('averaged_perceptron_tagger')

# URL Hugging Face Space
HF_SPACE_URL = os.environ.get('HF_SPACE_URL', 'https://YuYulche-grant-platform-ai.hf.space')

# Русские стоп-слова
try:
    russian_stopwords = set(stopwords.words('russian'))
except:
    russian_stopwords = set()

# ===== ФУНКЦИИ ДЛЯ ВЫЗОВА API =====
def get_sentiment_via_api(text):
    """Вызов анализа тональности через Hugging Face API"""
    try:
        response = requests.post(
            f'{HF_SPACE_URL}/sentiment',
            json={'text': text[:512]},
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Ошибка API тональности: {e}")
    return {'label': 'NEUTRAL', 'score': 0.5}

def get_embedding_via_api(text):
    """Вызов получения эмбеддинга через Hugging Face API"""
    try:
        response = requests.post(
            f'{HF_SPACE_URL}/embed',
            json={'text': text},
            timeout=30
        )
        if response.status_code == 200:
            return response.json()['embedding']
    except Exception as e:
        print(f"Ошибка API эмбеддинга: {e}")
    return None

# ===== ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ (analyze_field_text, check_financial_data, 
# ai_validate_application_detailed, generate_hearing_schedule, detect_anomalies, 
# generate_final_report, auto_assign_experts) ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ =====
# НО нужно убрать импорт transformers и sentence_transformers!

def analyze_field_text(text, field_name, min_length=50, keywords=None):
    """Детальный анализ текстового поля с проверкой ключевых слов"""
    if not text or len(text.strip()) < 10:
        return {
            'status': 'error',
            'score': 0,
            'message': 'Поле не заполнено',
            'recommendation': 'Заполните поле содержательным описанием',
            'details': {'length': 0, 'sentences': 0, 'words': 0},
            'missing_keywords': keywords if keywords else []
        }

    if len(text.strip()) < min_length:
        return {
            'status': 'warning',
            'score': max(0, min(100, (len(text) / min_length) * 50)),
            'message': f'Текст слишком короткий ({len(text)} символов, рекомендуем {min_length})',
            'recommendation': f'Расширьте описание до {min_length} символов',
            'details': {'length': len(text), 'sentences': 0, 'words': 0},
            'missing_keywords': keywords if keywords else []
        }

    sentences = sent_tokenize(text)
    words = word_tokenize(text.lower())
    words_clean = [w for w in words if w.isalpha() and w not in russian_stopwords and len(w) > 2]

    length_score = min(100, (len(text) / min_length) * 100)

    paragraphs = text.split('\n\n')
    paragraphs_score = min(100, (len(paragraphs) / 3) * 100)
    sentences_score = min(100, (len(sentences) / 5) * 100)
    structure_score = (paragraphs_score + sentences_score) / 2

    if words_clean:
        word_freq = FreqDist(words_clean)
        rare_words = sum(1 for freq in word_freq.values() if freq == 1)
        uniqueness_score = min(100, (rare_words / len(word_freq)) * 200)
    else:
        uniqueness_score = 0

    keyword_score = 100
    missing_keywords = []
    if keywords:
        text_lower = text.lower()
        found_count = 0
        for kw in keywords:
            if kw.lower() in text_lower:
                found_count += 1
            else:
                missing_keywords.append(kw)
        keyword_score = (found_count / len(keywords)) * 100 if keywords else 100

    final_score = (length_score * 0.35 + structure_score * 0.25 + uniqueness_score * 0.20 + keyword_score * 0.20)

    if final_score >= 80:
        status = 'excellent'
        message = 'Поле заполнено отлично, тема раскрыта полностью'
        recommendation = ''
    elif final_score >= 60:
        status = 'good'
        message = 'Поле заполнено хорошо'
        recommendation = ''
    elif final_score >= 40:
        status = 'warning'
        message = 'Поле требует доработки'
        recommendation = 'Добавьте больше деталей и структурируйте текст'
    else:
        status = 'error'
        message = 'Поле заполнено неудовлетворительно'
        recommendation = 'Полностью переработайте описание, добавьте конкретику'

    return {
        'status': status,
        'score': round(final_score, 2),
        'message': message,
        'recommendation': recommendation,
        'missing_keywords': missing_keywords,
        'details': {
            'length': len(text),
            'sentences': len(sentences),
            'paragraphs': len(paragraphs),
            'unique_words': len(set(words_clean)) if words_clean else 0,
            'total_words': len(words_clean)
        }
    }

def check_passport_validity(series, number):
    """Проверка паспортных данных"""
    errors = []
    if not series or not series.isdigit() or len(series) != 4:
        errors.append('Серия паспорта должна содержать 4 цифры')
    if not number or not number.isdigit() or len(number) != 6:
        errors.append('Номер паспорта должен содержать 6 цифр')

    if errors:
        return {'status': 'error', 'errors': errors, 'score': 0}
    return {'status': 'valid', 'errors': [], 'score': 100}

def check_financial_data(amount, team_size=None):
    """Проверка финансовых данных"""
    errors = []
    recommendations = []

    try:
        amount = float(amount)
        if amount <= 0:
            errors.append('Сумма должна быть положительной')
        elif amount > 1000000:
            errors.append('Сумма превышает максимальный лимит гранта (1 млн рублей)')
            recommendations.append('Уменьшите запрашиваемую сумму или добавьте софинансирование')
        elif amount < 100000:
            recommendations.append('Рекомендуется увеличить запрашиваемую сумму для масштабирования проекта')

        if team_size and team_size > 0:
            efficiency = amount / team_size
            if efficiency > 1000000:
                recommendations.append('Высокая стоимость проекта на одного участника, проверьте обоснование расходов')
    except:
        errors.append('Некорректный формат суммы')

    if errors:
        return {'status': 'error', 'errors': errors, 'recommendations': recommendations, 'score': 0}
    elif recommendations:
        return {'status': 'warning', 'errors': [], 'recommendations': recommendations, 'score': 70}
    return {'status': 'valid', 'errors': [], 'recommendations': [], 'score': 100}

def ai_validate_application_detailed(data):
    """Детальная AI проверка заявки с анализом каждого поля (0-100 баллов)"""
    result = {
        'total_score': 0,
        'status': 'pending',
        'fields_analysis': {},
        'summary': {},
        'recommendations': [],
        'can_approve': False
    }

    field_results = {}

    # 1. Анализ паспортных данных
    passport_result = check_passport_validity(
        data.get('passport_series', ''),
        data.get('passport_number', '')
    )
    field_results['passport_data'] = passport_result
    passport_score = 100 if passport_result['status'] == 'valid' else 0

    if passport_score == 0:
        result['recommendations'].extend(passport_result.get('errors', []))

    # 2. Анализ текстовых полей
    text_fields = {
        'summary': {'weight': 3, 'name': 'Краткое описание проекта', 'min_length': 100, 'keywords': []},
        'problem': {'weight': 3, 'name': 'Описание проблемы', 'min_length': 100, 'keywords': []},
        'uniqueness': {'weight': 2, 'name': 'Уникальность решения', 'min_length': 80, 'keywords': []},
        'plan': {'weight': 2, 'name': 'План реализации', 'min_length': 100, 'keywords': []},
        'results': {'weight': 2, 'name': 'Ожидаемые результаты', 'min_length': 80, 'keywords': []},
        'audience': {'weight': 1, 'name': 'Целевая аудитория', 'min_length': 50, 'keywords': []}
    }

    total_weight = 0
    weighted_score_sum = 0

    for field_key, field_info in text_fields.items():
        text = data.get(field_key, '')
        analysis = analyze_field_text(
            text, field_info['name'],
            field_info['min_length'],
            field_info.get('keywords', [])
        )
        field_results[field_key] = analysis

        total_weight += field_info['weight']
        weighted_score_sum += analysis['score'] * field_info['weight']

        if analysis['status'] in ['error', 'warning'] and analysis['recommendation']:
            result['recommendations'].append(f"{field_info['name']}: {analysis['recommendation']}")

        if analysis.get('missing_keywords'):
            result['recommendations'].append(
                f"{field_info['name']}: не найдены ключевые слова: {', '.join(analysis['missing_keywords'][:3])}"
            )

    if total_weight > 0:
        text_score = weighted_score_sum / total_weight
    else:
        text_score = 0
    text_score = round(text_score, 2)

    # 3. Анализ финансов
    amount = data.get('amount', 0)
    team_size = data.get('team_size', None)

    if amount and float(amount) > 0:
        financial_result = check_financial_data(amount, team_size)
        if financial_result['status'] == 'valid':
            financial_score = 100
        elif financial_result['status'] == 'warning':
            financial_score = 70
            result['recommendations'].extend(financial_result.get('recommendations', []))
        else:
            financial_score = 0
            result['recommendations'].extend(financial_result.get('errors', []))
    else:
        financial_score = 0
        financial_result = {'status': 'error', 'errors': ['Сумма не указана'], 'recommendations': [], 'score': 0}
        result['recommendations'].append('Финансы: укажите запрашиваемую сумму')
    field_results['financial'] = financial_result

    # 4. Проверка направления
    direction = data.get('direction', '')
    valid_directions = [
        'Цифровые технологии', 'Медицина', 'Биотехнологии',
        'Ресурсосберегающая техника', 'Новые материалы и химические технологии',
        'Новые приборы и интеллектуальные производственные технологии',
        'Креативные индустрии'
    ]
    if direction in valid_directions:
        direction_score = 100
        field_results['direction'] = {'status': 'valid', 'score': 100, 'message': f'Направление: {direction}'}
    else:
        direction_score = 0
        field_results['direction'] = {'status': 'error', 'score': 0, 'message': 'Направление не указано или не из списка'}
        result['recommendations'].append('Выберите направление из списка')

    # 5. Проверка команды
    try:
        team_size = int(data.get('team_size', 0)) if data.get('team_size') else 0
        if team_size >= 2:
            team_score = 100
            field_results['team'] = {'status': 'valid', 'score': 100, 'message': f'Команда: {team_size} человека'}
        elif team_size == 1:
            team_score = 50
            field_results['team'] = {'status': 'warning', 'score': 50, 'message': 'Рекомендуется расширить команду'}
            result['recommendations'].append('Для реализации проекта рекомендуется собрать команду из 2+ человек')
        else:
            team_score = 0
            field_results['team'] = {'status': 'error', 'score': 0, 'message': 'Не указан размер команды'}
            result['recommendations'].append('Укажите количество участников команды')
    except:
        team_score = 0
        field_results['team'] = {'status': 'error', 'score': 0, 'message': 'Некорректные данные'}
        result['recommendations'].append('Укажите корректное количество участников команды')

    # Расчет итогового балла
    scores_list = [text_score, financial_score, direction_score, team_score]
    result['total_score'] = round(sum(scores_list) / len(scores_list), 2)

    if result['total_score'] > 100:
        result['total_score'] = 100

    field_results['Средний балл'] = {
        'status': 'good' if text_score >= 60 else ('warning' if text_score >= 40 else 'error'),
        'score': text_score,
        'message': f'Средний балл по текстовым полям: {text_score}%'
    }

    if result['total_score'] >= 75:
        result['status'] = 'approved'
        result['can_approve'] = True
        result['recommendations'].insert(0, 'Заявка одобрена по результатам AI проверки')
    elif result['total_score'] >= 50:
        result['status'] = 'review'
        result['can_approve'] = False
        result['recommendations'].insert(0, 'Заявка требует доработки')
    else:
        result['status'] = 'rejected'
        result['can_approve'] = False
        result['recommendations'].insert(0, 'Заявка отклонена по результатам AI проверки')

    result['fields_analysis'] = field_results
    result['summary'] = {
        'total_fields': len(field_results),
        'valid_fields': sum(1 for f in field_results.values() if f.get('status') in ['valid', 'excellent', 'good']),
        'warning_fields': sum(1 for f in field_results.values() if f.get('status') == 'warning'),
        'error_fields': sum(1 for f in field_results.values() if f.get('status') == 'error')
    }

    result['score_details'] = {
        'text_score': text_score,
        'financial_score': financial_score,
        'direction_score': direction_score,
        'team_score': team_score
    }

    return result

def generate_hearing_schedule(applications, contest_id=None):
    """Формирование графика заслушиваний"""
    schedule = []
    if not applications:
        return schedule

    if contest_id:
        applications = [app for app in applications if app.get('contest_id') == contest_id]

    start_date = datetime.now()
    days_until_monday = (7 - start_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    current_date = start_date + timedelta(days=days_until_monday)

    time_slots = ['10:00', '10:30', '11:00', '11:30', '12:00', '12:30',
                  '14:00', '14:30', '15:00', '15:30', '16:00', '16:30']

    slot_index = 0
    for app in applications:
        schedule.append({
            'application_id': app.get('id', 0),
            'project_name': app.get('project_name', 'Без названия'),
            'applicant': app.get('full_name', 'Не указан'),
            'date': current_date.strftime('%Y-%m-%d'),
            'time': time_slots[slot_index % len(time_slots)],
            'duration_minutes': 15
        })
        slot_index += 1
        if slot_index >= len(time_slots):
            slot_index = 0
            current_date += timedelta(days=1)
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)
    return schedule

def detect_anomalies(evaluations):
    """Выявление аномальных оценок"""
    if not evaluations or len(evaluations) < 3:
        return []
    scores = [e.get('score', 0) for e in evaluations]
    mean = np.mean(scores) if scores else 0
    std = np.std(scores) if scores else 0
    anomalies = []
    if std > 0:
        for evaluation in evaluations:
            z_score = abs((evaluation.get('score', 0) - mean) / std)
            if z_score > 2:
                anomalies.append({
                    'evaluation_id': evaluation.get('id', 0),
                    'expert_id': evaluation.get('expert_id', 0),
                    'score': evaluation.get('score', 0),
                    'z_score': round(z_score, 2),
                    'reason': f'Отклонение от среднего на {round(z_score, 2)} сигм'
                })
    return anomalies

def generate_final_report(applications, contest_id=None):
    """Формирование итогового отчета"""
    if not applications:
        return {'total': 0, 'winners': [], 'reserve': [], 'rejected': [], 'average_score': 0}
    
    if contest_id:
        applications = [app for app in applications if app.get('contest_id') == contest_id]

    sorted_apps = sorted(applications, key=lambda x: x.get('score', 0), reverse=True)
    scores = [a.get('score', 0) for a in sorted_apps]
    average_score = round(np.mean(scores), 2) if scores else 0
    total = len(sorted_apps)
    winners_count = min(3, total)
    reserve_count = min(3, total - winners_count)
    return {
        'total': total,
        'winners': sorted_apps[:winners_count],
        'reserve': sorted_apps[winners_count:winners_count + reserve_count],
        'rejected': sorted_apps[winners_count + reserve_count:],
        'average_score': average_score
    }

def auto_assign_experts(application_data, all_experts):
    """Автоматическое назначение экспертов"""
    if not all_experts:
        return []
    direction = application_data.get('direction', '')
    scored_experts = []
    for expert in all_experts:
        score = 0.0
        reasons = []
        expertise_areas = expert.get('expertise_areas', [])
        if expertise_areas and direction in expertise_areas:
            score += 40.0
            reasons.append('Направление соответствует компетенции')
        elif not expertise_areas:
            score += 20.0
            reasons.append('Компетенции не указаны')
        current_load = expert.get('current_load', 0)
        max_load = expert.get('max_load', 5)
        if current_load < max_load:
            load_score = ((max_load - current_load) / max_load) * 30.0
            score += load_score
            reasons.append(f'Доступен (нагрузка {current_load}/{max_load})')
        rating = expert.get('rating', 5.0)
        try:
            rating_float = float(rating)
        except:
            rating_float = 5.0
        rating_score = (rating_float / 5.0) * 20.0
        score += rating_score
        if expert.get('is_available', True):
            score += 10.0
            reasons.append('Активен')
        scored_experts.append({
            'expert_id': expert['id'],
            'full_name': expert['full_name'],
            'score': round(score, 2),
            'current_load': current_load,
            'reasons': reasons
        })
    scored_experts.sort(key=lambda x: x['score'], reverse=True)
    return scored_experts[:3]
