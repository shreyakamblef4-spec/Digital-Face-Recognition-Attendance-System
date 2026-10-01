import urllib.request
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "ImagesAttendance"
ATTENDANCE_FILE = BASE_DIR / "Attendance.csv"
FACE_DETECTOR_MODEL = BASE_DIR / "data" / "face_detection_yunet_2023mar.onnx"
FACE_RECOGNIZER_MODEL = BASE_DIR / "data" / "face_recognition_sface_2021dec.onnx"
WINDOW_NAME = "Webcam"
COOLDOWN_SECONDS = 5
RECOGNITION_THRESHOLD = 0.5


def get_face_detector():
    if FACE_DETECTOR_MODEL.exists():
        detector = cv2.FaceDetectorYN_create(str(FACE_DETECTOR_MODEL), "", (320, 320))
        if detector is not None:
            return detector

    FACE_DETECTOR_MODEL.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(
            "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
            FACE_DETECTOR_MODEL,
        )
    except Exception as exc:
        raise RuntimeError(f"Unable to download the face detector model: {exc}") from exc

    detector = cv2.FaceDetectorYN_create(str(FACE_DETECTOR_MODEL), "", (320, 320))
    if detector is None:
        raise RuntimeError("The downloaded face detector model could not be loaded")

    return detector


def detect_faces(image):
    detector = get_face_detector()
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


def get_face_recognizer():
    if FACE_RECOGNIZER_MODEL.exists():
        recognizer = cv2.FaceRecognizerSF_create(str(FACE_RECOGNIZER_MODEL), "")
        if recognizer is not None:
            return recognizer

    FACE_RECOGNIZER_MODEL.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(
            "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
            FACE_RECOGNIZER_MODEL,
        )
    except Exception as exc:
        raise RuntimeError(f"Unable to download the face recognizer model: {exc}") from exc

    recognizer = cv2.FaceRecognizerSF_create(str(FACE_RECOGNIZER_MODEL), "")
    if recognizer is None:
        raise RuntimeError("The downloaded face recognizer model could not be loaded")

    return recognizer


def load_known_faces(image_dir: Path):
    names = []
    face_samples = []

    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory does not exist: {image_dir}")

    image_files = sorted(image_dir.iterdir())
    if not image_files:
        raise FileNotFoundError(f"No images found in {image_dir}")

    recognizer = get_face_recognizer()

    for image_path in image_files:
        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}:
            continue

        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Skipping unreadable image: {image_path.name}")
            continue

        faces = detect_faces(image)
        if len(faces) == 0:
            print(f"No face detected in {image_path.name}; skipping")
            continue

        x1, y1, x2, y2 = faces[0]
        face_roi = image[y1:y2, x1:x2]
        if face_roi.size == 0:
            print(f"Invalid detected face in {image_path.name}; skipping")
            continue

        face_roi = cv2.resize(face_roi, (112, 112))
        names.append(image_path.stem.upper())
        face_samples.append(face_roi)

    if not face_samples:
        print(f"No recognizable faces were found in {image_dir}; continuing with an empty recognizer")
        return names, recognizer

    return names, recognizer, face_samples


def mark_attendance(name: str, attendance_file: Path) -> bool:
    attendance_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H:%M:%S")

    if not attendance_file.exists() or attendance_file.stat().st_size == 0:
        with attendance_file.open("a", encoding="utf-8") as handle:
            handle.write("Name,Date,Time,Status\n")

    with attendance_file.open("r", encoding="utf-8") as handle:
        existing_rows = handle.readlines()

    for row in existing_rows:
        fields = [field.strip() for field in row.strip().split(",")]
        if len(fields) >= 2 and fields[0].lower() == name.lower() and fields[1] == today:
            return False

    with attendance_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{name},{today},{timestamp},Present\n")

    return True


def main() -> int:
    try:
        class_names, recognizer, face_samples = load_known_faces(IMAGE_DIR)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Unable to start attendance system: {exc}")
        return 1

    print("Encoding complete")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Unable to access the webcam. Please connect a camera and try again.")
        return 1

    last_marked = {}

    try:
        while True:
            success, img = cap.read()
            if not success:
                print("Failed to read from the webcam.")
                break

            gray_frame = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = detect_faces(img)

            for (x1, y1, x2, y2) in faces:
                face_roi = img[y1:y2, x1:x2]
                if face_roi.size == 0:
                    continue
                face_roi = cv2.resize(face_roi, (112, 112))
                face_embedding = recognizer.feature(face_roi)

                if class_names and face_samples:
                    known_embeddings = [recognizer.feature(sample) for sample in face_samples]
                    similarities = [np.linalg.norm(embedding - face_embedding) for embedding in known_embeddings]
                    best_index = int(np.argmin(similarities)) if similarities else -1
                    if best_index >= 0 and similarities[best_index] < RECOGNITION_THRESHOLD:
                        name = class_names[best_index]
                        now = datetime.now()
                        if last_marked.get(name) is None or (now - last_marked[name]).total_seconds() >= COOLDOWN_SECONDS:
                            if mark_attendance(name, ATTENDANCE_FILE):
                                print(f"Attendance marked for {name}")
                            last_marked[name] = now
                    else:
                        name = "Unknown"
                else:
                    name = "Unknown"

                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(img, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            cv2.imshow(WINDOW_NAME, img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
