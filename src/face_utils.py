from __future__ import annotations

import sys
from math import hypot
from pathlib import Path
from statistics import mean

import cv2
import numpy as np

from image_utils import compute_brightness, compute_sharpness, crop_image
from runtime_env import prepare_runtime_environment

prepare_runtime_environment()

import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core import base_options


RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)
MOUTH = (61, 291, 13, 14)

def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


class MediaPipeFaceAnalyzer:
    def __init__(self, min_face_confidence: float = 0.5, max_faces: int = 4) -> None:
        if getattr(sys, "frozen", False):
            models_base = Path(sys._MEIPASS)
        else:
            models_base = Path(__file__).resolve().parents[1]
        detector_model = models_base / "models" / "face_detector.tflite"
        landmarker_model = models_base / "models" / "face_landmarker.task"

        if not detector_model.exists():
            raise FileNotFoundError(f"Не найдена модель детектора лиц: {detector_model}")
        if not landmarker_model.exists():
            raise FileNotFoundError(f"Не найдена модель face landmarker: {landmarker_model}")

        detector_options = vision.FaceDetectorOptions(
            base_options=base_options.BaseOptions(model_asset_path=str(detector_model)),
            min_detection_confidence=min_face_confidence,
        )
        landmarker_options = vision.FaceLandmarkerOptions(
            base_options=base_options.BaseOptions(model_asset_path=str(landmarker_model)),
            num_faces=1,
            min_face_detection_confidence=min_face_confidence,
            min_face_presence_confidence=0.3,
            min_tracking_confidence=0.3,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=False,
        )

        self.max_faces = max_faces
        self.face_detector = vision.FaceDetector.create_from_options(detector_options)
        self.face_landmarker = vision.FaceLandmarker.create_from_options(landmarker_options)
        self.upper_body_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_upperbody.xml"
        )

    def close(self) -> None:
        self.face_detector.close()
        self.face_landmarker.close()

    def detect_person(
        self,
        image_bgr: np.ndarray,
        min_confidence: float = 0.5,
        haar_config: dict | None = None,
    ) -> bool:
        """Haar upper-body detection as fallback when face is not found.

        Works well for seated people on a chairlift where HOG (full-body
        pedestrian detector) fails.  ``min_confidence`` is kept in the
        signature for config compatibility but the cascade uses
        ``minNeighbors`` internally.

        Parameters from ``haar_config`` (or defaults):
        - scale_factor: 1.05 — how much the image size is reduced at each scale.
        - min_neighbors: 3 — how many neighbors each candidate rectangle should have.
        - min_size: 60 — minimum object size in pixels.
        """
        height, width = image_bgr.shape[:2]
        if width == 0 or height == 0:
            return False

        hc = haar_config or {}
        scale_factor = hc.get("scale_factor", 1.05)
        min_neighbors = hc.get("min_neighbors", 3)
        min_size = hc.get("min_size", 60)

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

        detections = self.upper_body_cascade.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=(min_size, min_size),
        )
        return len(detections) > 0

    def analyze_faces(self, image_bgr: np.ndarray) -> list[dict]:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detection_result = self.face_detector.detect(mp_image)

        faces: list[dict] = []
        for detection in list(detection_result.detections or [])[: self.max_faces]:
            faces.append(self._analyze_detection(image_bgr, detection))

        return faces

    def _analyze_detection(self, image_bgr: np.ndarray, detection) -> dict:
        height, width = image_bgr.shape[:2]
        bbox = detection.bounding_box

        x1 = max(int(bbox.origin_x), 0)
        y1 = max(int(bbox.origin_y), 0)
        x2 = min(int(bbox.origin_x + bbox.width), width)
        y2 = min(int(bbox.origin_y + bbox.height), height)
        confidence = float(detection.categories[0].score) if detection.categories else 0.0

        padded_crop = crop_image(image_bgr, (x1, y1, x2, y2), padding_ratio=0.18)
        landmarker_face = self._analyze_face_crop(image_bgr, padded_crop, (x1, y1, x2, y2))
        if landmarker_face is None:
            face_crop = crop_image(image_bgr, (x1, y1, x2, y2), padding_ratio=0.08)
            return {
                "confidence": confidence,
                "bbox": (x1, y1, x2, y2),
                "yaw": 180.0,
                "pitch": 180.0,
                "roll": 180.0,
                "ear": 0.0,
                "mouth_ratio": 0.0,
                "sharpness": compute_sharpness(face_crop) if face_crop.size else 0.0,
                "brightness": compute_brightness(face_crop) if face_crop.size else 0.0,
            }

        landmarker_face["confidence"] = confidence
        if intersection_over_union((x1, y1, x2, y2), landmarker_face["bbox"]) < 0.05:
            landmarker_face["bbox"] = (x1, y1, x2, y2)
        return landmarker_face

    def _analyze_face_crop(
        self,
        full_image_bgr: np.ndarray,
        crop_bgr: np.ndarray,
        original_bbox: tuple[int, int, int, int],
    ) -> dict | None:
        if crop_bgr.size == 0:
            return None

        crop_height, crop_width = crop_bgr.shape[:2]
        original_x1, original_y1, original_x2, original_y2 = original_bbox
        offset_x = max(original_x1 - int((original_x2 - original_x1) * 0.18), 0)
        offset_y = max(original_y1 - int((original_y2 - original_y1) * 0.18), 0)

        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        crop_image_mp = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_rgb)
        result = self.face_landmarker.detect(crop_image_mp)
        if not result.face_landmarks:
            return None

        landmarks = result.face_landmarks[0]
        blendshape_scores = extract_blendshape_scores(result)
        global_points = [global_landmark_point(point, crop_width, crop_height, offset_x, offset_y) for point in landmarks]
        xs = [point[0] for point in global_points]
        ys = [point[1] for point in global_points]

        bbox = (
            max(int(min(xs)), 0),
            max(int(min(ys)), 0),
            min(int(max(xs)), full_image_bgr.shape[1]),
            min(int(max(ys)), full_image_bgr.shape[0]),
        )

        face_crop = crop_image(full_image_bgr, bbox, padding_ratio=0.05)
        yaw, pitch, roll = estimate_head_pose(global_points, full_image_bgr.shape[1], full_image_bgr.shape[0])
        ear = mean(
            [
                compute_eye_aspect_ratio(global_points, RIGHT_EYE),
                compute_eye_aspect_ratio(global_points, LEFT_EYE),
            ]
        )

        return {
            "confidence": 0.5,
            "bbox": bbox,
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
            "ear": ear,
            "mouth_ratio": compute_mouth_ratio(global_points),
            "sharpness": compute_sharpness(face_crop) if face_crop.size else 0.0,
            "brightness": compute_brightness(face_crop) if face_crop.size else 0.0,
        }


def extract_blendshape_scores(result) -> dict[str, float]:
    if not result.face_blendshapes:
        return {}
    return {
        category.category_name: float(category.score)
        for category in result.face_blendshapes[0]
    }


def global_landmark_point(landmark, crop_width: int, crop_height: int, offset_x: int, offset_y: int) -> np.ndarray:
    return np.array(
        [
            offset_x + landmark.x * crop_width,
            offset_y + landmark.y * crop_height,
        ],
        dtype=np.float64,
    )


def euclidean_distance(point_a: np.ndarray, point_b: np.ndarray) -> float:
    return hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def compute_eye_aspect_ratio(points: list[np.ndarray], indices: tuple[int, ...]) -> float:
    p1, p2, p3, p4, p5, p6 = [points[index] for index in indices]
    denominator = 2.0 * euclidean_distance(p1, p4)
    if denominator == 0:
        return 0.0
    numerator = euclidean_distance(p2, p6) + euclidean_distance(p3, p5)
    return float(numerator / denominator)


def compute_mouth_ratio(points: list[np.ndarray]) -> float:
    left, right, top, bottom = [points[index] for index in MOUTH]
    mouth_width = euclidean_distance(left, right)
    if mouth_width == 0:
        return 0.0
    mouth_height = euclidean_distance(top, bottom)
    return float(mouth_height / mouth_width)


def estimate_head_pose(points: list[np.ndarray], image_width: int, image_height: int) -> tuple[float, float, float]:
    image_points = np.array(
        [
            points[1],
            points[152],
            points[263],
            points[33],
            points[287],
            points[57],
        ],
        dtype=np.float64,
    )

    model_points = np.array(
        [
            (0.0, 0.0, 0.0),
            (0.0, -330.0, -65.0),
            (-225.0, 170.0, -135.0),
            (225.0, 170.0, -135.0),
            (-150.0, -150.0, -125.0),
            (150.0, -150.0, -125.0),
        ],
        dtype=np.float64,
    )

    camera_matrix = np.array(
        [
            [image_width, 0, image_width / 2.0],
            [0, image_width, image_height / 2.0],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )

    success, rotation_vector, translation_vector = cv2.solvePnP(
        model_points,
        image_points,
        camera_matrix,
        np.zeros((4, 1), dtype=np.float64),
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        return 180.0, 180.0, 180.0

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    projection_matrix = np.hstack((rotation_matrix, translation_vector))
    _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(projection_matrix)

    pitch, yaw, roll = [normalize_pose_angle(float(angle)) for angle in euler_angles.flatten()]
    return yaw, pitch, roll


def intersection_over_union(
    bbox_a: tuple[int, int, int, int],
    bbox_b: tuple[int, int, int, int],
) -> float:
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_width = max(inter_x2 - inter_x1, 0)
    inter_height = max(inter_y2 - inter_y1, 0)
    intersection = inter_width * inter_height
    if intersection == 0:
        return 0.0

    area_a = max(ax2 - ax1, 0) * max(ay2 - ay1, 0)
    area_b = max(bx2 - bx1, 0) * max(by2 - by1, 0)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return float(intersection / union)


def normalize_pose_angle(angle: float) -> float:
    normalized = ((angle + 180.0) % 360.0) - 180.0
    if normalized > 90.0:
        normalized -= 180.0
    if normalized < -90.0:
        normalized += 180.0
    return normalized
