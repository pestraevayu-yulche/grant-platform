from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
import psycopg2
import psycopg2.extras
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
import json
from ai_services import ai_validate_application_detailed, generate_hearing_schedule, detect_anomalies, \
    generate_final_report, auto_assign_experts
from file_validator import validate_all_documents, extract_text_from_file

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

# ===== НАСТРОЙКИ ДЛЯ ЗАГРУЗКИ ФАЙЛОВ =====
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ===== БАЗА ДАННЫХ =====
def get_db_connection():
    return psycopg2.connect(
        dbname="grants_rf_new",
        user="postgres",
        password="1234",
        host="localhost",
        port="5432"
    )


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(200) NOT NULL,
            full_name VARCHAR(200) NOT NULL,
            email VARCHAR(100),
            phone VARCHAR(20),
            region VARCHAR(100),
            organization VARCHAR(200),
            role VARCHAR(50) DEFAULT 'applicant',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Таблица заявок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            contest VARCHAR(100),
            project_name VARCHAR(300) NOT NULL,
            full_name VARCHAR(200) NOT NULL,
            amount DECIMAL(12,2),
            team_size INTEGER DEFAULT 1,
            duration INTEGER DEFAULT 12,
            summary TEXT,
            problem TEXT,
            uniqueness TEXT,
            plan TEXT,
            results TEXT,
            audience TEXT,
            consent_file VARCHAR(500),
            education_file VARCHAR(500),
            status VARCHAR(50) DEFAULT 'На рассмотрении',
            created_at TIMESTAMP DEFAULT NOW(),
            ai_score INTEGER,
            ai_status VARCHAR(50),
            ai_recommendations TEXT,
            formal_score INTEGER,
            expert_score INTEGER,
            validation_errors TEXT,
            document_validation TEXT
        )
    """)

    # Таблица экспертов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experts (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(200) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            phone VARCHAR(20),
            expertise_areas TEXT[],
            current_load INTEGER DEFAULT 0,
            max_load INTEGER DEFAULT 5,
            rating DECIMAL(3,2) DEFAULT 5.0,
            is_available BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Таблица назначения экспертов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_experts (
            id SERIAL PRIMARY KEY,
            application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
            expert_ids INTEGER[],
            status VARCHAR(50) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Таблица оценок экспертов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expert_scores (
            id SERIAL PRIMARY KEY,
            project_expert_id INTEGER REFERENCES project_experts(id) ON DELETE CASCADE,
            expert_id INTEGER REFERENCES experts(id) ON DELETE CASCADE,
            criteria_name VARCHAR(100),
            score INTEGER CHECK (score >= 0 AND score <= 10),
            comment TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(project_expert_id, expert_id, criteria_name)
        )
    """)

    # Таблица уведомлений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expert_notifications (
            id SERIAL PRIMARY KEY,
            expert_id INTEGER REFERENCES experts(id) ON DELETE CASCADE,
            project_expert_id INTEGER REFERENCES project_experts(id) ON DELETE CASCADE,
            criteria VARCHAR(100),
            current_score INTEGER,
            recommended_score INTEGER,
            message TEXT,
            is_resolved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP
        )
    """)

    # Таблица рейтингов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_ratings (
            id SERIAL PRIMARY KEY,
            application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
            average_score DECIMAL(5,2),
            final_status VARCHAR(50),
            anomaly_detected BOOLEAN DEFAULT FALSE,
            report_data TEXT,
            expert_score DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Добавляем тестовых экспертов
    cursor.execute("SELECT * FROM experts WHERE email = 'a.kuznetsova@expert.ru'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO experts (full_name, email, expertise_areas, rating, is_available) VALUES
            ('Анна Сергеевна Кузнецова', 'a.kuznetsova@expert.ru', ARRAY['Культурный код'], 4.8, TRUE),
            ('Дмитрий Андреевич Морозов', 'd.morozov@expert.ru', ARRAY['Социальное действие'], 4.5, TRUE),
            ('Елена Владимировна Соколова', 'e.sokolova@expert.ru', ARRAY['Культурный код', 'Социальное действие'], 4.9, TRUE)
        """)

    # Добавляем админа
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (username, password, role, full_name, email)
            VALUES (%s, %s, 'admin', %s, %s)
        """, ('admin', generate_password_hash('admin123'), 'Главный организатор', 'admin@shagvpered.ru'))

    conn.commit()
    cursor.close()
    conn.close()


init_db()


# ===== ДЕКОРАТОРЫ =====
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect('/login')
        return f(*args, **kwargs)

    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect('/login')
        return f(*args, **kwargs)

    return wrapper


def expert_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('expert_id'):
            return redirect('/expert/login')
        return f(*args, **kwargs)

    return wrapper


# ===== ОСНОВНЫЕ МАРШРУТЫ =====
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = generate_password_hash(request.form.get('password'))
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        region = request.form.get('region')
        organization = request.form.get('organization')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (username, password, full_name, email, phone, region, organization)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (username, password, full_name, email, phone, region, organization))
            conn.commit()
            return redirect('/login')
        except psycopg2.IntegrityError:
            conn.rollback()
            return render_template('auth/register.html', error='Пользователь уже существует')
        finally:
            cursor.close()
            conn.close()
    return render_template('auth/register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            session['username'] = user['username']

            if user['role'] == 'admin':
                return redirect('/admin/dashboard')
            return redirect('/profile')

        return render_template('auth/login.html', error='Неверный логин или пароль')
    return render_template('auth/login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/apply', methods=['GET', 'POST'])
@login_required
def apply():
    if session.get('role') != 'applicant':
        return redirect('/login')

    selected_contest = request.args.get('contest', '')

    if request.method == 'POST':
        data = request.form.to_dict()

        consent_file = request.files.get('consent_file')
        education_file = request.files.get('education_file')

        consent_filename = None
        education_filename = None

        if consent_file and allowed_file(consent_file.filename):
            consent_filename = secure_filename(
                f"consent_{session['user_id']}_{datetime.now().timestamp()}_{consent_file.filename}")
            consent_file.save(os.path.join(app.config['UPLOAD_FOLDER'], consent_filename))

        if education_file and allowed_file(education_file.filename):
            education_filename = secure_filename(
                f"education_{session['user_id']}_{datetime.now().timestamp()}_{education_file.filename}")
            education_file.save(os.path.join(app.config['UPLOAD_FOLDER'], education_filename))

        contest_name = ''
        if data.get('contest') == 'youth':
            contest_name = 'Гранты Главы Республики Башкортостан'
        elif data.get('contest') == 'student':
            contest_name = 'Студенческие гранты России'
        else:
            contest_name = data.get('contest', '')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO applications (
                user_id, contest, project_name, full_name, amount, team_size, duration,
                summary, problem, uniqueness, plan, results, audience,
                consent_file, education_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session['user_id'],
            contest_name,
            data.get('project_name'),
            data.get('full_name'),
            data.get('amount'),
            data.get('team_size', 2),
            data.get('duration', 12),
            data.get('summary'),
            data.get('problem'),
            data.get('uniqueness'),
            data.get('plan'),
            data.get('results'),
            data.get('audience'),
            consent_filename,
            education_filename
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect('/profile')

    return render_template('apply.html', selected_contest=selected_contest)


@app.route('/profile')
@login_required
def profile():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT id, project_name, contest, amount, status, created_at
        FROM applications WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session['user_id'],))
    applications = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('profile.html', applications=applications, user=session)


# ===== АДМИН-ПАНЕЛЬ =====
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT a.*, u.username, u.email
        FROM applications a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.created_at DESC
    """)
    applications = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/dashboard.html', applications=applications)


@app.route('/admin/application/<int:app_id>')
@admin_required
def admin_application(app_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT a.*, u.username, u.email, u.phone, u.region
        FROM applications a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.id = %s
    """, (app_id,))
    app_data = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('admin/application_detail.html', app=app_data)


@app.route('/admin/update_status/<int:app_id>', methods=['POST'])
@admin_required
def update_status(app_id):
    new_status = request.form.get('status')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET status = %s WHERE id = %s", (new_status, app_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(f'/admin/application/{app_id}')


@app.route('/admin/download/<filename>')
@admin_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ===== AI МАРШРУТЫ =====
@app.route('/admin/ai_check/<int:app_id>')
@admin_required
def ai_check_application(app_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM applications WHERE id = %s", (app_id,))
    app_data = cursor.fetchone()

    if not app_data:
        return "Заявка не найдена", 404

    ai_result = ai_validate_application_detailed(dict(app_data))

    new_status = app_data['status']
    if ai_result['can_approve'] and ai_result['total_score'] >= 75:
        new_status = 'Одобрено'
    elif ai_result['total_score'] < 50:
        new_status = 'Отклонено'

    cursor.execute("""
        UPDATE applications 
        SET ai_score = %s,
            ai_status = %s,
            ai_recommendations = %s,
            formal_score = %s,
            validation_errors = %s,
            status = %s
        WHERE id = %s
    """, (
        ai_result['total_score'],
        ai_result['status'],
        json.dumps(ai_result['recommendations'], ensure_ascii=False),
        ai_result['total_score'],
        json.dumps(ai_result, ensure_ascii=False, default=str),
        new_status,
        app_id
    ))

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(f'/admin/application/{app_id}')


@app.route('/admin/ai_check_all')
@admin_required
def ai_check_all():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM applications")
    applications = cursor.fetchall()

    results = []
    for app in applications:
        ai_result = ai_validate_application_detailed(dict(app))

        new_status = app['status']
        if ai_result['can_approve'] and ai_result['total_score'] >= 75:
            new_status = 'Одобрено'
        elif ai_result['total_score'] < 50 and app['status'] == 'На рассмотрении':
            new_status = 'Отклонено'

        cursor.execute("""
            UPDATE applications 
            SET ai_score = %s,
                ai_status = %s,
                formal_score = %s,
                validation_errors = %s,
                status = %s
            WHERE id = %s
        """, (
            ai_result['total_score'],
            ai_result['status'],
            ai_result['total_score'],
            json.dumps(ai_result, ensure_ascii=False, default=str),
            new_status,
            app['id']
        ))

        results.append({
            'id': app['id'],
            'project_name': app['project_name'],
            'score': ai_result['total_score'],
            'new_status': new_status,
            'summary': ai_result['summary'],
            'fields_analysis': ai_result.get('fields_analysis', {}),
            'recommendations': ai_result.get('recommendations', [])[:5]
        })

    conn.commit()
    cursor.close()
    conn.close()
    return render_template('admin/ai_check_report.html', results=results, total=len(results))


# ===== УПРАВЛЕНИЕ ЭКСПЕРТАМИ =====
@app.route('/admin/experts')
@admin_required
def experts_list():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM experts ORDER BY rating DESC")
    experts = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/experts_list.html', experts=experts)


@app.route('/admin/experts/add', methods=['GET', 'POST'])
@admin_required
def add_expert():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        expertise_areas = request.form.getlist('expertise_areas')
        max_load = request.form.get('max_load', 5)
        rating = request.form.get('rating', 5.0)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO experts (full_name, email, phone, expertise_areas, max_load, rating, is_available)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """, (full_name, email, phone, expertise_areas, max_load, rating))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect('/admin/experts')

    return render_template('admin/add_expert.html')


@app.route('/admin/experts/<int:expert_id>/toggle')
@admin_required
def toggle_expert(expert_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE experts SET is_available = NOT is_available WHERE id = %s", (expert_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/admin/experts')


@app.route('/admin/experts/<int:expert_id>/delete')
@admin_required
def delete_expert(expert_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM experts WHERE id = %s", (expert_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/admin/experts')


# ===== НАЗНАЧЕНИЕ ЭКСПЕРТОВ =====
@app.route('/admin/assign_experts')
@admin_required
def assign_experts_page():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT a.* FROM applications a
        LEFT JOIN project_experts pe ON a.id = pe.application_id
        WHERE pe.id IS NULL AND a.status = 'Одобрено'
        ORDER BY a.created_at DESC
    """)
    pending_apps = cursor.fetchall()
    cursor.execute("SELECT * FROM experts WHERE is_available = TRUE ORDER BY rating DESC")
    experts = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/assign_experts.html', applications=pending_apps, experts=experts)


@app.route('/admin/assign_experts/do', methods=['POST'])
@admin_required
def do_assign_experts():
    application_id = request.form.get('application_id')
    expert_ids = request.form.getlist('expert_ids')

    if not application_id or not expert_ids:
        return redirect('/admin/assign_experts')

    conn = get_db_connection()
    cursor = conn.cursor()
    expert_ids_int = [int(e) for e in expert_ids]

    cursor.execute("""
        INSERT INTO project_experts (application_id, expert_ids, status)
        VALUES (%s, %s, 'pending')
    """, (application_id, expert_ids_int))

    for expert_id in expert_ids_int:
        cursor.execute("UPDATE experts SET current_load = current_load + 1 WHERE id = %s", (expert_id,))

    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/admin/project_experts')


@app.route('/admin/auto_assign')
@admin_required
def auto_assign():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT a.* FROM applications a
        LEFT JOIN project_experts pe ON a.id = pe.application_id
        WHERE pe.id IS NULL AND a.status = 'Одобрено'
        ORDER BY a.created_at DESC
    """)
    pending_apps = cursor.fetchall()
    cursor.execute("SELECT * FROM experts WHERE is_available = TRUE ORDER BY rating DESC")
    all_experts = cursor.fetchall()

    results = []
    for app in pending_apps:
        assigned = auto_assign_experts(dict(app), [dict(e) for e in all_experts])
        if assigned:
            expert_ids = [a['expert_id'] for a in assigned[:3]]
            cursor.execute("""
                INSERT INTO project_experts (application_id, expert_ids, status)
                VALUES (%s, %s, 'pending')
            """, (app['id'], expert_ids))
            for expert_id in expert_ids:
                cursor.execute("UPDATE experts SET current_load = current_load + 1 WHERE id = %s", (expert_id,))
            results.append({
                'application_id': app['id'],
                'project_name': app['project_name'],
                'assigned_experts': [a['full_name'] for a in assigned[:3]]
            })

    conn.commit()
    cursor.close()
    conn.close()
    return render_template('admin/auto_assign_result.html', results=results)


@app.route('/admin/project_experts')
@admin_required
def project_experts_list():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT 
            pe.id as pe_id,
            pe.application_id,
            pe.expert_ids,
            pe.status as pe_status,
            pe.created_at as assigned_date,
            a.project_name,
            a.full_name as applicant_name,
            a.direction,
            a.contest,
            a.status as app_status
        FROM project_experts pe
        JOIN applications a ON pe.application_id = a.id
        ORDER BY pe.created_at DESC
    """)

    assignments = []
    for row in cursor.fetchall():
        assignment = dict(row)
        expert_ids = assignment.get('expert_ids', [])
        if expert_ids:
            cursor.execute("SELECT id, full_name, email, rating FROM experts WHERE id = ANY(%s)", (expert_ids,))
            assignment['experts_detail'] = cursor.fetchall()
        else:
            assignment['experts_detail'] = []
        assignments.append(assignment)

    cursor.close()
    conn.close()
    return render_template('admin/project_experts_list.html', assignments=assignments)


@app.route('/admin/anomalies')
@admin_required
def anomalies_report():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT 
            pr.*,
            a.project_name,
            a.full_name as applicant_name
        FROM project_ratings pr
        JOIN applications a ON pr.application_id = a.id
        WHERE pr.anomaly_detected = TRUE
        ORDER BY pr.created_at DESC
    """)
    anomalies = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/anomalies.html', anomalies=anomalies)


# ===== ЭКСПЕРТНЫЙ КАБИНЕТ =====
@app.route('/expert/login', methods=['GET', 'POST'])
def expert_login():
    if request.method == 'POST':
        email = request.form.get('email')

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM experts WHERE email = %s", (email,))
        expert = cursor.fetchone()
        cursor.close()
        conn.close()

        if expert:
            session['expert_id'] = expert['id']
            session['expert_name'] = expert['full_name']
            session['expert_email'] = expert['email']
            session['role'] = 'expert'
            return redirect('/expert/dashboard')

        return render_template('expert/login.html', error='Эксперт с таким email не найден')

    return render_template('expert/login.html')


@app.route('/expert/dashboard')
@expert_required
def expert_dashboard():
    expert_id = session['expert_id']

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        SELECT n.*, a.project_name
        FROM expert_notifications n
        JOIN project_experts pe ON n.project_expert_id = pe.id
        JOIN applications a ON pe.application_id = a.id
        WHERE n.expert_id = %s AND n.is_resolved = FALSE
        ORDER BY n.created_at DESC
    """, (expert_id,))
    notifications = cursor.fetchall()

    cursor.execute("""
        SELECT 
            pe.id as pe_id,
            pe.application_id,
            pe.status as pe_status,
            a.project_name,
            a.full_name as applicant_name,
            a.summary,
            a.problem,
            a.direction,
            a.contest,
            a.amount,
            a.team_size
        FROM project_experts pe
        JOIN applications a ON pe.application_id = a.id
        WHERE %s = ANY(pe.expert_ids)
        ORDER BY 
            CASE WHEN pe.status = 'pending' THEN 0 ELSE 1 END,
            pe.created_at ASC
    """, (expert_id,))

    projects = []
    for row in cursor.fetchall():
        project = dict(row)
        cursor.execute("""
            SELECT COUNT(*) as score_count
            FROM expert_scores
            WHERE project_expert_id = %s AND expert_id = %s
        """, (project['pe_id'], expert_id))
        score_result = cursor.fetchone()
        project['has_scores'] = score_result['score_count'] > 0 if score_result else False
        projects.append(project)

    cursor.close()
    conn.close()

    return render_template('expert/dashboard.html',
                           projects=projects,
                           notifications=notifications,
                           expert_name=session.get('expert_name'))


@app.route('/expert/evaluate/<int:project_expert_id>', methods=['GET', 'POST'])
@expert_required
def expert_evaluate(project_expert_id):
    expert_id = session['expert_id']

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        SELECT 
            pe.*,
            a.project_name,
            a.full_name as applicant_name,
            a.summary,
            a.problem,
            a.uniqueness,
            a.plan,
            a.results,
            a.direction,
            a.contest,
            a.amount,
            a.team_size
        FROM project_experts pe
        JOIN applications a ON pe.application_id = a.id
        WHERE pe.id = %s
    """, (project_expert_id,))

    project = cursor.fetchone()

    if not project or expert_id not in project['expert_ids']:
        return "Доступ запрещён", 403

    if request.method == 'POST':
        criteria = ['Актуальность', 'Новизна', 'Реализуемость', 'Команда', 'Бюджет']

        for criterion in criteria:
            score = request.form.get(f'score_{criterion}')
            comment = request.form.get(f'comment_{criterion}')

            if score:
                cursor.execute("""
                    INSERT INTO expert_scores (project_expert_id, expert_id, criteria_name, score, comment)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (project_expert_id, expert_id, criteria_name) 
                    DO UPDATE SET score = EXCLUDED.score, comment = EXCLUDED.comment
                """, (project_expert_id, expert_id, criterion, int(score), comment))

        cursor.execute("UPDATE project_experts SET status = 'in_progress', updated_at = NOW() WHERE id = %s",
                       (project_expert_id,))
        conn.commit()

        cursor.execute("""
            SELECT COUNT(DISTINCT expert_id) as evaluated_count
            FROM expert_scores
            WHERE project_expert_id = %s
        """, (project_expert_id,))
        evaluated = cursor.fetchone()['evaluated_count']
        total_experts = len(project['expert_ids'])

        if evaluated >= total_experts:
            cursor.execute("UPDATE project_experts SET status = 'completed', updated_at = NOW() WHERE id = %s",
                           (project_expert_id,))
            conn.commit()

            # Функция финализации
            cursor.execute("""
                SELECT pe.application_id, a.project_name
                FROM project_experts pe
                JOIN applications a ON pe.application_id = a.id
                WHERE pe.id = %s
            """, (project_expert_id,))
            project_info = cursor.fetchone()

            cursor.execute("""
                SELECT AVG(score) as avg_score
                FROM expert_scores
                WHERE project_expert_id = %s
            """, (project_expert_id,))
            avg_result = cursor.fetchone()
            expert_score = round(avg_result['avg_score'] * 10, 2) if avg_result['avg_score'] else 0

            final_status = 'Победитель' if expert_score >= 85 else (
                'Рекомендовано' if expert_score >= 70 else 'Отклонено')

            cursor.execute("""
                INSERT INTO project_ratings (application_id, average_score, final_status, expert_score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (application_id) DO UPDATE SET
                    average_score = EXCLUDED.average_score,
                    final_status = EXCLUDED.final_status,
                    expert_score = EXCLUDED.expert_score
            """, (project_info['application_id'], expert_score, final_status, expert_score))

            cursor.execute("UPDATE applications SET status = %s, expert_score = %s WHERE id = %s",
                           (final_status, expert_score, project_info['application_id']))
            conn.commit()

        cursor.close()
        conn.close()
        return redirect('/expert/dashboard')

    cursor.execute("""
        SELECT criteria_name, score, comment
        FROM expert_scores
        WHERE project_expert_id = %s AND expert_id = %s
    """, (project_expert_id, expert_id))

    saved_scores = {}
    for row in cursor.fetchall():
        saved_scores[row['criteria_name']] = {'score': row['score'], 'comment': row['comment']}

    cursor.close()
    conn.close()

    return render_template('expert/evaluate.html', project=project, saved_scores=saved_scores)


@app.route('/expert/logout')
def expert_logout():
    session.pop('expert_id', None)
    session.pop('expert_name', None)
    session.pop('expert_email', None)
    return redirect('/expert/login')


# ===== ФИЛЬТРЫ =====
@app.template_filter('from_json')
def from_json_filter(value):
    if value:
        try:
            return json.loads(value)
        except:
            return {}
    return {}


# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    
