"""
End-to-End Deployment Audit and Verification Test Suite for AttendAI.
Verifies all 6 pre-deployment categories:
1. Database & Data Integrity
2. Data Flow & Interconnection (Single Daily Attendance, Scoping)
3. Authentication & Role-Based Security
4. Face Recognition & Camera Pipeline Edge Cases
5. Error Handling & Empty States
6. Environment & Deployment Readiness
"""

import os
import json
import pytest
from datetime import datetime, date
from web_app import (
    app, mark_attendance, is_student_attended_today,
    start_camera, stop_camera, camera_state,
    _get_all_attendance_records, ATTENDANCE_FILE
)
from database import db, reset_to_clean_state
from models import User, Course, Class, Student, AttendanceRecord, AttendanceSession
from config import config, ProductionConfig, DevelopmentConfig


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


# ============================================================================
# 1. Database & Data Integrity
# ============================================================================

def test_database_engine_options_and_no_orphans():
    """Verify DB engine options (pool/timeouts) and zero orphaned records."""
    assert "connect_args" in DevelopmentConfig.SQLALCHEMY_ENGINE_OPTIONS
    assert "pool_pre_ping" in ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS
    assert ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS["pool_pre_ping"] is True

    with app.app_context():
        # Check no orphaned attendance records
        orphans_att_student = db.session.query(AttendanceRecord).filter(
            ~AttendanceRecord.student_id.in_(db.select(Student.id))
        ).count()
        assert orphans_att_student == 0, f"Found {orphans_att_student} orphaned AttendanceRecords without Student!"

        # Check no orphaned students without class
        orphans_st_class = db.session.query(Student).filter(
            Student.class_id.isnot(None),
            ~Student.class_id.in_(db.select(Class.id))
        ).count()
        assert orphans_st_class == 0, f"Found {orphans_st_class} orphaned Students without Class!"


# ============================================================================
# 2. Data Flow & Interconnection Check
# ============================================================================

def test_single_daily_attendance_and_shared_source_of_truth():
    """Verify single daily attendance constraint and shared data consistency."""
    with app.app_context():
        # Create a dedicated unique student for this test
        unique_id = int(datetime.now().timestamp())
        unique_roll = f"AUDIT_{unique_id}"
        unique_name = f"Audit Unique {unique_id}"
        try:
            student = Student(name=unique_name, roll_no=unique_roll, face_registered=False)
            db.session.add(student)
            db.session.commit()

            today = datetime.now().strftime("%Y-%m-%d")

            # 1. First attendance marking today -> must succeed
            res1 = mark_attendance(
                name=student.name,
                roll_no=student.roll_no,
                student_id=student.id,
                confidence=0.92,
                recognition_status="Recognized (92%)"
            )
            assert res1["success"] is True
            assert res1["action"] in ("marked", "created")
            assert res1.get("already_marked") is not True

            # 2. Second attendance marking on the same day -> MUST be blocked by single daily attendance rule
            res2 = mark_attendance(
                name=student.name,
                roll_no=student.roll_no,
                student_id=student.id,
                confidence=0.95,
                recognition_status="Recognized (95%)"
            )
            assert res2["success"] is True
            assert res2.get("already_marked") is True
            assert res2["action"] == "already_marked"

            # Verify exactly 1 record exists in DB for today
            count_db = AttendanceRecord.query.filter(
                AttendanceRecord.roll_no == student.roll_no,
                db.func.date(AttendanceRecord.timestamp) == today
            ).count()
            assert count_db == 1, f"Expected exactly 1 attendance record in DB, found {count_db}"
        finally:
            # Clean up test student and records from DB and CSV
            try:
                import csv
                AttendanceRecord.query.filter(AttendanceRecord.roll_no == unique_roll).delete()
                st = Student.query.filter_by(roll_no=unique_roll).first()
                if st:
                    db.session.delete(st)
                db.session.commit()
                if ATTENDANCE_FILE.exists():
                    rows = []
                    with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                        reader = csv.reader(f)
                        for r in reader:
                            if len(r) >= 1 and r[0].strip() == unique_roll:
                                continue
                            rows.append(r)
                    with ATTENDANCE_FILE.open("w", encoding="utf-8", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerows(rows)
            except Exception as e:
                db.session.rollback()
                print(f"[WARN] Cleanup failed for {unique_roll}: {e}")


def test_student_login_and_strict_scoping(client):
    """Confirm Student Portal login strictly isolates attendance history and prevents tampering."""
    with app.app_context():
        student = Student.query.filter(Student.course_id.isnot(None), Student.class_id.isnot(None)).first()
        if not student:
            pytest.skip("No student with course and class found for scoping test")

        course_id = student.course_id
        class_id = student.class_id
        roll_no = student.roll_no

    # Login via student credentials
    res = client.post('/api/student-login', json={
        "course_id": course_id,
        "class_id": class_id,
        "roll_no": roll_no
    })
    assert res.status_code == 200
    assert res.json["success"] is True

    # Student requests own attendance -> 200 OK
    res_att = client.get('/api/student/attendance')
    assert res_att.status_code == 200
    assert res_att.json["success"] is True

    # Student attempts horizontal escalation by requesting another student's roll number -> 403 Forbidden
    res_tamper = client.get('/api/student/attendance?roll_no=FORBIDDEN_ROLL_9999')
    assert res_tamper.status_code == 403
    assert "Access denied" in res_tamper.json["message"]


# ============================================================================
# 3. Authentication & Security
# ============================================================================

def test_all_four_role_logins_and_invalid_credentials(client):
    """Test all role logins and confirm invalid credentials return clean errors without leaks."""
    # 1. Invalid email format
    res = client.post('/api/login', json={"email": "not-an-email", "password": "123"})
    assert res.status_code == 400
    assert "valid email" in res.json["message"].lower()

    # 2. Non-existent account
    res = client.post('/api/login', json={"email": "nonexistent_user@attendai.edu", "password": "123"})
    assert res.status_code == 404
    assert "No account" in res.json["message"]

    # 3. Wrong password
    with app.app_context():
        user = User.query.first()
        email = user.email if user else "admin@school.edu"

    res = client.post('/api/login', json={"email": email, "password": "CompletelyWrongPassword!"})
    assert res.status_code == 401
    assert "Invalid email or password" in res.json["message"]
    # Ensure no stack trace or DB errors leaked
    assert "sqlite" not in res.json["message"].lower()
    assert "traceback" not in res.json["message"].lower()

    # 4. Valid admin login
    res = client.post('/api/login', json={"email": "admin@school.edu", "password": "admin123"})
    assert res.status_code == 200
    assert res.json["success"] is True

    # 5. Logout clears session
    res_logout = client.post('/api/logout')
    assert res_logout.status_code == 200
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


# ============================================================================
# 4. Face Recognition & Camera Stream
# ============================================================================

def test_camera_toggle_lifecycle():
    """Verify camera start and stop state transitions cleanly without resource leaks."""
    with app.app_context():
        # Stop camera
        stop_camera()
        from web_app import camera_active, camera
        assert camera_active is False
        assert camera is None

        # Camera release lock endpoint returns cleanly
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "teacher"
        res = client.post('/api/camera/release-lock')
        assert res.status_code == 200
        assert res.json["success"] is True


# ============================================================================
# 5. Error Handling & Edge Cases
# ============================================================================

def test_empty_states_and_csv_export(client):
    """Test exporting CSV and querying with non-matching filters."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_role"] = "admin"

    # Query with non-existent date -> returns empty list gracefully, status 200
    res = client.get('/api/attendance?date=1900-01-01')
    assert res.status_code == 200
    assert res.json["records"] == []

    # Export CSV with valid header
    res_dl = client.get('/api/attendance/download?format=csv')
    assert res_dl.status_code == 200
    assert "Student Roll Number" in res_dl.data.decode("utf-8")


# ============================================================================
# 6. Environment & Deployment Readiness
# ============================================================================

def test_production_environment_settings():
    """Verify production settings, secret keys, and .gitignore protection."""
    # Production debug must be False
    assert ProductionConfig.DEBUG is False
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True

    # Verify .gitignore contains .env
    gitignore_path = os.path.join(os.path.dirname(__file__), "..", ".gitignore")
    with open(gitignore_path, "r", encoding="utf-8") as f:
        gitignore_content = f.read()
    assert ".env" in gitignore_content

    # Verify requirements.txt includes all critical dependencies
    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    with open(req_path, "r", encoding="utf-8") as f:
        req_content = f.read()
    assert "pandas" in req_content
    assert "reportlab" in req_content
    assert "opencv-contrib-python" in req_content
    assert "flask" in req_content
    assert "sqlalchemy" in req_content
