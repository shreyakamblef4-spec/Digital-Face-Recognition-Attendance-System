"""
Student Directory Storage Manager for AttendAI.
Organizes registered student face data hierarchically by Course and Class:
    Student Directory/
        <Course>/
            <Class>/
                Roll_<RollNumber>_<StudentName>/
                    face.jpg
                    face_encoding.dat

Ensures filesystem safety, sanitized directory names, duplicate protection,
and seamless integration with SQLite database records.
"""

import os
import re
import json
import shutil
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import numpy as np
import cv2

logger = logging.getLogger("attendai.student_storage")

BASE_DIR = Path(__file__).resolve().parent
STUDENT_DIRECTORY_ROOT = BASE_DIR / "Student Directory"


def sanitize_folder_name(name: str) -> str:
    """
    Generate a clean, filesystem-safe folder name from a Course, Class, or Student name.
    Preserves semantic meaning while removing illegal characters across Windows and POSIX.
    
    Examples:
        'B.Sc Artificial Intelligence & Machine Learning' -> 'BSc_Artificial_Intelligence_and_Machine_Learning'
        'B.Sc 2nd Year' -> 'BSc_2nd_Year'
        'CS-01 / Section A' -> 'CS_01_Section_A'
    """
    if not name:
        return "Unknown"

    s = name.strip()
    # Replace '&' with 'and'
    s = re.sub(r'\s*&\s*', '_and_', s)
    # Remove dots from abbreviations (e.g. B.Sc -> BSc)
    s = re.sub(r'([A-Za-z])\.([A-Za-z])', r'\1\2', s)
    s = s.replace('.', '')
    # Replace all non-alphanumeric characters with underscores
    s = re.sub(r'[^A-Za-z0-9]+', '_', s)
    # Collapse multiple consecutive underscores
    s = re.sub(r'_+', '_', s)
    # Strip leading/trailing underscores
    s = s.strip('_')
    return s or "General"


def get_student_folder_name(roll_no: str, student_name: str) -> str:
    """
    Generate unique student folder identifier using Roll Number and Name.
    Format: Roll_<Sanitized_Roll>_<Sanitized_Name>
    """
    safe_roll = sanitize_folder_name(roll_no)
    safe_name = sanitize_folder_name(student_name)
    return f"Roll_{safe_roll}_{safe_name}"


def get_student_dir_path(
    course_name: str,
    class_name: str,
    roll_no: str,
    student_name: str,
    create: bool = False
) -> Path:
    """
    Compute the absolute directory path for a student's face data.
    
    Structure:
        Student Directory / <Course> / <Class> / Roll_<RollNo>_<Name>
    """
    safe_course = sanitize_folder_name(course_name)
    safe_class = sanitize_folder_name(class_name)
    safe_student = get_student_folder_name(roll_no, student_name)

    folder_path = STUDENT_DIRECTORY_ROOT / safe_course / safe_class / safe_student
    if create:
        folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path


def save_student_face_data(
    course_name: str,
    class_name: str,
    roll_no: str,
    student_name: str,
    img: np.ndarray,
    embedding: Optional[np.ndarray] = None
) -> Tuple[str, str, Path]:
    """
    Save the student's face photo and facial encoding in their designated Course/Class folder.
    
    Files created:
        - face.jpg: High-quality JPEG face image
        - face_encoding.dat: JSON or binary serialized facial embedding vector
        
    Returns:
        Tuple of:
            - rel_image_path (relative to project root, forward-slash normalized)
            - rel_encoding_path (relative to project root, forward-slash normalized)
            - student_dir (absolute Path)
    """
    student_dir = get_student_dir_path(course_name, class_name, roll_no, student_name, create=True)

    # 1. Save image
    image_path = student_dir / "face.jpg"
    success = cv2.imwrite(str(image_path), img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not success:
        raise IOError(f"Failed to write face photo to {image_path}")

    # 2. Save face encoding if provided
    encoding_path = student_dir / "face_encoding.dat"
    if embedding is not None:
        emb_list = embedding.tolist() if isinstance(embedding, np.ndarray) else list(embedding)
        with encoding_path.open("w", encoding="utf-8") as f:
            json.dump({
                "roll_no": roll_no,
                "name": student_name,
                "course": course_name,
                "class": class_name,
                "dim": len(emb_list),
                "embedding": emb_list
            }, f, indent=2)

    # Compute paths relative to project root with forward slashes
    rel_image_path = str(image_path.relative_to(BASE_DIR)).replace("\\", "/")
    rel_encoding_path = str(encoding_path.relative_to(BASE_DIR)).replace("\\", "/")

    logger.info("Saved face data for %s (%s) at %s", student_name, roll_no, rel_image_path)
    return rel_image_path, rel_encoding_path, student_dir


def load_student_encoding_file(encoding_path: Path) -> Optional[np.ndarray]:
    """Load a saved face_encoding.dat file into a normalized numpy float32 vector."""
    try:
        if not encoding_path.exists():
            return None
        with encoding_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            raw = data.get("embedding", [])
            vec = np.array(raw, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 1e-8:
                vec = vec / norm
            return vec
    except Exception as e:
        logger.error("Error reading encoding file %s: %s", encoding_path, e)
        return None


def delete_student_folder(student_dir: Path) -> bool:
    """Safely delete a student's face data folder and prune empty parent folders."""
    try:
        if student_dir and student_dir.exists() and student_dir.is_dir():
            shutil.rmtree(student_dir)
            logger.info("Removed student directory: %s", student_dir)

            # Prune empty class folder
            class_dir = student_dir.parent
            if class_dir.exists() and not any(class_dir.iterdir()):
                class_dir.rmdir()
                # Prune empty course folder
                course_dir = class_dir.parent
                if course_dir.exists() and not any(course_dir.iterdir()):
                    course_dir.rmdir()
            return True
    except Exception as e:
        logger.error("Error deleting student directory %s: %s", student_dir, e)
    return False


def resolve_photo_path(stored_path: Optional[str]) -> Optional[Path]:
    """
    Resolve a stored face_image_path from the database to an existing absolute file on disk.
    Supports both new hierarchical paths ('Student Directory/...') and legacy filenames ('101_Student.jpg').
    """
    if not stored_path:
        return None

    # Check direct relative to project root
    p1 = BASE_DIR / stored_path
    if p1.exists() and p1.is_file():
        return p1

    # Check under Student Directory
    p2 = STUDENT_DIRECTORY_ROOT / stored_path
    if p2.exists() and p2.is_file():
        return p2

    # Check legacy ImagesAttendance
    legacy_dir = BASE_DIR / "ImagesAttendance"
    p3 = legacy_dir / Path(stored_path).name
    if p3.exists() and p3.is_file():
        return p3

    # Recursive search under Student Directory by filename or roll number
    if STUDENT_DIRECTORY_ROOT.exists():
        filename = Path(stored_path).name
        for match in STUDENT_DIRECTORY_ROOT.glob(f"**/{filename}"):
            if match.is_file():
                return match

        # Also search folder by roll number or student name if stored_path is a roll/name string
        stem = Path(stored_path).stem
        parts = stem.split("_")
        if parts:
            roll_part = parts[0]
            if roll_part:
                for match in STUDENT_DIRECTORY_ROOT.glob(f"**/Roll_{roll_part}_*/face.jpg"):
                    if match.is_file():
                        return match
            if len(parts) > 1:
                name_part = "_".join(parts[1:])
                if name_part:
                    for match in STUDENT_DIRECTORY_ROOT.glob(f"**/Roll_*_{name_part}/face.jpg"):
                        if match.is_file():
                            return match

    return None
