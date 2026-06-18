import os
import psycopg2
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")

def init_db():
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable is missing!")
        return

    print("Connecting to cloud relational database engine...")
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                print("Purging stale tables to clear schema conflicts...")
                # Dropping tables in reverse order of foreign keys to avoid dependency blocks
                cursor.execute("DROP TABLE IF EXISTS configurations CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS attendance CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS schedules CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS subjects CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS users CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS sections CASCADE;")
                
                print("Deploying Fresh Relational Schema Matrices...")

                # 1. SECTIONS
                cursor.execute('''
                    CREATE TABLE sections (
                        id SERIAL PRIMARY KEY,
                        section_name TEXT UNIQUE NOT NULL
                    )
                ''')

                # 2. USERS
                cursor.execute('''
                    CREATE TABLE users (
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
                    CREATE TABLE subjects (
                        id SERIAL PRIMARY KEY,
                        subject_code TEXT UNIQUE NOT NULL,
                        subject_name TEXT NOT NULL,
                        teacher_id INTEGER,
                        FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                ''')
                
                # 4. SCHEDULES
                cursor.execute('''
                    CREATE TABLE schedules (
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
                    CREATE TABLE attendance (
                        id SERIAL PRIMARY KEY,
                        student_id INTEGER NOT NULL,
                        subject_id INTEGER NOT NULL,
                        date TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('Present', 'Absent')),
                        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
                    )
                ''')
                
                # 6. CONFIGURATIONS
                cursor.execute('''
                    CREATE TABLE configurations (
                        "key" TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                ''')
                
                # Seed system values
                cursor.execute('INSERT INTO configurations ("key", value) VALUES (\'min_attendance\', \'75\');')
                
                hashed_admin_password = generate_password_hash("admin123", method="scrypt")
                cursor.execute("""
                    INSERT INTO users (username, password, name, role, is_deleted) 
                    VALUES ('admin', %s, 'Root System Administrator', 'admin', 0);
                """, (hashed_admin_password,))
                
                conn.commit()
                print("Database tables built and seeded perfectly.")
    except Exception as e:
        print(f"Critical Error during initialization: {str(e)}")

if __name__ == '__main__':
    init_db()
