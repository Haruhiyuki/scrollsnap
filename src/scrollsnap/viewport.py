from __future__ import annotations

import cv2
import numpy as np

from .config import AnalyzerConfig
from .imaging import clamp_bbox, expand_bbox, to_gray_float
from .types import BBox


def _longest_true_run(mask: np.ndarray, min_len: int) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    start: int | None = None
    for idx, value in enumerate(mask.tolist() + [False]):
        if value and start is None:
            start = idx
        if not value and start is not None:
            end = idx
            if end - start >= min_len and (best is None or end - start > best[1] - best[0]):
                best = (start, end)
            start = None
    return best


def _strong_edge_index(projection: np.ndarray, start: int, end: int, prefer: str) -> int | None:
    start = max(0, start)
    end = min(len(projection), end)
    if end <= start:
        return None
    window = projection[start:end]
    peak = float(window.max())
    baseline = float(np.percentile(projection, 75))
    if peak < max(0.04, baseline * 2.2):
        return None
    candidates = np.flatnonzero(window >= peak * 0.88) + start
    if candidates.size == 0:
        return int(start + int(window.argmax()))
    if prefer == "first":
        return int(candidates[0])
    if prefer == "last":
        return int(candidates[-1])
    return int(candidates[len(candidates) // 2])


def _smooth_1d(projection: np.ndarray, width: int) -> np.ndarray:
    if projection.size < 3:
        return projection.astype(np.float32)
    width = max(3, min(width, projection.size))
    if width % 2 == 0:
        width -= 1
    kernel = np.ones(width, dtype=np.float32) / float(width)
    return np.convolve(projection.astype(np.float32), kernel, mode="same")


def _runs_from_score(score: np.ndarray, threshold: float) -> list[tuple[int, int, float]]:
    runs = []
    start: int | None = None
    for idx, value in enumerate((score >= threshold).tolist() + [False]):
        if value and start is None:
            start = idx
        if not value and start is not None:
            end = idx
            runs.append((start, end, float(score[start:end].max())))
            start = None
    return runs


def _edge_score_projection(gradient_region: np.ndarray) -> np.ndarray:
    if gradient_region.size == 0:
        return np.zeros(0, dtype=np.float32)
    threshold = max(0.04, float(np.percentile(gradient_region, 95)) * 0.22)
    coverage = (gradient_region > threshold).mean(axis=0).astype(np.float32)
    strength = gradient_region.mean(axis=0).astype(np.float32)
    if float(strength.max()) > 1e-6:
        strength = strength / float(strength.max())
    score = _smooth_1d(coverage, 7) * 0.82 + _smooth_1d(strength, 7) * 0.18
    return score.astype(np.float32)


def _interval_has_motion(motion: np.ndarray | None, start: int, end: int) -> bool:
    if motion is None:
        return True
    start = max(0, min(motion.size, start))
    end = max(0, min(motion.size, end))
    if end < start:
        start, end = end, start
    if end - start <= 8:
        return True
    interval = motion[start:end]
    threshold = max(0.006, float(np.percentile(motion, 70)) * 0.16, float(motion.max()) * 0.028)
    return float(np.percentile(interval, 55)) >= threshold


def _choose_left_edge(
    score: np.ndarray,
    core_left: int,
    core_center: int,
    motion: np.ndarray | None = None,
) -> int | None:
    if score.size == 0 or float(score.max()) < 0.08:
        return None
    threshold = max(0.12, float(np.percentile(score, 94)) * 0.42, float(score.max()) * 0.18)
    runs = [run for run in _runs_from_score(score, threshold) if run[1] <= core_left + 6]
    if not runs:
        return None
    candidates = [(start + end - 1) // 2 for start, end, _ in runs]
    enclosing = [candidate for candidate in candidates if candidate < core_center]
    if not enclosing:
        return None
    viable = [candidate for candidate in enclosing if _interval_has_motion(motion, candidate, core_left)]
    if viable:
        return int(min(viable))
    return int(max(enclosing))


def _choose_right_edge(
    score: np.ndarray,
    core_right: int,
    core_center: int,
    motion: np.ndarray | None = None,
) -> int | None:
    if score.size == 0 or float(score.max()) < 0.08:
        return None
    threshold = max(0.12, float(np.percentile(score, 94)) * 0.42, float(score.max()) * 0.18)
    runs = [run for run in _runs_from_score(score, threshold) if run[0] >= core_right - 6]
    if not runs:
        return None
    candidates = [(start + end - 1) // 2 for start, end, _ in runs]
    enclosing = [candidate for candidate in candidates if candidate > core_center]
    if not enclosing:
        return None
    viable = [candidate for candidate in enclosing if _interval_has_motion(motion, core_right, candidate)]
    if viable:
        return int(max(viable))
    return int(min(enclosing))


def _motion_projection(energy: np.ndarray | None, start: int, end: int, axis: int) -> np.ndarray | None:
    if energy is None:
        return None
    start = max(0, start)
    end = min(energy.shape[axis], end)
    if end <= start:
        return None
    if axis == 0:
        projection = np.percentile(energy[start:end, :], 70, axis=0)
    else:
        projection = np.percentile(energy[:, start:end], 70, axis=1)
    return _smooth_1d(projection.astype(np.float32), 15)


def _expand_bbox_to_container_edges(frame: np.ndarray, bbox: BBox, energy: np.ndarray | None = None) -> BBox:
    height, width = frame.shape[:2]
    x, y, w, h = bbox
    right = x + w
    bottom = y + h
    core_center_x = x + w // 2

    gray = to_gray_float(frame)
    v_grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))

    y0 = max(0, y - 4)
    y1 = min(height, bottom + 4)
    v_score = _edge_score_projection(v_grad[y0:y1, :])
    col_motion = _motion_projection(energy, y0, y1, axis=0)
    left_edge = _choose_left_edge(v_score, x, core_center_x, col_motion)
    right_edge = _choose_right_edge(v_score, right, core_center_x, col_motion)

    expanded_x = x if left_edge is None else left_edge
    if right_edge is None:
        expanded_right = width if width - right <= 28 else right
    else:
        expanded_right = width if width - right_edge <= 28 else right_edge + 1

    expanded_x = max(0, min(expanded_x, x))
    expanded_right = min(width, max(expanded_right, right))
    if expanded_right <= expanded_x:
        expanded_x, expanded_right = x, right

    return clamp_bbox((expanded_x, y, expanded_right - expanded_x, h), width, height)


def _snap_bbox_to_edges(frame: np.ndarray, bbox: BBox, energy: np.ndarray | None = None) -> BBox:
    height, width = frame.shape[:2]
    bbox = _expand_bbox_to_container_edges(frame, bbox, energy)
    x, y, w, h = bbox
    right = x + w
    bottom = y + h

    gray = to_gray_float(frame)
    v_grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    h_grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))

    y0 = max(0, y - 3)
    y1 = min(height, bottom + 3)
    v_projection = v_grad[y0:y1, :].mean(axis=0)

    left_edge = _strong_edge_index(v_projection, x - 36, x + 12, "last")
    right_edge = None if right >= width - 2 else _strong_edge_index(v_projection, right - 12, right + 42, "first")

    snapped_x = x if left_edge is None else left_edge
    snapped_right = right if right_edge is None else right_edge + 1

    x0 = max(0, snapped_x)
    x1 = min(width, snapped_right)
    if x1 <= x0:
        x0, x1 = x, right
    h_projection = h_grad[:, x0:x1].mean(axis=1)
    top_edge = _strong_edge_index(h_projection, y - 18, y + 28, "last")
    bottom_edge = None if bottom >= height - 2 else _strong_edge_index(h_projection, bottom - 28, bottom + 18, "last")

    snapped_y = y if top_edge is None else top_edge
    snapped_bottom = bottom if bottom_edge is None else bottom_edge + 1
    return clamp_bbox((snapped_x, snapped_y, snapped_right - snapped_x, snapped_bottom - snapped_y), width, height)


def detect_scroll_viewport(frames: list[np.ndarray], config: AnalyzerConfig) -> BBox:
    """Find the dominant moving rectangle in a scroll recording."""

    if not frames:
        raise ValueError("At least one frame is required")

    height, width = frames[0].shape[:2]
    if len(frames) < 2:
        return (0, 0, width, height)

    if len(frames) > config.viewport_sample_count:
        indices = np.linspace(0, len(frames) - 1, config.viewport_sample_count).round().astype(int)
        sampled = [frames[int(index)] for index in indices]
    else:
        sampled = frames

    diffs = []
    gray_frames = [to_gray_float(frame) for frame in sampled]
    previous = gray_frames[0]
    for current in gray_frames[1:]:
        diffs.append(np.abs(current - previous))
        previous = current

    diff_stack = np.stack(diffs, axis=0)
    frame_stack = np.stack(gray_frames, axis=0)
    diff_energy = np.percentile(diff_stack, 90, axis=0).astype(np.float32)
    std_energy = frame_stack.std(axis=0).astype(np.float32)
    if float(diff_energy.max()) > 1e-6:
        diff_energy = diff_energy / float(diff_energy.max())
    if float(std_energy.max()) > 1e-6:
        std_energy = std_energy / float(std_energy.max())
    energy = diff_energy * 0.42 + std_energy * 0.58
    energy = cv2.GaussianBlur(energy, (11, 11), 0)

    median = float(np.median(energy))
    mad = float(np.median(np.abs(energy - median))) + 1e-6
    threshold = max(median + 2.6 * mad, float(np.percentile(energy, 78)) * 0.22, 0.018)
    binary = (energy > threshold).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = width * height * config.viewport_min_area_ratio
    candidates: list[BBox] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h >= min_area:
            candidates.append((x, y, w, h))

    if candidates:
        bbox = max(candidates, key=lambda item: item[2] * item[3])
    else:
        col_energy = energy.mean(axis=0)
        row_energy = energy.mean(axis=1)
        col_threshold = max(float(np.percentile(col_energy, 75)) * 0.45, float(col_energy.max()) * 0.12)
        row_threshold = max(float(np.percentile(row_energy, 75)) * 0.45, float(row_energy.max()) * 0.12)
        col_run = _longest_true_run(col_energy > col_threshold, max(8, width // 20))
        row_run = _longest_true_run(row_energy > row_threshold, max(8, height // 20))
        if col_run is None or row_run is None:
            return (0, 0, width, height)
        bbox = (col_run[0], row_run[0], col_run[1] - col_run[0], row_run[1] - row_run[0])

    bbox = _snap_bbox_to_edges(frames[0], bbox, energy)
    if config.viewport_margin_px:
        bbox = expand_bbox(bbox, config.viewport_margin_px, width, height)
    return clamp_bbox(bbox, width, height)
