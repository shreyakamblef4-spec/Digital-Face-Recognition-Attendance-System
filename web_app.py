import csv
import json
import os
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, Response, jsonify, request, send_from_directory, send_file, session, redirect, url_for
from werkzeug.utils import secure_filename
from functools import wraps

import cv2
import numpy as np

# Import configuration and database
from config import config
from database import db, init_db
from models import (User, Department, Course, Class, Subject, Teacher, Student, 
                    FaceEmbedding, AttendanceSession, AttendanceRecord, 
                    AuditLog, FaceRecognitionLog, SystemSetting, ChatMessage)
from auth import (login_required, role_required, admin_required, teacher_required, 
                  student_required, faculty_required, log_audit_action, 
                  get_current_user, get_authenticated_user, generate_token)
from ai import chatbot_service
from student_storage import (
    STUDENT_DIRECTORY_ROOT,
    save_student_face_data,
    delete_student_folder,
    resolve_photo_path,
    get_student_dir_path,
    load_student_encoding_file
)

# Directory Setup
BASE_DIR = Path(__file__).resolve().parent
STUDENT_DIR = STUDENT_DIRECTORY_ROOT
STUDENT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR = BASE_DIR / "ImagesAttendance"
ATTENDANCE_FILE = BASE_DIR / "Attendance.csv"
DATA_DIR = BASE_DIR / "data"

FACE_DETECTOR_MODEL = DATA_DIR / "face_detection_yunet_2023mar.onnx"
FACE_DETECTOR_MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
FACE_RECOGNIZER_MODEL = DATA_DIR / "face_recognition_sface_2021dec.onnx"
FACE_RECOGNIZER_MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

COOLDOWN_SECONDS = 10
RECOGNITION_THRESHOLD = 0.55  # cosine similarity threshold for SF embeddings

# Create Flask app with configuration
app = Flask(__name__)
app.config.from_object(config)

# Initialize database
init_db(app, config)

from collections import deque

# State variables
camera = None
camera_active = False
camera_state = "IDLE"  # IDLE, INITIALIZING, ACTIVE, STOPPING, ERROR
camera_lock = threading.Lock()
latest_frame = None
camera_mirror_mode = False
camera_vflip_mode = False
latest_detection = None
recent_stream_events = deque(maxlen=100)

# Model and training state
model_lock = threading.Lock()
class_names = []
recognizer = None
face_embeddings = []
face_metadata = []
training_error = None

# Active recognition filter state (Course & Class)
active_recognition_filter = {"course_id": None, "class_id": None}

# Track last marked attendance to prevent multiple rapid logs
last_marked = {}


def get_face_detector():
    """Load or download the supported OpenCV face detector model."""
    if FACE_DETECTOR_MODEL.exists():
        detector = cv2.FaceDetectorYN_create(str(FACE_DETECTOR_MODEL), "", (320, 320))
        if detector is not None:
            return detector

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        print("Downloading face detector model...")
        urllib.request.urlretrieve(FACE_DETECTOR_MODEL_URL, FACE_DETECTOR_MODEL)
    except Exception as exc:
        raise RuntimeError(f"Unable to download the face detector model: {exc}") from exc

    detector = cv2.FaceDetectorYN_create(str(FACE_DETECTOR_MODEL), "", (320, 320))
    if detector is None:
        raise RuntimeError("The downloaded face detector model could not be loaded")
    return detector


def get_face_recognizer():
    """Load or download the supported OpenCV face recognition model."""
    if FACE_RECOGNIZER_MODEL.exists():
        recognizer = cv2.FaceRecognizerSF_create(str(FACE_RECOGNIZER_MODEL), "")
        if recognizer is not None:
            return recognizer

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        print("Downloading face recognizer model...")
        urllib.request.urlretrieve(FACE_RECOGNIZER_MODEL_URL, FACE_RECOGNIZER_MODEL)
    except Exception as exc:
        raise RuntimeError(f"Unable to download the face recognizer model: {exc}") from exc

    recognizer = cv2.FaceRecognizerSF_create(str(FACE_RECOGNIZER_MODEL), "")
    if recognizer is None:
        raise RuntimeError("The downloaded face recognizer model could not be loaded")
    return recognizer


def detect_faces(image, detector):
    """Detect faces using FaceDetectorYN and return bounding boxes."""
    if detector is None:
        return []

    height, width = image.shape[:2]
    detector.setInputSize((width, height))
    _, faces = detector.detect(image)
    boxes = []

    if faces is None:
        return boxes

    for face in faces:
        confidence = float(face[4])
        if confidence < 0.5:
            continue
        x1 = int(face[0])
        y1 = int(face[1])
        x2 = int(face[0] + face[2])
        y2 = int(face[1] + face[3])
        boxes.append((x1, y1, x2, y2))

    return boxes


def train_model():
    """Train/load facial embeddings thread-safely from database and disk."""
    global class_names, recognizer, face_embeddings, face_metadata, training_error
    import json

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    names = []
    embeddings = []
    metadata = []

    try:
        detector = get_face_detector()
        recognizer = get_face_recognizer()
    except Exception as e:
        with model_lock:
            training_error = f"Model initialization failed: {e}"
            recognizer = None
            class_names = []
            face_embeddings = []
            face_metadata = []
        return False

    # 1. Load stored embeddings from the FaceEmbedding database table
    try:
        with app.app_context():
            db_embeddings = FaceEmbedding.query.all()
            for emb_rec in db_embeddings:
                try:
                    student = emb_rec.student
                    if not student:
                        continue
                    vec = np.array(json.loads(emb_rec.embedding_vector), dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    if norm > 1e-8:
                        vec = vec / norm

                    entry = {
                        "student_id": student.id,
                        "roll_no": student.roll_no,
                        "name": student.name,
                        "class_id": student.class_id,
                        "class_name": student.class_name,
                        "course_id": student.course_id or (student.class_.course_id if student.class_ else None),
                        "course_name": student.course_name,
                        "embedding": vec,
                    }
                    metadata.append(entry)
                    names.append(student.name.upper())
                    embeddings.append(vec)
                except Exception as e:
                    print(f"Error parsing database embedding {emb_rec.id}: {e}")
    except Exception as e:
        print(f"Database embedding load error: {e}")

    # 2. Check disk student directories (Student Directory and images)
    # Check both face_encoding.dat (instant, exact) and face.jpg (detector-based)
    found_student_dirs = []
    if STUDENT_DIR.exists():
        for p in STUDENT_DIR.rglob("*"):
            if p.is_dir() and ((p / "face_encoding.dat").exists() or (p / "face.jpg").exists()):
                found_student_dirs.append(p)

    for s_dir in found_student_dirs:
        enc_file = s_dir / "face_encoding.dat"
        img_file = s_dir / "face.jpg"

        s_name = None
        s_roll = None
        s_course_str = None
        s_class_str = None
        embedding = None

        if enc_file.exists():
            try:
                with enc_file.open("r", encoding="utf-8") as ef:
                    enc_data = json.load(ef)
                    s_name = enc_data.get("name")
                    s_roll = enc_data.get("roll_no")
                    s_course_str = enc_data.get("course")
                    s_class_str = enc_data.get("class")
                    raw_emb = enc_data.get("embedding", [])
                    if raw_emb:
                        vec = np.array(raw_emb, dtype=np.float32)
                        norm = np.linalg.norm(vec)
                        if norm > 1e-8:
                            embedding = vec / norm
            except Exception as e:
                print(f"Error reading encoding file {enc_file}: {e}")

        # If embedding wasn't in face_encoding.dat, extract from face.jpg
        if embedding is None and img_file.exists() and detector is not None and recognizer is not None:
            image = cv2.imread(str(img_file))
            if image is not None:
                try:
                    detector.setInputSize((image.shape[1], image.shape[0]))
                    _, raw_faces = detector.detect(image)
                    if raw_faces is not None and len(raw_faces) > 0:
                        face_align = recognizer.alignCrop(image, raw_faces[0])
                        emb = recognizer.feature(face_align).flatten()
                        norm = np.linalg.norm(emb)
                        if norm > 1e-8:
                            embedding = emb / norm
                except Exception as e:
                    print(f"Failed to extract embedding from {img_file}: {e}")

        if embedding is None:
            continue

        # Parse name & roll from folder name if not populated
        folder_stem = s_dir.name
        if not s_roll or not s_name:
            parts = folder_stem.split("_")
            if parts[0].lower() == "roll" and len(parts) >= 3:
                s_roll = s_roll or parts[1]
                s_name = s_name or " ".join(parts[2:])
            elif len(parts) >= 2:
                s_roll = s_roll or parts[0]
                s_name = s_name or " ".join(parts[1:])
            else:
                s_roll = s_roll or folder_stem
                s_name = s_name or folder_stem

        # Parse course and class from directory hierarchy if needed
        try:
            rel_parts = s_dir.relative_to(STUDENT_DIR).parts
            if len(rel_parts) >= 3:
                s_course_str = s_course_str or rel_parts[0].replace("_", " ")
                s_class_str = s_class_str or rel_parts[1].replace("_", " ")
        except Exception:
            pass

        # Check if already added to metadata
        if any(
            (m.get("roll_no") and m["roll_no"] == s_roll) or
            (m.get("name") and m["name"].strip().upper() == s_name.strip().upper())
            for m in metadata
        ):
            continue

        # Match or auto-register in SQLite database
        s_id = None
        s_cls_id = None
        s_cls_name = s_class_str or "N/A"
        s_crs_id = None
        s_crs_name = s_course_str or "N/A"

        try:
            with app.app_context():
                matched_student = Student.query.filter(
                    db.or_(
                        Student.roll_no == s_roll,
                        db.func.upper(Student.name) == s_name.strip().upper()
                    )
                ).first()

                # Match Course
                crs_obj = None
                if s_course_str:
                    clean_crs = s_course_str.strip().upper()
                    crs_obj = Course.query.filter(
                        db.or_(
                            db.func.upper(Course.name) == clean_crs,
                            db.func.upper(Course.code) == clean_crs,
                            Course.name.ilike(f"%{clean_crs[:10]}%")
                        )
                    ).first()
                # Match Class
                cls_obj = None
                if s_class_str:
                    clean_cls = s_class_str.strip().upper()
                    cls_obj = Class.query.filter(
                        db.or_(
                            db.func.upper(Class.name) == clean_cls,
                            db.func.upper(Class.code) == clean_cls,
                            Class.name.ilike(f"%{clean_cls[:8]}%")
                        )
                    ).first()

                if matched_student:
                    s_id = matched_student.id
                    s_roll = matched_student.roll_no
                    s_name = matched_student.name
                    s_cls_id = matched_student.class_id
                    s_cls_name = matched_student.class_name
                    s_crs_id = matched_student.course_id
                    s_crs_name = matched_student.course_name
                else:
                    s_id = None
                    s_cls_id = cls_obj.id if cls_obj else None
                    s_crs_id = crs_obj.id if crs_obj else None
        except Exception as sync_err:
            print(f"[STUDENT-SYNC] Error syncing student '{s_name}': {sync_err}")

        metadata.append({
            "student_id": s_id,
            "roll_no": s_roll,
            "name": s_name,
            "class_id": s_cls_id,
            "class_name": s_cls_name,
            "course_id": s_crs_id,
            "course_name": s_crs_name,
            "embedding": embedding,
        })
        names.append(s_name.upper())
        embeddings.append(embedding)

    # 3. Check legacy IMAGE_DIR for any standalone images
    if IMAGE_DIR.exists():
        for image_path in sorted(IMAGE_DIR.iterdir()):
            if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                continue
            stem = image_path.stem
            if any(m.get("roll_no") == stem or (m.get("name") and m["name"].upper() == stem.upper().replace("_", " ")) for m in metadata):
                continue
            image = cv2.imread(str(image_path))
            if image is None:
                continue
            detector.setInputSize((image.shape[1], image.shape[0]))
            _, raw_faces = detector.detect(image)
            if raw_faces is None or len(raw_faces) == 0:
                continue
            try:
                face_align = recognizer.alignCrop(image, raw_faces[0])
                embedding = recognizer.feature(face_align).flatten()
                norm = np.linalg.norm(embedding)
                if norm > 1e-8:
                    embedding = embedding / norm
            except Exception:
                continue
            s_name = stem.upper().replace("_", " ")
            s_roll = stem
            metadata.append({
                "student_id": None,
                "roll_no": s_roll,
                "name": s_name,
                "class_id": None,
                "class_name": "N/A",
                "course_id": None,
                "course_name": "N/A",
                "embedding": embedding,
            })
            names.append(s_name)
            embeddings.append(embedding)

    if not embeddings:
        with model_lock:
            training_error = "No student face data registered. Add a student with face photo to start."
            recognizer = None
            class_names = []
            face_embeddings = []
            face_metadata = []
        return False

    with model_lock:
        class_names.clear()
        class_names.extend(names)
        face_embeddings.clear()
        face_embeddings.extend(embeddings)
        face_metadata.clear()
        face_metadata.extend(metadata)
        training_error = None

    print(f"Face embeddings registered successfully! {len(metadata)} profile(s) loaded.")
    return True


def repair_attendance_file():
    """Ensure the CSV exists and uses the 8-field format."""
    ATTENDANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = []
    header_fields = [
        "Student Roll Number",
        "Student Name",
        "Class",
        "Course",
        "Date",
        "Time",
        "Attendance Status",
        "Face Recognition Status"
    ]

    if ATTENDANCE_FILE.exists():
        try:
            with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if not row or not any(row):
                        continue
                    if len(row) >= 8:
                        records.append(row[:8])
                    elif len(row) >= 4:
                        # Legacy format: Name, Date, Time, Status
                        name_val = row[0]
                        date_val = row[1]
                        time_val = row[2]
                        status_val = row[3] if len(row) > 3 else "Present"
                        records.append(["—", name_val, "—", "—", date_val, time_val, status_val, "Legacy"])
        except Exception as e:
            print(f"Error reading CSV during repair: {e}")

    try:
        with ATTENDANCE_FILE.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header_fields)
            for r in records:
                writer.writerow(r)
        print("Attendance CSV checked and formatted.")
    except Exception as e:
        print(f"Error writing CSV file: {e}")


def is_student_attended_today(student_id: int = None, roll_no: str = None, name: str = None, check_date=None) -> tuple:
    """
    Authoritatively determine if a student has already attended for the given date (default today).
    Enforces the single-attendance-per-day rule: A student can attend only 1 time in a day.
    Checks both the SQLite AttendanceRecord database and Attendance.csv file.
    """
    now = datetime.now()
    target_date = check_date or now.date()
    today_str = target_date.strftime("%Y-%m-%d")
    today_start = datetime.combine(target_date, datetime.min.time())
    today_end = datetime.combine(target_date, datetime.max.time())

    clean_roll = (roll_no or "").strip()
    clean_name = (name or "").strip()

    # 1. Check SQLite AttendanceRecord table
    try:
        ident_conditions = []
        if student_id:
            ident_conditions.append(AttendanceRecord.student_id == student_id)
        if clean_roll and clean_roll != "—":
            ident_conditions.append(AttendanceRecord.roll_no == clean_roll)
            ident_conditions.append(AttendanceRecord.roll_no == clean_roll.lstrip('0'))
            ident_conditions.append(AttendanceRecord.roll_no == clean_roll.zfill(3))
        if clean_name:
            matching_student_ids = db.select(Student.id).filter(
                db.func.upper(Student.name) == clean_name.upper()
            )
            ident_conditions.append(AttendanceRecord.student_id.in_(matching_student_ids))

        if ident_conditions:
            existing = AttendanceRecord.query.filter(
                db.or_(
                    db.func.date(AttendanceRecord.timestamp) == today_str,
                    db.and_(
                        AttendanceRecord.timestamp >= today_start,
                        AttendanceRecord.timestamp <= today_end
                    )
                ),
                AttendanceRecord.status.in_(['present', 'late', 'Present', 'Late']),
                db.or_(*ident_conditions)
            ).first()

            if existing:
                st_name = clean_name
                st_roll = clean_roll
                if existing.student:
                    st_name = existing.student.name or st_name
                    st_roll = existing.student.roll_no or st_roll
                return True, {
                    "id": existing.id,
                    "student_id": existing.student_id,
                    "name": st_name,
                    "roll_no": existing.roll_no or st_roll,
                    "course_name": existing.course_name,
                    "class_name": existing.class_name,
                    "date": existing.formatted_date,
                    "time": existing.formatted_time,
                    "status": "Present",
                    "recognition_status": existing.recognition_status or "Recognized",
                    "source": "database"
                }
    except Exception as e:
        print(f"[ATTENDANCE-CHECK] Error checking DB for today's attendance: {e}")

    # 2. Check Attendance.csv file
    try:
        repair_attendance_file()
        if ATTENDANCE_FILE.exists():
            with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 5:
                        r_roll = row[0].strip()
                        r_name = row[1].strip()
                        r_class = row[2].strip() if len(row) > 2 else "—"
                        r_course = row[3].strip() if len(row) > 3 else "—"
                        r_date = row[4].strip()
                        r_time = row[5].strip() if len(row) > 5 else "—"
                        r_status = row[6].strip().lower() if len(row) > 6 else "present"
                        r_rec = row[7].strip() if len(row) > 7 else "Recognized"

                        if r_date == today_str and r_status in ("present", "late", ""):
                            matched = False
                            if clean_roll and clean_roll != "—" and (
                                r_roll == clean_roll or
                                r_roll.lstrip('0') == clean_roll.lstrip('0') or
                                r_roll == clean_roll.zfill(3)
                            ):
                                matched = True
                            elif clean_name and r_name.upper() == clean_name.upper():
                                matched = True

                            if matched:
                                return True, {
                                    "id": None,
                                    "student_id": student_id,
                                    "name": r_name,
                                    "roll_no": r_roll,
                                    "course_name": r_course,
                                    "class_name": r_class,
                                    "date": r_date,
                                    "time": r_time,
                                    "status": "Present",
                                    "recognition_status": r_rec,
                                    "source": "csv"
                                }
    except Exception as e:
        print(f"[ATTENDANCE-CHECK] Error checking CSV for today's attendance: {e}")

    return False, None


def mark_attendance(name: str, roll_no: str = None, student_id: int = None, course_id: int = None, class_id: int = None, confidence: float = None, recognition_status: str = "Recognized") -> dict:
    """Record student attendance inside Attendance.csv AND SQLite DB with robust session handling, duplicate protection, and audit logging."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    timestamp_str = now.strftime("%H:%M:%S")

    final_roll = roll_no or "—"
    final_name = name
    final_class = "—"
    final_course = "—"
    final_course_id = course_id
    final_class_id = class_id
    resolved_id = student_id

    conf_pct = int(confidence * 100) if confidence is not None else None
    print(f"[ATTENDANCE-CHAIN] Step 3: mark_attendance() invoked for student '{name}' (Roll: {roll_no}, ID: {student_id}, Conf: {conf_pct}%)")

    try:
        with app.app_context():
            resolved_student = None
            if student_id:
                resolved_student = db.session.get(Student, student_id)
            if not resolved_student and roll_no:
                resolved_student = Student.query.filter_by(roll_no=roll_no).first()
            if not resolved_student and name:
                resolved_student = Student.query.filter(
                    db.or_(
                        db.func.upper(Student.name) == name.strip().upper(),
                        db.func.upper(Student.roll_no) == name.strip().upper()
                    )
                ).first()
            if not resolved_student:
                clean_name = (name or "").strip()
                clean_roll = (roll_no or "").strip()
                if clean_name:
                    resolved_student = Student.query.filter(
                        db.func.upper(Student.name) == clean_name.upper()
                    ).first()
                if not resolved_student and clean_roll and clean_roll != "—":
                    resolved_student = Student.query.filter(
                        db.or_(
                            Student.roll_no == clean_roll,
                            Student.roll_no == clean_roll.lstrip('0'),
                            Student.roll_no == clean_roll.zfill(3),
                            db.func.upper(Student.roll_no) == clean_roll.upper()
                        )
                    ).first()

            if not resolved_student and (name or roll_no):
                # Auto-create student so SQLite foreign key is satisfied
                auto_name = clean_name or f"Student {clean_roll}"
                auto_roll = clean_roll if clean_roll and clean_roll != "—" else f"ROLL_{int(time.time())}"
                existing_by_roll = Student.query.filter_by(roll_no=auto_roll).first()
                if existing_by_roll:
                    resolved_student = existing_by_roll
                else:
                    resolved_student = Student(
                        name=auto_name,
                        roll_no=auto_roll,
                        course_id=final_course_id,
                        class_id=final_class_id,
                        face_registered=True
                    )
                    db.session.add(resolved_student)
                    db.session.commit()
                    print(f"[ATTENDANCE-CHAIN] Auto-registered Student #{resolved_student.id} ('{auto_name}') in DB")

            if resolved_student:
                resolved_id = resolved_student.id
                final_roll = resolved_student.roll_no or final_roll
                final_name = resolved_student.name or final_name
                final_class = resolved_student.class_name or final_class
                final_course = resolved_student.course_name or final_course
                final_course_id = resolved_student.course_id or final_course_id
                final_class_id = resolved_student.class_id or final_class_id
    except Exception as e:
        print(f"[ATTENDANCE-CHAIN] Error resolving student details: {e}")

    final_rec_status = recognition_status or (f"Recognized ({conf_pct}%)" if conf_pct else "Recognized")

    # ── Rule: A student can attend only 1 time in a day ──
    try:
        with app.app_context():
            already_attended, prior_rec = is_student_attended_today(
                student_id=resolved_id or student_id,
                roll_no=final_roll,
                name=final_name,
                check_date=now.date()
            )
            if already_attended:
                msg = f"{final_name} (Roll: {final_roll}) has already attended today. A student can attend only 1 time in a day."
                print(f"[ATTENDANCE-CHAIN] Single daily attendance enforced: {msg}")

                event_payload = {
                    "id": str(uuid.uuid4()),
                    "type": "already_marked",
                    "student_id": resolved_id or student_id,
                    "name": final_name,
                    "roll_no": final_roll,
                    "course_name": final_course,
                    "class_name": final_class,
                    "confidence": conf_pct,
                    "date": today_str,
                    "time": prior_rec.get("time", timestamp_str) if prior_rec else timestamp_str,
                    "message": msg,
                    "timestamp": time.time(),
                    "record": prior_rec
                }
                recent_stream_events.append(event_payload)

                return {
                    "success": True,
                    "action": "already_marked",
                    "message": msg,
                    "record": prior_rec,
                    "already_marked": True
                }
    except Exception as check_err:
        print(f"[ATTENDANCE-CHAIN] Error in daily attendance check: {check_err}")

    # 1. Write to SQLite DB (AttendanceRecord & AttendanceSession)
    db_marked = False
    already_present = False
    record_obj = None

    try:
        with app.app_context():
            s_id = resolved_id or student_id
            if s_id:
                # Close any outdated sessions from previous days that are still marked 'active'
                try:
                    outdated_sessions = AttendanceSession.query.filter(
                        AttendanceSession.date < now.date(),
                        AttendanceSession.status == 'active'
                    ).all()
                    for old_sess in outdated_sessions:
                        old_sess.status = 'completed'
                    if outdated_sessions:
                        db.session.commit()
                except Exception as sess_clean_err:
                    print(f"[ATTENDANCE-CHAIN] Notice: Outdated session cleanup skipped: {sess_clean_err}")
                    db.session.rollback()

                # Find or create active session for TODAY
                active_session = None
                target_class_id = final_class_id or 1
                if target_class_id:
                    active_session = AttendanceSession.query.filter(
                        AttendanceSession.class_id == target_class_id,
                        AttendanceSession.date == now.date(),
                        AttendanceSession.status == 'active'
                    ).first()

                    if not active_session:
                        # Check if any session exists for today regardless of status
                        active_session = AttendanceSession.query.filter(
                            AttendanceSession.class_id == target_class_id,
                            AttendanceSession.date == now.date()
                        ).first()

                if not active_session:
                    teacher = Teacher.query.first()
                    active_session = AttendanceSession(
                        teacher_id=teacher.id if teacher else 1,
                        class_id=target_class_id,
                        date=now.date(),
                        start_time=now.time(),
                        status='active',
                        notes='Auto-created for Face Recognition Attendance'
                    )
                    db.session.add(active_session)
                    db.session.commit()
                    print(f"[ATTENDANCE-CHAIN] Step 4: Created new AttendanceSession #{active_session.id} for class {target_class_id} on {now.date()}")

                rec = AttendanceRecord(
                    session_id=active_session.id if active_session else None,
                    student_id=s_id,
                    roll_no=final_roll,
                    course_id=final_course_id,
                    class_id=final_class_id,
                    timestamp=now,
                    status='present',
                    confidence=confidence,
                    recognition_status=final_rec_status,
                    marked_by_teacher=False,
                    notes='Auto-marked via Face Recognition Stream'
                )
                db.session.add(rec)
                db.session.commit()
                db_marked = True
                record_obj = {
                    "id": rec.id,
                    "student_id": s_id,
                    "name": final_name,
                    "roll_no": final_roll,
                    "course_name": final_course,
                    "class_name": final_class,
                    "date": rec.formatted_date,
                    "time": rec.formatted_time,
                    "status": "Present",
                    "recognition_status": final_rec_status
                }
                print(f"[ATTENDANCE-CHAIN] Step 4: DB INSERT SUCCESSFUL! Recorded ID #{rec.id} for '{final_name}' (Roll: {final_roll}) in Session #{active_session.id}")
    except Exception as e:
        print(f"[ATTENDANCE-CHAIN] Step 4: ERROR writing DB attendance record: {e}")
        import traceback
        traceback.print_exc()

    # 2. Write to Attendance.csv
    repair_attendance_file()
    csv_marked = False
    try:
        csv_already_present = False
        with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 5:
                    r_roll = row[0].strip()
                    r_name = row[1].strip().upper()
                    r_date = row[4].strip()
                    match_ident = (final_roll != "—" and r_roll == final_roll) or (r_name == final_name.strip().upper())
                    if match_ident and r_date == today_str:
                        csv_already_present = True
                        break

        if not csv_already_present:
            with ATTENDANCE_FILE.open("a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    final_roll,
                    final_name,
                    final_class,
                    final_course,
                    today_str,
                    timestamp_str,
                    "Present",
                    final_rec_status
                ])
            csv_marked = True
            print(f"[ATTENDANCE-CHAIN] Step 4: Appended attendance row to Attendance.csv for '{final_name}'")
    except Exception as e:
        print(f"[ATTENDANCE-CHAIN] Error writing attendance CSV: {e}")

    # 3. Emit real-time event for frontend listener
    ev_type = "marked" if (db_marked or csv_marked) else ("already_marked" if already_present else "error")
    msg = (f"Attendance marked for {final_name} (Roll: {final_roll})" if ev_type == "marked"
           else f"{final_name} is already marked Present for today." if ev_type == "already_marked"
           else "Failed to record attendance")

    event_payload = {
        "id": str(uuid.uuid4()),
        "type": ev_type,
        "student_id": resolved_id or student_id,
        "name": final_name,
        "roll_no": final_roll,
        "course_name": final_course,
        "class_name": final_class,
        "confidence": conf_pct,
        "date": today_str,
        "time": timestamp_str,
        "message": msg,
        "timestamp": time.time(),
        "record": record_obj
    }
    recent_stream_events.append(event_payload)
    print(f"[ATTENDANCE-CHAIN] Step 5: Emitted real-time event [{ev_type}] for '{final_name}'")

    return {
        "success": (db_marked or csv_marked or already_present),
        "action": ev_type,
        "message": msg,
        "record": record_obj,
        "already_marked": already_present
    }



def make_placeholder_frame(title="Camera Stream Paused", subtitle="Click 'Start Feed' to activate recognition"):
    """Generate a placeholder JPEG frame for the camera stream when hardware is inactive."""
    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
    placeholder[:] = (26, 21, 19)  # Deep dark slate background (BGR)

    # Draw camera icon outline
    cv2.rectangle(placeholder, (260, 160), (380, 245), (70, 60, 55), 2, cv2.LINE_AA)
    cv2.circle(placeholder, (320, 202), 26, (90, 80, 75), 2, cv2.LINE_AA)
    cv2.circle(placeholder, (320, 202), 10, (120, 110, 105), -1, cv2.LINE_AA)
    cv2.rectangle(placeholder, (280, 145), (310, 160), (70, 60, 55), -1, cv2.LINE_AA)

    # Draw title and subtitle
    (w1, _), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    cv2.putText(placeholder, title, (int(320 - w1 / 2), 290),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (235, 235, 235), 2, cv2.LINE_AA)

    (w2, _), _ = cv2.getTextSize(subtitle, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    cv2.putText(placeholder, subtitle, (int(320 - w2 / 2), 320),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 150), 1, cv2.LINE_AA)

    ret, jpeg = cv2.imencode('.jpg', placeholder, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return jpeg.tobytes() if ret else b''


def start_camera():
    """Start the video capture device reliably across platforms, trying DirectShow on Windows and scanning indices."""
    global camera, camera_active, camera_state
    with camera_lock:
        if camera_active and camera is not None and camera.isOpened() and camera_state == "ACTIVE":
            return True

        if camera_state == "INITIALIZING":
            print("[CAMERA] Camera is already initializing. Ignoring duplicate start request.")
            return False

        camera_state = "INITIALIZING"

        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass
            camera = None
            camera_active = False

        opened_cam = None
        for idx in [0, 1, 2]:
            if os.name == 'nt':
                try:
                    c = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                    if c.isOpened():
                        ret, test_frame = c.read()
                        if ret and test_frame is not None and test_frame.size > 0:
                            opened_cam = c
                            print(f"[CAMERA] Webcam opened via CAP_DSHOW on index {idx}")
                            break
                        c.release()
                except Exception as e:
                    print(f"[CAMERA] Error testing camera idx {idx} with CAP_DSHOW: {e}")

            try:
                c = cv2.VideoCapture(idx)
                if c.isOpened():
                    ret, test_frame = c.read()
                    if ret and test_frame is not None and test_frame.size > 0:
                        opened_cam = c
                        print(f"[CAMERA] Webcam opened via default backend on index {idx}")
                        break
                    c.release()
            except Exception as e:
                print(f"[CAMERA] Error testing camera idx {idx} with default backend: {e}")

        if opened_cam is not None:
            camera = opened_cam
            camera_active = True
            camera_state = "ACTIVE"
            try:
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                camera.set(cv2.CAP_PROP_FPS, 30)
            except Exception:
                pass
            return True
        else:
            camera = None
            camera_active = False
            camera_state = "ERROR"
            print("[CAMERA] No physical webcam could be opened.")
            return False


def stop_camera():
    """Stop the video capture device and release lock."""
    global camera, camera_active, camera_state, latest_frame, latest_detection
    with camera_lock:
        camera_state = "STOPPING"
        camera_active = False
        latest_frame = None
        latest_detection = None
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass
            camera = None
            print("[CAMERA] Webcam released.")
        camera_state = "IDLE"
        return True


def generate_frames():
    """Generate camera stream frames with robust face detection, mirror-mode support, and recognition overlay."""
    global camera, camera_active, last_marked, recognizer, training_error, latest_frame, latest_detection, camera_mirror_mode, camera_vflip_mode
    
    try:
        detector = get_face_detector()
    except Exception as e:
        print(f"Face Detector load failed in stream: {e}")
        detector = None
        
    while True:
        with camera_lock:
            active = camera_active
            cam = camera

        if not active or cam is None or not cam.isOpened():
            frame_bytes = make_placeholder_frame("Camera Stream Halted", "Click 'Start Feed' to activate real-time recognition")
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.25)
            continue

        try:
            with camera_lock:
                if not camera_active or camera is None or not camera.isOpened():
                    success, frame = False, None
                else:
                    success, frame = camera.read()
                    if success and frame is not None and frame.size > 0:
                        latest_frame = frame.copy()
        except Exception as e:
            print(f"Error reading webcam frame: {e}")
            success, frame = False, None

        if not success or frame is None or frame.size == 0:
            frame_bytes = make_placeholder_frame("Connecting to Camera...", "Waiting for webcam video signal")
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.15)
            continue

        h, w = frame.shape[:2]
        small_frame = cv2.resize(frame, (640, int(640 * h / w))) if w > 640 else frame.copy()
        
        if camera_vflip_mode:
            small_frame = cv2.flip(small_frame, 0)

        sh, sw = small_frame.shape[:2]

        if detector is not None:
            try:
                detector.setInputSize((sw, sh))
                _, raw_faces = detector.detect(small_frame)
            except Exception as e:
                raw_faces = None

            if raw_faces is not None and len(raw_faces) > 0:
                for face_row in raw_faces:
                    conf = float(face_row[14]) if len(face_row) > 14 else float(face_row[4])
                    if conf < 0.45:
                        continue

                    x1 = max(0, int(face_row[0]))
                    y1 = max(0, int(face_row[1]))
                    box_w = int(face_row[2])
                    box_h = int(face_row[3])
                    x2 = min(sw, x1 + box_w)
                    y2 = min(sh, y1 + box_h)

                    name = "Unknown Student"
                    roll_no = ""
                    roll_no_display = ""
                    confidence_score = 0
                    confidence_str = ""
                    color = (0, 0, 255)  # Red for unknown
                    is_recognized = False

                    print(f"[ATTENDANCE-CHAIN] Step 1: Face detected at ({x1}, {y1}) size {box_w}x{box_h} with detector conf={conf:.2f}")

                    with model_lock:
                        current_recognizer = recognizer
                        current_meta = list(face_metadata)
                        current_filter = dict(active_recognition_filter)

                    # Filter candidate pool based on active Course/Class filter
                    filtered_candidates = []
                    if current_meta:
                        for item in current_meta:
                            if current_filter.get("class_id") and item.get("class_id") != current_filter["class_id"]:
                                continue
                            if current_filter.get("course_id") and item.get("course_id") != current_filter["course_id"]:
                                continue
                            filtered_candidates.append(item)

                    if current_recognizer is not None and filtered_candidates:
                        try:
                            # Align face using 5 landmarks for accurate feature extraction
                            face_align = current_recognizer.alignCrop(small_frame, face_row)
                            embedding = current_recognizer.feature(face_align).flatten()
                            norm = np.linalg.norm(embedding)
                            if norm > 1e-8:
                                embedding = embedding / norm

                            best_match = None
                            best_score = -1.0
                            for cand in filtered_candidates:
                                known = cand["embedding"].flatten()
                                score = float(np.dot(embedding, known))
                                if score > best_score:
                                    best_score = score
                                    best_match = cand

                            # Match threshold: 0.58
                            if best_match and best_score >= 0.58:
                                name = best_match["name"]
                                roll_no = best_match.get("roll_no") or "—"
                                roll_no_display = f" [#{roll_no}]" if roll_no != "—" else ""
                                color = (0, 255, 0)  # Green for recognized
                                confidence_score = int(max(0, min(100, best_score * 100)))
                                confidence_str = f" [{confidence_score}%]"
                                is_recognized = True

                                print(f"[ATTENDANCE-CHAIN] Step 2: Confidence check PASSED: {confidence_score}% >= 58% -> Match: '{name}' (Roll: {roll_no})")

                                now = datetime.now()
                                cooldown_key = f"{roll_no}_{name}"
                                if cooldown_key not in last_marked or (now - last_marked[cooldown_key]).total_seconds() >= COOLDOWN_SECONDS:
                                    mark_res = mark_attendance(
                                        name=name,
                                        roll_no=roll_no if roll_no != "—" else None,
                                        student_id=best_match.get("student_id"),
                                        course_id=best_match.get("course_id"),
                                        class_id=best_match.get("class_id"),
                                        confidence=best_score,
                                        recognition_status=f"Recognized ({confidence_score}%)"
                                    )
                                    action = mark_res.get("action") if isinstance(mark_res, dict) else ("created" if mark_res else "failed")
                                    if mark_res.get("already_marked"):
                                        last_marked[cooldown_key] = now + timedelta(seconds=60)
                                    else:
                                        last_marked[cooldown_key] = now
                            elif best_match:
                                cand_score = int(max(0, min(100, best_score * 100)))
                                print(f"[ATTENDANCE-CHAIN] Step 2: Confidence check FAILED: best_score={cand_score}% < 58% threshold for candidate '{best_match.get('name')}'")
                        except Exception as e:
                            print(f"[ATTENDANCE-CHAIN] Error during face recognition inference: {e}")

                    # Update latest detection state for client-side HTML overlay
                    with camera_lock:
                        latest_detection = {
                            "detected": True,
                            "name": name,
                            "roll_no": roll_no if is_recognized else "",
                            "confidence": confidence_score if is_recognized else 0,
                            "is_recognized": is_recognized,
                            "box": [x1, y1, box_w, box_h],
                            "frame_size": [sw, sh],
                            "timestamp": time.time()
                        }

                    # Draw bounding box and snug label (font size ~12-13px with compact padding)
                    cv2.rectangle(small_frame, (x1, y1), (x2, y2), color, 2)
                    label = f"{name}{roll_no_display}{confidence_str}"
                    font_scale = 0.45
                    font_thickness = 1
                    (lw, lh), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
                    pad_x = 6
                    pad_y = 3
                    bg_w = lw + pad_x * 2
                    bg_h = lh + pad_y * 2 + baseline
                    bg_y1 = y2 if (y2 + bg_h <= sh) else max(0, y1 - bg_h)
                    bg_y2 = min(sh, y2 + bg_h) if (y2 + bg_h <= sh) else y1
                    bg_x1 = max(0, min(x1, sw - bg_w))
                    bg_x2 = min(sw, bg_x1 + bg_w)
                    cv2.rectangle(small_frame, (bg_x1, bg_y1), (bg_x2, bg_y2), color, cv2.FILLED)
                    cv2.rectangle(small_frame, (bg_x1, bg_y1), (bg_x2, bg_y2), (20, 20, 20), 1)
                    text_x = bg_x1 + pad_x
                    text_y = bg_y1 + pad_y + lh
                    cv2.putText(small_frame, label, (text_x, text_y),
                                cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)
            else:
                with camera_lock:
                    if latest_detection and time.time() - latest_detection.get("timestamp", 0) > 2.0:
                        latest_detection = {"detected": False}

        ret, jpeg = cv2.imencode('.jpg', small_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ret:
            continue
        
        frame_bytes = jpeg.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/download-demo-video')
def download_demo_video():
    """Route to download the demo video walkthrough MP4 file."""
    video_path = os.path.join(app.root_path, 'AttendAI_Demo_Walkthrough.mp4')
    if os.path.exists(video_path):
        return send_file(video_path, as_attachment=True, download_name='AttendAI_Demo_Walkthrough.mp4', mimetype='video/mp4')
    return jsonify({"success": False, "message": "Demo video file not found"}), 404


def _normalize_academic_str(val):
    """Normalize academic strings (courses, classes) for fuzzy and resilient matching."""
    if not val:
        return ""
    s = str(val).lower()
    s = s.replace("&", "and")
    s = s.replace(".", "")
    s = "".join(c for c in s if c.isalnum())
    return s


def _find_matching_student(course_input, class_input, roll_input):
    """
    Look up a student from the existing student records (Student model) by matching
    Course + Class/Year + Roll Number together as the identity key.
    Supports Course & Class as numeric IDs or human-readable names.
    Also falls back to Student Directory folders on disk if a registered profile exists.
    """
    if not course_input or not class_input or not roll_input:
        return None

    clean_roll = str(roll_input).strip()
    norm_course = _normalize_academic_str(course_input)
    norm_class = _normalize_academic_str(class_input)

    crs_id = int(course_input) if str(course_input).isdigit() else None
    cls_id = int(class_input) if str(class_input).isdigit() else None

    # 1. Query candidates from Student table by roll number
    candidates = Student.query.filter(
        db.or_(
            Student.roll_no == clean_roll,
            db.func.lower(Student.roll_no) == clean_roll.lower()
        )
    ).all()

    if not candidates and clean_roll.isdigit():
        # Match stripped leading zeroes (e.g. '01' <-> '1')
        all_students = Student.query.all()
        candidates = [
            s for s in all_students
            if s.roll_no and s.roll_no.strip().isdigit() and int(s.roll_no.strip()) == int(clean_roll)
        ]

    for student in candidates:
        # Verify course match
        course_matched = False
        if crs_id and (student.course_id == crs_id or (student.class_ and student.class_.course_id == crs_id)):
            course_matched = True
        elif norm_course:
            s_crs_norm = _normalize_academic_str(student.course_name)
            c_rel_norm = _normalize_academic_str(getattr(student.course, 'name', ''))
            cl_crs_norm = _normalize_academic_str(getattr(getattr(student.class_, 'course', None), 'name', ''))
            if (norm_course in (s_crs_norm, c_rel_norm, cl_crs_norm) or
                (norm_course and norm_course in s_crs_norm) or
                (s_crs_norm and s_crs_norm in norm_course)):
                course_matched = True

        # Verify class match
        class_matched = False
        if cls_id and student.class_id == cls_id:
            class_matched = True
        elif norm_class:
            s_cls_norm = _normalize_academic_str(student.class_name)
            cl_rel_norm = _normalize_academic_str(getattr(student.class_, 'name', ''))
            if (norm_class in (s_cls_norm, cl_rel_norm) or
                (norm_class and norm_class in s_cls_norm) or
                (s_cls_norm and s_cls_norm in norm_class)):
                class_matched = True

        if course_matched and class_matched:
            return student

    # 2. Check Student Directory on disk in case student exists on disk but not yet in DB
    if STUDENT_DIR.exists():
        for s_dir in STUDENT_DIR.glob("*/*/*"):
            if not s_dir.is_dir():
                continue
            enc_file = s_dir / "face_encoding.dat"
            disk_roll, disk_name, disk_course, disk_class = None, None, None, None
            if enc_file.exists():
                try:
                    data = json.loads(enc_file.read_text(encoding="utf-8"))
                    disk_roll = data.get("roll_no")
                    disk_name = data.get("name")
                    disk_course = data.get("course")
                    disk_class = data.get("class")
                except Exception:
                    pass

            if not disk_roll:
                parts = s_dir.name.split("_")
                if parts[0].lower() == "roll" and len(parts) >= 3:
                    disk_roll = parts[1]
                    disk_name = " ".join(parts[2:])
                elif len(parts) >= 2:
                    disk_roll = parts[0]
                    disk_name = " ".join(parts[1:])

            if not disk_roll:
                continue

            roll_match = (str(disk_roll).strip().lower() == clean_roll.lower() or
                          (str(disk_roll).strip().isdigit() and clean_roll.isdigit() and int(str(disk_roll).strip()) == int(clean_roll)))
            if not roll_match:
                continue

            # Course & Class matching for disk folder
            try:
                rel_parts = s_dir.relative_to(STUDENT_DIR).parts
                dir_course = disk_course or (rel_parts[0].replace("_", " ") if len(rel_parts) >= 1 else "")
                dir_class = disk_class or (rel_parts[1].replace("_", " ") if len(rel_parts) >= 2 else "")
            except Exception:
                dir_course, dir_class = disk_course or "", disk_class or ""

            c_match = False
            if crs_id:
                crs_obj = Course.query.get(crs_id)
                c_match = crs_obj and (_normalize_academic_str(crs_obj.name) in _normalize_academic_str(dir_course) or _normalize_academic_str(dir_course) in _normalize_academic_str(crs_obj.name))
            elif norm_course:
                c_match = norm_course in _normalize_academic_str(dir_course) or _normalize_academic_str(dir_course) in norm_course

            cl_match = False
            if cls_id:
                cls_obj = Class.query.get(cls_id)
                cl_match = cls_obj and (_normalize_academic_str(cls_obj.name) in _normalize_academic_str(dir_class) or _normalize_academic_str(dir_class) in _normalize_academic_str(cls_obj.name))
            elif norm_class:
                cl_match = norm_class in _normalize_academic_str(dir_class) or _normalize_academic_str(dir_class) in norm_class

            if c_match and cl_match:
                try:
                    c_model = Course.query.filter(Course.name.ilike(f"%{dir_course[:10]}%")).first()
                    cl_model = Class.query.filter(Class.name.ilike(f"%{dir_class[:8]}%")).first()
                    new_student = Student(
                        name=disk_name or s_dir.name,
                        roll_no=clean_roll,
                        course_id=c_model.id if c_model else (crs_id or None),
                        class_id=cl_model.id if cl_model else (cls_id or None),
                        department_id=cl_model.department_id if cl_model else None,
                        face_registered=True,
                        face_images_count=1,
                        face_image_path=f"{s_dir.relative_to(STUDENT_DIR)}/face.jpg" if (s_dir / "face.jpg").exists() else None
                    )
                    db.session.add(new_student)
                    db.session.commit()
                    return new_student
                except Exception as sync_e:
                    db.session.rollback()
                    print(f"Error auto-syncing disk student: {sync_e}")

    return None


def _get_unique_active_courses():
    """Fetch active courses ensuring deduplicated entries (e.g. normalizing '&' and 'and')."""
    courses = Course.query.filter(Course.status == 'active').order_by(Course.id).all()
    if not courses:
        courses = Course.query.order_by(Course.id).all()
    seen = set()
    unique = []
    for c in courses:
        norm = c.name.lower().replace('&', 'and').strip()
        norm = ' '.join(norm.split())
        if norm not in seen:
            seen.add(norm)
            unique.append(c)
    return unique


@app.route('/api/public/courses', methods=['GET'])
def api_public_courses():
    """Public endpoint to fetch active courses for student login dropdown."""
    courses = _get_unique_active_courses()
    return jsonify({
        "success": True,
        "courses": [{"id": c.id, "name": c.name, "code": c.code} for c in courses]
    })


@app.route('/api/public/classes', methods=['GET'])
def api_public_classes():
    """Public endpoint to fetch active classes for student login dropdown."""
    course_id = request.args.get('course_id')
    query = Class.query.filter(Class.status == 'active')
    if course_id and str(course_id).isdigit():
        c_id = int(course_id)
        query = query.filter(db.or_(Class.course_id == c_id, Class.department_id == c_id))
    classes = query.order_by(Class.name).all()
    if not classes and not course_id:
        classes = Class.query.order_by(Class.name).all()
    return jsonify({
        "success": True,
        "classes": [{"id": cl.id, "name": cl.name, "code": cl.code, "course_id": cl.course_id} for cl in classes]
    })


@app.route('/student-login', methods=['GET', 'POST'])
def student_login_page():
    """Dedicated Student Login Portal using Course, Class/Year, and Roll Number."""
    if request.method == 'POST':
        return api_student_login()

    if session.get('student_id'):
        return redirect(url_for('student_attendance_view'))

    courses = _get_unique_active_courses()
    classes = Class.query.filter(Class.status == 'active').order_by(Class.name).all()
    if not classes:
        classes = Class.query.order_by(Class.name).all()

    return render_template('login.html', courses=courses, classes=classes, default_tab='student')


@app.route('/api/student-login', methods=['POST'])
def api_student_login():
    """Handle student authentication via Course + Class/Year + Roll Number."""
    data = request.get_json(silent=True) or request.form or {}
    course_val = data.get('course_id') or data.get('course')
    class_val = data.get('class_id') or data.get('class')
    roll_val = data.get('roll_no') or data.get('roll')

    if not course_val or not class_val or not roll_val:
        return jsonify({
            'success': False,
            'message': 'No student found with these details. Please check your Course, Class/Year, and Roll Number.'
        }), 400

    student = _find_matching_student(course_val, class_val, roll_val)

    if not student:
        return jsonify({
            'success': False,
            'message': 'No student found with these details. Please check your Course, Class/Year, and Roll Number.'
        }), 404

    # Scoped student session
    session['student_id'] = student.id
    session['student_roll_no'] = student.roll_no
    session['student_name'] = student.name or 'Student'
    session['student_course_id'] = student.course_id
    session['student_course_name'] = student.course_name
    session['student_class_id'] = student.class_id
    session['student_class_name'] = student.class_name
    session['user_role'] = 'student'
    session['user_name'] = student.name or 'Student'
    session['user_email'] = student.email or f"{str(student.roll_no).lower()}@student.attendai.edu"

    token = generate_token(student.id, 'student', student.name or 'Student', student.email or f"{student.roll_no}@student.attendai.edu")

    try:
        log_audit_action(None, 'student_portal_login', table_name='students', record_id=student.id,
                         details=f'Student {student.name} (Roll: {student.roll_no}) logged into Student Portal')
    except Exception:
        pass

    if request.is_json or request.headers.get('Accept', '').find('application/json') != -1 or request.path.startswith('/api/'):
        return jsonify({
            'success': True,
            'message': 'Login successful.',
            'redirect_url': '/student/attendance',
            'token': token,
            'student': {
                'id': student.id,
                'name': student.name or 'Student',
                'roll_no': student.roll_no,
                'course_id': student.course_id,
                'course_name': student.course_name,
                'class_id': student.class_id,
                'class_name': student.class_name
            }
        }), 200

    return redirect(url_for('student_attendance_view'))


@app.route('/student/attendance', methods=['GET'])
def student_attendance_view():
    """Dedicated Student Attendance Dashboard showing student records and metrics."""
    student_id = session.get('student_id')
    if not student_id:
        auth_user = get_authenticated_user()
        if auth_user and auth_user.get('role') == 'student':
            student_id = auth_user.get('user_id')
            session['student_id'] = student_id

    if not student_id:
        return redirect(url_for('student_login_page'))

    student = db.session.get(Student, student_id)
    if not student:
        session.pop('student_id', None)
        return redirect(url_for('student_login_page'))

    student_data = {
        'id': student.id,
        'name': student.name or 'Student',
        'roll_no': student.roll_no,
        'course_id': student.course_id,
        'course_name': student.course_name,
        'class_id': student.class_id,
        'class_name': student.class_name
    }
    return render_template('student_attendance.html', student=student_data)


@app.route('/api/student/my-attendance', methods=['GET'])
@app.route('/api/student/attendance', methods=['GET'])
def api_student_my_attendance():
    """
    Fetch attendance records strictly scoped to the authenticated student session.
    Validates requested parameters to prevent horizontal privilege escalation.
    """
    student_id = session.get('student_id')
    if not student_id:
        auth_user = get_authenticated_user()
        if auth_user and auth_user.get('role') == 'student':
            student_id = auth_user.get('user_id')

    if not student_id:
        return jsonify({'success': False, 'message': 'Unauthorized. Please sign in via the Student Portal.'}), 401

    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'success': False, 'message': 'Authenticated student profile not found.'}), 404

    # Security validation against requested parameters
    req_roll = request.args.get('roll_no') or request.args.get('roll')
    req_course = request.args.get('course_id') or request.args.get('course')
    req_class = request.args.get('class_id') or request.args.get('class')

    if req_roll:
        clean_s_roll = str(student.roll_no).strip().lower()
        clean_r_roll = str(req_roll).strip().lower()
        roll_match = (clean_s_roll == clean_r_roll or 
                      (clean_s_roll.isdigit() and clean_r_roll.isdigit() and int(clean_s_roll) == int(clean_r_roll)))
        if not roll_match:
            return jsonify({
                'success': False,
                'message': 'Access denied: Requested roll number does not match your authenticated session.'
            }), 403

    if req_course:
        course_valid = False
        if str(req_course).isdigit() and student.course_id and int(req_course) == student.course_id:
            course_valid = True
        elif _normalize_academic_str(req_course) in (_normalize_academic_str(student.course_name), _normalize_academic_str(getattr(student.course, 'name', ''))):
            course_valid = True
        if not course_valid:
            return jsonify({
                'success': False,
                'message': 'Access denied: Requested course does not match your authenticated session.'
            }), 403

    if req_class:
        class_valid = False
        if str(req_class).isdigit() and student.class_id and int(req_class) == student.class_id:
            class_valid = True
        elif _normalize_academic_str(req_class) in (_normalize_academic_str(student.class_name), _normalize_academic_str(getattr(student.class_, 'name', ''))):
            class_valid = True
        if not class_valid:
            return jsonify({
                'success': False,
                'message': 'Access denied: Requested class/year does not match your authenticated session.'
            }), 403

    date_filter = request.args.get('date')
    search = request.args.get('search', '').strip().lower()

    records = []
    seen_timestamps = set()

    # 1. From AttendanceRecord table in DB
    try:
        query = AttendanceRecord.query.filter(
            db.or_(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.roll_no == student.roll_no
            )
        ).order_by(AttendanceRecord.timestamp.desc())

        for r in query.all():
            r_date = r.formatted_date
            r_time = r.formatted_time
            if date_filter and r_date != date_filter:
                continue
            r_status = r.status.capitalize() if r.status else "Present"
            r_rec_status = r.recognition_status or (f"Recognized ({int(r.confidence * 100)}%)" if r.confidence else "Recognized")
            if search and (search not in r_date.lower() and search not in r_status.lower() and search not in r_rec_status.lower()):
                continue

            seen_timestamps.add((r_date, r_time))
            records.append({
                "id": r.id,
                "date": r_date,
                "time": r_time,
                "status": r_status,
                "confidence": f"{int(r.confidence * 100)}%" if r.confidence is not None else None,
                "recognition_status": r_rec_status
            })
    except Exception as e:
        print(f"Error querying student DB attendance: {e}")

    # 2. From Attendance.csv
    if ATTENDANCE_FILE.exists():
        try:
            with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for idx, row in enumerate(reader):
                    if not row or not any(row):
                        continue
                    if len(row) >= 8:
                        r_roll, r_name, r_class, r_course, r_date, r_time, r_status, r_rec = row[:8]
                    elif len(row) >= 4:
                        r_name, r_date, r_time, r_status = row[:4]
                        r_roll, r_class, r_course, r_rec = "—", "—", "—", "Legacy"
                    else:
                        continue

                    # Match roll number
                    clean_s_roll = str(student.roll_no).strip().lower()
                    clean_r_roll = str(r_roll).strip().lower()
                    roll_match = (clean_s_roll == clean_r_roll or 
                                  (clean_s_roll.isdigit() and clean_r_roll.isdigit() and int(clean_s_roll) == int(clean_r_roll)))
                    if not roll_match:
                        continue

                    # Match course
                    s_crs_norm = _normalize_academic_str(student.course_name)
                    r_crs_norm = _normalize_academic_str(r_course)
                    c_rel_norm = _normalize_academic_str(getattr(student.course, 'name', ''))
                    course_match = (not r_crs_norm or r_crs_norm == "—" or 
                                    r_crs_norm in (s_crs_norm, c_rel_norm) or
                                    (s_crs_norm and (r_crs_norm in s_crs_norm or s_crs_norm in r_crs_norm)))
                    if not course_match:
                        continue

                    # Match class
                    s_cls_norm = _normalize_academic_str(student.class_name)
                    r_cls_norm = _normalize_academic_str(r_class)
                    cl_rel_norm = _normalize_academic_str(getattr(student.class_, 'name', ''))
                    class_match = (not r_cls_norm or r_cls_norm == "—" or 
                                   r_cls_norm in (s_cls_norm, cl_rel_norm) or
                                   (s_cls_norm and (r_cls_norm in s_cls_norm or s_cls_norm in r_cls_norm)))
                    if not class_match:
                        continue

                    if date_filter and r_date != date_filter:
                        continue
                    if search and (search not in r_date.lower() and search not in r_status.lower() and search not in r_rec.lower()):
                        continue

                    key = (r_date, r_time)
                    if key not in seen_timestamps:
                        seen_timestamps.add(key)
                        records.append({
                            "id": f"csv-{idx+1}",
                            "date": r_date,
                            "time": r_time,
                            "status": r_status.capitalize() if r_status else "Present",
                            "confidence": None,
                            "recognition_status": r_rec
                        })
        except Exception as e:
            print(f"Error querying student CSV attendance: {e}")

    records.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)

    total_sessions = len(records)
    total_present = sum(1 for r in records if (r.get("status") or "").lower() == "present")
    total_absent = total_sessions - total_present
    percentage = round((total_present / total_sessions * 100), 1) if total_sessions > 0 else 0

    return jsonify({
        "success": True,
        "records": records,
        "summary": {
            "total_sessions": total_sessions,
            "total_present": total_present,
            "total_absent": total_absent,
            "percentage": percentage
        },
        "student": {
            "id": student.id,
            "name": student.name or 'Student',
            "roll_no": student.roll_no,
            "course_id": student.course_id,
            "course_name": student.course_name,
            "class_id": student.class_id,
            "class_name": student.class_name
        }
    })


@app.route('/student/logout', methods=['GET', 'POST'])
def student_logout():
    """Log out student from portal and clear session."""
    session.pop('student_id', None)
    session.pop('student_roll_no', None)
    session.pop('student_name', None)
    session.pop('student_course_id', None)
    session.pop('student_course_name', None)
    session.pop('student_class_id', None)
    session.pop('student_class_name', None)
    if session.get('user_role') == 'student':
        session.clear()
    return redirect(url_for('student_login_page'))


@app.route('/api/student/logout', methods=['POST'])
def api_student_logout():
    """API endpoint to log out student."""
    session.pop('student_id', None)
    session.pop('student_roll_no', None)
    session.pop('student_name', None)
    session.pop('student_course_id', None)
    session.pop('student_course_name', None)
    session.pop('student_class_id', None)
    session.pop('student_class_name', None)
    if session.get('user_role') == 'student':
        session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.', 'redirect_url': '/student-login'}), 200


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Display the login page or handle login POST."""
    if request.method == 'POST':
        return api_login()
    if 'user_id' in session:
        user = User.query.get(session.get('user_id'))
        if not user or not user.is_active:
            session.clear()
        elif request.args.get('tab') or request.args.get('switch'):
            # Allow clean role switching without getting blocked by active session redirect
            session.clear()
        else:
            return redirect(url_for('index'))
    if 'student_id' in session:
        if request.args.get('tab') or request.args.get('switch'):
            session.clear()
        else:
            return redirect(url_for('student_attendance_view'))

    courses = _get_unique_active_courses()
    classes = Class.query.filter(Class.status == 'active').order_by(Class.name).all()
    if not classes:
        classes = Class.query.order_by(Class.name).all()

    default_tab = request.args.get('tab', 'teacher')
    return render_template('login.html', courses=courses, classes=classes, default_tab=default_tab)


@app.route('/api/login', methods=['POST'])
def api_login():
    """Handle user login (supports all roles: admin, faculty, teacher, student)."""
    data = request.get_json(silent=True) or request.form or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required.'}), 400

    import re
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return jsonify({'success': False, 'message': 'Please enter a valid email address.'}), 400

    try:
        # Check user in database
        user = User.query.filter_by(email=email).first()

        # Self-healing: if a standard default account was deleted or reset in Admin, restore it immediately
        if not user and email in ('teacher@school.edu', 'admin@school.edu', 'admin@attendai.edu', 'faculty@school.edu', 'student1@school.edu'):
            from database import ensure_default_accounts
            try:
                ensure_default_accounts()
                user = User.query.filter_by(email=email).first()
            except Exception as seed_err:
                print(f"Error restoring default accounts on login: {seed_err}")
                db.session.rollback()

        if not user:
            return jsonify({'success': False, 'message': 'No account was found with these credentials.'}), 404

        if not user.is_active:
            # Self-healing: if the standard demo teacher account was deactivated, reactivate it automatically
            if email == 'teacher@school.edu':
                user.is_active = True
                db.session.commit()
            else:
                return jsonify({'success': False, 'message': 'Your account is currently inactive. Please contact the administrator.'}), 403

        if not user.check_password(password):
            log_audit_action(user.id, 'login_failed', details='Failed login attempt (wrong password)')
            return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401

        # Self-healing: ensure teacher profile exists for teacher / faculty accounts
        if user.role in ('teacher', 'faculty') and not user.teacher:
            try:
                dept = Department.query.first()
                t_profile = Teacher(
                    user_id=user.id,
                    employee_id=f"TCH{user.id:03d}",
                    department_id=dept.id if dept else None,
                    office="Faculty Room A-101",
                    phone="555-0101"
                )
                db.session.add(t_profile)
                db.session.commit()
            except Exception as t_err:
                db.session.rollback()
                print(f"Error auto-linking teacher profile on login: {t_err}")

        # Update last login timestamp
        user.last_login = datetime.utcnow()
        db.session.commit()

        # Store user info in session
        session['user_id'] = user.id
        session['user_email'] = user.email
        session['user_name'] = user.name
        session['user_role'] = user.role

        # Backward compatibility for existing templates/scripts
        session['teacher_email'] = user.email
        session['teacher_name'] = user.name

        # Generate JWT/token if client uses token-based requests
        token = generate_token(user.id, user.role, user.name, user.email)

        log_audit_action(user.id, 'user_login', details=f'Logged in as {user.role}')

        return jsonify({
            'success': True,
            'message': 'Login successful.',
            'user_id': user.id,
            'user_name': user.name,
            'user_email': user.email,
            'user_role': user.role,
            'token': token
        }), 200

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'Login service is temporarily unavailable.'}), 500


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Handle user logout and ensure hardware camera is fully released."""
    stop_camera()

    user_id = session.get('user_id')
    if user_id:
        try:
            log_audit_action(user_id, 'user_logout', details='User logged out')
        except Exception:
            pass
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.'}), 200


@app.route('/')
@login_required
def index():
    """Main dashboard - teacher view."""
    user_role = session.get('user_role', 'teacher')
    if user_role == 'admin':
        return redirect(url_for('admin_dashboard_page'))
    if user_role == 'faculty':
        return redirect(url_for('faculty_dashboard_page'))
    if user_role == 'student':
        if session.get('student_id'):
            return redirect(url_for('student_attendance_view'))
        return redirect(url_for('student_dashboard_page'))
    return render_template('index.html')


@app.route('/admin')
@login_required
def admin_dashboard_page():
    """Admin dashboard page."""
    if session.get('user_role') != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html')


@app.route('/faculty')
@login_required
def faculty_dashboard_page():
    """Faculty dashboard page."""
    if session.get('user_role') not in ('faculty', 'admin'):
        return redirect(url_for('index'))
    return render_template('faculty.html')


@app.route('/student')
@login_required
def student_dashboard_page():
    """Student dashboard page."""
    if session.get('user_role') != 'student':
        return redirect(url_for('index'))
    return render_template('student.html')


@app.route('/api/me', methods=['GET'])
@login_required
def api_me():
    """Return current logged-in user info."""
    return jsonify({
        'id': session.get('user_id'),
        'name': session.get('user_name'),
        'email': session.get('user_email'),
        'role': session.get('user_role'),
    })


@app.after_request
def add_security_and_cache_headers(response):
    """Add cache control headers to prevent caching protected pages and Back button issues."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/video_feed')
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    # CRITICAL: Do NOT auto-start camera here! If inactive, generate_frames() streams placeholder frames.
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/camera/toggle', methods=['POST'])
def toggle_camera():
    """Start or stop the webcam."""
    global camera_active, camera_state
    data = request.json or {}
    action = data.get("action", "")
    
    if action == "start":
        success = start_camera()
        return jsonify({"success": success, "camera_active": camera_active, "state": camera_state})
    elif action == "stop":
        stop_camera()
        return jsonify({"success": True, "camera_active": camera_active, "state": camera_state})
    else:
        # Toggle current state
        if camera_active:
            stop_camera()
        else:
            start_camera()
        return jsonify({"success": True, "camera_active": camera_active, "state": camera_state})


@app.route('/api/camera/status', methods=['GET'])
def camera_status():
    global camera_active, camera_state, camera_mirror_mode, latest_detection
    with camera_lock:
        det = dict(latest_detection) if latest_detection else None
        if det and time.time() - det.get("timestamp", 0) > 2.5:
            det["detected"] = False
    return jsonify({
        "camera_active": camera_active,
        "state": camera_state,
        "mirror": camera_mirror_mode,
        "latest_detection": det
    })


@app.route('/api/camera/mirror', methods=['GET', 'POST'])
def camera_mirror_toggle():
    """Mirror-mode endpoint retained for backwards compatibility (disabled)."""
    return jsonify({"success": True, "mirror": False})


@app.route('/api/camera/stream-events', methods=['GET'])
def camera_stream_events():
    """Retrieve real-time camera recognition events and current detection box for live UI feedback."""
    global latest_detection, camera_mirror_mode
    since = request.args.get('since', 0, type=float)
    with camera_lock:
        det = dict(latest_detection) if latest_detection else None
        if det and time.time() - det.get("timestamp", 0) > 2.5:
            det["detected"] = False

    events = [e for e in recent_stream_events if e.get("timestamp", 0) > since]
    return jsonify({
        "success": True,
        "events": events,
        "latest_detection": det,
        "camera_mirror": camera_mirror_mode
    })


@app.route('/api/mark-attendance', methods=['POST'])
@app.route('/api/attendance/mark', methods=['POST'])
def api_mark_attendance():
    """Mark attendance endpoint with confidence threshold validation and audit logging."""
    data = request.get_json(silent=True) or {}
    print(f"[ATTENDANCE-CHAIN] Step 1: POST /api/mark-attendance received: {data}")

    student_id = data.get("student_id")
    name = data.get("name")
    roll_no = data.get("roll_no")
    course_id = data.get("course_id")
    class_id = data.get("class_id")
    confidence = data.get("confidence")

    if not student_id and not name and not roll_no:
        print("[ATTENDANCE-CHAIN] Step 1: FAILED - missing student identifier")
        return jsonify({"success": False, "message": "Missing student identifier (student_id, name, or roll_no required)."}), 400

    # Step 2: Confidence threshold check (default 0.58)
    if confidence is not None:
        try:
            conf_val = float(confidence)
            # Normalize percentage (e.g. 82 -> 0.82)
            if conf_val > 1.0:
                conf_val = conf_val / 100.0
            
            if conf_val < 0.58:
                pct = int(conf_val * 100)
                print(f"[ATTENDANCE-CHAIN] Step 2: Confidence check FAILED: {pct}% < 58% threshold")
                return jsonify({
                    "success": False,
                    "reason": "low_confidence",
                    "confidence": conf_val,
                    "threshold": 0.58,
                    "message": f"Recognition confidence ({pct}%) is below the required 58% threshold."
                }), 400
            print(f"[ATTENDANCE-CHAIN] Step 2: Confidence check PASSED: {int(conf_val*100)}% >= 58%")
            confidence = conf_val
        except ValueError:
            pass

    # Step 3 & 4: Execute mark_attendance
    result = mark_attendance(
        name=name or "",
        roll_no=roll_no,
        student_id=student_id,
        course_id=course_id,
        class_id=class_id,
        confidence=float(confidence) if confidence is not None else None,
        recognition_status=f"Recognized ({int(float(confidence)*100)}%)" if confidence is not None else "Recognized"
    )

    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code


@app.route('/api/camera/release-lock', methods=['POST'])
def release_camera_lock():
    """Temporarily stop backend webcam so browser getUserMedia can access the hardware without conflict."""
    global camera_active, camera_state
    try:
        stop_camera()
        time.sleep(0.15)  # Allow OS driver to fully release DirectShow/MSMF handle
        return jsonify({
            "success": True,
            "message": "Webcam released successfully for browser preview.",
            "camera_active": False,
            "state": "IDLE"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/camera/snapshot', methods=['GET'])
def camera_snapshot():
    """Return a single JPEG frame from the server webcam for registration capture."""
    global latest_frame, camera, camera_active

    frame_to_send = None
    with camera_lock:
        if latest_frame is not None:
            frame_to_send = latest_frame.copy()

    if frame_to_send is None:
        if not start_camera():
            return jsonify({"success": False, "message": "Unable to open webcam."}), 500

        try:
            with camera_lock:
                if camera is None or not camera.isOpened():
                    return jsonify({"success": False, "message": "Webcam is unavailable."}), 500
                success, frame_to_send = camera.read()
                if success and frame_to_send is not None:
                    latest_frame = frame_to_send.copy()
        except Exception as e:
            return jsonify({"success": False, "message": f"Camera capture error: {e}"}), 500

        if not success or frame_to_send is None:
            return jsonify({"success": False, "message": "Failed to capture camera frame."}), 500

    ret, jpeg = cv2.imencode('.jpg', frame_to_send, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ret:
        return jsonify({"success": False, "message": "Failed to encode captured image."}), 500

    response = Response(jpeg.tobytes(), mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


@app.route('/api/camera/registration-feed')
def registration_feed():
    """Stream live webcam frames specifically for the registration modal preview with face detection guide."""
    def gen_reg_frames():
        global camera, camera_active
        if not camera_active:
            start_camera()

        while True:
            with camera_lock:
                if not camera_active or camera is None or not camera.isOpened():
                    break
                success, frame = camera.read()

            if not success or frame is None:
                time.sleep(0.04)
                continue

            # Draw guide rectangle / detection box
            display_frame = frame.copy()
            try:
                detector = get_face_detector()
                if detector is not None:
                    faces = detector.detect(display_frame)
                    if faces is not None and len(faces[1]) > 0:
                        for f in faces[1]:
                            fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
                            cv2.rectangle(display_frame, (fx, fy), (fx + fw, fy + fh), (94, 234, 212), 2)
                            cv2.putText(display_frame, "Face Detected", (fx, max(22, fy - 8)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (94, 234, 212), 1, cv2.LINE_AA)
            except Exception:
                pass

            ret, jpeg = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.033)

    return Response(gen_reg_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/courses', methods=['GET'])
@login_required
def api_get_courses():
    """Retrieve all available courses from central database."""
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    query = Course.query
    if not include_inactive and session.get('user_role') != 'admin':
        query = query.filter(Course.status == 'active')

    courses = query.order_by(Course.name).all()
    return jsonify({
        "success": True,
        "courses": [{
            "id": c.id,
            "name": c.name,
            "code": c.code,
            "description": c.description,
            "status": c.status
        } for c in courses]
    })


@app.route('/api/classes', methods=['GET'])
@login_required
def api_get_classes():
    """Retrieve all classes, optionally filtered by course_id."""
    course_id = request.args.get('course_id')
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    query = Class.query
    if not include_inactive and session.get('user_role') != 'admin':
        query = query.filter(Class.status == 'active')

    if course_id and str(course_id).isdigit():
        c_id = int(course_id)
        query = query.filter(db.or_(Class.course_id == c_id, Class.department_id == c_id))

    classes = query.order_by(Class.name).all()
    return jsonify({
        "success": True,
        "classes": [{
            "id": c.id,
            "name": c.name,
            "code": c.code,
            "course_id": c.course_id,
            "course_name": c.course_name,
            "status": c.status,
            "capacity": c.capacity
        } for c in classes]
    })



@app.route('/api/camera/session-filter', methods=['GET', 'POST'])
@login_required
def api_camera_session_filter():
    """Get or set the active recognition filter (Course and/or Class)."""
    global active_recognition_filter
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form or {}
        course_id = data.get('course_id')
        class_id = data.get('class_id')

        active_recognition_filter = {
            "course_id": int(course_id) if course_id and str(course_id).isdigit() else None,
            "class_id": int(class_id) if class_id and str(class_id).isdigit() else None,
        }

    crs_name = "All Courses"
    cls_name = "All Classes"
    if active_recognition_filter.get("course_id"):
        crs = Course.query.get(active_recognition_filter["course_id"])
        if crs:
            crs_name = crs.name
    if active_recognition_filter.get("class_id"):
        cls = Class.query.get(active_recognition_filter["class_id"])
        if cls:
            cls_name = cls.name

    filter_data = dict(active_recognition_filter)
    filter_data["course_name"] = crs_name
    filter_data["class_name"] = cls_name

    return jsonify({
        "success": True,
        "filter": filter_data,
        "course_name": crs_name,
        "class_name": cls_name
    })


@app.route('/api/students', methods=['GET'])
@login_required
def list_students():
    """List registered student details with Roll Number, Course, Class, and Face status."""
    students = []
    seen_ids = set()

    # 1. Query from Student database table (primary authoritative source)
    try:
        db_students = Student.query.order_by(Student.name).all()
        for s in db_students:
            seen_ids.add(s.id)
            img_rel_path = s.face_image_path or f"{s.roll_no}_{s.name.replace(' ', '_')}.jpg"
            resolved = resolve_photo_path(img_rel_path)
            photo_url = f"/api/students/photo/{img_rel_path}" if resolved else None

            students.append({
                "id": s.id,
                "roll_no": s.roll_no,
                "name": s.name,
                "course_id": s.course_id,
                "course_name": s.course_name,
                "class_id": s.class_id,
                "class_name": s.class_name,
                "face_registered": s.face_registered,
                "photo_url": photo_url,
                "filename": img_rel_path,
                "registered_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else ""
            })
    except Exception as e:
        print(f"Error querying students from database: {e}")

    # 2. Fallback to legacy unlinked images on disk
    if IMAGE_DIR.exists():
        image_files = sorted(IMAGE_DIR.iterdir())
        valid_images = [img for img in image_files if img.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}]
        existing_filenames = {s["filename"] for s in students}

        for img_path in valid_images:
            if img_path.name in existing_filenames:
                continue
            stat = img_path.stat()
            created_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            stem_parts = img_path.stem.split("_")
            roll_guess = stem_parts[0] if len(stem_parts) > 1 and stem_parts[0].isalnum() else "—"
            name_guess = img_path.stem.upper().replace("_", " ")

            students.append({
                "id": None,
                "roll_no": roll_guess,
                "name": name_guess,
                "course_id": None,
                "course_name": "—",
                "class_id": None,
                "class_name": "—",
                "face_registered": True,
                "photo_url": f"/api/students/photo/{img_path.name}",
                "filename": img_path.name,
                "registered_at": created_time
            })

    with model_lock:
        curr_error = training_error
        curr_classes = class_names

    return jsonify({
        "students": students,
        "classes_loaded": curr_classes,
        "training_error": curr_error
    })


@app.route('/api/students/photo/<path:filename>')
def get_student_photo(filename):
    """Serve student photo files securely from Student Directory or legacy paths."""
    resolved = resolve_photo_path(filename)
    if resolved and resolved.exists() and resolved.is_file():
        try:
            # Prevent directory traversal attacks
            resolved.resolve().relative_to(BASE_DIR.resolve())
            return send_file(str(resolved), mimetype='image/jpeg')
        except ValueError:
            return jsonify({"success": False, "message": "Access denied."}), 403
    return jsonify({"success": False, "message": "Photo not found."}), 404


@app.route('/api/students', methods=['POST'])
@teacher_required
def add_student():
    """
    Register a new student or update an existing student's face data.
    Organizes physical face storage under:
        Student Directory / <Course> / <Class> / Roll_<RollNumber>_<Name> /
            face.jpg
            face_encoding.dat
    """
    roll_no = request.form.get('roll_no', '').strip()
    name = request.form.get('name', '').strip()
    course_id = request.form.get('course_id', '').strip()
    class_id = request.form.get('class_id', '').strip()
    update_existing = request.form.get('update_existing', '').strip().lower() in ('true', '1', 'yes')

    # 1. Validation
    if not roll_no:
        return jsonify({"success": False, "message": "Student Roll Number is required."}), 400

    if not name:
        return jsonify({"success": False, "message": "Student Name is required."}), 400

    if not course_id:
        return jsonify({"success": False, "message": "Course must be selected."}), 400

    if not class_id:
        return jsonify({"success": False, "message": "Class must be selected."}), 400

    # Sanitize inputs
    name_clean = " ".join(name.split())
    roll_clean = roll_no.strip()

    try:
        c_id = int(course_id)
        cl_id = int(class_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid Course or Class identifier."}), 400

    # Verify Course and Class exist in centralized database
    selected_course = Course.query.get(c_id)
    if not selected_course:
        return jsonify({"success": False, "message": "Selected Course does not exist."}), 404

    selected_class = Class.query.get(cl_id)
    if not selected_class:
        return jsonify({"success": False, "message": "Selected Class does not exist."}), 404

    # 2. Check for duplicate roll number
    existing_student = Student.query.filter(db.func.upper(Student.roll_no) == roll_clean.upper()).first()
    is_update = False
    if existing_student:
        # If updating the same student or explicitly requested
        if update_existing or (existing_student.name.strip().upper() == name_clean.upper()):
            is_update = True
        else:
            return jsonify({
                "success": False,
                "message": f"A student with Roll Number '{roll_no}' is already registered ({existing_student.name}). Roll Number must be unique."
            }), 409

    file = request.files.get('image')
    if not file:
        return jsonify({"success": False, "message": "Face photo is required for facial recognition."}), 400

    created_dir = None
    try:
        file_bytes = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({"success": False, "message": "Uploaded file is not a valid image format."}), 400

        # 3. Detect faces using FaceDetectorYN preserving facial landmarks
        net = get_face_detector()
        net.setInputSize((img.shape[1], img.shape[0]))
        _, raw_faces = net.detect(img)

        if raw_faces is None or len(raw_faces) == 0:
            return jsonify({
                "success": False,
                "message": "No face detected in the photo. Please capture or upload a clear frontal photo of the face."
            }), 400

        valid_faces = [f for f in raw_faces if (float(f[14]) if len(f) > 14 else float(f[4])) >= 0.45]
        if not valid_faces:
            return jsonify({
                "success": False,
                "message": "No clear face detected in the photo. Please capture or upload a clear frontal photo of the face."
            }), 400

        if len(valid_faces) > 1:
            return jsonify({
                "success": False,
                "message": f"Multiple faces detected ({len(valid_faces)} faces found). Please ensure only the student's face is in the photo."
            }), 400

        # 4. Generate Face Embedding using FaceRecognizerSF with landmark alignment
        recognizer_model = get_face_recognizer()
        try:
            face_align = recognizer_model.alignCrop(img, valid_faces[0])
            embedding = recognizer_model.feature(face_align).flatten()
            norm = np.linalg.norm(embedding)
            if norm > 1e-8:
                embedding = embedding / norm
        except Exception as exc:
            return jsonify({"success": False, "message": f"Face encoding extraction failed: {exc}"}), 500

        # 5. Save face photo & encoding hierarchically by Course + Class
        rel_image_path, rel_encoding_path, created_dir = save_student_face_data(
            course_name=selected_course.name,
            class_name=selected_class.name,
            roll_no=roll_clean,
            student_name=name_clean,
            img=img,
            embedding=embedding
        )

        import hashlib
        raw_img_bytes = cv2.imencode('.jpg', img)[1].tobytes()
        img_hash = hashlib.sha256(f"{roll_clean}_{hashlib.sha256(raw_img_bytes).hexdigest()}".encode()).hexdigest()

        # 6. Store or update Student record in Database
        student_email = f"{roll_clean.lower().replace('-', '_')}@student.attendai.edu"
        user_account = User.query.filter_by(email=student_email).first()
        if not user_account:
            user_account = User(
                email=student_email,
                name=name_clean,
                role='student',
                is_active=True
            )
            user_account.set_password('Student@123')
            db.session.add(user_account)
            db.session.flush()

        if is_update and existing_student:
            student_record = existing_student
            student_record.name = name_clean
            student_record.course_id = c_id
            student_record.class_id = cl_id
            student_record.department_id = selected_class.department_id or c_id
            student_record.face_registered = True
            student_record.face_images_count = (student_record.face_images_count or 0) + 1
            student_record.face_image_path = rel_image_path
        else:
            student_record = Student(
                user_id=user_account.id if user_account else None,
                name=name_clean,
                roll_no=roll_clean,
                email=student_email,
                course_id=c_id,
                class_id=cl_id,
                department_id=selected_class.department_id or c_id,
                face_registered=True,
                face_images_count=1,
                face_image_path=rel_image_path
            )
            db.session.add(student_record)

        db.session.flush()

        # 7. Store FaceEmbedding record in Database
        emb_record = FaceEmbedding.query.filter_by(student_id=student_record.id).first()
        if not emb_record:
            emb_record = FaceEmbedding(student_id=student_record.id)
            db.session.add(emb_record)

        emb_record.embedding_vector = json.dumps(embedding.tolist())
        emb_record.image_filename = rel_image_path
        emb_record.image_hash = img_hash
        emb_record.quality_score = float(valid_faces[0][14]) if len(valid_faces[0]) > 14 else (float(valid_faces[0][4]) if len(valid_faces[0]) > 4 else 1.0)

        db.session.commit()

        # Audit log
        user_id = session.get('user_id')
        log_audit_action(user_id, 'student_registered', 'students', record_id=student_record.id,
                         details=f'Registered student: {name_clean} (Roll: {roll_clean}, Course: {student_record.course_name}, Class: {student_record.class_name})')

        # 8. Retrain/refresh model cache in-memory
        train_model()

        return jsonify({
            "success": True,
            "message": f"Student '{name_clean}' (Roll No: {roll_clean}) registered successfully in {selected_course.name} - {selected_class.name}!",
            "student": {
                "id": student_record.id,
                "roll_no": student_record.roll_no,
                "name": student_record.name,
                "course_name": student_record.course_name,
                "class_name": student_record.class_name,
                "photo_url": f"/api/students/photo/{rel_image_path}"
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        # Transaction safety: remove newly created folder if database commit failed
        if created_dir and not is_update:
            delete_student_folder(created_dir)
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500


@app.route('/api/students/<path:target>', methods=['DELETE'])
@teacher_required
def delete_student(target):
    """Delete a student, remove their face directory, and retrain the model."""
    user_id = session.get('user_id')
    try:
        student = None
        if target.isdigit():
            student = Student.query.get(int(target))
        else:
            student = Student.query.filter(
                db.or_(
                    Student.face_image_path == target,
                    Student.roll_no == target.split("_")[0]
                )
            ).first()

        filename = target
        if student:
            filename = student.face_image_path or f"{student.roll_no}_{student.name.replace(' ', '_')}.jpg"
            # Delete physical student folder in Student Directory
            resolved = resolve_photo_path(filename)
            if resolved and resolved.exists():
                delete_student_folder(resolved.parent)

            db.session.delete(student)
            db.session.commit()

        # Legacy file cleanup
        target_path = IMAGE_DIR / Path(filename).name
        if target_path.exists():
            target_path.unlink()

        log_audit_action(user_id, 'student_deleted', 'students', details=f'Student deleted: {target}')
        train_model()
        return jsonify({"success": True, "message": "Student profile deleted successfully and model retrained."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting student: {e}"}), 500


def _get_student_directory_count():
    """Get the authoritative count of all registered students in the Student Directory."""
    students = []
    try:
        from flask import has_app_context
        if has_app_context():
            db_students = Student.query.all()
        else:
            with app.app_context():
                db_students = Student.query.all()
        for s in db_students:
            students.append(s)
    except Exception as e:
        print(f"Error querying Student directory: {e}")
        db_students = []

    if IMAGE_DIR.exists():
        existing_filenames = set()
        for s in db_students:
            img_rel = s.face_image_path or f"{s.roll_no}_{s.name.replace(' ', '_')}.jpg"
            existing_filenames.add(img_rel)
            if s.face_image_path:
                existing_filenames.add(Path(s.face_image_path).name)
        try:
            for img_path in sorted(IMAGE_DIR.iterdir()):
                if img_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                    if img_path.name not in existing_filenames:
                        students.append(img_path.name)
        except Exception as e:
            print(f"Error checking IMAGE_DIR: {e}")
    return len(students)


def _get_all_attendance_records(course_id=None, class_id=None, date_filter=None, search=None):
    """Retrieve unified, authoritative attendance records from DB and CSV."""
    records = []
    seen_keys = set()

    target_course = None
    target_class = None
    if course_id and str(course_id).isdigit():
        target_course = db.session.get(Course, int(course_id))
    if class_id and str(class_id).isdigit():
        target_class = db.session.get(Class, int(class_id))

    # 1. Query database records
    try:
        query = AttendanceRecord.query.order_by(AttendanceRecord.timestamp.desc())
        if class_id and str(class_id).isdigit():
            c_int = int(class_id)
            query = query.filter(db.or_(AttendanceRecord.class_id == c_int, AttendanceRecord.student.has(Student.class_id == c_int)))
        if course_id and str(course_id).isdigit():
            crs_int = int(course_id)
            query = query.filter(db.or_(AttendanceRecord.course_id == crs_int, AttendanceRecord.student.has(Student.course_id == crs_int)))

        db_records = query.all()
        for r in db_records:
            r_date = r.formatted_date
            r_time = r.formatted_time
            r_roll = r.student_roll_no
            r_name = r.student_name
            r_class = r.class_name
            r_course = r.course_name
            r_course_id = r.course_id or (r.student.course_id if r.student else None)
            r_class_id = r.class_id or (r.student.class_id if r.student else None)
            r_status = r.status.capitalize() if r.status else "Present"
            r_rec_status = r.recognition_status or (f"Recognized ({int(r.confidence * 100)}%)" if r.confidence else "Recognized")

            # Apply filters
            if date_filter and r_date != date_filter:
                continue
            if search and (search not in r_name.lower() and search not in r_roll.lower()):
                continue

            dedup_key = (r_roll.strip().lower() if r_roll else "", r_name.strip().lower(), r_date, r_time)
            seen_keys.add(dedup_key)

            records.append({
                "id": r.id,
                "roll_no": r_roll,
                "name": r_name,
                "course_id": r_course_id,
                "class_id": r_class_id,
                "class_name": r_class,
                "course_name": r_course,
                "date": r_date,
                "time": r_time,
                "status": r_status,
                "recognition_status": r_rec_status
            })
    except Exception as e:
        print(f"Error querying AttendanceRecord: {e}")

    # 2. Also incorporate Attendance.csv records so no data is missed
    if ATTENDANCE_FILE.exists():
        try:
            with ATTENDANCE_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for idx, row in enumerate(reader):
                    if not row or not any(row):
                        continue
                    if len(row) >= 8:
                        r_roll, r_name, r_class, r_course, r_date, r_time, r_status, r_rec = [c.strip() for c in row[:8]]
                    elif len(row) >= 5:
                        r_roll, r_name, r_class, r_course, r_date = [c.strip() for c in row[:5]]
                        r_time = row[5].strip() if len(row) > 5 else "00:00:00"
                        r_status = row[6].strip() if len(row) > 6 else "Present"
                        r_rec = row[7].strip() if len(row) > 7 else "Recognized"
                    elif len(row) >= 4:
                        r_name, r_date, r_time, r_status = [c.strip() for c in row[:4]]
                        r_roll = "—"
                        r_class = "—"
                        r_course = "—"
                        r_rec = "Legacy"
                    else:
                        continue

                    if date_filter and r_date != date_filter:
                        continue
                    if search and (search not in r_name.lower() and search not in r_roll.lower()):
                        continue

                    # Filter by course/class if specified
                    if target_course and r_course and r_course.lower() != target_course.name.lower() and (not target_course.code or r_course.lower() != target_course.code.lower()):
                        continue
                    if target_class and r_class and r_class.lower() != target_class.name.lower() and (not target_class.code or r_class.lower() != target_class.code.lower()):
                        continue

                    dedup_key = (r_roll.lower() if r_roll else "", r_name.lower(), r_date, r_time)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    csv_course_id = target_course.id if (target_course and r_course and (r_course.lower() == target_course.name.lower() or (target_course.code and r_course.lower() == target_course.code.lower()))) else None
                    csv_class_id = target_class.id if (target_class and r_class and (r_class.lower() == target_class.name.lower() or (target_class.code and r_class.lower() == target_class.code.lower()))) else None

                    records.append({
                        "id": idx + 10000,
                        "roll_no": r_roll,
                        "name": r_name,
                        "course_id": csv_course_id,
                        "class_id": csv_class_id,
                        "class_name": r_class,
                        "course_name": r_course,
                        "date": r_date,
                        "time": r_time,
                        "status": r_status.capitalize() if r_status else "Present",
                        "recognition_status": r_rec
                    })
        except Exception as e:
            print(f"Error parsing Attendance.csv: {e}")

    # Sort descending by date, then time
    records.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    return records


@app.route('/api/attendance', methods=['GET'])
@login_required
def get_attendance():
    """Retrieve full attendance list with all 8 fields and filters."""
    course_id = request.args.get('course_id')
    class_id = request.args.get('class_id')
    date_filter = request.args.get('date')
    search = request.args.get('search', '').strip().lower()

    records = _get_all_attendance_records(course_id=course_id, class_id=class_id, date_filter=date_filter, search=search)
    return jsonify({"records": records})


def build_export_response(rows, filename_prefix, format_type='csv'):
    """Helper to convert list of dicts into CSV, Excel (.xlsx), or PDF (.pdf) Flask Response."""
    format_type = (format_type or 'csv').lower()
    
    if format_type in ('xlsx', 'excel'):
        import pandas as pd
        import io
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Report')
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f"{filename_prefix}.xlsx")
        
    elif format_type == 'pdf':
        import io
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        elements.append(Paragraph(f"<b>{filename_prefix.replace('_', ' ').title()}</b>", styles['Heading1']))
        elements.append(Spacer(1, 12))
        
        if rows:
            headers = list(rows[0].keys())
            table_data = [headers]
            for row in rows:
                table_data.append([str(row.get(h, '')) for h in headers])
            
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#22D3EE')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 10),
                ('BOTTOMPADDING', (0,0), (-1,0), 6),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No records found.", styles['Normal']))
            
        doc.build(elements)
        output.seek(0)
        return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=f"{filename_prefix}.pdf")
        
    else:
        import csv
        import io
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        else:
            output.write("Student Roll Number,Student Name,Class,Course,Date,Time,Attendance Status,Face Recognition Status\r\n")
        return Response(output.getvalue(), mimetype='text/csv', headers={"Content-Disposition": f"attachment; filename={filename_prefix}.csv"})


@app.route('/api/attendance/download', methods=['GET'])
@teacher_required
def download_attendance():
    """Download Attendance report file (supports format=csv, xlsx, pdf) with course/class filters."""
    user_id = session.get('user_id')
    format_type = request.args.get('format', 'csv')
    course_id = request.args.get('course_id')
    class_id = request.args.get('class_id')
    date_filter = request.args.get('date')
    search = request.args.get('search', '').strip().lower()
    
    log_audit_action(user_id, 'attendance_downloaded', 'attendance_records', details=f'User downloaded attendance report ({format_type})')
    
    records = _get_all_attendance_records(course_id=course_id, class_id=class_id, date_filter=date_filter, search=search)
    rows = []
    for r in records:
        rows.append({
            "Student Roll Number": r.get("roll_no") or "",
            "Student Name": r.get("name") or "",
            "Class": r.get("class_name") or "",
            "Course": r.get("course_name") or "",
            "Date": r.get("date") or "",
            "Time": r.get("time") or "",
            "Attendance Status": r.get("status") or "Present",
            "Face Recognition Status": r.get("recognition_status") or "Recognized"
        })
            
    return build_export_response(rows, "Attendance_Report", format_type)



@app.route('/api/attendance', methods=['DELETE'])
@admin_required
def clear_attendance():
    """Clear all attendance history from both SQLite database and Attendance.csv."""
    user_id = session.get('user_id')
    log_audit_action(user_id, 'attendance_cleared', 'attendance_records', details='Admin cleared all attendance records')
    
    try:
        # 1. Delete from authoritative SQLite database
        AttendanceRecord.query.delete()
        db.session.commit()

        # 2. Reset Attendance.csv with unified 8-column header
        with ATTENDANCE_FILE.open("w", encoding="utf-8") as f:
            f.write("Student Roll Number,Student Name,Class,Course,Date,Time,Attendance Status,Face Recognition Status\n")
        return jsonify({"success": True, "message": "Attendance history cleared successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error resetting logs: {e}"}), 500


@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Calculate attendance statistics for Dashboard widgets from authoritative live records."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Total Students: count of all students in Student Directory
    total_students = _get_student_directory_count()

    # 2. Get today's attendance records from the exact same live source
    today_records = _get_all_attendance_records(date_filter=today)
    
    unique_present_today = set()
    last_active = "N/A"
    last_present_name = ""

    for r in today_records:
        r_status = (r.get("status") or "").strip().lower()
        if r_status == "present":
            roll = (r.get("roll_no") or "").strip()
            name = (r.get("name") or "").strip()
            s_key = roll.lower() if (roll and roll not in ("—", "-", "N/A")) else name.lower()
            if s_key:
                unique_present_today.add(s_key)
            if last_active == "N/A" and r.get("time"):
                last_active = r["time"]
                last_present_name = name or roll

    present_count = len(unique_present_today)
    absent_count = max(0, total_students - present_count)
    rate = round((present_count / total_students * 100)) if total_students > 0 else 0

    return jsonify({
        "total_students": total_students,
        "total_present_today": present_count,
        "total_absent_today": absent_count,
        "attendance_rate": rate,
        "last_active": last_active,
        "last_student": f"{last_present_name} ({last_active})" if last_present_name and last_active != "N/A" else "N/A"
    })


# ============================================================================
# PHASE 3: ADMIN MANAGEMENT & DASHBOARD
# ============================================================================

@app.route('/api/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    """Get admin dashboard summary statistics."""
    user_id = session.get('user_id')
    log_audit_action(user_id, 'admin_dashboard_viewed', 'admin_access', details='Admin viewed dashboard')
    
    try:
        total_users = User.query.count()
        admin_count = User.query.filter_by(role='admin').count()
        faculty_count = User.query.filter_by(role='faculty').count()
        teacher_count = User.query.filter_by(role='teacher').count()
        student_count = User.query.filter_by(role='student').count()
        
        total_courses = Course.query.count()
        total_departments = Department.query.count()
        total_classes = Class.query.count()
        total_subjects = Subject.query.count()
        
        total_sessions = AttendanceSession.query.count()
        completed_sessions = AttendanceSession.query.filter_by(status='completed').count()
        active_sessions = AttendanceSession.query.filter_by(status='active').count()
        
        return jsonify({
            "success": True,
            "users": {
                "total": total_users,
                "admins": admin_count,
                "faculty": faculty_count,
                "teachers": teacher_count,
                "students": student_count
            },
            "structure": {
                "courses": total_courses,
                "departments": total_departments,
                "classes": total_classes,
                "subjects": total_subjects
            },
            "sessions": {
                "total": total_sessions,
                "completed": completed_sessions,
                "active": active_sessions
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching dashboard data: {e}"}), 500


# ============================================================================
# ADMIN USERS MANAGEMENT
# ============================================================================

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def list_users():
    """List all users with their roles and status."""
    try:
        users = User.query.all()
        user_list = []
        for u in users:
            user_list.append({
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None
            })
        return jsonify({"success": True, "users": user_list})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching users: {e}"}), 500


@app.route('/api/admin/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user account."""
    user_id = session.get('user_id')
    
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        name = data.get('name', '').strip()
        role = data.get('role', 'student').lower()
        
        if not email or not password or not name:
            return jsonify({"success": False, "message": "Email, password, and name are required"}), 400
        
        if role not in ['admin', 'faculty', 'teacher', 'student']:
            return jsonify({"success": False, "message": "Invalid role. Must be admin, faculty, teacher, or student"}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({"success": False, "message": "Email already registered"}), 409
        
        if len(password) < 6:
            return jsonify({"success": False, "message": "Password must be at least 6 characters"}), 400
        
        new_user = User(email=email, name=name, role=role, is_active=True)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        log_audit_action(user_id, 'user_created', 'users', record_id=new_user.id, 
                        details=f'New user created: {email} ({role})')
        
        return jsonify({
            "success": True, 
            "message": f"User '{email}' created successfully",
            "user_id": new_user.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error creating user: {e}"}), 500


@app.route('/api/admin/users/<int:target_user_id>', methods=['GET'])
@admin_required
def get_user(target_user_id):
    """Get specific user details."""
    try:
        user = User.query.get(target_user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching user: {e}"}), 500


@app.route('/api/admin/users/<int:target_user_id>', methods=['PUT'])
@admin_required
def update_user(target_user_id):
    """Update user details (name, role, active status)."""
    admin_user_id = session.get('user_id')
    
    try:
        user = User.query.get(target_user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        if user.id == admin_user_id:
            return jsonify({"success": False, "message": "Cannot modify your own account"}), 403
        
        data = request.get_json()
        old_data = {
            "name": user.name,
            "role": user.role,
            "is_active": user.is_active
        }
        
        if 'name' in data:
            user.name = data['name'].strip()
        if 'role' in data:
            new_role = data['role'].lower()
            if new_role not in ['admin', 'faculty', 'teacher', 'student']:
                return jsonify({"success": False, "message": "Invalid role"}), 400
            user.role = new_role
        if 'is_active' in data:
            user.is_active = bool(data['is_active'])
        
        db.session.commit()
        
        log_audit_action(admin_user_id, 'user_updated', 'users', record_id=user.id,
                        old_value=str(old_data), new_value=str({"name": user.name, "role": user.role, "is_active": user.is_active}),
                        details=f'User updated: {user.email}')
        
        return jsonify({"success": True, "message": "User updated successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating user: {e}"}), 500


@app.route('/api/admin/users/<int:target_user_id>/reset-password', methods=['PUT'])
@admin_required
def admin_reset_password(target_user_id):
    """Admin endpoint to reset a user's password."""
    admin_user_id = session.get('user_id')
    try:
        user = User.query.get(target_user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        data = request.get_json() or {}
        new_password = data.get('new_password', '').strip()
        if not new_password or len(new_password) < 6:
            return jsonify({"success": False, "message": "Password must be at least 6 characters"}), 400
        
        user.set_password(new_password)
        db.session.commit()
        log_audit_action(admin_user_id, 'password_reset', 'users', record_id=user.id, details=f'Reset password for {user.email}')
        return jsonify({"success": True, "message": f"Password reset successfully for {user.email}"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# ADMIN STUDENT & FACE MANAGEMENT
# ============================================================================

@app.route('/api/admin/students', methods=['GET'])
@admin_required
def admin_list_students():
    """List all students with class & department info."""
    try:
        students = Student.query.all()
        result = []
        for s in students:
            result.append({
                "id": s.id,
                "name": s.name,
                "roll_no": s.roll_no,
                "admission_no": s.admission_no,
                "email": s.email,
                "course_id": s.course_id,
                "course_name": s.course_name,
                "class_id": s.class_id,
                "class_name": s.class_name,
                "department_id": s.department_id,
                "department_name": s.department.name if s.department else None,
                "face_registered": s.face_registered,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "user_id": s.user_id
            })
        return jsonify({"success": True, "students": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/admin/students', methods=['POST'])
@admin_required
def admin_create_student():
    """Create a new student."""
    admin_user_id = session.get('user_id')
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        roll_no = data.get('roll_no', '').strip()
        class_id = data.get('class_id')
        dept_id = data.get('department_id')
        email = data.get('email', '').strip().lower()
        
        if not name or not roll_no:
            return jsonify({"success": False, "message": "Name and Roll No are required"}), 400
        if Student.query.filter_by(roll_no=roll_no).first():
            return jsonify({"success": False, "message": "Roll No already exists"}), 409
            
        student = Student(name=name, roll_no=roll_no, class_id=class_id, department_id=dept_id, email=email)
        db.session.add(student)
        db.session.commit()
        log_audit_action(admin_user_id, 'student_created', 'students', record_id=student.id, details=f'Created student: {name} ({roll_no})')
        return jsonify({"success": True, "message": f"Student '{name}' created successfully", "student_id": student.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/admin/students/<int:student_id>/register-face', methods=['POST'])
@admin_required
def admin_register_student_face(student_id):
    """Register or re-capture facial data for a student."""
    admin_user_id = session.get('user_id')
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404
        
        if 'image' in request.files:
            file = request.files['image']
            filename = secure_filename(file.filename)
            filepath = IMAGE_DIR / f"{student.roll_no}_{filename}"
            file.save(filepath)
            student.face_registered = True
            student.face_images_count += 1
            db.session.commit()
            train_model()
            log_audit_action(admin_user_id, 'face_registered', 'students', record_id=student.id, details=f'Registered face for {student.name}')
            return jsonify({"success": True, "message": "Face registered and model retrained successfully."})
        else:
            data = request.get_json() or {}
            if data.get('face_registered') is not None:
                student.face_registered = bool(data['face_registered'])
                db.session.commit()
                return jsonify({"success": True, "message": "Student face status updated."})
            return jsonify({"success": False, "message": "No image file provided"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# ACADEMIC SUBJECTS MANAGEMENT
# ============================================================================

@app.route('/api/admin/subjects', methods=['GET'])
@admin_required
def admin_list_subjects():
    try:
        subjects = Subject.query.all()
        res = []
        for s in subjects:
            res.append({
                "id": s.id,
                "name": s.name,
                "code": s.code,
                "class_id": s.class_id,
                "class_name": s.class_.name if s.class_ else None,
                "credits": s.credits
            })
        return jsonify({"success": True, "subjects": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/admin/subjects', methods=['POST'])
@admin_required
def admin_create_subject():
    admin_user_id = session.get('user_id')
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        code = data.get('code', '').strip().upper()
        class_id = data.get('class_id')
        credits = data.get('credits', 3)
        if not name or not code or not class_id:
            return jsonify({"success": False, "message": "Name, code, and class_id are required"}), 400
        
        subj = Subject(name=name, code=code, class_id=class_id, credits=credits)
        db.session.add(subj)
        db.session.commit()
        log_audit_action(admin_user_id, 'subject_created', 'subjects', record_id=subj.id, details=f'Created subject: {name}')
        return jsonify({"success": True, "message": f"Subject '{name}' created successfully", "subject_id": subj.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# SYSTEM SETTINGS & AUDIT LOGS
# ============================================================================

@app.route('/api/admin/settings', methods=['GET'])
@admin_required
def admin_get_settings():
    try:
        settings = SystemSetting.query.all()
        res = {s.key: {"value": s.value, "description": s.description} for s in settings}
        defaults = {
            "confidence_threshold": "0.6",
            "session_duration_minutes": "60",
            "late_threshold_minutes": "15",
            "academic_year": "2025-2026",
            "academic_semester": "Spring"
        }
        for k, v in defaults.items():
            if k not in res:
                res[k] = {"value": v, "description": f"Default {k}"}
        return jsonify({"success": True, "settings": res})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Settings error: {e}"}), 500


@app.route('/api/admin/settings', methods=['PUT'])
@admin_required
def admin_update_settings():
    admin_user_id = session.get('user_id')
    try:
        data = request.get_json() or {}
        for key, value in data.items():
            setting = SystemSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = str(value)
            else:
                setting = SystemSetting(key=key, value=str(value), description=f"Setting for {key}")
                db.session.add(setting)
        db.session.commit()
        log_audit_action(admin_user_id, 'settings_updated', 'system_settings', details=f'Updated settings: {list(data.keys())}')
        return jsonify({"success": True, "message": "Settings updated successfully"})
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Update error: {e}"}), 500


@app.route('/api/admin/audit-logs', methods=['GET'])
@admin_required
def admin_get_audit_logs():
    try:
        user_id = request.args.get('user_id', type=int)
        action = request.args.get('action')
        limit = request.args.get('limit', 100, type=int)
        
        query = AuditLog.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        if action:
            query = query.filter(AuditLog.action.ilike(f"%{action}%"))
        
        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
        res = []
        for l in logs:
            user_name = "System"
            if l.user_id:
                u = User.query.get(l.user_id)
                if u:
                    user_name = u.name
            res.append({
                "id": l.id,
                "user_id": l.user_id,
                "user_name": user_name,
                "action": l.action,
                "table_name": l.table_name,
                "record_id": l.record_id,
                "old_value": l.old_value,
                "new_value": l.new_value,
                "details": l.details,
                "ip_address": l.ip_address,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None
            })
        return jsonify({"success": True, "logs": res})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Audit log error: {e}"}), 500







@app.route('/api/admin/users/<int:target_user_id>', methods=['DELETE'])
@admin_required
def delete_user(target_user_id):
    """Delete a user account."""
    admin_user_id = session.get('user_id')
    
    try:
        user = User.query.get(target_user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        if user.id == admin_user_id:
            return jsonify({"success": False, "message": "Cannot delete your own account"}), 403

        # Protect standard default system accounts
        if user.email in ("teacher@school.edu", "admin@school.edu", "admin@attendai.edu"):
            return jsonify({"success": False, "message": f"Cannot delete standard system account '{user.email}'."}), 403

        email = user.email
        role = user.role
        
        db.session.delete(user)
        db.session.commit()
        
        log_audit_action(admin_user_id, 'user_deleted', 'users', record_id=target_user_id,
                        details=f'User deleted: {email} ({role})')
        
        return jsonify({"success": True, "message": f"User '{email}' deleted successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting user: {e}"}), 500


# ============================================================================
# ADMIN DEPARTMENTS MANAGEMENT
# ============================================================================

@app.route('/api/admin/departments', methods=['GET'])
@admin_required
def list_departments():
    """List all departments."""
    try:
        departments = Department.query.all()
        dept_list = []
        for d in departments:
            dept_list.append({
                "id": d.id,
                "name": d.name,
                "code": d.code,
                "description": d.description,
                "class_count": len(d.classes) if d.classes else 0
            })
        return jsonify({"success": True, "departments": dept_list})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching departments: {e}"}), 500


@app.route('/api/admin/departments', methods=['POST'])
@admin_required
def create_department():
    """Create a new department."""
    user_id = session.get('user_id')
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        code = data.get('code', '').strip().upper()
        description = data.get('description', '').strip()
        
        if not name or not code:
            return jsonify({"success": False, "message": "Name and code are required"}), 400
        
        if Department.query.filter_by(name=name).first():
            return jsonify({"success": False, "message": "Department name already exists"}), 409
        if Department.query.filter_by(code=code).first():
            return jsonify({"success": False, "message": "Department code already exists"}), 409
        
        new_dept = Department(name=name, code=code, description=description)
        db.session.add(new_dept)
        db.session.commit()
        
        log_audit_action(user_id, 'department_created', 'departments', record_id=new_dept.id,
                        details=f'Department created: {name} ({code})')
        
        return jsonify({
            "success": True,
            "message": f"Department '{name}' created successfully",
            "department_id": new_dept.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error creating department: {e}"}), 500


@app.route('/api/admin/departments/<int:dept_id>', methods=['PUT'])
@admin_required
def update_department(dept_id):
    """Update department details."""
    user_id = session.get('user_id')
    
    try:
        dept = Department.query.get(dept_id)
        if not dept:
            return jsonify({"success": False, "message": "Department not found"}), 404
        
        data = request.get_json()
        old_data = {"name": dept.name, "code": dept.code, "description": dept.description}
        
        if 'name' in data:
            new_name = data['name'].strip()
            if new_name != dept.name and Department.query.filter_by(name=new_name).first():
                return jsonify({"success": False, "message": "Department name already exists"}), 409
            dept.name = new_name
        
        if 'code' in data:
            new_code = data['code'].strip().upper()
            if new_code != dept.code and Department.query.filter_by(code=new_code).first():
                return jsonify({"success": False, "message": "Department code already exists"}), 409
            dept.code = new_code
        
        if 'description' in data:
            dept.description = data['description'].strip()
        
        db.session.commit()
        
        log_audit_action(user_id, 'department_updated', 'departments', record_id=dept.id,
                        old_value=str(old_data), new_value=str({"name": dept.name, "code": dept.code, "description": dept.description}),
                        details=f'Department updated: {dept.name}')
        
        return jsonify({"success": True, "message": "Department updated successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating department: {e}"}), 500


@app.route('/api/admin/departments/<int:dept_id>', methods=['DELETE'])
@admin_required
def delete_department(dept_id):
    """Delete a department."""
    user_id = session.get('user_id')
    
    try:
        dept = Department.query.get(dept_id)
        if not dept:
            return jsonify({"success": False, "message": "Department not found"}), 404
        
        if dept.classes and len(dept.classes) > 0:
            return jsonify({"success": False, "message": "Cannot delete department with existing classes"}), 409
        
        name = dept.name
        db.session.delete(dept)
        db.session.commit()
        
        log_audit_action(user_id, 'department_deleted', 'departments', record_id=dept_id,
                        details=f'Department deleted: {name}')
        
        return jsonify({"success": True, "message": f"Department '{name}' deleted successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting department: {e}"}), 500


# ============================================================================
# ADMIN COURSES MANAGEMENT
# ============================================================================

@app.route('/api/admin/courses', methods=['GET'])
@admin_required
def admin_list_courses():
    """List all courses with classes and students counts."""
    try:
        courses = Course.query.order_by(Course.id.desc()).all()
        course_list = []
        for c in courses:
            course_list.append({
                "id": c.id,
                "name": c.name,
                "code": c.code,
                "description": c.description,
                "status": c.status,
                "class_count": len(c.classes) if c.classes else 0,
                "student_count": len(c.students) if c.students else 0,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None
            })
        return jsonify({"success": True, "courses": course_list})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching courses: {e}"}), 500


@app.route('/api/admin/courses', methods=['POST'])
@admin_required
def admin_create_course():
    """Create a new course."""
    user_id = session.get('user_id')
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        code = data.get('code', '').strip().upper()
        description = data.get('description', '').strip()
        status = data.get('status', 'active').strip().lower()

        if not name:
            return jsonify({"success": False, "message": "Course name is required."}), 400

        if not code:
            code = "".join([w[0] for w in name.split() if w]).upper()[:10]
            if not code:
                code = "CRS"

        if Course.query.filter(db.func.lower(Course.name) == name.lower()).first():
            return jsonify({"success": False, "message": f"Course with name '{name}' already exists."}), 409

        if Course.query.filter(db.func.upper(Course.code) == code.upper()).first():
            cnt = Course.query.filter(Course.code.ilike(f"{code}%")).count()
            code = f"{code}_{cnt+1}"

        new_course = Course(
            name=name,
            code=code,
            description=description,
            status=status if status in ('active', 'inactive') else 'active'
        )
        db.session.add(new_course)
        db.session.commit()

        log_audit_action(user_id, 'course_created', 'courses', record_id=new_course.id,
                         details=f'Course created: {name} ({code})')

        return jsonify({
            "success": True,
            "message": f"Course '{name}' created successfully.",
            "course": {
                "id": new_course.id,
                "name": new_course.name,
                "code": new_course.code,
                "status": new_course.status
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error creating course: {e}"}), 500


@app.route('/api/admin/courses/<int:course_id>', methods=['PUT'])
@admin_required
def admin_update_course(course_id):
    """Update course name, code, description, and status."""
    user_id = session.get('user_id')
    try:
        course = Course.query.get(course_id)
        if not course:
            return jsonify({"success": False, "message": "Course not found."}), 404

        data = request.get_json() or {}
        old_data = {"name": course.name, "code": course.code, "status": course.status}

        if 'name' in data:
            new_name = data['name'].strip()
            if not new_name:
                return jsonify({"success": False, "message": "Course name cannot be empty."}), 400
            existing = Course.query.filter(db.func.lower(Course.name) == new_name.lower()).first()
            if existing and existing.id != course.id:
                return jsonify({"success": False, "message": f"Course with name '{new_name}' already exists."}), 409
            course.name = new_name

        if 'code' in data:
            new_code = data['code'].strip().upper()
            if new_code:
                existing_code = Course.query.filter(db.func.upper(Course.code) == new_code).first()
                if existing_code and existing_code.id != course.id:
                    return jsonify({"success": False, "message": f"Course code '{new_code}' already exists."}), 409
                course.code = new_code

        if 'description' in data:
            course.description = data['description'].strip()

        if 'status' in data:
            st = data['status'].strip().lower()
            if st in ('active', 'inactive'):
                course.status = st

        db.session.commit()

        log_audit_action(user_id, 'course_updated', 'courses', record_id=course.id,
                         old_value=str(old_data), new_value=str({"name": course.name, "code": course.code, "status": course.status}),
                         details=f'Course updated: {course.name}')

        return jsonify({"success": True, "message": f"Course '{course.name}' updated successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating course: {e}"}), 500


@app.route('/api/admin/courses/<int:course_id>/status', methods=['PUT'])
@admin_required
def admin_toggle_course_status(course_id):
    """Toggle or set course active/inactive status."""
    user_id = session.get('user_id')
    try:
        course = Course.query.get(course_id)
        if not course:
            return jsonify({"success": False, "message": "Course not found."}), 404

        data = request.get_json(silent=True) or {}
        new_status = data.get('status')
        if new_status in ('active', 'inactive'):
            course.status = new_status
        else:
            course.status = 'inactive' if course.status == 'active' else 'active'

        db.session.commit()
        log_audit_action(user_id, 'course_status_changed', 'courses', record_id=course.id,
                         details=f'Course {course.name} status changed to {course.status}')

        return jsonify({
            "success": True,
            "message": f"Course status updated to '{course.status}'.",
            "status": course.status
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error toggling course status: {e}"}), 500


@app.route('/api/admin/courses/<int:course_id>', methods=['DELETE'])
@admin_required
def admin_delete_course(course_id):
    """Delete a course only if it has no classes or registered students."""
    user_id = session.get('user_id')
    try:
        course = Course.query.get(course_id)
        if not course:
            return jsonify({"success": False, "message": "Course not found."}), 404

        if course.classes and len(course.classes) > 0:
            return jsonify({
                "success": False,
                "message": f"Cannot delete course '{course.name}' because it contains {len(course.classes)} class(es). Please delete or reassign classes first, or deactivate the course instead."
            }), 409

        if course.students and len(course.students) > 0:
            return jsonify({
                "success": False,
                "message": f"Cannot delete course '{course.name}' because it has {len(course.students)} enrolled student(s). Deactivate the course instead."
            }), 409

        name = course.name
        db.session.delete(course)
        db.session.commit()

        log_audit_action(user_id, 'course_deleted', 'courses', record_id=course_id,
                         details=f'Course deleted: {name}')

        return jsonify({"success": True, "message": f"Course '{name}' deleted successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting course: {e}"}), 500


# ============================================================================
# ADMIN CLASSES MANAGEMENT
# ============================================================================

@app.route('/api/admin/classes', methods=['GET'])
@admin_required
def list_classes():
    """List all classes with course and department info."""
    try:
        course_id = request.args.get('course_id')
        query = Class.query
        if course_id and str(course_id).isdigit():
            query = query.filter(Class.course_id == int(course_id))

        classes = query.order_by(Class.id.desc()).all()
        class_list = []
        for c in classes:
            class_list.append({
                "id": c.id,
                "name": c.name,
                "code": c.code,
                "course_id": c.course_id,
                "course_name": c.course_name,
                "department_id": c.department_id,
                "department_name": c.department.name if c.department else None,
                "capacity": c.capacity,
                "status": c.status,
                "student_count": len(c.students) if c.students else 0
            })
        return jsonify({"success": True, "classes": class_list})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching classes: {e}"}), 500


@app.route('/api/admin/classes', methods=['POST'])
@admin_required
def create_class():
    """Create a new class linked to a Course."""
    user_id = session.get('user_id')
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        code = data.get('code', '').strip().upper()
        course_id = data.get('course_id')
        department_id = data.get('department_id')
        capacity = data.get('capacity', 60)
        status = data.get('status', 'active').strip().lower()

        if not name:
            return jsonify({"success": False, "message": "Class name is required."}), 400

        if not course_id:
            course = Course.query.first()
            if not course:
                dept_obj = Department.query.get(department_id) if department_id else None
                c_name = dept_obj.name if dept_obj else "General Course"
                c_code = dept_obj.code if dept_obj else "GEN"
                course = Course(name=c_name, code=c_code, description="Auto-created course")
                db.session.add(course)
                db.session.flush()
            course_id = course.id
        else:
            course = Course.query.get(course_id)
            if not course:
                return jsonify({"success": False, "message": "Selected Course does not exist."}), 404

        if not code:
            code = f"{course.code}_{''.join([w[0] for w in name.split() if w]).upper()}"
            if Class.query.filter_by(code=code).first():
                code = f"{code}_{Class.query.count()+1}"

        if Class.query.filter_by(code=code).first():
            return jsonify({"success": False, "message": f"Class code '{code}' already exists."}), 409

        # If department not provided, use first available department or create default
        if not department_id:
            first_dept = Department.query.first()
            if not first_dept:
                first_dept = Department(name="General Academic Department", code="GEN", description="Default academic department")
                db.session.add(first_dept)
                db.session.flush()
            department_id = first_dept.id

        new_class = Class(
            name=name,
            code=code,
            course_id=course.id,
            department_id=department_id,
            capacity=capacity,
            status=status if status in ('active', 'inactive') else 'active'
        )
        db.session.add(new_class)
        db.session.commit()

        log_audit_action(user_id, 'class_created', 'classes', record_id=new_class.id,
                         details=f'Class created: {name} ({code}) under Course {course.name}')

        return jsonify({
            "success": True,
            "message": f"Class '{name}' created successfully under Course '{course.name}'.",
            "class_id": new_class.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error creating class: {e}"}), 500


@app.route('/api/admin/classes/<int:class_id>', methods=['PUT'])
@admin_required
def update_class(class_id):
    """Update class details."""
    user_id = session.get('user_id')
    try:
        cls = Class.query.get(class_id)
        if not cls:
            return jsonify({"success": False, "message": "Class not found."}), 404

        data = request.get_json() or {}
        old_data = {"name": cls.name, "code": cls.code, "capacity": cls.capacity, "course_id": cls.course_id}

        if 'name' in data:
            cls.name = data['name'].strip()
        if 'code' in data:
            new_code = data['code'].strip().upper()
            if new_code != cls.code and Class.query.filter_by(code=new_code).first():
                return jsonify({"success": False, "message": "Class code already exists."}), 409
            cls.code = new_code
        if 'capacity' in data:
            cls.capacity = int(data['capacity'])
        if 'course_id' in data:
            c_id = data['course_id']
            if not Course.query.get(c_id):
                return jsonify({"success": False, "message": "Specified Course does not exist."}), 404
            cls.course_id = c_id
        if 'department_id' in data and data['department_id']:
            cls.department_id = data['department_id']
        if 'status' in data:
            st = data['status'].strip().lower()
            if st in ('active', 'inactive'):
                cls.status = st

        db.session.commit()

        log_audit_action(user_id, 'class_updated', 'classes', record_id=cls.id,
                         old_value=str(old_data), new_value=str({"name": cls.name, "code": cls.code, "capacity": cls.capacity}),
                         details=f'Class updated: {cls.name}')

        return jsonify({"success": True, "message": "Class updated successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating class: {e}"}), 500


@app.route('/api/admin/classes/<int:class_id>/status', methods=['PUT'])
@admin_required
def admin_toggle_class_status(class_id):
    """Toggle class active/inactive status."""
    user_id = session.get('user_id')
    try:
        cls = Class.query.get(class_id)
        if not cls:
            return jsonify({"success": False, "message": "Class not found."}), 404

        data = request.get_json(silent=True) or {}
        new_status = data.get('status')
        if new_status in ('active', 'inactive'):
            cls.status = new_status
        else:
            cls.status = 'inactive' if cls.status == 'active' else 'active'

        db.session.commit()
        log_audit_action(user_id, 'class_status_changed', 'classes', record_id=cls.id,
                         details=f'Class {cls.name} status changed to {cls.status}')

        return jsonify({"success": True, "message": f"Class status updated to '{cls.status}'.", "status": cls.status})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating class status: {e}"}), 500


@app.route('/api/admin/classes/<int:class_id>', methods=['DELETE'])
@admin_required
def delete_class(class_id):
    """Delete a class."""
    user_id = session.get('user_id')
    try:
        cls = Class.query.get(class_id)
        if not cls:
            return jsonify({"success": False, "message": "Class not found."}), 404

        if cls.students and len(cls.students) > 0:
            return jsonify({"success": False, "message": f"Cannot delete class with {len(cls.students)} enrolled student(s). Deactivate it instead."}), 409

        name = cls.name
        db.session.delete(cls)
        db.session.commit()

        log_audit_action(user_id, 'class_deleted', 'classes', record_id=class_id,
                         details=f'Class deleted: {name}')

        return jsonify({"success": True, "message": f"Class '{name}' deleted successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting class: {e}"}), 500


@app.route('/api/admin/clean-database', methods=['POST'])
@admin_required
def admin_clean_database():
    """Reset database to a clean/blank initial state (retaining only admin user)."""
    user_id = session.get('user_id')
    try:
        from database import reset_to_clean_state
        success = reset_to_clean_state(app)
        if not success:
            return jsonify({"success": False, "message": "Failed to clean database."}), 500

        # Reload face model in memory (which will now be empty)
        train_model()

        log_audit_action(user_id, 'database_cleaned', 'system',
                         details='Admin reset system database to clean blank state')

        return jsonify({
            "success": True,
            "message": "Database reset to clean state successfully. All courses, classes, students, and attendance records removed."
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error cleaning database: {e}"}), 500



# ==================== TEACHER DASHBOARD & FEATURES ====================

def _ensure_teacher_profile(user):
    """Ensure a User with role teacher or faculty has an associated Teacher record."""
    if not user:
        return None
    if user.teacher:
        return user.teacher
    try:
        from models import Teacher, Department
        dept = Department.query.first()
        t_profile = Teacher(
            user_id=user.id,
            employee_id=f"TCH{user.id:03d}",
            department_id=dept.id if dept else None,
            office="Faculty Room A-101",
            phone="555-0101"
        )
        db.session.add(t_profile)
        db.session.commit()
        return t_profile
    except Exception as e:
        db.session.rollback()
        print(f"Error ensuring teacher profile: {e}")
        return Teacher.query.filter_by(user_id=user.id).first()


@app.route('/api/teacher/dashboard', methods=['GET'])
@teacher_required
def teacher_dashboard():
    """Get teacher dashboard summary with statistics and overview."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        teacher = _ensure_teacher_profile(user)
        if not teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        dept_id = teacher.department_id
        
        # Get today's date
        from datetime import date
        today = date.today()
        
        # Count statistics
        assigned_classes = Class.query.filter(
            Class.subjects.any(AttendanceSession.teacher_id == teacher.id)
        ).distinct().count()
        
        assigned_subjects = Subject.query.filter(
            Subject.sessions.any(AttendanceSession.teacher_id == teacher.id)
        ).distinct().count()
        
        # Today's sessions
        todays_sessions = AttendanceSession.query.filter(
            AttendanceSession.teacher_id == teacher.id,
            AttendanceSession.date == today
        ).all()
        
        # Attendance stats for today
        total_present_today = 0
        total_marked_today = 0
        for sess_obj in todays_sessions:
            marked = AttendanceRecord.query.filter(
                AttendanceRecord.session_id == sess_obj.id
            ).count()
            total_marked_today += marked
            present = AttendanceRecord.query.filter(
                AttendanceRecord.session_id == sess_obj.id,
                AttendanceRecord.status == 'present'
            ).count()
            total_present_today += present
        
        # Overall class attendance percentage (last 30 days)
        from datetime import timedelta
        thirty_days_ago = today - timedelta(days=30)
        
        recent_sessions = AttendanceSession.query.filter(
            AttendanceSession.teacher_id == teacher.id,
            AttendanceSession.date >= thirty_days_ago
        ).all()
        
        total_attendance_records = 0
        total_present_records = 0
        for sess_obj in recent_sessions:
            records = AttendanceRecord.query.filter(
                AttendanceRecord.session_id == sess_obj.id
            ).all()
            for record in records:
                if record.status != 'absent':
                    total_present_records += 1
                total_attendance_records += 1
        
        class_avg_attendance = (total_present_records / total_attendance_records * 100) if total_attendance_records > 0 else 0
        
        # Low attendance students (less than 75% in last 30 days)
        low_attendance_threshold = 75
        low_attendance_count = 0
        
        for sess_obj in recent_sessions:
            if sess_obj.class_ and sess_obj.class_.students:
                for student in sess_obj.class_.students:
                    student_records = AttendanceRecord.query.filter(
                        AttendanceRecord.student_id == student.id,
                        AttendanceRecord.session_id.in_([s.id for s in recent_sessions])
                    ).all()
                    
                    if len(student_records) > 0:
                        present_count = sum(1 for r in student_records if r.status != 'absent')
                        attendance_pct = (present_count / len(student_records)) * 100
                        if attendance_pct < low_attendance_threshold:
                            low_attendance_count += 1
        
        dept_name = teacher.department.name if teacher.department else "N/A"
        
        return jsonify({
            "success": True,
            "data": {
                "teacher_name": user.name,
                "assigned_classes": assigned_classes,
                "assigned_subjects": assigned_subjects,
                "todays_sessions_count": len(todays_sessions),
                "todays_attendance": {
                    "marked": total_marked_today,
                    "present": total_present_today
                },
                "class_avg_attendance": round(class_avg_attendance, 2),
                "low_attendance_students": low_attendance_count,
                "department": dept_name
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching dashboard: {e}"}), 500


@app.route('/api/teacher/classes', methods=['GET'])
@teacher_required
def teacher_get_classes():
    """Get all classes assigned to the teacher."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        teacher = _ensure_teacher_profile(user)
        if not teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        # Get classes for which teacher has created attendance sessions
        classes = Class.query.filter(
            Class.sessions.any(AttendanceSession.teacher_id == teacher.id)
        ).distinct().all()
        
        classes_data = []
        for cls in classes:
            classes_data.append({
                "id": cls.id,
                "name": cls.name,
                "code": cls.code,
                "capacity": cls.capacity,
                "department": cls.department.name if cls.department else "N/A"
            })
        
        return jsonify({
            "success": True,
            "data": classes_data
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching classes: {e}"}), 500


@app.route('/api/teacher/classes/<int:class_id>/attendance-stats', methods=['GET'])
@teacher_required
def teacher_class_attendance_stats(class_id):
    """Get attendance statistics for a specific class."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        teacher = _ensure_teacher_profile(user)
        if not teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        cls = Class.query.get(class_id)
        
        if not cls:
            return jsonify({"success": False, "message": "Class not found"}), 404
        
        # Get all sessions for this teacher and class
        sessions = AttendanceSession.query.filter(
            AttendanceSession.teacher_id == teacher.id,
            AttendanceSession.class_id == class_id
        ).all()
        
        if not sessions:
            return jsonify({
                "success": True,
                "data": {
                    "class_name": cls.name,
                    "class_code": cls.code,
                    "total_students": len(cls.students),
                    "average_attendance": 0,
                    "total_sessions": 0,
                    "student_attendance": []
                }
            })
        
        # Calculate per-student attendance
        student_attendance = []
        for student in cls.students:
            records = AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.session_id.in_([s.id for s in sessions])
            ).all()
            
            if len(records) > 0:
                present = sum(1 for r in records if r.status != 'absent')
                percentage = (present / len(records)) * 100
            else:
                present = 0
                percentage = 0
            
            student_attendance.append({
                "student_id": student.id,
                "name": student.name,
                "roll_no": student.roll_no,
                "present": present,
                "total": len(records),
                "percentage": round(percentage, 2)
            })
        
        # Calculate class average
        if student_attendance:
            avg_attendance = sum(s["percentage"] for s in student_attendance) / len(student_attendance)
        else:
            avg_attendance = 0
        
        return jsonify({
            "success": True,
            "data": {
                "class_name": cls.name,
                "class_code": cls.code,
                "total_students": len(cls.students),
                "average_attendance": round(avg_attendance, 2),
                "total_sessions": len(sessions),
                "student_attendance": student_attendance
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching attendance stats: {e}"}), 500


@app.route('/api/teacher/low-attendance', methods=['GET'])
@teacher_required
def teacher_low_attendance():
    """Get students with low attendance across all classes."""
    user_id = session.get('user_id')
    threshold = request.args.get('threshold', 75, type=float)
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        teacher = _ensure_teacher_profile(user)
        if not teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        # Get all classes taught by this teacher
        classes = Class.query.filter(
            Class.sessions.any(AttendanceSession.teacher_id == teacher.id)
        ).distinct().all()
        
        low_attendance_students = []
        
        for cls in classes:
            sessions = AttendanceSession.query.filter(
                AttendanceSession.teacher_id == teacher.id,
                AttendanceSession.class_id == cls.id
            ).all()
            
            for student in cls.students:
                records = AttendanceRecord.query.filter(
                    AttendanceRecord.student_id == student.id,
                    AttendanceRecord.session_id.in_([s.id for s in sessions])
                ).all()
                
                if len(records) > 0:
                    present = sum(1 for r in records if r.status != 'absent')
                    percentage = (present / len(records)) * 100
                    
                    if percentage < threshold:
                        low_attendance_students.append({
                            "student_id": student.id,
                            "name": student.name,
                            "roll_no": student.roll_no,
                            "class": cls.name,
                            "attendance_percentage": round(percentage, 2),
                            "present": present,
                            "total": len(records)
                        })
        
        # Sort by attendance percentage
        low_attendance_students.sort(key=lambda x: x["attendance_percentage"])
        
        return jsonify({
            "success": True,
            "data": {
                "threshold": threshold,
                "students": low_attendance_students
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching low attendance: {e}"}), 500


@app.route('/api/teacher/attendance-sessions', methods=['GET'])
@teacher_required
def teacher_get_sessions():
    """Get all attendance sessions created by the teacher."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        teacher = _ensure_teacher_profile(user)
        if not teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        sessions = AttendanceSession.query.filter(
            AttendanceSession.teacher_id == teacher.id
        ).order_by(AttendanceSession.date.desc(), AttendanceSession.start_time.desc()).all()
        
        sessions_data = []
        for sess in sessions:
            sessions_data.append({
                "id": sess.id,
                "class_name": sess.class_.name if sess.class_ else "N/A",
                "subject_name": sess.subject.name if sess.subject else "N/A",
                "date": sess.date.isoformat(),
                "start_time": sess.start_time.isoformat() if sess.start_time else "N/A",
                "end_time": sess.end_time.isoformat() if sess.end_time else "N/A",
                "status": sess.status,
                "total_expected": sess.total_students_expected,
                "notes": sess.notes
            })
        
        return jsonify({
            "success": True,
            "data": sessions_data
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching sessions: {e}"}), 500


@app.route('/api/teacher/attendance-sessions', methods=['POST'])
@teacher_required
def teacher_create_session():
    """Create a new attendance session."""
    user_id = session.get('user_id')
    data = request.get_json()
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        teacher = _ensure_teacher_profile(user)
        if not teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        # Validate required fields
        if not data.get('class_id') or not data.get('date') or not data.get('start_time'):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        class_id = data.get('class_id')
        subject_id = data.get('subject_id')
        date_str = data.get('date')
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')
        notes = data.get('notes', '')
        
        cls = Class.query.get(class_id)
        if not cls:
            return jsonify({"success": False, "message": "Class not found"}), 404
        
        if subject_id:
            subject = Subject.query.get(subject_id)
            if not subject:
                return jsonify({"success": False, "message": "Subject not found"}), 404
        
        # Parse dates/times
        from datetime import datetime as dt
        date_obj = dt.strptime(date_str, '%Y-%m-%d').date()
        start_time_obj = dt.strptime(start_time_str, '%H:%M:%S').time()
        end_time_obj = dt.strptime(end_time_str, '%H:%M:%S').time() if end_time_str else None
        
        # Check for duplicate session
        existing = AttendanceSession.query.filter(
            AttendanceSession.teacher_id == teacher.id,
            AttendanceSession.class_id == class_id,
            AttendanceSession.date == date_obj
        ).first()
        
        if existing:
            return jsonify({"success": False, "message": "Session already exists for this class on this date"}), 409
        
        # Create new session
        session_obj = AttendanceSession(
            teacher_id=teacher.id,
            class_id=class_id,
            subject_id=subject_id if subject_id else None,
            date=date_obj,
            start_time=start_time_obj,
            end_time=end_time_obj,
            status='pending',
            total_students_expected=len(cls.students),
            notes=notes
        )
        
        db.session.add(session_obj)
        db.session.commit()
        
        log_audit_action(user_id, 'attendance_session_created', 'attendance_sessions', 
                        record_id=session_obj.id,
                        details=f'Session created: {cls.name} on {date_obj}')
        
        return jsonify({
            "success": True,
            "message": "Attendance session created successfully",
            "data": {
                "session_id": session_obj.id,
                "class_name": cls.name,
                "date": date_obj.isoformat(),
                "status": session_obj.status
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error creating session: {e}"}), 500


@app.route('/api/teacher/attendance-sessions/<int:session_id>', methods=['GET'])
@teacher_required
def teacher_get_session(session_id):
    """Get details of a specific attendance session."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        session_obj = AttendanceSession.query.get(session_id)
        
        if not session_obj:
            return jsonify({"success": False, "message": "Session not found"}), 404
        
        if session_obj.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        # Get attendance records for this session
        records = AttendanceRecord.query.filter(
            AttendanceRecord.session_id == session_id
        ).all()
        
        attendance_data = []
        for record in records:
            attendance_data.append({
                "id": record.id,
                "student_name": record.student.name,
                "student_id": record.student.id,
                "roll_no": record.student.roll_no,
                "status": record.status,
                "timestamp": record.timestamp.isoformat() if record.timestamp else None,
                "confidence": record.confidence,
                "marked_by_teacher": record.marked_by_teacher,
                "notes": record.notes
            })
        
        return jsonify({
            "success": True,
            "data": {
                "session_id": session_obj.id,
                "class_name": session_obj.class_.name,
                "subject_name": session_obj.subject.name if session_obj.subject else "N/A",
                "date": session_obj.date.isoformat(),
                "start_time": session_obj.start_time.isoformat() if session_obj.start_time else None,
                "end_time": session_obj.end_time.isoformat() if session_obj.end_time else None,
                "status": session_obj.status,
                "total_expected": session_obj.total_students_expected,
                "notes": session_obj.notes,
                "attendance_records": attendance_data
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching session: {e}"}), 500


@app.route('/api/teacher/attendance-sessions/<int:session_id>', methods=['PUT'])
@teacher_required
def teacher_update_session(session_id):
    """Update an attendance session."""
    user_id = session.get('user_id')
    data = request.get_json()
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        session_obj = AttendanceSession.query.get(session_id)
        
        if not session_obj:
            return jsonify({"success": False, "message": "Session not found"}), 404
        
        if session_obj.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        # Can only update pending sessions
        if session_obj.status != 'pending':
            return jsonify({"success": False, "message": "Can only update pending sessions"}), 409
        
        # Update allowed fields
        if 'status' in data:
            session_obj.status = data['status']
        if 'notes' in data:
            session_obj.notes = data['notes']
        if 'end_time' in data and data['end_time']:
            from datetime import datetime as dt
            session_obj.end_time = dt.strptime(data['end_time'], '%H:%M:%S').time()
        
        session_obj.updated_at = datetime.utcnow()
        db.session.commit()
        
        log_audit_action(user_id, 'attendance_session_updated', 'attendance_sessions',
                        record_id=session_id,
                        details=f'Session updated: {session_obj.class_.name}')
        
        return jsonify({
            "success": True,
            "message": "Session updated successfully"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating session: {e}"}), 500


@app.route('/api/teacher/attendance-sessions/<int:session_id>', methods=['DELETE'])
@teacher_required
def teacher_delete_session(session_id):
    """Delete an attendance session."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        session_obj = AttendanceSession.query.get(session_id)
        
        if not session_obj:
            return jsonify({"success": False, "message": "Session not found"}), 404
        
        if session_obj.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        # Can only delete pending or cancelled sessions
        if session_obj.status not in ('pending', 'cancelled'):
            return jsonify({"success": False, "message": "Can only delete pending or cancelled sessions"}), 409
        
        class_name = session_obj.class_.name
        db.session.delete(session_obj)
        db.session.commit()
        
        log_audit_action(user_id, 'attendance_session_deleted', 'attendance_sessions',
                        record_id=session_id,
                        details=f'Session deleted: {class_name}')
        
        return jsonify({
            "success": True,
            "message": "Session deleted successfully"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting session: {e}"}), 500


@app.route('/api/teacher/attendance-sessions/<int:session_id>/start', methods=['POST'])
@teacher_required
def teacher_start_session(session_id):
    """Start an attendance session."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        session_obj = AttendanceSession.query.get(session_id)
        
        if not session_obj:
            return jsonify({"success": False, "message": "Session not found"}), 404
        
        if session_obj.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        if session_obj.status != 'pending':
            return jsonify({"success": False, "message": "Session can only be started from pending status"}), 409
        
        session_obj.status = 'active'
        session_obj.updated_at = datetime.utcnow()
        db.session.commit()
        
        log_audit_action(user_id, 'attendance_session_started', 'attendance_sessions',
                        record_id=session_id,
                        details=f'Session started: {session_obj.class_.name}')
        
        return jsonify({
            "success": True,
            "message": "Attendance session started successfully",
            "data": {
                "session_id": session_obj.id,
                "status": session_obj.status
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error starting session: {e}"}), 500


@app.route('/api/teacher/attendance-sessions/<int:session_id>/complete', methods=['POST'])
@teacher_required
def teacher_complete_session(session_id):
    """Complete an attendance session."""
    user_id = session.get('user_id')
    data = request.get_json() or {}
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        session_obj = AttendanceSession.query.get(session_id)
        
        if not session_obj:
            return jsonify({"success": False, "message": "Session not found"}), 404
        
        if session_obj.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        if session_obj.status != 'active':
            return jsonify({"success": False, "message": "Session must be active to complete"}), 409
        
        session_obj.status = 'completed'
        session_obj.end_time = datetime.utcnow().time()
        session_obj.updated_at = datetime.utcnow()
        
        # Mark absent students who weren't marked present
        class_students = session_obj.class_.students
        for student in class_students:
            existing = AttendanceRecord.query.filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student.id
            ).first()
            
            if not existing:
                # Mark as absent if not already marked
                attendance = AttendanceRecord(
                    session_id=session_id,
                    student_id=student.id,
                    timestamp=datetime.utcnow(),
                    status='absent',
                    marked_by_teacher=True,
                    notes='Auto-marked absent at session completion'
                )
                db.session.add(attendance)
        
        db.session.commit()
        
        log_audit_action(user_id, 'attendance_session_completed', 'attendance_sessions',
                        record_id=session_id,
                        details=f'Session completed: {session_obj.class_.name}')
        
        return jsonify({
            "success": True,
            "message": "Attendance session completed successfully",
            "data": {
                "session_id": session_obj.id,
                "status": session_obj.status
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error completing session: {e}"}), 500


# ==================== ATTENDANCE CORRECTION & MANUAL MARKING ====================

@app.route('/api/attendance/mark-manual', methods=['POST'])
@teacher_required
def mark_attendance_manual():
    """Manually mark a student present or absent in an attendance session."""
    user_id = session.get('user_id')
    data = request.get_json()
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        
        # Validate required fields
        if not data.get('session_id') or not data.get('student_id') or not data.get('status'):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        session_id = data['session_id']
        student_id = data['student_id']
        status = data['status'].lower()
        notes = data.get('notes', '')
        
        if status not in ('present', 'absent', 'late'):
            return jsonify({"success": False, "message": "Invalid status"}), 400
        
        # Verify session belongs to this teacher
        session_obj = AttendanceSession.query.get(session_id)
        if not session_obj:
            return jsonify({"success": False, "message": "Session not found"}), 404
        
        if session_obj.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        # Verify student is in the class
        student = Student.query.get(student_id)
        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404
        
        if student.class_id != session_obj.class_id:
            return jsonify({"success": False, "message": "Student not in this class"}), 409
        
        # Check for existing attendance record
        attendance = AttendanceRecord.query.filter(
            AttendanceRecord.session_id == session_id,
            AttendanceRecord.student_id == student_id
        ).first()
        
        if attendance:
            # Update existing record
            old_status = attendance.status
            attendance.status = status
            attendance.marked_by_teacher = True
            attendance.notes = notes
            attendance.updated_at = datetime.utcnow()
            
            log_audit_action(user_id, 'attendance_corrected', 'attendance_records',
                            record_id=attendance.id,
                            old_value=str({"status": old_status}),
                            new_value=str({"status": status}),
                            details=f'Attendance corrected for {student.name}: {old_status} -> {status}')
        else:
            # Create new record
            attendance = AttendanceRecord(
                session_id=session_id,
                student_id=student_id,
                timestamp=datetime.utcnow(),
                status=status,
                marked_by_teacher=True,
                notes=notes
            )
            db.session.add(attendance)
            
            log_audit_action(user_id, 'attendance_marked_manual', 'attendance_records',
                            record_id=None,
                            details=f'Attendance marked for {student.name}: {status}')
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Attendance marked successfully",
            "data": {
                "session_id": session_id,
                "student_id": student_id,
                "status": status,
                "marked_by_teacher": True
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error marking attendance: {e}"}), 500


@app.route('/api/attendance/<int:record_id>/correct', methods=['PUT'])
@teacher_required
def correct_attendance(record_id):
    """Correct an existing attendance record."""
    user_id = session.get('user_id')
    data = request.get_json()
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        
        # Get the attendance record
        attendance = AttendanceRecord.query.get(record_id)
        if not attendance:
            return jsonify({"success": False, "message": "Attendance record not found"}), 404
        
        # Verify teacher owns the session
        if attendance.session.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        old_status = attendance.status
        
        # Update allowed fields
        if 'status' in data:
            new_status = data['status'].lower()
            if new_status not in ('present', 'absent', 'late', 'unknown'):
                return jsonify({"success": False, "message": "Invalid status"}), 400
            attendance.status = new_status
        
        if 'notes' in data:
            attendance.notes = data['notes']
        
        attendance.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        log_audit_action(user_id, 'attendance_corrected', 'attendance_records',
                        record_id=record_id,
                        old_value=str({"status": old_status}),
                        new_value=str({"status": attendance.status}),
                        details=f'Attendance corrected for {attendance.student.name}')
        
        return jsonify({
            "success": True,
            "message": "Attendance record updated successfully",
            "data": {
                "record_id": record_id,
                "old_status": old_status,
                "new_status": attendance.status
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error correcting attendance: {e}"}), 500


@app.route('/api/attendance/<int:record_id>', methods=['DELETE'])
@teacher_required
def delete_attendance(record_id):
    """Delete an attendance record (only for pending sessions)."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        
        # Get the attendance record
        attendance = AttendanceRecord.query.get(record_id)
        if not attendance:
            return jsonify({"success": False, "message": "Attendance record not found"}), 404
        
        # Verify teacher owns the session
        if attendance.session.teacher_id != teacher.id:
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        # Can only delete from active sessions
        if attendance.session.status not in ('pending', 'active'):
            return jsonify({"success": False, "message": "Cannot delete attendance from completed/cancelled sessions"}), 409
        
        student_name = attendance.student.name
        db.session.delete(attendance)
        db.session.commit()
        
        log_audit_action(user_id, 'attendance_deleted', 'attendance_records',
                        record_id=record_id,
                        details=f'Attendance deleted for {student_name}')
        
        return jsonify({
            "success": True,
            "message": "Attendance record deleted successfully"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting attendance: {e}"}), 500


# ==================== FACULTY DASHBOARD & FEATURES ====================

@app.route('/api/faculty/dashboard', methods=['GET'])
@faculty_required
def faculty_dashboard():
    """Get faculty dashboard summary with department-level statistics."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        teacher = getattr(user, 'teacher', None)
        dept = teacher.department if teacher else None

        if not dept:
            dept = Department.query.first()
            if not dept:
                return jsonify({
                    "success": True,
                    "data": {
                        "faculty_name": user.name,
                        "department": "All Departments",
                        "total_students": 0,
                        "total_classes": 0,
                        "total_subjects": 0,
                        "dept_avg_attendance": 0,
                        "low_attendance_students": 0,
                        "dept_sessions_last_30_days": 0
                    }
                })
        
        from datetime import date, timedelta
        today = date.today()
        
        # Department statistics
        dept_classes = Class.query.filter(Class.department_id == dept.id).all()
        dept_subjects = Subject.query.filter(
            Subject.class_id.in_([cls.id for cls in dept_classes])
        ).all()
        
        total_students = Student.query.filter(Student.department_id == dept.id).count()
        total_classes = len(dept_classes)
        total_subjects = len(dept_subjects)
        
        # Department average attendance (last 30 days)
        thirty_days_ago = today - timedelta(days=30)
        dept_sessions = AttendanceSession.query.filter(
            AttendanceSession.class_id.in_([cls.id for cls in dept_classes]),
            AttendanceSession.date >= thirty_days_ago
        ).all()
        
        total_records = 0
        present_records = 0
        for att_sess in dept_sessions:
            records = AttendanceRecord.query.filter(
                AttendanceRecord.session_id == att_sess.id
            ).all()
            for record in records:
                if record.status != 'absent':
                    present_records += 1
                total_records += 1
        
        dept_avg_attendance = (present_records / total_records * 100) if total_records > 0 else 0
        
        # Low attendance students in department
        low_threshold = 75
        low_attendance_count = 0
        
        for student in Student.query.filter(Student.department_id == dept.id).all():
            student_records = AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.session_id.in_([s.id for s in dept_sessions])
            ).all()
            
            if len(student_records) > 0:
                present = sum(1 for r in student_records if r.status != 'absent')
                pct = (present / len(student_records)) * 100
                if pct < low_threshold:
                    low_attendance_count += 1
        
        return jsonify({
            "success": True,
            "data": {
                "faculty_name": user.name,
                "department": dept.name,
                "total_students": total_students,
                "total_classes": total_classes,
                "total_subjects": total_subjects,
                "dept_avg_attendance": round(dept_avg_attendance, 2),
                "low_attendance_students": low_attendance_count,
                "dept_sessions_last_30_days": len(dept_sessions)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching dashboard: {e}"}), 500


@app.route('/api/faculty/attendance-trends', methods=['GET'])
@faculty_required
def faculty_attendance_trends():
    """Get attendance trends for the faculty's department."""
    user_id = session.get('user_id')
    days = request.args.get('days', 30, type=int)
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        teacher = getattr(user, 'teacher', None)
        dept = teacher.department if teacher else None

        if not dept:
            dept = Department.query.first()
            if not dept:
                return jsonify({
                    "success": True,
                    "data": {
                        "department": "All Departments",
                        "period_days": days,
                        "trends": {}
                    }
                })
        
        from datetime import date, timedelta
        today = date.today()
        start_date = today - timedelta(days=days)
        
        dept_classes = Class.query.filter(Class.department_id == dept.id).all()
        
        # Get daily attendance stats
        daily_stats = {}
        
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            sessions = AttendanceSession.query.filter(
                AttendanceSession.class_id.in_([cls.id for cls in dept_classes]),
                AttendanceSession.date == current_date
            ).all()
            
            total = 0
            present = 0
            for att_sess in sessions:
                records = AttendanceRecord.query.filter(
                    AttendanceRecord.session_id == att_sess.id
                ).all()
                for record in records:
                    if record.status != 'absent':
                        present += 1
                    total += 1
            
            if total > 0:
                daily_stats[current_date.isoformat()] = {
                    "date": current_date.isoformat(),
                    "present": present,
                    "total": total,
                    "percentage": round((present / total) * 100, 2)
                }
        
        return jsonify({
            "success": True,
            "data": {
                "department": dept.name,
                "period_days": days,
                "trends": daily_stats
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching trends: {e}"}), 500


# ==================== REPORT GENERATION ====================

@app.route('/api/teacher/reports/attendance', methods=['GET'])
@teacher_required
def teacher_attendance_report():
    """Generate attendance report for a teacher's classes (CSV)."""
    user_id = session.get('user_id')
    class_id = request.args.get('class_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    format_type = request.args.get('format', 'csv')  # csv, json
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        
        # Build query for sessions
        query = AttendanceSession.query.filter(AttendanceSession.teacher_id == teacher.id)
        
        if class_id:
            query = query.filter(AttendanceSession.class_id == class_id)
        
        if start_date:
            from datetime import datetime as dt
            start = dt.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(AttendanceSession.date >= start)
        
        if end_date:
            from datetime import datetime as dt
            end = dt.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(AttendanceSession.date <= end)
        
        sessions = query.order_by(AttendanceSession.date.desc()).all()
        
        if not sessions:
            return jsonify({"success": False, "message": "No sessions found for the given criteria"}), 404
        
        # Prepare report data
        report_data = []
        
        for session in sessions:
            records = AttendanceRecord.query.filter(
                AttendanceRecord.session_id == session.id
            ).all()
            
            for record in records:
                report_data.append({
                    'Date': session.date.strftime('%Y-%m-%d'),
                    'Class': session.class_.name,
                    'Subject': session.subject.name if session.subject else 'N/A',
                    'Student Name': record.student.name,
                    'Roll No': record.student.roll_no,
                    'Status': record.status.capitalize(),
                    'Time': record.timestamp.strftime('%H:%M:%S') if record.timestamp else 'N/A',
                    'Marked By Teacher': 'Yes' if record.marked_by_teacher else 'No',
                    'Notes': record.notes or ''
                })
        
        if format_type == 'json':
            return jsonify({
                "success": True,
                "data": report_data
            })
        
        # CSV format
        import io
        output = io.StringIO()
        if report_data:
            fieldnames = report_data[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(report_data)
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=attendance_report.csv'
        return response
    
    except Exception as e:
        return jsonify({"success": False, "message": f"Error generating report: {e}"}), 500


@app.route('/api/teacher/reports/class-summary', methods=['GET'])
@teacher_required
def teacher_class_summary_report():
    """Generate class attendance summary report."""
    user_id = session.get('user_id')
    class_id = request.args.get('class_id', type=int)
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Teacher profile not found"}), 404
        
        teacher = user.teacher
        
        if not class_id:
            return jsonify({"success": False, "message": "class_id is required"}), 400
        
        cls = Class.query.get(class_id)
        if not cls:
            return jsonify({"success": False, "message": "Class not found"}), 404
        
        sessions = AttendanceSession.query.filter(
            AttendanceSession.teacher_id == teacher.id,
            AttendanceSession.class_id == class_id
        ).all()
        
        # Generate per-student summary
        summary_data = []
        
        for student in cls.students:
            records = AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.session_id.in_([s.id for s in sessions])
            ).all()
            
            if len(records) > 0:
                present = sum(1 for r in records if r.status == 'present')
                absent = sum(1 for r in records if r.status == 'absent')
                late = sum(1 for r in records if r.status == 'late')
                percentage = (present / len(records)) * 100
            else:
                present = absent = late = 0
                percentage = 0
            
            summary_data.append({
                'Student Name': student.name,
                'Roll No': student.roll_no,
                'Total Sessions': len(records),
                'Present': present,
                'Absent': absent,
                'Late': late,
                'Attendance %': round(percentage, 2)
            })
        
        return jsonify({
            "success": True,
            "data": {
                "class_name": cls.name,
                "total_sessions": len(sessions),
                "summary": summary_data
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error generating report: {e}"}), 500


@app.route('/api/faculty/reports/department-summary', methods=['GET'])
@faculty_required
def faculty_department_report():
    """Generate department attendance summary report."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.teacher:
            return jsonify({"success": False, "message": "Faculty profile not found"}), 404
        
        teacher = user.teacher
        dept = teacher.department
        
        if not dept:
            return jsonify({"success": False, "message": "Faculty not assigned to department"}), 404
        
        from datetime import date, timedelta
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)
        
        # Get all classes in department
        dept_classes = Class.query.filter(Class.department_id == dept.id).all()
        
        report_data = []
        
        for cls in dept_classes:
            sessions = AttendanceSession.query.filter(
                AttendanceSession.class_id == cls.id,
                AttendanceSession.date >= thirty_days_ago
            ).all()
            
            total_records = 0
            present_records = 0
            
            for session in sessions:
                records = AttendanceRecord.query.filter(
                    AttendanceRecord.session_id == session.id
                ).all()
                
                for record in records:
                    if record.status != 'absent':
                        present_records += 1
                    total_records += 1
            
            avg_attendance = (present_records / total_records * 100) if total_records > 0 else 0
            
            report_data.append({
                'Class': cls.name,
                'Code': cls.code,
                'Capacity': cls.capacity,
                'Total Sessions': len(sessions),
                'Total Marked': total_records,
                'Present': present_records,
                'Absent': total_records - present_records,
                'Avg Attendance %': round(avg_attendance, 2)
            })
        
        return jsonify({
            "success": True,
            "data": {
                "department": dept.name,
                "period": f"Last 30 days",
                "report": report_data
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error generating report: {e}"}), 500


# ==================== PHASE 5: STUDENT DASHBOARD ====================

@app.route('/api/student/dashboard', methods=['GET'])
@student_required
def student_dashboard():
    """Get student dashboard with overall attendance statistics."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": False, "message": "Student profile not found"}), 404
        
        student = user.student
        
        # Get all attendance records for this student
        all_records = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id
        ).all()
        
        if not all_records:
            return jsonify({
                "success": True,
                "data": {
                    "student_name": student.name,
                    "roll_no": student.roll_no,
                    "course_name": student.course_name,
                    "class_name": student.class_name,
                    "overall_percentage": 0,
                    "total_classes": 0,
                    "present": 0,
                    "absent": 0,
                    "late": 0,
                    "recent_records": []
                }
            })
        
        # Calculate overall statistics
        present = sum(1 for r in all_records if r.status == 'present')
        absent = sum(1 for r in all_records if r.status == 'absent')
        late = sum(1 for r in all_records if r.status == 'late')
        total = len(all_records)
        overall_percentage = (present / total) * 100 if total > 0 else 0
        
        # Get recent records (last 10)
        recent_records = sorted(all_records, key=lambda x: x.timestamp, reverse=True)[:10]
        recent_data = []
        for record in recent_records:
            session_obj = AttendanceSession.query.get(record.session_id)
            subject = Subject.query.get(session_obj.subject_id) if session_obj else None
            recent_data.append({
                "date": session_obj.date.isoformat() if session_obj else "N/A",
                "subject": subject.name if subject else "Unknown",
                "status": record.status,
                "time": record.timestamp.strftime('%H:%M:%S') if record.timestamp else "N/A"
            })
        
        return jsonify({
            "success": True,
            "data": {
                "student_name": student.name,
                "roll_no": student.roll_no,
                "course_name": student.course_name,
                "class_name": student.class_name,
                "overall_percentage": round(overall_percentage, 2),
                "total_classes": total,
                "present": present,
                "absent": absent,
                "late": late,
                "recent_records": recent_data
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching dashboard: {e}"}), 500


@app.route('/api/student/attendance/summary', methods=['GET'])
@student_required
def student_attendance_summary():
    """Get overall attendance summary for student."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": False, "message": "Student profile not found"}), 404
        
        student = user.student
        records = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id
        ).all()
        
        if not records:
            return jsonify({
                "success": True,
                "data": {
                    "total_classes": 0,
                    "present": 0,
                    "absent": 0,
                    "late": 0,
                    "percentage": 0,
                    "status": "No attendance records yet"
                }
            })
        
        present = sum(1 for r in records if r.status == 'present')
        absent = sum(1 for r in records if r.status == 'absent')
        late = sum(1 for r in records if r.status == 'late')
        total = len(records)
        percentage = (present / total) * 100 if total > 0 else 0
        
        # Determine status based on threshold (75%)
        if percentage >= 75:
            status = "Good"
        elif percentage >= 65:
            status = "At Risk"
        else:
            status = "Critical"
        
        return jsonify({
            "success": True,
            "data": {
                "total_classes": total,
                "present": present,
                "absent": absent,
                "late": late,
                "percentage": round(percentage, 2),
                "status": status
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {e}"}), 500


@app.route('/api/student/notifications', methods=['GET'])
@student_required
def student_notifications():
    """Get in-app notifications for logged-in student."""
    user_id = session.get('user_id')
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": True, "notifications": []})
        
        notifications = []
        student = user.student
        records = AttendanceRecord.query.filter_by(student_id=student.id).all()
        
        if records:
            present = sum(1 for r in records if r.status == 'present')
            total = len(records)
            pct = (present / total * 100) if total > 0 else 0
            if pct < 75:
                notifications.append({
                    "id": 1,
                    "title": "Low Attendance Warning",
                    "message": f"Your overall attendance is {pct:.1f}%, which is below the 75% threshold.",
                    "type": "warning",
                    "date": datetime.utcnow().strftime('%Y-%m-%d')
                })
        
        recent_records = sorted(records, key=lambda x: x.timestamp, reverse=True)[:5]
        for idx, rec in enumerate(recent_records, start=2):
            session_obj = AttendanceSession.query.get(rec.session_id)
            subject = Subject.query.get(session_obj.subject_id) if session_obj and session_obj.subject_id else None
            notifications.append({
                "id": idx,
                "title": f"Attendance Marked ({rec.status.capitalize()})",
                "message": f"Marked {rec.status} for {subject.name if subject else 'Session'} on {rec.timestamp.strftime('%Y-%m-%d %H:%M')}",
                "type": "info" if rec.status == 'present' else "danger",
                "date": rec.timestamp.strftime('%Y-%m-%d')
            })
            
        return jsonify({"success": True, "notifications": notifications})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/student/attendance/history', methods=['GET'])
@student_required
def student_attendance_history():
    """Get complete attendance history for student (paginated)."""
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    sort_by = request.args.get('sort', 'date_desc')  # date_desc, date_asc, status
    
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": False, "message": "Student profile not found"}), 404
        
        student = user.student
        query = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id
        )
        
        # Apply sorting
        if sort_by == 'date_asc':
            query = query.join(AttendanceSession).order_by(AttendanceSession.date.asc())
        elif sort_by == 'status':
            query = query.order_by(AttendanceRecord.status.asc())
        else:  # date_desc (default)
            query = query.join(AttendanceSession).order_by(AttendanceSession.date.desc())
        
        total_records = query.count()
        total_pages = (total_records + limit - 1) // limit
        
        records = query.offset((page - 1) * limit).limit(limit).all()
        
        history_data = []
        for record in records:
            session_obj = AttendanceSession.query.get(record.session_id)
            subject = Subject.query.get(session_obj.subject_id) if session_obj else None
            cls = Class.query.get(session_obj.class_id) if session_obj else None
            
            history_data.append({
                "record_id": record.id,
                "date": session_obj.date.isoformat() if session_obj else "N/A",
                "class": cls.name if cls else "Unknown",
                "subject": subject.name if subject else "Unknown",
                "status": record.status,
                "time": record.timestamp.strftime('%H:%M:%S') if record.timestamp else "N/A",
                "marked_by_teacher": record.marked_by_teacher or False,
                "notes": record.notes or ""
            })
        
        return jsonify({
            "success": True,
            "data": {
                "total_records": total_records,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "records": history_data
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching history: {e}"}), 500


@app.route('/api/student/attendance/by-subject', methods=['GET'])
@student_required
def student_attendance_by_subject():
    """Get subject-wise attendance breakdown."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": False, "message": "Student profile not found"}), 404
        
        student = user.student
        
        # Get all unique subjects the student has attended
        all_records = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id
        ).all()
        
        if not all_records:
            return jsonify({
                "success": True,
                "data": {
                    "subjects": [],
                    "message": "No attendance records found"
                }
            })
        
        # Group by subject
        subject_data = {}
        for record in all_records:
            session_obj = AttendanceSession.query.get(record.session_id)
            if not session_obj:
                continue
            
            subject = Subject.query.get(session_obj.subject_id)
            if not subject:
                continue
            
            if subject.id not in subject_data:
                subject_data[subject.id] = {
                    "subject_name": subject.name,
                    "subject_code": subject.code,
                    "present": 0,
                    "absent": 0,
                    "late": 0,
                    "total": 0
                }
            
            subject_data[subject.id]["total"] += 1
            if record.status == "present":
                subject_data[subject.id]["present"] += 1
            elif record.status == "absent":
                subject_data[subject.id]["absent"] += 1
            elif record.status == "late":
                subject_data[subject.id]["late"] += 1
        
        # Calculate percentages
        subjects_list = []
        for subject_id, data in subject_data.items():
            total = data["total"]
            percentage = ((data["present"] + data["late"]) / total * 100) if total > 0 else 0
            subjects_list.append({
                "subject_name": data["subject_name"],
                "subject_code": data["subject_code"],
                "present": data["present"],
                "late": data["late"],
                "absent": data["absent"],
                "total": total,
                "percentage": round(percentage, 2)
            })
        
        # Sort by percentage (highest first)
        subjects_list.sort(key=lambda x: x["percentage"], reverse=True)
        
        return jsonify({
            "success": True,
            "data": {
                "subjects": subjects_list,
                "total_subjects": len(subjects_list)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching subject breakdown: {e}"}), 500


@app.route('/api/student/low-attendance-warning', methods=['GET'])
@student_required
def student_low_attendance_warning():
    """Check if student has low attendance and return warning."""
    user_id = session.get('user_id')
    threshold = request.args.get('threshold', 75, type=int)
    
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": False, "message": "Student profile not found"}), 404
        
        student = user.student
        records = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id
        ).all()
        
        if not records:
            return jsonify({
                "success": True,
                "data": {
                    "has_warning": False,
                    "message": "No attendance records yet"
                }
            })
        
        present = sum(1 for r in records if r.status == 'present')
        total = len(records)
        percentage = (present / total) * 100 if total > 0 else 0
        
        has_warning = percentage < threshold
        
        warning_data = {
            "has_warning": has_warning,
            "current_percentage": round(percentage, 2),
            "threshold": threshold,
            "classes_needed": 0
        }
        
        if has_warning:
            # Calculate classes needed to reach threshold
            # percentage_needed = threshold
            # (present + x) / (total + x) = threshold / 100
            # 100 * (present + x) = threshold * (total + x)
            # 100 * present + 100 * x = threshold * total + threshold * x
            # 100 * x - threshold * x = threshold * total - 100 * present
            # x * (100 - threshold) = threshold * total - 100 * present
            # x = (threshold * total - 100 * present) / (100 - threshold)
            
            if threshold < 100:
                classes_needed = max(0, int((threshold * total - 100 * present) / (100 - threshold)) + 1)
                warning_data["classes_needed"] = classes_needed
                warning_data["message"] = f"Attendance below {threshold}%. Need {classes_needed} more classes to reach target."
            else:
                warning_data["message"] = "Invalid threshold"
        else:
            warning_data["message"] = "Attendance is good"
        
        return jsonify({
            "success": True,
            "data": warning_data
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error checking attendance warning: {e}"}), 500


@app.route('/api/student/reports/attendance', methods=['GET'])
@student_required
def student_attendance_report():
    """Generate attendance report for student (CSV/JSON)."""
    user_id = session.get('user_id')
    format_type = request.args.get('format', 'json')  # json, csv
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": False, "message": "Student profile not found"}), 404
        
        student = user.student
        
        # Build query
        query = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id
        )
        
        if start_date:
            from datetime import datetime as dt
            start = dt.strptime(start_date, '%Y-%m-%d').date()
            query = query.join(AttendanceSession).filter(AttendanceSession.date >= start)
        
        if end_date:
            from datetime import datetime as dt
            end = dt.strptime(end_date, '%Y-%m-%d').date()
            query = query.join(AttendanceSession).filter(AttendanceSession.date <= end)
        
        records = query.order_by(AttendanceRecord.timestamp.desc()).all()
        
        if not records:
            return jsonify({"success": False, "message": "No attendance records found"}), 404
        
        # Prepare report data
        report_rows = []
        for record in records:
            session_obj = AttendanceSession.query.get(record.session_id)
            subject = Subject.query.get(session_obj.subject_id) if session_obj else None
            cls = Class.query.get(session_obj.class_id) if session_obj else None
            
            report_rows.append({
                'Date': session_obj.date.isoformat() if session_obj else 'N/A',
                'Class': cls.name if cls else 'Unknown',
                'Subject': subject.name if subject else 'Unknown',
                'Status': record.status.capitalize(),
                'Time': record.timestamp.strftime('%H:%M:%S') if record.timestamp else 'N/A',
                'Notes': record.notes or ''
            })
        
        if format_type == 'csv':
            import io
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=['Date', 'Class', 'Subject', 'Status', 'Time', 'Notes'])
            writer.writeheader()
            writer.writerows(report_rows)
            
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f"attendance_report_{student.roll_no}.csv"
            )
        else:
            return jsonify({
                "success": True,
                "data": {
                    "student_name": student.name,
                    "roll_no": student.roll_no,
                    "report": report_rows
                }
            })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error generating report: {e}"}), 500


@app.route('/api/student/reports/semester-summary', methods=['GET'])
@student_required
def student_semester_summary():
    """Generate semester summary report for student."""
    user_id = session.get('user_id')
    
    try:
        user = User.query.get(user_id)
        if not user or not user.student:
            return jsonify({"success": False, "message": "Student profile not found"}), 404
        
        student = user.student
        records = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id
        ).all()
        
        if not records:
            return jsonify({
                "success": True,
                "data": {
                    "message": "No attendance records",
                    "summary": {}
                }
            })
        
        # Group by subject
        subject_summary = {}
        for record in records:
            session_obj = AttendanceSession.query.get(record.session_id)
            if not session_obj:
                continue
            
            subject = Subject.query.get(session_obj.subject_id)
            if not subject:
                continue
            
            if subject.id not in subject_summary:
                subject_summary[subject.id] = {
                    "subject_name": subject.name,
                    "subject_code": subject.code,
                    "present": 0,
                    "absent": 0,
                    "late": 0,
                    "total": 0
                }
            
            subject_summary[subject.id]["total"] += 1
            if record.status == "present":
                subject_summary[subject.id]["present"] += 1
            elif record.status == "absent":
                subject_summary[subject.id]["absent"] += 1
            elif record.status == "late":
                subject_summary[subject.id]["late"] += 1
        
        # Calculate summary statistics
        summary_list = []
        total_present = 0
        total_absent = 0
        total_late = 0
        total_classes = 0
        
        for subject_id, data in subject_summary.items():
            total = data["total"]
            percentage = ((data["present"] + data["late"]) / total * 100) if total > 0 else 0
            
            total_present += data["present"]
            total_absent += data["absent"]
            total_late += data["late"]
            total_classes += total
            
            summary_list.append({
                "subject_name": data["subject_name"],
                "subject_code": data["subject_code"],
                "present": data["present"],
                "late": data["late"],
                "absent": data["absent"],
                "total": total,
                "percentage": round(percentage, 2)
            })
        
        overall_percentage = ((total_present + total_late) / total_classes * 100) if total_classes > 0 else 0
        
        return jsonify({
            "success": True,
            "data": {
                "student_name": student.name,
                "roll_no": student.roll_no,
                "overall_summary": {
                    "total_classes": total_classes,
                    "present": total_present,
                    "late": total_late,
                    "absent": total_absent,
                    "overall_percentage": round(overall_percentage, 2)
                },
                "subject_wise_summary": summary_list
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Error generating semester summary: {e}"}), 500


# ============================================================================
# CENTRALIZED AI CHATBOT SERVICE ENDPOINTS (SHARED ACROSS ALL 4 PORTALS)
# Teacher -> /api/chat | Faculty -> /api/chat | Student -> /api/chat | Admin -> /api/chat
# ============================================================================

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """
    Centralized AttendAI Chatbot API endpoint.
    Shared across Teacher, Faculty, Student, and Admin portals.
    Role and identity are extracted exclusively from authenticated session/token.
    """
    user_info = get_authenticated_user()
    if not user_info:
        return jsonify({"success": False, "message": "Authentication required to access AI Assistant."}), 401

    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id', '').strip() or None

    if not message:
        return jsonify({"success": False, "message": "Message text cannot be empty."}), 400

    if len(message) > 4000:
        return jsonify({"success": False, "message": "Message exceeds maximum allowed length of 4000 characters."}), 400

    # Process message through centralized chatbot service
    result = chatbot_service.handle_message(
        user_info=user_info,
        message_text=message,
        conversation_id=conversation_id
    )

    # Log audit event for compliance
    try:
        user_id = user_info.get('user_id')
        role = user_info.get('role', 'unknown')
        log_audit_action(user_id, 'chatbot_query', details=f"Chatbot query by {role} in conv {result.get('conversation_id')}")
    except Exception as e:
        print(f"Chatbot audit log note: {e}")

    # Determine HTTP status based on result
    status_code = 200
    if not result.get('success'):
        error_type = result.get('error_type')
        if error_type == 'rate_limit':
            status_code = 429
        elif error_type in ('auth_error', 'not_configured'):
            status_code = 503
        else:
            status_code = 502

    return jsonify(result), status_code


@app.route('/api/chat/history', methods=['GET'])
@login_required
def api_chat_history():
    """Retrieve message history for a specific conversation session."""
    user_info = get_authenticated_user()
    if not user_info:
        return jsonify({"success": False, "message": "Authentication required."}), 401

    conversation_id = request.args.get('conversation_id', '').strip()
    if not conversation_id:
        return jsonify({"success": True, "messages": []})

    messages = chatbot_service.get_conversation_history(user_info.get('user_id'), conversation_id)
    return jsonify({"success": True, "conversation_id": conversation_id, "messages": messages})


@app.route('/api/chat/clear', methods=['POST'])
@login_required
def api_chat_clear():
    """Clear message history for the specified conversation."""
    user_info = get_authenticated_user()
    if not user_info:
        return jsonify({"success": False, "message": "Authentication required."}), 401

    data = request.get_json(silent=True) or {}
    conversation_id = data.get('conversation_id', '').strip()
    if not conversation_id:
        return jsonify({"success": False, "message": "conversation_id is required."}), 400

    success = chatbot_service.clear_conversation(user_info.get('user_id'), conversation_id)
    return jsonify({"success": success, "message": "Conversation history cleared."})


@app.route('/api/chat/new', methods=['POST'])
@login_required
def api_chat_new():
    """Start a new chat session by generating a fresh conversation identifier."""
    user_info = get_authenticated_user()
    if not user_info:
        return jsonify({"success": False, "message": "Authentication required."}), 401

    new_conv_id = uuid.uuid4().hex
    return jsonify({"success": True, "conversation_id": new_conv_id})


@app.route('/api/chat/config', methods=['GET'])
@login_required
def api_chat_config():
    """Return public metadata for the chatbot interface without exposing any keys."""
    user_info = get_authenticated_user()
    if not user_info:
        return jsonify({"success": False, "message": "Authentication required."}), 401

    role = (user_info.get('role') or 'student').lower().strip()
    return jsonify({
        "success": True,
        "role": role,
        "user_name": user_info.get('name', 'User'),
        "configured": chatbot_service.config.is_configured(),
        "provider": chatbot_service.config.provider,
        "model": chatbot_service.config.model,
        "rate_limit": chatbot_service.config.rate_limit,
    })


# Server initialization
with app.app_context():
    db.create_all()

repair_attendance_file()
train_model()

# CRITICAL: Camera must NOT auto-start on server startup.
# It starts strictly on explicit user action (e.g. clicking 'Start Feed').

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

