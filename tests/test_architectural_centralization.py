import os
import io
import sys
import json
import cv2
import numpy as np

# Set console encoding
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from web_app import app, face_metadata, active_recognition_filter, train_model
from database import db, reset_to_clean_state
from models import User, Course, Class, Student, FaceEmbedding, AttendanceRecord, AttendanceSession

def test_e2e_centralization():
    print("=" * 75)
    print("ATTENDAI - ARCHITECTURAL CENTRALIZATION & DATA UNIFICATION VERIFICATION")
    print("=" * 75)

    import shutil
    db_file = ROOT_DIR / "attendance_system.db"
    backup_file = ROOT_DIR / "attendance_system.db.test_bak"
    csv_file = ROOT_DIR / "Attendance.csv"
    csv_bak = ROOT_DIR / "Attendance.csv.test_bak"

    if db_file.exists():
        shutil.copy2(str(db_file), str(backup_file))
    if csv_file.exists():
        shutil.copy2(str(csv_file), str(csv_bak))

    try:
        _run_e2e_centralization_steps()
    finally:
        if backup_file.exists():
            with app.app_context():
                db.engine.dispose()
            shutil.copy2(str(backup_file), str(db_file))
            try:
                backup_file.unlink()
            except Exception:
                pass
        if csv_bak.exists():
            shutil.copy2(str(csv_bak), str(csv_file))
            try:
                csv_bak.unlink()
            except Exception:
                pass

def _run_e2e_centralization_steps():
    client = app.test_client()

    artifact_dir = r"C:\Users\Dell\.gemini\antigravity-ide\brain\75aaf02c-94b5-42c0-961f-5493d733456e"
    student_img_path = os.path.join(artifact_dir, "test_student_face_1789955589363.jpg")
    unknown_img_path = os.path.join(artifact_dir, "unknown_person_face_1789955612856.jpg")

    assert os.path.exists(student_img_path), f"Student face image missing at {student_img_path}"
    assert os.path.exists(unknown_img_path), f"Unknown face image missing at {unknown_img_path}"

    with app.app_context():
        # Ensure admin user exists
        admin_user = User.query.filter_by(role='admin').first()
        if not admin_user:
            admin_user = User(email="admin@attendai.edu", name="System Admin", role="admin", is_active=True)
            admin_user.set_password("Admin@123")
            db.session.add(admin_user)
            db.session.commit()

        # =====================================================================
        # STEP 1: Fresh Database / Clean State
        # =====================================================================
        print("\n[STEP 1] Testing Fresh Database / Blank Initial State...")
        # Reset database to clean state
        reset_success = reset_to_clean_state(app)
        assert reset_success, "Failed to reset database to clean state"
        train_model()

        # Set admin session
        with client.session_transaction() as sess:
            sess["user_id"] = admin_user.id
            sess["user_email"] = admin_user.email
            sess["user_role"] = "admin"
            sess["user_name"] = admin_user.name

        # Check Admin Dashboard
        res = client.get("/api/admin/dashboard")
        assert res.status_code == 200, f"Failed GET /api/admin/dashboard: {res.data}"
        data = res.json
        print(f"  Admin Dashboard Stats: courses={data['structure']['courses']}, classes={data['structure']['classes']}, students={data['users']['students']}")
        assert data["structure"]["courses"] == 0, f"Expected 0 courses, got {data['structure']['courses']}"
        assert data["structure"]["classes"] == 0, f"Expected 0 classes, got {data['structure']['classes']}"
        assert data["users"]["students"] == 0, f"Expected 0 students, got {data['users']['students']}"

        # Check /api/courses
        res = client.get("/api/courses")
        assert res.status_code == 200
        assert len(res.json["courses"]) == 0, f"Expected 0 courses on clean DB, got {len(res.json['courses'])}"
        print("  /api/courses returns clean [] (No fake courses)")

        # Check /api/classes
        res = client.get("/api/classes")
        assert res.status_code == 200
        assert len(res.json["classes"]) == 0, f"Expected 0 classes on clean DB, got {len(res.json['classes'])}"
        print("  /api/classes returns clean [] (No fake classes)")

        # Check /api/admin/students
        res = client.get("/api/admin/students")
        assert res.status_code == 200
        assert len(res.json["students"]) == 0, f"Expected 0 students on clean DB, got {len(res.json['students'])}"
        print("  /api/admin/students returns clean [] (No fake students)")
        print("  PASSED: Step 1 Clean Database Verified")

        # =====================================================================
        # STEP 2: Admin Creates Course ("B.Sc AI & ML")
        # =====================================================================
        print("\n[STEP 2] Admin Creates Course: 'B.Sc AI & ML'...")
        res = client.post("/api/admin/courses", json={
            "name": "B.Sc AI & ML",
            "code": "BSC-AIML",
            "description": "Bachelor of Science in Artificial Intelligence & Machine Learning"
        })
        assert res.status_code == 201, f"Failed creating course: {res.data}"
        course_id = res.json["course"]["id"]
        course_name = res.json["course"]["name"]
        print(f"  Created Course ID: {course_id}, Name: '{course_name}', Status: {res.json['course']['status']}")

        # Verify Course in Central DB
        c_db = Course.query.get(course_id)
        assert c_db is not None and c_db.name == "B.Sc AI & ML"
        assert c_db.status == "active"

        # Verify Course is immediately visible in general /api/courses
        res = client.get("/api/courses")
        assert res.status_code == 200
        assert any(c["id"] == course_id and c["name"] == "B.Sc AI & ML" for c in res.json["courses"])
        print("  Verified: Course 'B.Sc AI & ML' is available in central /api/courses")
        print("  PASSED: Step 2 Admin Course Creation Verified")

        # =====================================================================
        # STEP 3: Admin Creates Class under the Course ("2nd Year")
        # =====================================================================
        print("\n[STEP 3] Admin Creates Class: '2nd Year' under Course 'B.Sc AI & ML'...")
        res = client.post("/api/admin/classes", json={
            "name": "2nd Year",
            "code": "AIML-2Y",
            "course_id": course_id,
            "capacity": 60
        })
        assert res.status_code == 201, f"Failed creating class: {res.data}"
        class_id = res.json["class_id"]
        print(f"  Created Class ID: {class_id} under Course ID: {course_id}")

        # Verify Class in Central DB
        cl_db = Class.query.get(class_id)
        assert cl_db is not None and cl_db.name == "2nd Year"
        assert cl_db.course_id == course_id
        assert cl_db.course_name == "B.Sc AI & ML"

        # Verify /api/classes filtered by course_id
        res = client.get(f"/api/classes?course_id={course_id}")
        assert res.status_code == 200
        assert len(res.json["classes"]) == 1
        assert res.json["classes"][0]["name"] == "2nd Year"
        assert res.json["classes"][0]["course_name"] == "B.Sc AI & ML"
        print(f"  Verified: Class '2nd Year' dynamically returned for Course ID {course_id}")
        print("  PASSED: Step 3 Admin Class Creation Verified")

        # =====================================================================
        # STEP 4: Register Student (Roll 101, Test Student, B.Sc AI & ML, 2nd Year)
        # =====================================================================
        print("\n[STEP 4] Registering Student: Roll 101, 'Test Student' with Face Capture...")
        with open(student_img_path, "rb") as f:
            img_bytes = f.read()

        res = client.post("/api/students", data={
            "roll_no": "101",
            "name": "Test Student",
            "course_id": course_id,
            "class_id": class_id,
            "image": (io.BytesIO(img_bytes), "test_student.jpg")
        })
        assert res.status_code == 201, f"Student registration failed: {res.data}"
        print(f"  Registration response: {res.json['message']}")

        # Verify Database records & relationships
        st = Student.query.filter_by(roll_no="101").first()
        assert st is not None, "Student record missing in DB"
        assert st.name == "Test Student"
        assert st.course_id == course_id
        assert st.class_id == class_id
        assert st.course_name == "B.Sc AI & ML"
        assert st.class_name == "2nd Year"
        assert st.face_registered == True

        # Verify FaceEmbedding
        fe = FaceEmbedding.query.filter_by(student_id=st.id).first()
        assert fe is not None, "Face embedding missing in DB"
        assert len(json.loads(fe.embedding_vector)) == 128

        # Verify Student User Account Auto-Created for portal login
        st_user = User.query.filter_by(email="101@student.attendai.edu").first()
        assert st_user is not None, "Student user login account was not created!"
        assert st_user.role == "student"
        assert st.user_id == st_user.id
        print(f"  Verified DB Entity: Student ID={st.id}, Roll={st.roll_no}, Course={st.course_name}, Class={st.class_name}")
        print(f"  Verified Login User: Email={st_user.email}, Role={st_user.role}")
        print("  PASSED: Step 4 Student Registration & Account Linkage Verified")

        # =====================================================================
        # STEP 5: Verify Student in Admin / Structure Views
        # =====================================================================
        print("\n[STEP 5] Verifying Student appears under 'B.Sc AI & ML' -> '2nd Year'...")
        res = client.get("/api/admin/students")
        assert res.status_code == 200
        students_list = res.json["students"]
        assert len(students_list) == 1
        st_entry = students_list[0]
        assert st_entry["roll_no"] == "101"
        assert st_entry["name"] == "Test Student"
        assert st_entry["course_name"] == "B.Sc AI & ML"
        assert st_entry["class_name"] == "2nd Year"
        assert st_entry["face_registered"] == True
        print(f"  Admin View confirms: {st_entry['name']} (Roll: {st_entry['roll_no']}) -> {st_entry['course_name']} -> {st_entry['class_name']}")
        print("  PASSED: Step 5 Student Structure Placement Verified")

        # =====================================================================
        # STEP 6: Teacher Login & Session Filter
        # =====================================================================
        print("\n[STEP 6] Teacher Login & Course/Class Filter Selection...")
        teacher_user = User.query.filter_by(role='teacher').first()
        if not teacher_user:
            teacher_user = User(email="teacher@attendai.edu", name="Prof. Alan Turing", role="teacher", is_active=True)
            teacher_user.set_password("Teacher@123")
            db.session.add(teacher_user)
            db.session.commit()

        # Switch session to Teacher
        with client.session_transaction() as sess:
            sess["user_id"] = teacher_user.id
            sess["user_email"] = teacher_user.email
            sess["user_role"] = "teacher"
            sess["user_name"] = teacher_user.name

        # Teacher selects B.Sc AI & ML -> 2nd Year
        res = client.post("/api/camera/session-filter", json={
            "course_id": course_id,
            "class_id": class_id
        })
        assert res.status_code == 200
        f = res.json["filter"]
        assert f["course_id"] == course_id and f["course_name"] == "B.Sc AI & ML"
        assert f["class_id"] == class_id and f["class_name"] == "2nd Year"
        print(f"  Teacher Active Filter set: Course='{f['course_name']}', Class='{f['class_name']}'")
        print("  PASSED: Step 6 Teacher Filter Selection Verified")

        # =====================================================================
        # STEP 7: Face Recognition Inference
        # =====================================================================
        print("\n[STEP 7] Face Recognition for 'Test Student' with Course+Class Filter...")
        train_model()

        from web_app import get_face_detector, get_face_recognizer, mark_attendance

        detector = get_face_detector()
        recognizer = get_face_recognizer()

        test_img = cv2.imread(student_img_path)
        h, w = test_img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(test_img)
        assert faces is not None and len(faces) > 0, "Face detection failed"

        face_align = recognizer.alignCrop(test_img, faces[0])
        current_emb = recognizer.feature(face_align).flatten()
        current_emb /= np.linalg.norm(current_emb)

        # Candidates filtered strictly by Course and Class
        candidates = [m for m in face_metadata if m["course_id"] == course_id and m["class_id"] == class_id]
        assert len(candidates) == 1, f"Expected 1 candidate in scoped pool, got {len(candidates)}"

        best_score = float(np.dot(current_emb, candidates[0]["embedding"]))
        print(f"  Face Recognition Match Score: {best_score:.4f} (Threshold: 0.58)")
        assert best_score >= 0.58, "Recognition score below threshold"
        best_match = candidates[0]
        assert best_match["roll_no"] == "101"
        assert best_match["name"] == "Test Student"
        assert best_match["course_name"] == "B.Sc AI & ML"
        assert best_match["class_name"] == "2nd Year"
        print(f"  Recognized: Roll={best_match['roll_no']}, Name={best_match['name']}, Course={best_match['course_name']}, Class={best_match['class_name']}")
        print("  PASSED: Step 7 Scoped Face Recognition Verified")

        # =====================================================================
        # STEP 8: Mark Attendance
        # =====================================================================
        print("\n[STEP 8] Marking Attendance for Recognized Student (Roll 101)...")
        recorded = mark_attendance(
            name=best_match["name"],
            student_id=best_match["student_id"],
            roll_no=best_match["roll_no"],
            course_id=best_match["course_id"],
            class_id=best_match["class_id"],
            confidence=best_score,
            recognition_status="Recognized (95%)"
        )
        assert recorded, "mark_attendance returned False"

        # Verify Attendance record in database
        att_rec = AttendanceRecord.query.filter_by(student_id=st.id).first()
        assert att_rec is not None, "Attendance record not found in DB!"
        assert att_rec.roll_no == "101"
        assert att_rec.course_id == course_id
        assert att_rec.class_id == class_id
        assert att_rec.status == "present"
        print(f"  Attendance DB Record: ID={att_rec.id}, Roll={att_rec.roll_no}, Status={att_rec.status}, Course ID={att_rec.course_id}, Class ID={att_rec.class_id}")
        print("  PASSED: Step 8 Attendance Marked Successfully")

        # =====================================================================
        # STEP 9: Admin Verification of Student & Attendance
        # =====================================================================
        print("\n[STEP 9] Admin Verification of Shared Student and Attendance Records...")
        with client.session_transaction() as sess:
            sess["user_id"] = admin_user.id
            sess["user_email"] = admin_user.email
            sess["user_role"] = "admin"
            sess["user_name"] = admin_user.name

        # Admin checks attendance list
        res = client.get("/api/attendance")
        assert res.status_code == 200
        records = res.json["records"]
        assert len(records) >= 1
        admin_rec = next((r for r in records if r["roll_no"] == "101"), None)
        assert admin_rec is not None, "Admin cannot see student 101 attendance record!"
        assert admin_rec["course_name"] == "B.Sc AI & ML"
        assert admin_rec["class_name"] == "2nd Year"
        assert admin_rec["status"] == "Present"
        print(f"  Admin sees identical record: Roll={admin_rec['roll_no']}, Name={admin_rec['name']}, Course={admin_rec['course_name']}, Class={admin_rec['class_name']}")
        print("  PASSED: Step 9 Admin Shared Data Verified")

        # =====================================================================
        # STEP 10: Faculty Verification of Shared Course/Class/Student
        # =====================================================================
        print("\n[STEP 10] Faculty Section Access & Shared Data Verification...")
        faculty_user = User.query.filter_by(role='faculty').first()
        if not faculty_user:
            faculty_user = User(email="faculty@attendai.edu", name="Faculty Lead", role="faculty", is_active=True)
            faculty_user.set_password("Faculty@123")
            db.session.add(faculty_user)
            db.session.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = faculty_user.id
            sess["user_email"] = faculty_user.email
            sess["user_role"] = "faculty"
            sess["user_name"] = faculty_user.name

        # Faculty calls dashboard
        res = client.get("/api/faculty/dashboard")
        assert res.status_code == 200, f"Faculty dashboard failed: {res.data}"
        print(f"  Faculty Dashboard accessed successfully: Status={res.json['success']}")

        # Faculty accesses same courses & classes
        res = client.get("/api/courses")
        assert res.status_code == 200
        assert any(c["id"] == course_id and c["name"] == "B.Sc AI & ML" for c in res.json["courses"])
        res = client.get(f"/api/classes?course_id={course_id}")
        assert res.status_code == 200
        assert any(cl["id"] == class_id and cl["name"] == "2nd Year" for cl in res.json["classes"])
        print("  Faculty reads identical Course and Class entities from database")
        print("  PASSED: Step 10 Faculty Shared Entities Verified")

        # =====================================================================
        # STEP 11: Student Profile & Attendance Verification
        # =====================================================================
        print("\n[STEP 11] Student Login & Profile/Attendance Verification...")
        with client.session_transaction() as sess:
            sess["user_id"] = st_user.id
            sess["user_email"] = st_user.email
            sess["user_role"] = "student"
            sess["user_name"] = st.name

        res = client.get("/api/student/dashboard")
        assert res.status_code == 200, f"Student dashboard failed: {res.data}"
        st_data = res.json["data"]
        print(f"  Student Profile: Name='{st_data['student_name']}', Roll='{st_data['roll_no']}', Course='{st_data.get('course_name')}', Class='{st_data.get('class_name')}'")
        assert st_data["roll_no"] == "101"
        assert st_data["student_name"] == "Test Student"
        assert st_data["course_name"] == "B.Sc AI & ML"
        assert st_data["class_name"] == "2nd Year"
        assert st_data["total_classes"] >= 1
        assert st_data["present"] >= 1
        print("  Student correctly sees their own Course, Class, and Attendance Record")
        print("  PASSED: Step 11 Student Profile & Attendance Verified")

    try:
        from database import ensure_default_accounts, seed_default_academic_data
        with app.app_context():
            ensure_default_accounts()
            seed_default_academic_data()
    except Exception as e:
        print(f"Teardown restoration notice: {e}")

    print("\n" + "=" * 75)
    print("ALL 11 ARCHITECTURAL REQUIREMENTS VERIFIED WITH 100% SUCCESS!")
    print("=" * 75)

if __name__ == "__main__":
    test_e2e_centralization()
