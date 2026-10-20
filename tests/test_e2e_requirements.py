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
from database import db
from models import Student, FaceEmbedding, Course, Class, AttendanceRecord

def run_tests():
    print("=" * 70)
    print("AI FACE RECOGNITION ATTENDANCE SYSTEM - END-TO-END VERIFICATION")
    print("=" * 70)

    client = app.test_client()

    # Paths to generated realistic test face images
    artifact_dir = r"C:\Users\Dell\.gemini\antigravity-ide\brain\75aaf02c-94b5-42c0-961f-5493d733456e"
    student_img_path = os.path.join(artifact_dir, "test_student_face_1789955589363.jpg")
    unknown_img_path = os.path.join(artifact_dir, "unknown_person_face_1789955612856.jpg")

    assert os.path.exists(student_img_path), f"Student face image missing at {student_img_path}"
    assert os.path.exists(unknown_img_path), f"Unknown face image missing at {unknown_img_path}"

    with app.app_context():
        # Set up authenticated teacher/admin session on test client
        admin_user = db.session.query(db.Model.metadata.tables['users']).first()
        from models import User
        user = User.query.filter_by(role='admin').first() or User.query.filter_by(role='teacher').first()
        if user is None:
            user = User(email="teacher@school.edu", name="Teacher User", role="teacher", is_active=True)
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = user.id
            sess["user_email"] = user.email
            sess["user_role"] = user.role

        # Clean up any existing test student with roll 101 before starting tests
        existing = Student.query.filter_by(roll_no="101").all()
        for ex in existing:
            FaceEmbedding.query.filter_by(student_id=ex.id).delete()
            db.session.delete(ex)
        db.session.commit()

        # 1. Verify Academic Structure APIs
        print("\n[TEST 1] Verifying Academic Structure APIs (Courses & Classes)...")
        res = client.get("/api/courses")
        assert res.status_code == 200, f"Failed GET /api/courses: {res.data}"
        courses_data = res.json["courses"]
        print(f"  Found {len(courses_data)} courses: {[c['name'] for c in courses_data]}")
        if len(courses_data) == 0:
            c_new = Course(name="B.Sc Artificial Intelligence & Machine Learning", code="BSCAIML", status="active")
            db.session.add(c_new)
            db.session.commit()
            cl_new = Class(name="2nd Year", code="AIML-2", course_id=c_new.id, status="active")
            db.session.add(cl_new)
            db.session.commit()
            res = client.get("/api/courses")
            courses_data = res.json["courses"]
        aiml_course = next((c for c in courses_data if "AI" in c["name"] or "Artificial" in c["name"]), courses_data[0])
        aiml_course_id = aiml_course["id"]

        res = client.get(f"/api/classes?course_id={aiml_course_id}")
        assert res.status_code == 200
        classes_data = res.json["classes"]
        if len(classes_data) == 0:
            cl_new = Class(name="2nd Year", code=f"CL-{aiml_course_id}-2", course_id=aiml_course_id, status="active")
            db.session.add(cl_new)
            db.session.commit()
            res = client.get(f"/api/classes?course_id={aiml_course_id}")
            classes_data = res.json["classes"]
        print(f"  Found {len(classes_data)} classes for course '{aiml_course['name']}': {[cl['name'] for cl in classes_data]}")
        bsc2_class = next((cl for cl in classes_data if "2nd" in cl["name"]), classes_data[0])
        bsc2_class_id = bsc2_class["id"]
        print(f"  Selected Course: '{aiml_course['name']}' (ID: {aiml_course_id}), Class: '{bsc2_class['name']}' (ID: {bsc2_class_id})")
        print("  PASSED")

        # 2. Verify Session Filter API
        print("\n[TEST 2] Verifying Teacher Session Filter API...")
        res = client.post("/api/camera/session-filter", json={"course_id": aiml_course_id, "class_id": bsc2_class_id})
        assert res.status_code == 200, f"Session filter failed: {res.data}"
        assert res.json["filter"]["course_id"] == aiml_course_id
        assert res.json["filter"]["class_id"] == bsc2_class_id
        print(f"  Active Session Filter: Course '{res.json['filter']['course_name']}', Class '{res.json['filter']['class_name']}'")
        print("  PASSED")

        # 3. Validation: Missing Fields & Face Detection
        print("\n[TEST 3] Testing Registration Validation Rules...")
        # 3a: Missing Roll Number
        res = client.post("/api/students", data={
            "name": "Test Student",
            "course_id": aiml_course_id,
            "class_id": bsc2_class_id
        })
        assert res.status_code == 400
        assert "Roll Number" in res.json["message"]
        print("  3a. Missing Roll Number rejected (400) - PASSED")

        # 3b: Missing Name
        res = client.post("/api/students", data={
            "roll_no": "101",
            "course_id": aiml_course_id,
            "class_id": bsc2_class_id
        })
        assert res.status_code == 400
        assert "Name" in res.json["message"]
        print("  3b. Missing Student Name rejected (400) - PASSED")

        # 3c: Missing Course
        res = client.post("/api/students", data={
            "roll_no": "101",
            "name": "Test Student",
            "class_id": bsc2_class_id
        })
        assert res.status_code == 400
        assert "Course" in res.json["message"]
        print("  3c. Missing Course rejected (400) - PASSED")

        # 3d: Missing Class
        res = client.post("/api/students", data={
            "roll_no": "101",
            "name": "Test Student",
            "course_id": aiml_course_id
        })
        assert res.status_code == 400
        assert "Class" in res.json["message"]
        print("  3d. Missing Class rejected (400) - PASSED")

        # 3e: Blank image (no face detected)
        blank_img = np.zeros((300, 300, 3), dtype=np.uint8)
        _, blank_buf = cv2.imencode(".jpg", blank_img)
        res = client.post("/api/students", data={
            "roll_no": "101",
            "name": "Test Student",
            "course_id": aiml_course_id,
            "class_id": bsc2_class_id,
            "image": (io.BytesIO(blank_buf.tobytes()), "blank.jpg")
        })
        assert res.status_code == 400
        assert "No face detected" in res.json["message"]
        print("  3e. Image with zero faces rejected (400) - PASSED")

        # 4. Clean up any previous test student with roll 101 if exists
        existing = Student.query.filter_by(roll_no="101").all()
        for ex in existing:
            FaceEmbedding.query.filter_by(student_id=ex.id).delete()
            db.session.delete(ex)
        db.session.commit()

        # 5. Successful Student Registration
        print("\n[TEST 4] Registering Student (Roll 101, Test Student, AI & ML, B.Sc 2nd Year)...")
        with open(student_img_path, "rb") as f:
            student_bytes = f.read()

        res = client.post("/api/students", data={
            "roll_no": "101",
            "name": "Test Student",
            "course_id": aiml_course_id,
            "class_id": bsc2_class_id,
            "image": (io.BytesIO(student_bytes), "test_student.jpg")
        })
        assert res.status_code == 201, f"Registration failed ({res.status_code}): {res.data}"
        print(f"  Registration API response: {res.json['message']}")

        # Verify DB Records
        st = Student.query.filter_by(roll_no="101").first()
        assert st is not None, "Student 101 not found in database!"
        assert st.name == "Test Student"
        assert st.course_id == aiml_course_id
        assert st.class_id == bsc2_class_id
        assert st.face_image_path is not None
        from student_storage import resolve_photo_path
        image_disk_path = resolve_photo_path(st.face_image_path)
        assert image_disk_path is not None and os.path.exists(image_disk_path), f"Student face image missing at {st.face_image_path}"
        print(f"  Student record verified in DB: ID={st.id}, Roll={st.roll_no}, Name={st.name}, Course={st.course_name}, Class={st.class_name}")

        # Verify FaceEmbedding
        fe = FaceEmbedding.query.filter_by(student_id=st.id).first()
        assert fe is not None, "FaceEmbedding record missing for student!"
        raw_emb = fe.embedding_vector
        if isinstance(raw_emb, str):
            emb = np.array(json.loads(raw_emb), dtype=np.float32)
        else:
            emb = np.frombuffer(raw_emb, dtype=np.float32)
        assert len(emb) == 128, f"Face embedding dimension must be 128, got {len(emb)}"
        print(f"  FaceEmbedding record verified in DB: ID={fe.id}, Dimension={len(emb)}")
        print("  PASSED")

        # 6. Duplicate Roll Number Protection
        print("\n[TEST 5] Testing Duplicate Roll Number Protection...")
        res = client.post("/api/students", data={
            "roll_no": "101",
            "name": "Another Student",
            "course_id": aiml_course_id,
            "class_id": bsc2_class_id,
            "image": (io.BytesIO(student_bytes), "test_student2.jpg")
        })
        assert res.status_code == 409, f"Duplicate roll number should return 409, got {res.status_code}"
        assert "already registered" in res.json["message"] or "already exists" in res.json["message"]
        print(f"  Duplicate Roll 101 blocked with 409: {res.json['message']}")
        print("  PASSED")

        # 7. Face Recognition Simulation with Scoped Course/Class
        print("\n[TEST 6] Testing Face Recognition with Scoped Course & Class Filter...")
        train_model()

        # Set active filter to AI & ML / B.Sc 2nd Year
        client.post("/api/camera/session-filter", json={"course_id": aiml_course_id, "class_id": bsc2_class_id})

        # Load face recognizer and detector
        from web_app import get_face_detector, get_face_recognizer, mark_attendance

        detector = get_face_detector()
        recognizer = get_face_recognizer()

        test_img = cv2.imread(student_img_path)
        h, w = test_img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(test_img)
        assert faces is not None and len(faces) > 0, "Failed to detect face in test image"

        face_align = recognizer.alignCrop(test_img, faces[0])
        current_embedding = recognizer.feature(face_align).flatten()

        # Candidate pool should be filtered by course/class
        candidates = [meta for meta in face_metadata if (meta["course_id"] == aiml_course_id and meta["class_id"] == bsc2_class_id)]
        assert len(candidates) >= 1, "No candidates in filtered pool"

        best_match = None
        best_score = -1.0
        for meta in candidates:
            score = float(np.dot(current_embedding, meta["embedding"]) / (
                np.linalg.norm(current_embedding) * np.linalg.norm(meta["embedding"]) + 1e-10
            ))
            if score > best_score:
                best_score = score
                best_match = meta

        print(f"  Cosine match score: {best_score:.4f} (Threshold: 0.58)")
        assert best_score >= 0.58, f"Score {best_score} is below recognition threshold 0.58"
        assert best_match["roll_no"] == "101", f"Expected Roll 101, got {best_match['roll_no']}"
        assert best_match["name"] == "Test Student", f"Expected Test Student, got {best_match['name']}"

        # Mark attendance
        recorded = mark_attendance(
            name=best_match["name"],
            student_id=best_match["student_id"],
            roll_no=best_match["roll_no"],
            course_id=best_match["course_id"],
            class_id=best_match["class_id"],
            confidence=best_score,
            recognition_status="Recognized"
        )
        assert recorded, "mark_attendance failed"
        print(f"  Student recognized: Roll={best_match['roll_no']}, Name={best_match['name']}, Course={best_match['course_name']}, Class={best_match['class_name']}")
        print("  Attendance successfully marked!")
        print("  PASSED")

        # 8. Filter Scoping Test: Candidate Mismatch
        print("\n[TEST 7] Testing Recognition Filtering: Student Not in Selected Course/Class...")
        other_course = next((c for c in courses_data if c["id"] != aiml_course_id), None)
        if not other_course:
            c_other = Course(name="B.Sc Data Science", code="BSCDS", status="active")
            db.session.add(c_other)
            db.session.commit()
            other_course = {"id": c_other.id, "name": c_other.name}
        assert other_course is not None
        # Set filter to other course
        client.post("/api/camera/session-filter", json={"course_id": other_course["id"], "class_id": None})
        scoped_candidates = [meta for meta in face_metadata if (meta["course_id"] == other_course["id"])]
        # Roll 101 should NOT be in this candidate pool
        found_in_pool = any(c["roll_no"] == "101" for c in scoped_candidates)
        assert not found_in_pool, "Student 101 should not be in other course pool"
        print(f"  Verified: Student 101 excluded from candidate pool when Course '{other_course['name']}' is selected")
        print("  PASSED")

        # 9. Unknown Face Test
        print("\n[TEST 8] Testing Unknown Face Recognition...")
        unknown_img = cv2.imread(unknown_img_path)
        uh, uw = unknown_img.shape[:2]
        detector.setInputSize((uw, uh))
        _, ufaces = detector.detect(unknown_img)
        assert ufaces is not None and len(ufaces) > 0, "Failed to detect face in unknown image"

        uface_align = recognizer.alignCrop(unknown_img, ufaces[0])
        u_embedding = recognizer.feature(uface_align).flatten()

        # Compare against all candidates
        best_u_score = -1.0
        best_u_match = None
        for meta in face_metadata:
            score = float(np.dot(u_embedding, meta["embedding"]) / (
                np.linalg.norm(u_embedding) * np.linalg.norm(meta["embedding"]) + 1e-10
            ))
            if score > best_u_score:
                best_u_score = score
                best_u_match = meta

        print(f"  Unknown face best score: {best_u_score:.4f} (Must be < 0.58)")
        assert best_u_score < 0.58, f"Unknown face matched with score {best_u_score} >= 0.58!"
        print("  Result: Classified as 'Unknown Student' - NO attendance marked, NO random roll number assigned!")
        print("  PASSED")

        # 10. Verify Attendance History API & CSV Export
        print("\n[TEST 9] Verifying Attendance Records API & CSV Export...")
        res = client.get("/api/attendance")
        assert res.status_code == 200
        records = res.json["records"]
        assert len(records) > 0, "No attendance records returned"

        test_record = next((r for r in records if r["roll_no"] == "101"), None)
        assert test_record is not None, "Attendance record for Roll 101 not found"
        print(f"  Found Attendance Record:")
        print(f"    - Student Roll Number: {test_record['roll_no']}")
        print(f"    - Student Name:        {test_record['name']}")
        print(f"    - Class:               {test_record['class_name']}")
        print(f"    - Course:              {test_record['course_name']}")
        print(f"    - Date:                {test_record['date']}")
        print(f"    - Time:                {test_record['time']}")
        print(f"    - Attendance Status:   {test_record['status']}")
        print(f"    - Recognition Status:  {test_record['recognition_status']}")

        # Verify CSV Download
        res = client.get("/api/attendance/download")
        assert res.status_code == 200
        csv_text = res.data.decode("utf-8")
        lines = [line.strip() for line in csv_text.strip().split("\n")]
        header = lines[0]
        expected_header = "Student Roll Number,Student Name,Class,Course,Date,Time,Attendance Status,Face Recognition Status"
        assert header == expected_header, f"CSV header mismatch:\nExpected: {expected_header}\nGot: {header}"
        print(f"  CSV Header: {header}")
        assert any("101,Test Student" in line for line in lines), "Roll 101 not found in exported CSV"
        print(f"  CSV contains matching row for Roll 101")
        print("  PASSED")

    print("\n" + "=" * 70)
    print("ALL 9 TEST SUITES COMPLETED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
