from pathlib import Path

import cv2

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "ImagesAttendance"
REFERENCE_IMAGE = IMAGE_DIR / "Riddhi.jpg"
TEST_IMAGE = IMAGE_DIR / "neha.jpg"


def main() -> int:
    if not REFERENCE_IMAGE.exists() or not TEST_IMAGE.exists():
        print("Required sample images were not found in the ImagesAttendance directory.")
        return 1

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if face_cascade.empty():
        print("Unable to load the OpenCV face detector.")
        return 1

    reference_image = cv2.imread(str(REFERENCE_IMAGE))
    test_image = cv2.imread(str(TEST_IMAGE))
    if reference_image is None or test_image is None:
        print("Unable to read one or more sample images.")
        return 1

    reference_gray = cv2.cvtColor(reference_image, cv2.COLOR_BGR2GRAY)
    test_gray = cv2.cvtColor(test_image, cv2.COLOR_BGR2GRAY)

    reference_faces = face_cascade.detectMultiScale(reference_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    test_faces = face_cascade.detectMultiScale(test_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(reference_faces) == 0 or len(test_faces) == 0:
        print("No face detected in one of the sample images.")
        return 1

    x, y, w, h = reference_faces[0]
    cv2.rectangle(reference_image, (x, y), (x + w, y + h), (255, 0, 255), 2)
    x, y, w, h = test_faces[0]
    cv2.rectangle(test_image, (x, y), (x + w, y + h), (255, 0, 255), 2)

    cv2.imshow("Reference Face", reference_image)
    cv2.imshow("Test Face", test_image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
