"""
Unit tests for the Single Daily Attendance constraint.
Enforces the business rule: 'A student can attend only 1 time in a day'.
"""

import pytest
from datetime import datetime, date
from web_app import app, db, Student, AttendanceRecord, mark_attendance, is_student_attended_today, ATTENDANCE_FILE
import csv


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client


def test_single_daily_attendance_enforced():
    """Verify that a student can only have their attendance recorded once per day."""
    with app.app_context():
        # Ensure student exists
        test_roll = "TEST_ONCE_01"
        test_name = "Single Attendance Tester"
        student = Student.query.filter_by(roll_no=test_roll).first()
        if not student:
            student = Student(name=test_name, roll_no=test_roll, face_registered=True)
            db.session.add(student)
            db.session.commit()

        # Clean any today's attendance for this test student
        today_start = datetime.combine(datetime.now().date(), datetime.min.time())
        AttendanceRecord.query.filter(
            AttendanceRecord.roll_no == test_roll,
            AttendanceRecord.timestamp >= today_start
        ).delete()
        db.session.commit()

        # Clean from CSV if present
        if ATTENDANCE_FILE.exists():
            rows = []
            today_str = datetime.now().strftime("%Y-%m-%d")
            with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for r in reader:
                    if len(r) >= 5 and r[0].strip() == test_roll and r[4].strip() == today_str:
                        continue
                    rows.append(r)
            with ATTENDANCE_FILE.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

        try:
            # First mark: Should succeed
            res1 = mark_attendance(
                name=test_name,
                roll_no=test_roll,
                student_id=student.id,
                confidence=0.85,
                recognition_status="Recognized (85%)"
            )
            assert res1["success"] is True
            assert res1.get("already_marked") in (False, None)
            assert res1.get("action") == "marked"

            # Count records in DB for today
            count_db1 = AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.timestamp >= today_start
            ).count()
            assert count_db1 == 1, f"Expected exactly 1 record in DB, got {count_db1}"

            # Count rows in CSV for today
            count_csv1 = 0
            with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for r in reader:
                    if len(r) >= 5 and r[0].strip() == test_roll and r[4].strip() == today_str:
                        count_csv1 += 1
            assert count_csv1 == 1, f"Expected exactly 1 row in CSV, got {count_csv1}"

            # Second mark attempt: Should be blocked by single daily attendance rule
            res2 = mark_attendance(
                name=test_name,
                roll_no=test_roll,
                student_id=student.id,
                confidence=0.90,
                recognition_status="Recognized (90%)"
            )
            assert res2["already_marked"] is True
            assert res2["action"] == "already_marked"
            assert "already attended today" in res2["message"].lower()

            # Confirm DB still has exactly 1 record (no duplicate created)
            count_db2 = AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.timestamp >= today_start
            ).count()
            assert count_db2 == 1, f"Duplicate was created in DB! Total count: {count_db2}"

            # Confirm CSV still has exactly 1 row (no duplicate appended)
            count_csv2 = 0
            with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for r in reader:
                    if len(r) >= 5 and r[0].strip() == test_roll and r[4].strip() == today_str:
                        count_csv2 += 1
            assert count_csv2 == 1, f"Duplicate was appended to CSV! Total count: {count_csv2}"
        finally:
            # Clean up test records from DB AND CSV
            AttendanceRecord.query.filter(
                AttendanceRecord.roll_no == test_roll
            ).delete()
            st = Student.query.filter_by(roll_no=test_roll).first()
            if st:
                db.session.delete(st)
            db.session.commit()
            if ATTENDANCE_FILE.exists():
                rows = []
                with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for r in reader:
                        if len(r) >= 1 and r[0].strip() == test_roll:
                            continue
                        rows.append(r)
                with ATTENDANCE_FILE.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
