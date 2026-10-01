"""
Database initialization and helper functions.
Provides the SQLAlchemy db instance for use throughout the application.
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from pathlib import Path
import os

# Initialize SQLAlchemy
db = SQLAlchemy()


def migrate_schema(app):
    """
    Safely migrate SQLite database schema to ensure new tables and columns exist
    without dropping existing tables or losing any existing records.
    """
    with app.app_context():
        # Ensure all model tables exist
        db.create_all()

        try:
            inspector = inspect(db.engine)
            existing_tables = set(inspector.get_table_names())

            def get_cols(tbl):
                if tbl not in existing_tables:
                    return set()
                return {c["name"] for c in inspector.get_columns(tbl)}

            # 1. Update courses table
            if "courses" in existing_tables:
                course_cols = get_cols("courses")
                if "status" not in course_cols:
                    db.session.execute(db.text("ALTER TABLE courses ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                    print("  [MIGRATE] Added status to courses table")
                if "updated_at" not in course_cols:
                    db.session.execute(db.text("ALTER TABLE courses ADD COLUMN updated_at DATETIME"))
                    print("  [MIGRATE] Added updated_at to courses table")

            # 2. Update classes table
            if "classes" in existing_tables:
                class_cols = get_cols("classes")
                if "course_id" not in class_cols:
                    db.session.execute(db.text("ALTER TABLE classes ADD COLUMN course_id INTEGER REFERENCES courses(id)"))
                    print("  [MIGRATE] Added course_id to classes table")
                if "status" not in class_cols:
                    db.session.execute(db.text("ALTER TABLE classes ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                    print("  [MIGRATE] Added status to classes table")
                if "updated_at" not in class_cols:
                    db.session.execute(db.text("ALTER TABLE classes ADD COLUMN updated_at DATETIME"))
                    print("  [MIGRATE] Added updated_at to classes table")

            # 3. Update students table
            if "students" in existing_tables:
                student_cols = get_cols("students")
                if "course_id" not in student_cols:
                    db.session.execute(db.text("ALTER TABLE students ADD COLUMN course_id INTEGER REFERENCES courses(id)"))
                    print("  [MIGRATE] Added course_id to students table")
                if "face_image_path" not in student_cols:
                    db.session.execute(db.text("ALTER TABLE students ADD COLUMN face_image_path VARCHAR(255)"))
                    print("  [MIGRATE] Added face_image_path to students table")

            # 4. Update attendance_records table
            if "attendance_records" in existing_tables:
                rec_cols = get_cols("attendance_records")
                if "roll_no" not in rec_cols:
                    db.session.execute(db.text("ALTER TABLE attendance_records ADD COLUMN roll_no VARCHAR(50)"))
                    print("  [MIGRATE] Added roll_no to attendance_records table")
                if "course_id" not in rec_cols:
                    db.session.execute(db.text("ALTER TABLE attendance_records ADD COLUMN course_id INTEGER REFERENCES courses(id)"))
                    print("  [MIGRATE] Added course_id to attendance_records table")
                if "class_id" not in rec_cols:
                    db.session.execute(db.text("ALTER TABLE attendance_records ADD COLUMN class_id INTEGER REFERENCES classes(id)"))
                    print("  [MIGRATE] Added class_id to attendance_records table")
                if "recognition_status" not in rec_cols:
                    db.session.execute(db.text("ALTER TABLE attendance_records ADD COLUMN recognition_status VARCHAR(50) DEFAULT 'Recognized'"))
                    print("  [MIGRATE] Added recognition_status to attendance_records table")

            db.session.commit()
            print("  [OK] Schema migration completed without auto-seeding demo data.")

        except Exception as e:
            db.session.rollback()
            print(f"  [WARN] Schema migration note: {e}")


def reset_to_clean_state(app):
    """
    Reset database to a clean production state:
    Removes all courses, classes, students, teachers, face data, and attendance records,
    while ensuring the primary administrator account is present to access Admin.
    """
    from models import (User, Course, Class, Student, Teacher, Department,
                        Subject, FaceEmbedding, AttendanceSession, AttendanceRecord,
                        AuditLog, FaceRecognitionLog)
    with app.app_context():
        try:
            # Delete records in dependency order
            AttendanceRecord.query.delete()
            AttendanceSession.query.delete()
            FaceRecognitionLog.query.delete()
            FaceEmbedding.query.delete()
            Student.query.delete()
            Subject.query.delete()
            Teacher.query.delete()
            Class.query.delete()
            Course.query.delete()
            Department.query.delete()
            AuditLog.query.delete()

            # Remove non-admin users
            User.query.filter(User.role != 'admin').delete()

            # Ensure at least one admin account exists
            admin_user = User.query.filter_by(role='admin').first()
            if not admin_user:
                admin_user = User(
                    email="admin@school.edu",
                    name="System Administrator",
                    role="admin",
                    is_active=True
                )
                admin_user.set_password("admin123")
                db.session.add(admin_user)
            else:
                admin_user.is_active = True

            db.session.commit()

            # Synchronize CSV file with clean database state
            csv_path = Path(__file__).resolve().parent / "Attendance.csv"
            try:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    f.write("Student Roll Number,Student Name,Class,Course,Date,Time,Attendance Status,Face Recognition Status\n")
            except Exception as e:
                print(f"[WARN] Could not reset Attendance.csv: {e}")

            print("[CLEAN] Database reset to clean state successfully.")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Clean database reset failed: {e}")
            return False


def seed_default_academic_data():
    """Ensure standard courses and classes exist for the Face Recognition Attendance System."""
    from models import Course, Class, Department

    # Standard course definitions
    standard_courses = [
        ("Artificial Intelligence & Machine Learning", "AI & ML", "AI & ML Specialization Course"),
        ("Computer Science", "CS", "Computer Science Degree Course"),
        ("Data Science", "DS", "Data Science & Big Data Course"),
    ]

    for name, code, desc in standard_courses:
        existing = Course.query.filter((Course.code == code) | (Course.name == name)).first()
        if not existing:
            c = Course(name=name, code=code, description=desc)
            db.session.add(c)
    db.session.commit()

    # Link existing classes or seed standard classes (B.Sc 1st, 2nd, 3rd Year)
    aiml_course = Course.query.filter_by(code="AI & ML").first()
    cs_course = Course.query.filter_by(code="CS").first()
    ds_course = Course.query.filter_by(code="DS").first()

    dept = Department.query.first()
    dept_id = dept.id if dept else 1

    standard_classes = [
        ("B.Sc 1st Year", "AIML-1", aiml_course.id if aiml_course else None),
        ("B.Sc 2nd Year", "AIML-2", aiml_course.id if aiml_course else None),
        ("B.Sc 3rd Year", "AIML-3", aiml_course.id if aiml_course else None),
        ("B.Sc 1st Year", "CS-1", cs_course.id if cs_course else None),
        ("B.Sc 2nd Year", "CS-2", cs_course.id if cs_course else None),
        ("B.Sc 3rd Year", "CS-3", cs_course.id if cs_course else None),
        ("B.Sc 1st Year", "DS-1", ds_course.id if ds_course else None),
        ("B.Sc 2nd Year", "DS-2", ds_course.id if ds_course else None),
        ("B.Sc 3rd Year", "DS-3", ds_course.id if ds_course else None),
    ]

    for name, code, course_id in standard_classes:
        if not course_id:
            continue
        existing_cls = Class.query.filter_by(name=name, course_id=course_id).first()
        if not existing_cls:
            cls_obj = Class(name=name, code=code, course_id=course_id, department_id=dept_id, capacity=60)
            db.session.add(cls_obj)

    # Link any unlinked classes to CS course
    if cs_course:
        unlinked = Class.query.filter(Class.course_id.is_(None)).all()
        for u in unlinked:
            u.course_id = cs_course.id

    db.session.commit()


def ensure_default_accounts():
    """
    Ensure standard verified accounts exist for all four roles
    (Admin, Teacher, Faculty, Student) with hashed passwords and associated profile records.
    """
    from models import User, Teacher, Student, Department, Class

    # Ensure default department exists
    dept = Department.query.first()
    if not dept:
        dept = Department(name="Computer Science & Engineering", code="CSE")
        db.session.add(dept)
        db.session.flush()

    default_users = [
        {
            "email": "admin@school.edu",
            "name": "Administrator",
            "role": "admin",
            "password": "admin123",
        },
        {
            "email": "admin@attendai.edu",
            "name": "System Administrator",
            "role": "admin",
            "password": "admin123",
        },
        {
            "email": "teacher@school.edu",
            "name": "Teacher Account",
            "role": "teacher",
            "password": "password123",
            "employee_id": "TCH001",
        },
        {
            "email": "faculty@school.edu",
            "name": "Prof. David Miller",
            "role": "faculty",
            "password": "faculty123",
            "employee_id": "FAC001",
        },
        {
            "email": "student1@school.edu",
            "name": "Student Account",
            "role": "student",
            "password": "student123",
        },
    ]

    for item in default_users:
        user = User.query.filter_by(email=item["email"]).first()
        if not user:
            user = User(
                email=item["email"],
                name=item["name"],
                role=item["role"],
                is_active=True,
            )
            user.set_password(item["password"])
            db.session.add(user)
            db.session.flush()
            print(f"  [SEED] Created default {item['role']} user: {item['email']}")
        else:
            # Ensure active and proper role
            user.is_active = True
            user.role = item["role"]
            if not user.password_hash:
                user.set_password(item["password"])

        # Link profile if needed
        if item["role"] in ("teacher", "faculty"):
            t_profile = Teacher.query.filter_by(user_id=user.id).first()
            if not t_profile and "employee_id" in item:
                existing_emp = Teacher.query.filter_by(employee_id=item["employee_id"]).first()
                if not existing_emp:
                    t_profile = Teacher(
                        user_id=user.id,
                        employee_id=item["employee_id"],
                        department_id=dept.id if dept else None,
                        office="Faculty Room A-101",
                        phone="555-0101",
                    )
                    db.session.add(t_profile)

    # Note: Do not auto-seed dummy students into the student directory.
    # The student directory should only retain registered students added by the user or enrolled with face data.
    db.session.commit()


def init_db(app, config):
    """
    Initialize the database with the Flask application.
    
    Args:
        app: Flask application instance
        config: Configuration object
    """
    db.init_app(app)

    with app.app_context():
        migrate_schema(app)
        try:
            seed_default_academic_data()
            ensure_default_accounts()
        except Exception as e:
            db.session.rollback()
            print(f"  [WARN] Default data seed note: {e}")
        print("[OK] Database initialized and migrated successfully")


def create_all_tables(app):
    """Create all database tables (idempotent) and migrate schema."""
    with app.app_context():
        migrate_schema(app)
        print("[OK] All tables created and migrated")


def drop_all_tables(app):
    """Drop all database tables (use with caution)."""
    with app.app_context():
        response = input("WARNING: This will delete all data. Are you sure? (yes/no): ")
        if response.lower() == "yes":
            db.drop_all()
            print("[OK] All tables dropped")
        else:
            print("[CANCELLED] Cancelled")


def migrate_csv_to_db(app, csv_path="Attendance.csv"):
    """
    Migrate existing CSV attendance data to database.
    
    Args:
        app: Flask application instance
        csv_path: Path to the CSV file (relative to project root)
    """
    import csv
    from datetime import datetime
    from models import User, Student, Teacher, Class, AttendanceRecord, AttendanceSession

    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"[ERROR] CSV file not found: {csv_path}")
        return

    with app.app_context():
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                count = 0
                default_teacher = Teacher.query.first()
                default_class = Class.query.first()
                teacher_id = default_teacher.id if default_teacher else 1
                class_id = default_class.id if default_class else 1

                for row in reader:
                    try:
                        # Parse the CSV row
                        # Expected format: ID, Student Name, Date, Time, Status
                        student_id = int(row.get("ID", 0))
                        student_name = row.get("Student Name", "Unknown")
                        date_str = row.get("Date", "")
                        time_str = row.get("Time", "")
                        status = row.get("Status", "present").lower()

                        # Try to parse date and time
                        try:
                            attendance_date = datetime.strptime(
                                date_str, "%Y-%m-%d"
                            ).date()
                        except ValueError:
                            # Try alternative date format
                            try:
                                attendance_date = datetime.strptime(
                                    date_str, "%d/%m/%Y"
                                ).date()
                            except ValueError:
                                print(
                                    f"  ⚠ Skipping row - invalid date format: {date_str}"
                                )
                                continue

                        try:
                            attendance_time = datetime.strptime(
                                time_str, "%H:%M:%S"
                            ).time()
                        except ValueError:
                            attendance_time = datetime.strptime(
                                time_str, "%H:%M"
                            ).time()

                        # Check if student exists
                        student = Student.query.filter_by(id=student_id).first()
                        if not student:
                            # Create student if doesn't exist
                            student = Student(
                                id=student_id,
                                name=student_name,
                                roll_no=f"AUTO_{student_id}",
                                face_registered=False,
                            )
                            db.session.add(student)
                            db.session.flush()

                        # Create a default session if needed
                        existing_session = AttendanceSession.query.filter_by(
                            date=attendance_date
                        ).first()
                        if not existing_session:
                            session = AttendanceSession(
                                teacher_id=teacher_id,
                                class_id=class_id,
                                date=attendance_date,
                                start_time=datetime.strptime("09:00", "%H:%M").time(),
                                end_time=datetime.strptime("17:00", "%H:%M").time(),
                                status="completed",
                            )
                            db.session.add(session)
                            db.session.flush()
                            existing_session = session

                        # Create attendance record if not already recorded
                        existing_rec = AttendanceRecord.query.filter_by(
                            session_id=existing_session.id,
                            student_id=student.id,
                        ).first()
                        if not existing_rec:
                            record = AttendanceRecord(
                                session_id=existing_session.id,
                                student_id=student.id,
                                timestamp=datetime.combine(attendance_date, attendance_time),
                                status=status,
                                confidence=None,  # CSV doesn't have confidence
                            )
                            db.session.add(record)
                            count += 1

                        if count % 100 == 0:
                            db.session.commit()
                            print(f"  [OK] Migrated {count} records...")

                    except Exception as e:
                        print(f"  ⚠ Error processing row: {e}")
                        db.session.rollback()
                        continue

                db.session.commit()
                print(f"[OK] Migration complete: {count} attendance records migrated")

        except Exception as e:
            print(f"[ERROR] Migration failed: {e}")
            db.session.rollback()


def get_table_columns(model_class):
    """
    Get column names for a given model class.
    
    Args:
        model_class: SQLAlchemy model class
        
    Returns:
        List of column names
    """
    mapper = inspect(model_class)
    return [column.name for column in mapper.columns]


def table_exists(table_name):
    """Check if a table exists in the database."""
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()
