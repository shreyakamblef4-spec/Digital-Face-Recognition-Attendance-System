# Third-Party Licenses, Models & Attribution

This document provides a comprehensive inventory of all third-party software dependencies, pre-trained machine learning models, and educational reference materials used in the **AttendAI — AI Face Recognition Attendance System**.

The application is engineered to operate **completely self-contained** on local infrastructure. It does not clone, open, download from, or rely upon external GitHub repositories or web APIs during runtime face detection, recognition, or attendance tracking.

---

## 1. Quick Reference Inventory

| Name | Role / Category | Version | License | Source / Official Documentation |
| :--- | :--- | :--- | :--- | :--- |
| **OpenCV** (`opencv-contrib-python`) | Python Dependency (Core Vision) | >= 4.10.0 | Apache 2.0 | [OpenCV Documentation](https://docs.opencv.org/4.x/) |
| **YuNet Face Detector** | Local Model File (`.onnx`) | 2023mar | Apache 2.0 | [OpenCV FaceDetectorYN](https://docs.opencv.org/4.x/d0/da7/classcv_1_1FaceDetectorYN.html) / [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) |
| **SFace Face Recognizer** | Local Model File (`.onnx`) | 2021dec | Apache 2.0 | [OpenCV FaceRecognizerSF](https://docs.opencv.org/4.x/da/d60/classcv_1_1FaceRecognizerSF.html) / [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) |
| **Flask** | Python Dependency (Web Framework) | >= 3.0.0 | BSD 3-Clause | [Flask Documentation](https://flask.palletsprojects.com/en/3.0.x/) |
| **SQLAlchemy** | Python Dependency (ORM) | >= 2.0.0 | MIT | [SQLAlchemy Documentation](https://www.sqlalchemy.org/docs/) |
| **Flask-SQLAlchemy** | Python Dependency (Flask Extension) | >= 3.0.0 | BSD 3-Clause | [Flask-SQLAlchemy Documentation](https://flask-sqlalchemy.palletsprojects.com/) |
| **NumPy** | Python Dependency (Math / Arrays) | >= 1.26.0 | BSD 3-Clause | [NumPy Documentation](https://numpy.org/doc/) |
| **Werkzeug** | Python Dependency (WSGI / Security) | >= 3.0.0 | BSD 3-Clause | [Werkzeug Documentation](https://werkzeug.palletsprojects.com/) |
| **Pandas** | Python Dependency (Data Analysis) | >= 2.2.0 | BSD 3-Clause | [Pandas Documentation](https://pandas.pydata.org/) |
| **OpenPyXL** | Python Dependency (Excel Engine) | >= 3.0.0 | MIT | [OpenPyXL Documentation](https://openpyxl.readthedocs.io/) |
| **ReportLab** | Python Dependency (PDF Generation) | >= 4.0.0 | BSD License | [ReportLab Documentation](https://www.reportlab.com/docs/) |
| **PyJWT** | Python Dependency (JWT Security) | >= 2.8.0 | MIT | [PyJWT Documentation](https://pyjwt.readthedocs.io/) |
| **python-dotenv** | Python Dependency (Environment) | >= 1.0.0 | BSD 3-Clause | [python-dotenv Documentation](https://saurabh-kumar.com/python-dotenv/) |
| **Flask-WTF** | Python Dependency (CSRF / Forms) | >= 1.0.0 | BSD 3-Clause | [Flask-WTF Documentation](https://flask-wtf.readthedocs.io/) |
| **HTTPX** | Python Dependency (HTTP Client) | >= 0.27.0 | BSD 3-Clause | [HTTPX Documentation](https://www.python-httpx.org/) |
| **Pytest** | Python Dependency (Test Suite) | >= 8.0.0 | MIT | [Pytest Documentation](https://docs.pytest.org/) |
| **Caffe SSD ResNet-10 Detector** | Local Model File (`.caffemodel` + `.prototxt`) | 140,000 iter | BSD 2-Clause / OpenCV | OpenCV DNN Samples Repository |
| **Haar Cascade Frontal Face** | Local Model File (`.xml`) | Default Cascade | BSD 3-Clause | OpenCV Cascades Library |
| **Facial Recognition System** | Documentation / Educational Reference | N/A | Academic Reference | [Wikipedia Background](https://en.wikipedia.org/wiki/Facial_recognition_system) |
| **MLA Style Manual** | Documentation / Formatting Reference | N/A | Academic Reference | [MLA Style Manual](https://en.wikipedia.org/wiki/MLA_Style_Manual) / [Cornell Guide](https://www.library.cornell.edu/sites/default/files/mla_style_revised.pdf) |

---

## 2. Machine Learning Models (Stored Locally in `data/`)

All neural network and statistical model files are bundled directly within the project's `data/` directory to guarantee deterministic offline execution without runtime downloads:

### 2.1 YuNet Face Detection Model
* **Model File**: `data/face_detection_yunet_2023mar.onnx` (232.5 KB)
* **Architecture**: YuNet (Lightweight Convolutional Face Detector optimized for mobile & edge devices)
* **Origin**: OpenCV Zoo (`opencv/opencv_zoo`)
* **API In Code**: `cv2.FaceDetectorYN_create(model_path, "", (320, 320))`
* **Purpose**: Performs high-speed multi-face detection in camera frames and returns bounding boxes `[x, y, w, h]`, 5-point facial landmarks (right eye, left eye, nose tip, right mouth corner, left mouth corner), and detection confidence scores.
* **License**: Apache License 2.0

### 2.2 SFace Face Recognition Model
* **Model File**: `data/face_recognition_sface_2021dec.onnx` (38.7 MB)
* **Architecture**: SFace (SphereFace / MobileFaceNet variant trained on facial recognition datasets)
* **Origin**: OpenCV Zoo (`opencv/opencv_zoo`)
* **API In Code**: `cv2.FaceRecognizerSF_create(model_path, "")`
* **Purpose**: Performs geometric face crop alignment via 5 facial landmarks (`recognizer.alignCrop(frame, face)`) and extracts 128-dimensional L2-normalized biometric feature vectors (`recognizer.feature(aligned_face)`). Matches enrolled student embeddings via cosine similarity (`np.dot(vec1, vec2)`).
* **License**: Apache License 2.0

### 2.3 Res10 Caffe SSD Face Detector & Configuration
* **Model Files**:
  * `data/res10_300x300_ssd_iter_140000.caffemodel` (10.6 MB)
  * `data/deploy.prototxt.txt` (28.1 KB)
* **Architecture**: ResNet-10 backbone with Single Shot Multibox Detector (SSD) head
* **Origin**: OpenCV DNN Face Detector Samples
* **API In Code**: `cv2.dnn.readNetFromCaffe(prototxt, caffemodel)`
* **Purpose**: Serves as a pre-trained deep learning fallback detector for facial enrollment and verification.
* **License**: BSD 2-Clause License / OpenCV License

### 2.4 OpenCV Haar Cascade Frontal Face Classifier
* **Model File**: `data/haarcascade_frontalface_default.xml` (930 KB)
* **Architecture**: Viola-Jones Haar Feature-based Cascade Classifier
* **Origin**: OpenCV Data Repository
* **API In Code**: `cv2.CascadeClassifier(path)`
* **Purpose**: Provides a lightweight classical vision detector used in exploratory test scripts and baseline comparisons.
* **License**: BSD 3-Clause License

---

## 3. Python Package Dependencies

The following packages are installed via `pip install -r requirements.txt` and executed in the local Python runtime:

### 3.1 OpenCV (`opencv-contrib-python`)
* **Version**: `>= 4.10.0`
* **Role**: Primary computer vision library. Handles hardware camera capture (`cv2.VideoCapture` with `cv2.CAP_DSHOW`), image color conversions, video streaming JPEG compression (`cv2.imencode`), deep learning model inference (`FaceDetectorYN`, `FaceRecognizerSF`, `dnn`), and bounding box rendering.
* **License**: Apache License 2.0

### 3.2 Flask (`flask`)
* **Version**: `>= 3.0.0`
* **Role**: Core WSGI web framework. Powers HTTP request routing, template rendering (Jinja2), multipart streaming (`multipart/x-mixed-replace` for MJPEG camera feed), JSON API responses, and user session handling.
* **License**: BSD 3-Clause License

### 3.3 SQLAlchemy (`sqlalchemy`) & Flask-SQLAlchemy (`flask-sqlalchemy`)
* **Version**: `sqlalchemy>=2.0.0`, `flask-sqlalchemy>=3.0.0`
* **Role**: Object-Relational Mapping (ORM) and database connection pooling. Manages the academic catalog (`Department`, `Course`, `Class`, `Subject`), identity models (`User`, `Teacher`, `Student`), biometric storage (`FaceEmbedding`), and attendance tracking (`AttendanceSession`, `AttendanceRecord`, `AuditLog`).
* **License**: MIT License (SQLAlchemy) / BSD 3-Clause License (Flask-SQLAlchemy)

### 3.4 NumPy (`numpy`)
* **Version**: `>= 1.26.0`
* **Role**: High-performance multi-dimensional array operations. Computes L2 norms, dot products for cosine similarity matching, and raw pixel manipulation for placeholder and video frames.
* **License**: BSD 3-Clause License

### 3.5 Werkzeug (`werkzeug`)
* **Version**: `>= 3.0.0`
* **Role**: Cryptographic password hashing (`generate_password_hash`, `check_password_hash` with PBKDF2:SHA256) and sanitization (`secure_filename`).
* **License**: BSD 3-Clause License

### 3.6 Pandas (`pandas`) & OpenPyXL (`openpyxl`)
* **Version**: `pandas>=2.2.0`, `openpyxl>=3.0.0`
* **Role**: Dataframe structuring and tabular export generation for `.xlsx` and `.csv` administrative attendance reports.
* **License**: BSD 3-Clause License (Pandas) / MIT License (OpenPyXL)

### 3.7 ReportLab (`reportlab`)
* **Version**: `>= 4.0.0`
* **Role**: Programmatic PDF canvas rendering for downloadable student and faculty attendance summaries.
* **License**: BSD License

### 3.8 PyJWT (`pyjwt`)
* **Version**: `>= 2.8.0`
* **Role**: Encodes and verifies signed JSON Web Tokens for stateless API authentication.
* **License**: MIT License

### 3.9 python-dotenv (`python-dotenv`)
* **Version**: `>= 1.0.0`
* **Role**: Loads local `.env` environment variables into `os.environ` on application launch.
* **License**: BSD 3-Clause License

### 3.10 Flask-WTF (`flask-wtf`)
* **Version**: `>= 1.0.0`
* **Role**: Provides Cross-Site Request Forgery (CSRF) token generation and validation.
* **License**: BSD 3-Clause License

### 3.11 HTTPX (`httpx`)
* **Version**: `>= 0.27.0`
* **Role**: HTTP client for optional external AI chatbot assistance (e.g., Google Gemini, OpenAI, or local Ollama endpoints).
* **License**: BSD 3-Clause License

### 3.12 Pytest (`pytest`)
* **Version**: `>= 8.0.0`
* **Role**: Automated end-to-end and unit testing framework.
* **License**: MIT License

---

## 4. Academic & Theoretical References (Non-Runtime)

The following references provide background context, biometric conceptual theory, and documentation standards for this academic project. They are **not** software packages or runtime dependencies:

1. **Facial Recognition System Overview**:
   * *Description*: Encyclopedic background on facial recognition history, landmark detection algorithms, embedding vector spaces, and biometric verification principles.
   * *Reference*: [Wikipedia — Facial Recognition System](https://en.wikipedia.org/wiki/Facial_recognition_system)
2. **Modern Language Association (MLA) Style Manual**:
   * *Description*: Standardized academic reference format used for citing technical publications, datasets, and algorithms in college project reports.
   * *References*: [MLA Style Manual](https://en.wikipedia.org/wiki/MLA_Style_Manual) and [Cornell University Library Citation Guide](https://www.library.cornell.edu/sites/default/files/mla_style_revised.pdf)

---

## 5. Summary of Applicable Open Source Licenses

### Apache License, Version 2.0 (OpenCV, YuNet, SFace)
Licensed under the Apache License, Version 2.0 (the "License"); you may not use these files except in compliance with the License. You may obtain a copy of the License at:
http://www.apache.org/licenses/LICENSE-2.0

### BSD 3-Clause License (Flask, NumPy, Werkzeug, Pandas, python-dotenv, Flask-WTF, HTTPX)
Redistribution and use in source and binary forms, with or without modification, are permitted provided that the copyright notice and this list of conditions and disclaimer are retained.

### MIT License (SQLAlchemy, PyJWT, OpenPyXL, Pytest, AttendAI)
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software.

---

## 6. Self-Containment Confirmation

* **No Git Runtime Operations**: The application does not invoke `git clone`, `git pull`, or shell commands targeting external repositories.
* **Local Model Storage**: All pre-trained weights (`face_detection_yunet_2023mar.onnx`, `face_recognition_sface_2021dec.onnx`, and Caffe fallback models) are read directly from `data/`.
* **Zero External Code Imports**: No foreign repositories are copied into the codebase. All business logic, routing, UI, and database schemas are native to this project.
* **Independent Execution**: Once Python dependencies are installed via `pip install -r requirements.txt`, the application runs completely offline on `http://localhost:5000`.
