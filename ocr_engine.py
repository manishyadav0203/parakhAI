from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import easyocr
import numpy as np


_reader = None
_reader_lock = threading.Lock()


@dataclass
class ImageQuality:
    brightness: float
    contrast: float
    blur_variance: float
    warnings: list[str]


def get_reader():
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


def assess_image_quality(image: np.ndarray) -> ImageQuality:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    warnings = []
    if brightness < 40:
        warnings.append("Image is too dark.")
    elif brightness > 220:
        warnings.append("Image may have glare or overexposure.")
    if blur_variance < 100:
        warnings.append("Image appears blurry.")

    return ImageQuality(brightness, contrast, blur_variance, warnings)


def _deskew(binary: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(binary < 255))
    if len(coords) < 20:
        return binary

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    h, w = binary.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        binary,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
    thresholded = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )

    return _deskew(thresholded)


def _box_to_xyxy(box) -> list[int]:
    points = np.asarray(box, dtype=np.float32)
    x_min = int(np.min(points[:, 0]))
    y_min = int(np.min(points[:, 1]))
    x_max = int(np.max(points[:, 0]))
    y_max = int(np.max(points[:, 1]))
    return [x_min, y_min, x_max, y_max]


def extract_text(image: np.ndarray, physical_height_mm: float) -> list[dict]:
    quality = assess_image_quality(image)
    processed = preprocess_for_ocr(image)

    reader = get_reader()
    raw = reader.readtext(processed, detail=1, paragraph=False)

    image_h = image.shape[0]
    results = []

    for box, text, confidence in raw:
        xyxy = _box_to_xyxy(box)
        pixel_height = max(0, xyxy[3] - xyxy[1])
        font_height_mm = (pixel_height / image_h) * physical_height_mm if image_h else 0.0

        results.append(
            {
                "text": text.strip(),
                "confidence": round(float(confidence), 4),
                "bbox": xyxy,
                "pixel_height": pixel_height,
                "font_height_mm": round(float(font_height_mm), 3),
            }
        )

    return results, quality
