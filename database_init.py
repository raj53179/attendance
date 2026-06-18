import os
import psycopg2
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")

def init_db():
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable is missing!")
        return

    print("Connecting to cloud relational database engine...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("Deploying Relational Schema Matrices...")

    # 1. SECTIONS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id SERIAL PRIMARY KEY,
            section_name TEXT UNIQUE NOT NULL
        )
    ''')

    # 2. USERS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL, 
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'coordinator', 'teacher', 'student')),
            section_id INTEGER, 
            created_by INTEGER, 
            is_deleted INTEGER DEFAULT 0,
            FOREIGN KEY(section_id) REFERENCES sections(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')
    
    # 3. SUBJECTS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            subject_code TEXT UNIQUE NOT NULL,
            subject_name TEXT NOT NULL,
            teacher_id INTEGER,
            FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')
    
    # 4. SCHEDULES
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id SERIAL PRIMARY KEY,
            subject_id INTEGER,
            section_id INTEGER,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
            FOREIGN KEY(section_id) REFERENCES sections(id) ON DELETE CASCADE
        )
    ''')
    
    # 5. ATTENDANCE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            student_id INTEGER,
            subject_id INTEGER,
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            status TEXT NOT NULL CHECK(status IN ('Present', 'Absent')),
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    ''')
    
    # 6. CONFIGURATIONS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configurations (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Defaults and Root Seeding
    cursor.execute("INSERT INTO configurations (key, value) VALUES ('min_attendance', '75') ON CONFLICT (key) DO NOTHING;")
    
    hashed_admin_password = generate_password_hash("admin123", method="scrypt")
    cursor.execute("""
        INSERT INTO users (username, password, name, role, is_deleted) 
        VALUES ('admin', %s, 'Root System Administrator', 'admin', 0)
        ON CONFLICT (username) DO NOTHING;
    """, (hashed_admin_password,))
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialization step completed successfully.")

if __name__ == '__main__':
    init_db()