"""
Tests for Admin Panel Attendance Records with Course and Class filtering.
"""
import pytest
from app import app
from models import db, User, Course, Class, Student, AttendanceRecord
from datetime import datetime

def test_admin_attendance_course_and_class_filters():
    client = app.test_client()

    with app.app_context():
        # Retrieve or create admin
        admin = User.query.filter_by(role='admin').first()
        assert admin is not None

        # Verify courses and classes exist
        courses = Course.query.all()
        classes = Class.query.all()
        assert len(courses) > 0, "At least one course must exist"
        assert len(classes) > 0, "At least one class must exist"

        test_course = courses[0]
        test_class = Class.query.filter_by(course_id=test_course.id).first()
        if not test_class:
            test_class = classes[0]

    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["user_email"] = admin.email
        sess["user_role"] = "admin"
        sess["user_name"] = admin.name

    # 1. Fetch all attendance records
    res = client.get("/api/attendance")
    assert res.status_code == 200
    data = res.json
    assert "records" in data
    records = data["records"]

    # Verify that records include class_name and course_name
    for r in records:
        assert "class_name" in r
        assert "course_name" in r
        assert "roll_no" in r
        assert "name" in r
        assert "date" in r
        assert "time" in r
        assert "status" in r

    # 2. Filter by course_id
    res_course = client.get(f"/api/attendance?course_id={test_course.id}")
    assert res_course.status_code == 200
    course_records = res_course.json["records"]
    for r in course_records:
        if r.get("course_id"):
            assert r["course_id"] == test_course.id
        elif r.get("course_name"):
            assert (r["course_name"].lower() == test_course.name.lower() or 
                    (test_course.code and r["course_name"].lower() == test_course.code.lower()))

    # 3. Filter by class_id
    res_class = client.get(f"/api/attendance?class_id={test_class.id}")
    assert res_class.status_code == 200
    class_records = res_class.json["records"]
    for r in class_records:
        if r.get("class_id"):
            assert r["class_id"] == test_class.id
        elif r.get("class_name"):
            assert (r["class_name"].lower() == test_class.name.lower() or
                    (test_class.code and r["class_name"].lower() == test_class.code.lower()))

    # 4. Filter by both course_id and class_id
    res_both = client.get(f"/api/attendance?course_id={test_course.id}&class_id={test_class.id}")
    assert res_both.status_code == 200

    # 5. Download attendance CSV with course/class filter
    res_csv = client.get(f"/api/attendance/download?course_id={test_course.id}&class_id={test_class.id}&format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.content_type
    csv_text = res_csv.data.decode('utf-8')
    assert "Student Roll Number" in csv_text or "Class" in csv_text
