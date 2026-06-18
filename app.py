import os
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import database_init as db

app = Flask(__name__, template_folder='templates')
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

# Run database setup tables validation automatically on startup
if DATABASE_URL:
    db.init_db()

def get_db_connection():
    # Real-time connection string parsing for PostgreSQL
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# Helper utility to cleanly cast Real Dict Rows to primitive dictionaries
def row_to_dict(cursor_result):
    if cursor_result is None:
        return None
    return dict(cursor_result)

def rows_to_list(cursor_results):
    return [dict(row) for row in cursor_results]

@app.route('/')
def home():
    return render_template('index.html')


# --- AUTHENTICATION MODULE ENGINE ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    # 1. HARDCODED ADMIN CHECK
    if username == "admin":
        if password == "admin123":  # <-- Hardcoded Admin Credentials
            return jsonify({
                "status": "success",
                "role": "admin",
                "username": "admin",
                "name": "System Administrator"
            }), 200
        else:
            return jsonify({"error": "Invalid Admin Password"}), 401

    # 2. DATABASE USER CHECK (Teachers / Students / HODs)
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(
            "SELECT * FROM users WHERE username = %s AND is_deleted = 0", 
            (username,)
        )
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password'], password):
            return jsonify({
                'id': user['id'], 
                'username': user['username'], 
                'name': user['name'], 
                'role': user['role']
            }), 200
            
        return jsonify({'error': 'Invalid credentials'}), 401
    finally: 
        cursor.close()
        conn.close()

# --- SYSTEM ROOT ADMIN ROUTING PIPELINES ---
@app.route('/api/admin/coordinators', methods=['GET', 'POST'])
def manage_coordinators():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            hashed_password = generate_password_hash(data['password'], method='scrypt')
            cursor.execute("""
                INSERT INTO users (username, password, name, role, created_by, is_deleted) 
                VALUES (%s, %s, %s, 'coordinator', %s, 0)
            """, (data['username'], hashed_password, data['name'], data.get('admin_id')))
            conn.commit()
            return jsonify({'message': 'Coordinator deployment successful.'}), 201
            
        cursor.execute("SELECT id, username, name, role FROM users WHERE role = 'coordinator' AND is_deleted = 0")
        coordinators = cursor.fetchall()
        return jsonify(rows_to_list(coordinators))
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({'error': 'Coordinator reference ID already exists.'}), 400
    finally:
        cursor.close()
        conn.close()


# --- COORDINATOR HUB ADMINISTRATIVE ENDPOINTS ---
@app.route('/api/coordinator/users', methods=['GET', 'POST'])
def coordinator_manage_users():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            hashed_password = generate_password_hash(data['password'], method='scrypt')
            if data['role'] not in ['teacher', 'student']:
                return jsonify({'error': 'Unauthorized role layout configuration.'}), 403
                
            sec_id = None
            if data.get('section_name'):
                section_clean = data['section_name'].strip().upper()
                cursor.execute("INSERT INTO sections (section_name) VALUES (%s) ON CONFLICT (section_name) DO NOTHING", (section_clean,))
                cursor.execute("SELECT id FROM sections WHERE section_name = %s", (section_clean,))
                sec = cursor.fetchone()
                sec_id = sec['id'] if sec else None
                
            cursor.execute("""
                INSERT INTO users (username, password, name, role, section_id, created_by, is_deleted) 
                VALUES (%s, %s, %s, %s, %s, %s, 0)
            """, (data['username'].strip(), hashed_password, data['name'].strip(), data['role'], sec_id, data.get('coordinator_id')))
            conn.commit()
            return jsonify({'message': 'Profile provisioned successfully.'}), 201
            
        coordinator_id = request.args.get('coordinator_id')
        cursor.execute("""
            SELECT u.id, u.username, u.name, u.role, sec.section_name
            FROM users u 
            LEFT JOIN sections sec ON u.section_id = sec.id 
            WHERE u.role IN ('teacher', 'student') AND u.is_deleted = 0 AND u.created_by = %s
        """, (coordinator_id,))
        users = cursor.fetchall()
        return jsonify(rows_to_list(users))
    finally:
        cursor.close()
        conn.close()


@app.route('/api/coordinator/subjects', methods=['GET', 'POST'])
def coordinator_manage_subjects():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            cursor.execute("SELECT id FROM users WHERE username = %s AND role = 'teacher' AND is_deleted = 0", (data['teacher_id'].strip(),))
            teacher = cursor.fetchone()
            if not teacher:
                return jsonify({'error': f"Teacher ID '{data['teacher_id']}' does not exist."}), 404
                
            t_id = teacher['id']
            cursor.execute("INSERT INTO subjects (subject_code, subject_name, teacher_id) VALUES (%s, %s, %s)", 
                           (data['subject_code'].upper().strip(), data['subject_name'].strip(), t_id))
            conn.commit()
            return jsonify({'message': 'Subject mapped successfully.'}), 201
            
        cursor.execute("""
            SELECT s.id, s.subject_code, s.subject_name, u.username as teacher_uid, u.name as teacher_name 
            FROM subjects s LEFT JOIN users u ON s.teacher_id = u.id
        """)
        subjects = cursor.fetchall()
        return jsonify(rows_to_list(subjects))
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({'error': 'Subject code unique identifier duplication.'}), 400
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/coordinator/subjects/<int:sub_id>', methods=['DELETE'])
def coordinator_delete_subject(sub_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM subjects WHERE id = %s", (sub_id,))
        conn.commit()
        return jsonify({'message': 'Subject deleted successfully.'})
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/coordinator/schedules', methods=['GET', 'POST'])
def coordinator_manage_schedules():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            cursor.execute("SELECT id, subject_code FROM subjects WHERE subject_code = %s", (data['subject_code'].upper().strip(),))
            sub = cursor.fetchone()
            if not sub: 
                return jsonify({'error': 'Subject code does not exist in records.'}), 400
                
            cursor.execute("SELECT u.section_id FROM subjects s JOIN users u ON s.teacher_id = u.id WHERE s.id = %s", (sub['id'],))
            sub_mapping = cursor.fetchone()
            if sub_mapping and sub_mapping['section_id']:
                sec_id = sub_mapping['section_id']
            else:
                cursor.execute("SELECT id FROM sections LIMIT 1")
                default_sec = cursor.fetchone()
                sec_id = default_sec['id'] if default_sec else 1
                
            cursor.execute("""
                INSERT INTO schedules (subject_id, section_id, day_of_week, start_time, end_time) 
                VALUES (%s, %s, %s, %s, %s)
            """, (sub['id'], sec_id, data['day_of_week'], data['start_time'], data['end_time']))
            conn.commit()
            return jsonify({'message': 'Timetable entry generated successfully.'}), 201
            
        cursor.execute("""
            SELECT sch.id, sub.subject_code, sub.subject_name, sec.section_name, sch.day_of_week, sch.start_time, sch.end_time
            FROM schedules sch 
            JOIN subjects sub ON sch.subject_id = sub.id 
            LEFT JOIN sections sec ON sch.section_id = sec.id
            ORDER BY sch.day_of_week, sch.start_time
        """)
        schedules = cursor.fetchall()
        return jsonify(rows_to_list(schedules))
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/coordinator/schedules/<int:sch_id>', methods=['DELETE'])
def delete_schedule_slot(sch_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM schedules WHERE id = %s", (sch_id,))
        conn.commit()
        return jsonify({'message': 'Timetable block deleted.'})
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/coordinator/attendance-report', methods=['GET'])
def get_student_wise_attendance_report():
    coordinator_id = request.args.get('coordinator_id')
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT u.id, u.username as enrollment_no, u.name as student_name, sec.section_name,
                   COUNT(att.id) as total_lectures,
                   SUM(CASE WHEN att.status = 'Present' THEN 1 ELSE 0 END) as attended_lectures
            FROM users u
            LEFT JOIN sections sec ON u.section_id = sec.id
            LEFT JOIN attendance att ON u.id = att.student_id
            WHERE u.role = 'student' AND u.is_deleted = 0 AND u.created_by = %s
            GROUP BY u.id, u.username, u.name, sec.section_name
            ORDER BY u.username ASC
        """, (coordinator_id,))
        report = cursor.fetchall()
        
        extended_report = []
        for r in report:
            r_dict = dict(r)
            total = r_dict['total_lectures']
            present = r_dict['attended_lectures'] or 0
            r_dict['attendance_percentage'] = round((present / total) * 100) if total > 0 else 0
            extended_report.append(r_dict)
            
        return jsonify(extended_report)
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/admin/sections', methods=['GET', 'POST'])
def manage_sections():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            cursor.execute("INSERT INTO sections (section_name) VALUES (%s)", (data['section_name'].upper(),))
            conn.commit()
            return jsonify({'message': 'Section logged successfully'}), 201
        cursor.execute("SELECT * FROM sections")
        sections = cursor.fetchall()
        return jsonify(rows_to_list(sections))
    except psycopg2.errors.UniqueViolation: 
        conn.rollback()
        return jsonify({'error': 'Section already exists'}), 400
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/admin/users/edit', methods=['POST'])
def edit_user():
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed_password = generate_password_hash(data['password'], method='scrypt')
        # FIXED: Changed SQLite '?' formatting to PostgreSQL '%s' values
        cursor.execute(
            "UPDATE users SET name = %s, password = %s WHERE id = %s", 
            (data['name'].strip(), hashed_password, data['id'])
        )
        conn.commit()
        return jsonify({'message': 'User configuration modified'})
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def soft_delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET is_deleted = 1 WHERE id = %s", (user_id,))
        conn.commit()
        return jsonify({'message': 'Entry archived'})
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/admin/criteria', methods=['GET', 'POST'])
def manage_criteria():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            cursor.execute("UPDATE configurations SET value = %s WHERE key = 'min_attendance'", (data['min_attendance'],))
            conn.commit()
            return jsonify({'message': 'Criteria updated'})
        cursor.execute("SELECT value FROM configurations WHERE key = 'min_attendance'")
        crit = cursor.fetchone()
        return jsonify({'min_attendance': int(crit['value']) if crit else 75})
    finally: 
        cursor.close()
        conn.close()


# --- TEACHER MODULE ENDPOINTS ---
@app.route('/api/teacher/classes/<int:teacher_id>', methods=['GET'])
def get_teacher_classes(teacher_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT DISTINCT sec.id as section_id, sec.section_name
            FROM schedules sch
            JOIN subjects sub ON sch.subject_id = sub.id
            JOIN sections sec ON sch.section_id = sec.id
            WHERE sub.teacher_id = %s
        """, (teacher_id,))
        classes = cursor.fetchall()
        return jsonify(rows_to_list(classes))
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/teacher/schedules-by-class', methods=['GET'])
def get_schedules_by_class():
    teacher_id = request.args.get('teacher_id')
    section_id = request.args.get('section_id')
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT sch.id as schedule_id, sub.id as subject_id, sub.subject_code, sub.subject_name,
                   sch.day_of_week, sch.start_time, sch.end_time
            FROM schedules sch
            JOIN subjects sub ON sch.subject_id = sub.id
            WHERE sub.teacher_id = %s AND sch.section_id = %s
        """, (teacher_id, section_id))
        schedules = cursor.fetchall()
        return jsonify(rows_to_list(schedules))
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/teacher/students-by-section/<int:section_id>', methods=['GET'])
def get_section_students(section_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("SELECT id, username as enrollment_no, name FROM users WHERE role = 'student' AND section_id = %s AND is_deleted = 0", (section_id,))
        students = cursor.fetchall()
        return jsonify(rows_to_list(students))
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/teacher/fetch-past-attendance', methods=['GET'])
def fetch_past_attendance():
    subject_id = request.args.get('subject_id')
    date = request.args.get('date')
    start_time = request.args.get('start_time')
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT student_id, status FROM attendance 
            WHERE subject_id = %s AND date = %s AND start_time = %s
        """, (subject_id, date, start_time))
        records = cursor.fetchall()
        return jsonify(rows_to_list(records))
    finally: 
        cursor.close()
        conn.close()


@app.route('/api/teacher/attendance', methods=['POST'])
def submit_attendance():
    data = request.get_json() or {}
    subject_id = data.get('subject_id')
    date = data.get('date')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    records = data.get('records') or []
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for rec in records:
            cursor.execute("DELETE FROM attendance WHERE student_id = %s AND subject_id = %s AND date = %s AND start_time = %s", (rec['student_id'], subject_id, date, start_time))
            cursor.execute("INSERT INTO attendance (student_id, subject_id, date, start_time, end_time, status) VALUES (%s, %s, %s, %s, %s, %s)", (rec['student_id'], subject_id, date, start_time, end_time, rec['status']))
        conn.commit()
        return jsonify({'message': 'Attendance batch matrix logged successfully.'})
    finally: 
        cursor.close()
        conn.close()


# --- STUDENT PORTAL SERVICES ---
@app.route('/api/student/dashboard/<int:student_id>', methods=['GET'])
def get_student_dashboard(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("SELECT value FROM configurations WHERE key = 'min_attendance'")
        crit = cursor.fetchone()
        min_pct = int(crit['value']) if crit else 75
        
        cursor.execute("""
            SELECT s.id, s.subject_code, s.subject_name, COUNT(a.id) as total_classes, SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended
            FROM subjects s LEFT JOIN attendance a ON s.id = a.subject_id AND a.student_id = %s GROUP BY s.id, s.subject_code, s.subject_name
        """, (student_id,))
        subjects_data = cursor.fetchall()
        
        dashboard_report = []
        for sub in subjects_data:
            total = sub['total_classes']
            present = sub['attended'] or 0
            percentage = round((present / total) * 100) if total > 0 else 100
            status_alert = "Safe" if percentage >= min_pct else "Warning"
            
            consecutive_required = 0
            safe_skips = 0
            
            if percentage < min_pct:
                current_total = total
                current_present = present
                while (current_present / current_total * 100) < min_pct if current_total > 0 else True:
                    consecutive_required += 1
                    current_total += 1
                    current_present += 1
            else:
                current_total = total
                current_present = present
                while True:
                    next_total = current_total + 1
                    if (current_present / next_total * 100) >= min_pct:
                        safe_skips += 1
                        current_total += 1
                    else:
                        break
            
            dashboard_report.append({
                'subject_code': sub['subject_code'], 'subject_name': sub['subject_name'], 
                'total_classes': total, 'attended': present, 'percentage': percentage, 'status': status_alert,
                'consecutive_required': consecutive_required, 'safe_skips': safe_skips
            })
            
        cursor.execute("SELECT a.date, a.start_time, a.end_time, s.subject_code, s.subject_name, a.status FROM attendance a JOIN subjects s ON a.subject_id = s.id WHERE a.student_id = %s ORDER BY a.date DESC, a.start_time DESC", (student_id,))
        history = cursor.fetchall()
        return jsonify({'min_attendance_required': min_pct, 'subject_wise': dashboard_report, 'history': rows_to_list(history)})
    finally: 
        cursor.close()
        conn.close()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
