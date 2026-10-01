# AttendAI — AI Face Recognition Attendance System

A modern, production-grade AI Face Recognition Attendance System built with Python, Flask, OpenCV (YuNet + SFace), SQLAlchemy, and a glassmorphic Web UI.

The system performs real-time face detection, facial landmark alignment, neural embedding feature extraction, and cosine similarity matching to automatically track student attendance by **Roll Number**, **Name**, **Course**, and **Class**.

---

## 🌟 Key Features

* **Student Roll Number Integration**:
  - Roll number is a first-class required attribute on student profiles.
  - Displayed on live webcam bounding boxes, live session logs, historical records, and export files.
  - Never uses randomly generated roll numbers.

* **Academic Hierarchy & Scoped Recognition**:
  - Structured hierarchy: `Course -> Class / Year -> Student`.
  - Real-time teacher session filtering: scope face recognition to a specific course or class.
  - Pre-seeded academic catalog: AI & ML, Computer Science, Data Science courses with 1st, 2nd, and 3rd year classes.

* **Robust AI Face Recognition**:
  - **YuNet Face Detector** ONNX model (`data/face_detection_yunet_2023mar.onnx`) for high-speed multi-face detection.
  - **SFace Recognizer** ONNX model (`data/face_recognition_sface_2021dec.onnx`) using 5-point facial landmark crop alignment (`alignCrop`) and 128-dimensional L2-normalized embeddings.
  - Strict classification rules: Unknown faces display "Unknown Student" with a red bounding box and are **never** marked present or assigned a roll number.

* **Optimized Camera Engine**:
  - Windows DirectShow (`cv2.CAP_DSHOW`) hardware integration with fallback scanning.
  - Dynamic standby placeholder frames during camera pauses to prevent broken browser image streams.
  - In-memory `latest_frame` caching with safe concurrency locks.
  - Seamless snapshot capture (`/api/camera/snapshot`) for student registration photo capture without device collision.

* **Comprehensive 8-Column Attendance Table & Export**:
  - Columns: `Student Roll Number`, `Student Name`, `Class`, `Course`, `Date`, `Time`, `Attendance Status`, `Face Recognition Status`.
  - Synchronized across SQLite database (`AttendanceRecord`) and `Attendance.csv`.
  - CSV export with complete 8-column headers.

* **Role-Based Access Control (RBAC)**:
  - Multi-tier roles: `Admin`, `Faculty`, `Teacher`, and `Student`.
  - Secure session management, password hashing, and audit logging.

---

## 📁 Project Directory Structure

```text
Face-Recognition-and-Attendance-Project-main/
│
├── app.py                      # Application launcher (python app.py)
├── web_app.py                  # Main Flask backend, streaming & APIs
├── models.py                   # SQLAlchemy database models
├── database.py                 # DB initialization, session & schema migrations
├── init_db.py                  # Seed database with courses, classes & users
├── auth.py                     # Authentication & RBAC decorators
├── config.py                   # App configuration & environment settings
├── requirements.txt            # Python dependencies
├── attendance_system.db        # SQLite database
├── Attendance.csv              # 8-column attendance record file
│
├── data/                       # Pre-trained deep learning models
│   ├── face_detection_yunet_2023mar.onnx
│   ├── face_recognition_sface_2021dec.onnx
│   ├── deploy.prototxt.txt
│   ├── haarcascade_frontalface_default.xml
│   └── res10_300x300_ssd_iter_140000.caffemodel
│
├── ImagesAttendance/           # Stored registered student face photos
│
├── templates/                  # Frontend HTML templates
│   ├── index.html              # Teacher & attendance dashboard
│   ├── login.html              # Authentication page
│   ├── faculty.html            # Faculty department dashboard
│   ├── admin.html              # Admin management portal
│   └── student.html            # Student self-service portal
│
├── static/                     # Frontend static assets
│   ├── css/
│   │   └── style.css           # Modern glassmorphic theme & layout
│   └── js/
│       ├── app.js              # Live stream, cascading filters & registration
│       └── faculty.js          # Faculty dashboard analytics
│
├── tests/                      # Automated test suite
│   ├── conftest.py             # Test configuration & path setup
│   ├── test_e2e_requirements.py # End-to-end verification of all requirements
│   ├── test_rbac_matrix.py     # 30-test RBAC authorization matrix
│   ├── test_phase1.py          # Database and user integration tests
│   ├── test_phase2.py          # Session and teacher routes tests
│   ├── test_phase3.py          # Model inference tests
│   ├── test_phase4.py          # Full API workflow tests
│   └── test_phase5.py          # Final integration test suite
│
├── legacy/                     # Original starter scripts (for reference)
│   ├── basics.py
│   └── attendanceProject.py
│
└── docs/                       # Project documentation & reports
    ├── reports/                # Project phase reports & status
    └── index.html              # Showcase website
```

---

## 🚀 Quick Start

### 1. Prerequisites & Environment Setup

Ensure Python 3.10+ is installed on your system.

```bash
# Clone the repository
git clone https://github.com/Riddhi0124/Face-Recognition-and-Attendance-Project.git
cd Face-Recognition-and-Attendance-Project-main

# Create and activate virtual environment (optional)
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python app.py
```

The application will start on `http://localhost:5000` (and `http://0.0.0.0:5000`).

Open your browser and navigate to:
```
http://localhost:5000
```

### 3. Default Login Credentials

* **Teacher**: `teacher@attendai.edu` / `Teacher@123`
* **Admin**: `admin@attendai.edu` / `Admin@123`
* **Faculty**: `faculty@attendai.edu` / `Faculty@123`

---

## 🧪 Running Automated Tests

Run the complete end-to-end requirements test suite:

```bash
python tests/test_e2e_requirements.py
```

Run the RBAC security verification:

```bash
python tests/test_rbac_matrix.py
```

Run all unit tests:

```bash
python -m unittest discover tests
```

---

## 📊 Attendance Table & CSV Format

Both the web UI dashboard and `Attendance.csv` use the unified 8-column layout:

| Student Roll Number | Student Name | Class | Course | Date | Time | Attendance Status | Face Recognition Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 101 | Riddhi Verma | B.Sc 2nd Year | Artificial Intelligence & Machine Learning | 2026-09-20 | 10:15:30 | Present | Recognized (99%) |

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
