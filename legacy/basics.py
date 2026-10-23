"""
AttendAI - Classical Computer Vision Baseline (Haar Cascade Detection)

This script demonstrates the foundational Viola-Jones Haar Cascade face detection
technique (using haarcascade_frontalface_default.xml) compared to the deep learning
convolutional approach (YuNet ONNX) used in the primary AttendAI web application.

Used as an initial laboratory experiment for B.Sc. AIML project evaluation.
"""

from pathlib import Path
import cv2

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent
STUDENT_DIR = BASE_DIR / "Student Directory"
DATA_DIR = BASE_DIR / "data"

# Classical Haar Cascade Model File
CASCADE_FILE = DATA_DIR / "haarcascade_frontalface_default.xml"


def find_sample_student_image() -> Path | None:
    """Find a registered student face image from Student Directory for testing."""
    if STUDENT_DIR.exists():
        for img_path in STUDENT_DIR.rglob("face.jpg"):
            if img_path.is_file():
                return img_path
    return None


def main() -> int:
    """Run classical Haar Cascade face detection on a sample student face image."""
    print("=" * 60)
    print("AttendAI: Classical Haar Cascade Face Detection Baseline")
    print("=" * 60)

    # 1. Load Haar Cascade Classifier
    if CASCADE_FILE.exists():
        face_cascade = cv2.CascadeClassifier(str(CASCADE_FILE))
    else:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    if face_cascade.empty():
        print("[ERROR] Unable to load the OpenCV Haar cascade classifier.")
        return 1
    print("[OK] Loaded Haar cascade classifier successfully.")

    # 2. Locate a sample student image from registered students
    sample_image_path = find_sample_student_image()
    if not sample_image_path or not sample_image_path.exists():
        print("[INFO] No registered student faces found in Student Directory yet.")
        print("[INFO] Once a student is registered via AttendAI, their photo will be analyzed here.")
        return 0

    print(f"[INFO] Testing on registered student face: {sample_image_path.parent.name}")

    image = cv2.imread(str(sample_image_path))
    if image is None:
        print(f"[ERROR] Failed to read image at: {sample_image_path}")
        return 1

    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 3. Detect faces using multi-scale Haar features
    faces = face_cascade.detectMultiScale(
        gray_image,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30)
    )

    print(f"[RESULT] Haar Cascade detected {len(faces)} face(s).")
    for idx, (x, y, w, h) in enumerate(faces, start=1):
        print(f"  - Face {idx}: bounding box (x={x}, y={y}, w={w}, h={h})")
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

    print("\nNote: While Haar Cascades provide fast CPU-based detection, the main AttendAI")
    print("platform utilizes OpenCV YuNet (ONNX) for superior precision, angle invariance,")
    print("and 5-point facial landmark alignment coupled with SFace 128-D embeddings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
