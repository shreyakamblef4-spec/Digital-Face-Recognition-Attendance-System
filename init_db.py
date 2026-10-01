#!/usr/bin/env python
"""
Database initialization and demo data setup.
Run this script to set up the database and populate it with test data.

Usage:
    python init_db.py --init      # Create all tables
    python init_db.py --demo      # Add demo data
    python init_db.py --migrate   # Migrate CSV to database
    python init_db.py --all       # Do all of the above
"""

import sys
import argparse
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app import app
from database import db, create_all_tables, drop_all_tables, migrate_csv_to_db
from models import User, Student, Teacher, Department, Class, Subject, Course


def init_database():
    """Create all database tables."""
    print("\n📦 Creating database tables...")
    create_all_tables(app)
    print("✓ Database tables created successfully")


def add_demo_data():
    """Add demo data to the database."""
    print("\n🌱 Adding demo data...")

    with app.app_context():
        try:
            # Create demo departments
            dept_cse = Department.query.filter_by(code="CSE").first()
            if not dept_cse:
                dept_cse = Department(
                    name="Computer Science & Engineering",
                    code="CSE",
                    description="Computer Science and Engineering Department"
                )
                db.session.add(dept_cse)
                db.session.flush()

            dept_ece = Department.query.filter_by(code="ECE").first()
            if not dept_ece:
                dept_ece = Department(
                    name="Electronics & Communication",
                    code="ECE",
                    description="Electronics and Communication Department"
                )
                db.session.add(dept_ece)
                db.session.flush()

            # Create demo classes
            class_cse_1a = Class.query.filter_by(code="CSE-1A").first()
            if not class_cse_1a:
                class_cse_1a = Class(
                    name="CSE 1-A",
                    code="CSE-1A",
                    department_id=dept_cse.id,
                    capacity=60
                )
                db.session.add(class_cse_1a)
                db.session.flush()

            class_cse_2b = Class.query.filter_by(code="CSE-2B").first()
            if not class_cse_2b:
                class_cse_2b = Class(
                    name="CSE 2-B",
                    code="CSE-2B",
                    department_id=dept_cse.id,
                    capacity=60
                )
                db.session.add(class_cse_2b)
                db.session.flush()

            # Create demo subjects
            subj_dsa = Subject.query.filter_by(code="CS101").first()
            if not subj_dsa:
                subj_dsa = Subject(
                    name="Data Structures & Algorithms",
                    code="CS101",
                    class_id=class_cse_1a.id,
                    credits=4
                )
                db.session.add(subj_dsa)
                db.session.flush()

            subj_db = Subject.query.filter_by(code="CS102").first()
            if not subj_db:
                subj_db = Subject(
                    name="Database Management Systems",
                    code="CS102",
                    class_id=class_cse_1a.id,
                    credits=4
                )
                db.session.add(subj_db)
                db.session.flush()

            # Create admin user
            admin_user = User.query.filter_by(email="admin@school.edu").first()
            if not admin_user:
                admin_user = User(
                    email="admin@school.edu",
                    name="Administrator",
                    role="admin"
                )
                admin_user.set_password("admin123")
                db.session.add(admin_user)
                db.session.flush()

            # Create faculty user
            faculty_user = User.query.filter_by(email="faculty@school.edu").first()
            if not faculty_user:
                faculty_user = User(
                    email="faculty@school.edu",
                    name="Dr. Faculty Member",
                    role="faculty"
                )
                faculty_user.set_password("faculty123")
                db.session.add(faculty_user)
                db.session.flush()

            # Create teacher
            teacher_user = User.query.filter_by(email="teacher@school.edu").first()
            if not teacher_user:
                teacher_user = User(
                    email="teacher@school.edu",
                    name="Teacher Account",
                    role="teacher"
                )
                teacher_user.set_password("password123")
                db.session.add(teacher_user)
                db.session.flush()

            teacher_profile = Teacher.query.filter_by(user_id=teacher_user.id).first()
            if not teacher_profile:
                teacher_profile = Teacher(
                    user_id=teacher_user.id,
                    employee_id="TEA001",
                    department_id=dept_cse.id,
                    phone="9876543210",
                    office="A-101"
                )
                db.session.add(teacher_profile)
                db.session.flush()

            # Ensure student authentication account exists without creating dummy directory profiles
            student_user = User.query.filter_by(email="student1@school.edu").first()
            if not student_user:
                student_user = User(
                    email="student1@school.edu",
                    name="Student Account",
                    role="student"
                )
                student_user.set_password("student123")
                db.session.add(student_user)
                db.session.flush()

            # Note: Do not auto-seed dummy students into the student directory.
            # Only registered students enrolled with face data or created by user are kept.

            db.session.commit()
            print("✓ Demo data ensured successfully")
            print("\n📋 Demo Credentials:")
            print("  Admin:    admin@school.edu / admin123")
            print("  Faculty:  faculty@school.edu / faculty123")
            print("  Teacher:  teacher@school.edu / password123")
            print("  Student:  student1@school.edu / student123")

        except Exception as e:
            print(f"✗ Error adding demo data: {e}")
            db.session.rollback()
            sys.exit(1)


def migrate_csv():
    """Migrate existing CSV attendance data to database."""
    print("\n📚 Migrating CSV data...")
    migrate_csv_to_db(app)


def main():
    parser = argparse.ArgumentParser(
        description="Initialize Face Recognition Attendance System database"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create database tables"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Add demo data"
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate CSV attendance data"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all initialization tasks"
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop all tables (WARNING: destructive)"
    )

    args = parser.parse_args()

    if not any([args.init, args.demo, args.migrate, args.all, args.drop]):
        parser.print_help()
        return

    if args.drop:
        drop_all_tables(app)
        return

    if args.init or args.all:
        init_database()

    if args.demo or args.all:
        add_demo_data()

    if args.migrate or args.all:
        migrate_csv()

    print("\n✅ Database initialization complete!")


if __name__ == "__main__":
    main()
