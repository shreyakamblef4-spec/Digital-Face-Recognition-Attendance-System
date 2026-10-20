"""
Comprehensive test suite for:
1. Camera Release Lock & Status Management
2. Student Directory Hierarchical Storage (by Course + Class)
3. Transaction Safety, Photo Serving, and Scoped Recognition
"""

import os
import io
import json
import shutil
import pytest
import numpy as np
import cv2

from web_app import app, stop_camera, start_camera, train_model
from database import db
from models import User, Course, Class, Student, FaceEmbedding
from student_storage import (
    STUDENT_DIRECTORY_ROOT,
    sanitize_folder_name,
    resolve_photo_path,
    delete_student_folder
)


@pytest.fixture
def auth_client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            stop_camera()
            admin = User.query.filter_by(role='admin').first() or User.query.filter_by(role='teacher').first()
            if not admin:
                admin = User(email="teacher_test@attendai.edu", name="Test Teacher", role="teacher", is_active=True)
                admin.set_password("Teacher@123")
                db.session.add(admin)
                db.session.commit()
            
            with client.session_transaction() as sess:
                sess['user_id'] = admin.id
                sess['user_email'] = admin.email
                sess['user_role'] = admin.role

        yield client
        with app.app_context():
            stop_camera()


def _get_or_create_test_course_and_class(course_name, class_name):
    norm_name = course_name.replace(" and ", " & ")
    course = Course.query.filter((Course.name == course_name) | (Course.name == norm_name)).first()
    if not course:
        course = Course(name=course_name, code=course_name[:6].upper().replace(" ", ""), status="active")
        db.session.add(course)
        db.session.commit()

    cls = Class.query.filter_by(name=class_name, course_id=course.id).first()
    if not cls:
        cls = Class(name=class_name, code=f"{class_name[:4].upper()}-{course.id}", course_id=course.id, status="active")
        db.session.add(cls)
        db.session.commit()

    return course, cls


def _get_sample_face_bytes():
    # Use real face image if available from artifacts
    artifact_face = r"C:\Users\Dell\.gemini\antigravity-ide\brain\75aaf02c-94b5-42c0-961f-5493d733456e\test_student_face_1789955589363.jpg"
    if os.path.exists(artifact_face):
        with open(artifact_face, "rb") as f:
            return f.read()

    # Fallback to generating a synthetic image (will fail face detection in registration, but good for error tests)
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    _, buf = cv2.imencode('.jpg', img)
    return buf.tobytes()


def test_camera_release_lock_endpoint(auth_client):
    """Test that POST /api/camera/release-lock successfully releases webcam without errors."""
    res = auth_client.post('/api/camera/release-lock')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'released' in data['message'].lower()


def test_folder_sanitization():
    """Verify safe folder names are generated without corrupting Course/Class logical names."""
    assert sanitize_folder_name("B.Sc Artificial Intelligence & Machine Learning") == "BSc_Artificial_Intelligence_and_Machine_Learning"
    assert sanitize_folder_name("Computer Science / IT") == "Computer_Science_IT"
    assert sanitize_folder_name("2nd Year (Semester 3)") == "2nd_Year_Semester_3"
    assert sanitize_folder_name("Data Science & Big Data!!") == "Data_Science_and_Big_Data"


def test_registration_validation_zero_faces(auth_client):
    """Test that submitting an image without a face is rejected with a user-friendly error."""
    with app.app_context():
        course, cls = _get_or_create_test_course_and_class("Computer Science", "1st Year")
        c_id, cl_id = course.id, cls.id

    blank_img = np.zeros((300, 300, 3), dtype=np.uint8)
    _, buf = cv2.imencode('.jpg', blank_img)

    data = {
        'roll_no': 'TEST-BLANK-999',
        'name': 'Blank Face Student',
        'course_id': str(c_id),
        'class_id': str(cl_id),
        'image': (io.BytesIO(buf.tobytes()), 'blank.jpg')
    }
    res = auth_client.post('/api/students', data=data, content_type='multipart/form-data')
    assert res.status_code == 400
    res_data = res.get_json()
    assert res_data['success'] is False
    assert "No face detected" in res_data['message']


def test_registration_course_directory_separation(auth_client):
    """
    Test registration under two different courses:
    Course 1: Artificial Intelligence and Machine Learning -> 2nd Year
    Course 2: Computer Science -> 2nd Year
    Verify both are saved under their own distinct Course/Class directories.
    """
    face_bytes = _get_sample_face_bytes()

    with app.app_context():
        c1, cl1 = _get_or_create_test_course_and_class("Artificial Intelligence & Machine Learning", "2nd Year")
        c2, cl2 = _get_or_create_test_course_and_class("Computer Science", "2nd Year")
        c1_id, cl1_id = c1.id, cl1.id
        c2_id, cl2_id = c2.id, cl2.id

        # Clean existing test students if any
        for roll in ['AIML-001', 'CS-001']:
            st = Student.query.filter_by(roll_no=roll).first()
            if st:
                if st.face_image_path:
                    resolved = resolve_photo_path(st.face_image_path)
                    if resolved and resolved.exists():
                        delete_student_folder(resolved.parent)
                FaceEmbedding.query.filter_by(student_id=st.id).delete()
                db.session.delete(st)
        db.session.commit()

    # 1. Register AIML Student
    res1 = auth_client.post('/api/students', data={
        'roll_no': 'AIML-001',
        'name': 'Aarya Patel',
        'course_id': str(c1_id),
        'class_id': str(cl1_id),
        'image': (io.BytesIO(face_bytes), 'face.jpg')
    }, content_type='multipart/form-data')
    assert res1.status_code == 201, f"AIML Registration failed: {res1.data}"
    data1 = res1.get_json()
    assert data1['success'] is True

    # 2. Register CS Student
    res2 = auth_client.post('/api/students', data={
        'roll_no': 'CS-001',
        'name': 'Rohan Shah',
        'course_id': str(c2_id),
        'class_id': str(cl2_id),
        'image': (io.BytesIO(face_bytes), 'face.jpg')
    }, content_type='multipart/form-data')
    assert res2.status_code == 201, f"CS Registration failed: {res2.data}"
    data2 = res2.get_json()
    assert data2['success'] is True

    # 3. Verify physical directory separation
    with app.app_context():
        st_aiml = Student.query.filter_by(roll_no='AIML-001').first()
        st_cs = Student.query.filter_by(roll_no='CS-001').first()

        assert st_aiml is not None
        assert st_cs is not None

        # AIML storage checks
        assert "Artificial_Intelligence_and_Machine_Learning" in st_aiml.face_image_path
        assert "2nd_Year" in st_aiml.face_image_path
        assert "AIML_001" in st_aiml.face_image_path
        p_aiml = resolve_photo_path(st_aiml.face_image_path)
        assert p_aiml is not None and p_aiml.exists()
        assert p_aiml.name == "face.jpg"
        # Check encoding file exists alongside face.jpg
        encoding_file_aiml = p_aiml.parent / "face_encoding.dat"
        assert encoding_file_aiml.exists()

        # CS storage checks
        assert "Computer_Science" in st_cs.face_image_path
        assert "2nd_Year" in st_cs.face_image_path
        assert "CS_001" in st_cs.face_image_path
        p_cs = resolve_photo_path(st_cs.face_image_path)
        assert p_cs is not None and p_cs.exists()
        assert p_cs.name == "face.jpg"
        encoding_file_cs = p_cs.parent / "face_encoding.dat"
        assert encoding_file_cs.exists()

        # Ensure they are in completely separate directory branches
        assert p_aiml.parent != p_cs.parent
        assert p_aiml.parent.parent != p_cs.parent.parent

    # 4. Test Photo Serving API for nested paths
    photo_res = auth_client.get(f"/api/students/photo/{st_aiml.face_image_path}")
    assert photo_res.status_code == 200
    assert photo_res.content_type.startswith("image/")

    # 5. Test Path Traversal Protection
    bad_res = auth_client.get("/api/students/photo/../../secret.txt")
    assert bad_res.status_code in [403, 404]

    # Clean up test students
    with app.app_context():
        for st in [st_aiml, st_cs]:
            if st:
                p = resolve_photo_path(st.face_image_path)
                if p and p.exists():
                    delete_student_folder(p.parent)
                FaceEmbedding.query.filter_by(student_id=st.id).delete()
                db.session.delete(st)
        db.session.commit()


def test_multiple_students_in_same_course_class(auth_client):
    """Test registering 3 students under AI & ML -> 2nd Year, verify all share the same Course/Class folder."""
    face_bytes = _get_sample_face_bytes()

    with app.app_context():
        course, cls = _get_or_create_test_course_and_class("Artificial Intelligence & Machine Learning", "2nd Year")
        c_id, cl_id = course.id, cls.id

    student_rolls = ["AIML-101", "AIML-102", "AIML-103"]
    student_names = ["Student One", "Student Two", "Student Three"]

    created_paths = []
    try:
        for r, n in zip(student_rolls, student_names):
            res = auth_client.post('/api/students', data={
                'roll_no': r,
                'name': n,
                'course_id': str(c_id),
                'class_id': str(cl_id),
                'image': (io.BytesIO(face_bytes), 'face.jpg')
            }, content_type='multipart/form-data')
            assert res.status_code == 201

        with app.app_context():
            parent_dirs = set()
            for r in student_rolls:
                st = Student.query.filter_by(roll_no=r).first()
                assert st is not None
                p = resolve_photo_path(st.face_image_path)
                assert p is not None and p.exists()
                created_paths.append(p.parent)
                parent_dirs.add(p.parent.parent)

            # All 3 students should share the exact same Course/Class parent folder!
            assert len(parent_dirs) == 1
            shared_class_dir = list(parent_dirs)[0]
            assert shared_class_dir.name == "2nd_Year"
            assert shared_class_dir.parent.name == "Artificial_Intelligence_and_Machine_Learning"

        # Test GET /api/students listing
        list_res = auth_client.get('/api/students')
        assert list_res.status_code == 200
        list_data = list_res.get_json()
        assert 'students' in list_data
        rolls_in_api = [s['roll_no'] for s in list_data['students']]
        for r in student_rolls:
            assert r in rolls_in_api

    finally:
        # Cleanup
        with app.app_context():
            for r in student_rolls:
                st = Student.query.filter_by(roll_no=r).first()
                if st:
                    p = resolve_photo_path(st.face_image_path)
                    if p and p.exists():
                        delete_student_folder(p.parent)
                    FaceEmbedding.query.filter_by(student_id=st.id).delete()
                    db.session.delete(st)
            db.session.commit()


def test_session_filter_scoping(auth_client):
    """Test that setting active recognition filter scopes candidate pool to Course and Class."""
    with app.app_context():
        c1, cl1 = _get_or_create_test_course_and_class("Data Science", "Final Year")
        c1_id, cl1_id = c1.id, cl1.id

    res = auth_client.post('/api/camera/session-filter', json={
        'course_id': c1_id,
        'class_id': cl1_id
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['filter']['course_id'] == c1_id
    assert data['filter']['class_id'] == cl1_id
    assert data['course_name'] == "Data Science"
    assert data['class_name'] == "Final Year"

    # Reset filter
    auth_client.post('/api/camera/session-filter', json={'course_id': None, 'class_id': None})

