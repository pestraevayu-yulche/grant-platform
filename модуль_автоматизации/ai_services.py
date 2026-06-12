# ai_services.py
import nltk
import json
from datetime import datetime, timedelta
from collections import defaultdict
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.probability import FreqDist
from transformers import pipeline
from sentence_transformers import SentenceTransformer, util
import numpy as np

# Скачиваем данные NLTK (один раз)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('punkt_tab')
    nltk.download('stopwords')
    nltk.download('averaged_perceptron_tagger')

# Загружаем модели
print("Загрузка AI моделей...")
try:
    sentiment_pipeline = pipeline("sentiment-analysis", model="blanchefort/rubert-base-cased-sentiment")
    sentence_model = SentenceTransformer('distiluse-base-multilingual-cased-v2')
    russian_stopwords = set(stopwords.words('russian'))
    print("AI модели загружены!")
except Exception as e:
    print(f"Ошибка загрузки моделей: {e}")
    print("Используется упрощенный режим валидации")
    sentiment_pipeline = None
    sentence_model = None
    russian_stopwords = set()


def analyze_field_text(text, field_name, min_length=50):
    """Детальный анализ текстового поля"""
    if not text or len(text.strip()) < 10:
        return {
            'status': 'error',
            'score': 0,
            'message': 'Поле не заполнено или слишком короткое',
            'recommendation': 'Заполните поле содержательным описанием'
        }

    sentences = sent_tokenize(text)
    words = word_tokenize(text.lower())
    words_clean = [w for w in words if w.isalpha() and w not in russian_stopwords and len(w) > 2]

    length_score = min(100, (len(text) / min_length) * 100) if min_length > 0 else 100

    paragraphs = text.split('\n\n')
    paragraphs_score = min(100, (len(paragraphs) / 3) * 100)
    sentences_score = min(100, (len(sentences) / 10) * 100)
    structure_score = (paragraphs_score + sentences_score) / 2

    if words_clean:
        word_freq = FreqDist(words_clean)
        rare_words = sum(1 for freq in word_freq.values() if freq == 1)
        uniqueness_score = min(100, (rare_words / len(word_freq)) * 200)
    else:
        uniqueness_score = 0

    final_score = (length_score * 0.4 + structure_score * 0.3 + uniqueness_score * 0.3)

    if final_score >= 80:
        status = 'excellent'
        message = 'Поле заполнено отлично'
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
        'details': {
            'length': len(text),
            'sentences': len(sentences),
            'paragraphs': len(paragraphs),
            'unique_words': len(set(words_clean)) if words_clean else 0
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

    # Список для хранения баллов по каждому критерию (каждый от 0 до 100)
    scores = []
    field_results = {}

    # 1. Анализ паспортных данных (макс 100)
    passport_result = check_passport_validity(
        data.get('passport_series', ''),
        data.get('passport_number', '')
    )
    field_results['passport_data'] = passport_result
    passport_score = 100 if passport_result['status'] == 'valid' else 0
    scores.append(passport_score)

    if passport_score == 0:
        result['recommendations'].extend(passport_result.get('errors', []))

    # 2. Анализ текстовых полей (каждое поле дает свой вклад в общий балл)
    text_fields = {
        'summary': {'weight': 3, 'name': 'Краткое описание проекта', 'min_length': 100},
        'problem': {'weight': 3, 'name': 'Описание проблемы', 'min_length': 100},
        'uniqueness': {'weight': 2, 'name': 'Уникальность решения', 'min_length': 80},
        'plan': {'weight': 2, 'name': 'План реализации', 'min_length': 100},
        'results': {'weight': 2, 'name': 'Ожидаемые результаты', 'min_length': 80},
        'audience': {'weight': 1, 'name': 'Целевая аудитория', 'min_length': 50}
    }

    max_text_score = 100  # Максимальный балл за все текстовые поля
    total_weight = sum(f['weight'] for f in text_fields.values())
    weighted_score_sum = 0

    for field_key, field_info in text_fields.items():
        text = data.get(field_key, '')
        analysis = analyze_field_text(text, field_info['name'], field_info['min_length'])
        field_results[field_key] = analysis

        # Балл поля (0-100) умножаем на вес
        weighted_score_sum += analysis['score'] * field_info['weight']

        if analysis['status'] in ['error', 'warning'] and analysis['recommendation']:
            result['recommendations'].append(f"{field_info['name']}: {analysis['recommendation']}")

    # Нормализуем балл текстовых полей (0-100)
    if total_weight > 0:
        text_score = weighted_score_sum / total_weight
    else:
        text_score = 0
    scores.append(text_score)

    # 3. Анализ финансов (макс 100)
    financial_result = check_financial_data(
        data.get('amount', 0),
        data.get('team_size', None)
    )
    field_results['financial'] = financial_result
    if financial_result['status'] == 'valid':
        financial_score = 100
    elif financial_result['status'] == 'warning':
        financial_score = 70
        result['recommendations'].extend(financial_result.get('recommendations', []))
    else:
        financial_score = 0
        result['recommendations'].extend(financial_result.get('errors', []))
    scores.append(financial_score)

    # 4. Проверка направления (макс 100)
    direction = data.get('direction', '')
    valid_directions = [
        'Цифровые технологии', 'Медицина', 'Биотехнологии',
        'Ресурсосберегающая техника', 'Новые материалы и химические технологии',
        'Новые приборы и интеллектуальные производственные технологии',
        'Креативные индустрии'
    ]
    if direction in valid_directions:
        direction_score = 100
        field_results['direction'] = {'status': 'valid', 'score': 100}
    else:
        direction_score = 0
        field_results['direction'] = {'status': 'error', 'score': 0}
        result['recommendations'].append('Выберите направление из списка')
    scores.append(direction_score)

    # 5. Проверка команды (макс 100)
    try:
        team_size = int(data.get('team_size', 1))
        if team_size >= 2:
            team_score = 100
            field_results['team'] = {'status': 'valid', 'score': 100}
        elif team_size == 1:
            team_score = 50
            field_results['team'] = {'status': 'warning', 'score': 50}
            result['recommendations'].append('Для реализации проекта рекомендуется собрать команду из 2+ человек')
        else:
            team_score = 0
            field_results['team'] = {'status': 'error', 'score': 0}
            result['recommendations'].append('Укажите количество участников команды')
    except:
        team_score = 0
        field_results['team'] = {'status': 'error', 'score': 0}
        result['recommendations'].append('Укажите корректное количество участников команды')
    scores.append(team_score)

    # Расчет итогового балла (простое среднее всех критериев)
    if scores:
        result['total_score'] = round(sum(scores) / len(scores), 2)
    else:
        result['total_score'] = 0

    # Ограничиваем 100 баллами (на всякий случай)
    if result['total_score'] > 100:
        result['total_score'] = 100

    # Определение статуса для формальной проверки
    if result['total_score'] >= 75:
        result['status'] = 'approved'
        result['can_approve'] = True
        result['recommendations'].insert(0, 'Заявка одобрена после формальной проверки')
    elif result['total_score'] >= 50:
        result['status'] = 'review'
        result['can_approve'] = False
        result['recommendations'].insert(0, 'Заявка требует доработки')
    else:
        result['status'] = 'rejected'
        result['can_approve'] = False
        result['recommendations'].insert(0, 'Заявка отклонена по результатам формальной проверки')

    result['fields_analysis'] = field_results
    result['summary'] = {
        'total_fields': len(field_results),
        'valid_fields': sum(1 for f in field_results.values() if f.get('status') == 'valid'),
        'warning_fields': sum(1 for f in field_results.values() if f.get('status') == 'warning'),
        'error_fields': sum(1 for f in field_results.values() if f.get('status') == 'error')
    }

    return result


# ================= ДОБАВЛЕННЫЕ ФУНКЦИИ =================

def generate_hearing_schedule(applications, contest_id=None):
    """Формирование графика заслушиваний"""
    schedule = []
    if not applications:
        return schedule

    # Фильтруем по конкурсу если нужно
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
            'application_id': app['id'],
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
    anomalies = []
    if not evaluations or len(evaluations) < 3:
        return anomalies

    scores = [e.get('score', 0) for e in evaluations]
    mean = np.mean(scores)
    std = np.std(scores)

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
        return {
            'total': 0,
            'winners': [],
            'reserve': [],
            'rejected': [],
            'average_score': 0
        }
        # Фильтруем по конкурсу
        if contest_id:
            applications = [app for app in applications if app.get('contest_id') == contest_id]

    sorted_apps = sorted(applications, key=lambda x: x.get('score', 0), reverse=True)

    scores = [a.get('score', 0) for a in sorted_apps]
    average_score = round(np.mean(scores), 2) if scores else 0

    total = len(sorted_apps)
    winners_count = min(3, total)
    reserve_count = min(3, total - winners_count)

    report = {
        'total': total,
        'winners': sorted_apps[:winners_count],
        'reserve': sorted_apps[winners_count:winners_count + reserve_count],
        'rejected': sorted_apps[winners_count + reserve_count:],
        'average_score': average_score
    }

    return report


# ================= НАЗНАЧЕНИЕ ЭКСПЕРТОВ =================

def auto_assign_experts(application_data, all_experts):
    """
    Интеллектуальное назначение экспертов на заявку
    """
    if not all_experts:
        return []

    direction = application_data.get('direction', '')

    scored_experts = []

    for expert in all_experts:
        score = 0.0  # Явно указываем float
        reasons = []

        # 1. Соответствие компетенциям (40 баллов)
        expertise_areas = expert.get('expertise_areas', [])
        if expertise_areas and direction in expertise_areas:
            score += 40.0
            reasons.append('Направление соответствует компетенции')
        elif not expertise_areas:
            score += 20.0
            reasons.append('Компетенции не указаны (базовое соответствие)')

        # 2. Текущая нагрузка (30 баллов)
        current_load = expert.get('current_load', 0)
        max_load = expert.get('max_load', 5)
        if current_load < max_load:
            load_score = ((max_load - current_load) / max_load) * 30.0
            score += load_score
            reasons.append(f'Доступен (нагрузка {current_load}/{max_load})')
        else:
            reasons.append(f'Перегружен (нагрузка {current_load}/{max_load})')

        # 3. Рейтинг эксперта (20 баллов) - преобразуем Decimal в float
        rating = expert.get('rating', 5.0)
        # Преобразуем rating в float (если это Decimal)
        try:
            rating_float = float(rating)
        except (TypeError, ValueError):
            rating_float = 5.0
        rating_score = (rating_float / 5.0) * 20.0
        score += rating_score
        reasons.append(f'Рейтинг: {rating_float}')

        # 4. Доступность (10 баллов)
        if expert.get('is_available', True):
            score += 10.0
            reasons.append('Активен')
        else:
            reasons.append('Недоступен')

        scored_experts.append({
            'expert_id': expert['id'],
            'full_name': expert['full_name'],
            'score': round(score, 2),
            'current_load': current_load,
            'reasons': reasons,
            'expertise_match': direction in expertise_areas if expertise_areas else False
        })

    # Сортируем по убыванию балла
    scored_experts.sort(key=lambda x: x['score'], reverse=True)

    # Выбираем топ-3 экспертов
    assigned = scored_experts[:3]

    return assigned

def calculate_expert_load_distribution(applications, experts):
    """
    Оптимальное распределение нагрузки между экспертами
    """
    if not experts:
        return {}

    # Копируем экспертов для расчета
    expert_loads = {e['id']: float(e.get('current_load', 0)) for e in experts}
    assignments = {e['id']: [] for e in experts}

    # Сортируем заявки по важности (по баллам)
    sorted_apps = sorted(applications, key=lambda x: float(x.get('score', 0)), reverse=True)

    for app in sorted_apps:
        available_experts = [
            e for e in experts
            if expert_loads[e['id']] < float(e.get('max_load', 5)) and e.get('is_available', True)
        ]

        if available_experts:
            # Выбираем эксперта с наименьшей нагрузкой
            best_expert = min(available_experts, key=lambda x: expert_loads[x['id']])
            assignments[best_expert['id']].append(app['id'])
            expert_loads[best_expert['id']] += 1

    return {
        'expert_loads': {k: float(v) for k, v in expert_loads.items()},
        'assignments': assignments,
        'total_applications': len(applications)
    }


def get_expert_recommendations(application_id, all_experts, all_applications):
    """
    Получение рекомендаций по экспертам на основе анализа похожих проектов
    """
    recommendations = []

    if not all_experts:
        return recommendations

    for expert in all_experts:
        expert_score = {
            'expert_id': expert['id'],
            'full_name': expert['full_name'],
            'recommendation_score': 0.0,
            'previous_experience': [],
            'suitability_reasons': []
        }

        # Проверка компетенций
        expertise_areas = expert.get('expertise_areas', [])
        if expertise_areas:
            expert_score['recommendation_score'] += 30.0
            expert_score['suitability_reasons'].append(f'Компетенции: {", ".join(expertise_areas[:3])}')

        # Оценка нагрузки
        current_load = float(expert.get('current_load', 0))
        max_load = float(expert.get('max_load', 5))
        if current_load < max_load:
            availability = (max_load - current_load) / max_load
            expert_score['recommendation_score'] += availability * 40.0
            expert_score['suitability_reasons'].append(f'Доступность: {current_load}/{max_load}')

        # Рейтинг
        rating = expert.get('rating', 5.0)
        try:
            rating_float = float(rating)
        except (TypeError, ValueError):
            rating_float = 5.0
        expert_score['recommendation_score'] += (rating_float / 5.0) * 30.0

        recommendations.append(expert_score)

    # Сортируем по рекомендательному баллу
    recommendations.sort(key=lambda x: x['recommendation_score'], reverse=True)

    return recommendations[:5]