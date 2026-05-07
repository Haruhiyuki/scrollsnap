from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .types import BBox


def ensure_rgb(frame: np.ndarray) -> np.ndarray:
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"Expected RGB frame with shape HxWx3, got {frame.shape}")
    if frame.dtype != np.uint8:
        return np.clip(frame, 0, 255).astype(np.uint8)
    return frame


def to_gray_float(frame: np.ndarray) -> np.ndarray:
    rgb = ensure_rgb(frame)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return gray.astype(np.float32) / 255.0


def crop_bbox(frame: np.ndarray, bbox: BBox) -> np.ndarray:
    x, y, w, h = bbox
    return frame[y : y + h, x : x + w]


def clamp_bbox(bbox: BBox, width: int, height: int) -> BBox:
    x, y, w, h = bbox
    x = max(0, min(width - 1, x))
    y = max(0, min(height - 1, y))
    w = max(1, min(width - x, w))
    h = max(1, min(height - y, h))
    return (int(x), int(y), int(w), int(h))


def expand_bbox(bbox: BBox, margin: int, width: int, height: int) -> BBox:
    x, y, w, h = bbox
    return clamp_bbox((x - margin, y - margin, w + 2 * margin, h + 2 * margin), width, height)


def save_rgb(path: str | Path, image: np.ndarray) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(ensure_rgb(image)).save(path)


def preprocess_for_alignment(image: np.ndarray) -> np.ndarray:
    gray = to_gray_float(image)
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.2)
    high_pass = gray - blurred
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    feature = np.abs(high_pass) * 0.65 + grad * 0.35
    p98 = float(np.percentile(feature, 98))
    if p98 > 1e-6:
        feature = np.clip(feature / p98, 0.0, 1.0)
    return feature.astype(np.float32)

