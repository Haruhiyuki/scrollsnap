from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import AnalyzerConfig
from .imaging import crop_bbox, preprocess_for_alignment
from .types import BBox, Transition


@dataclass(slots=True)
class AlignmentFeature:
    dense: np.ndarray
    row_signature: np.ndarray


def _overlap_for_shift(a: np.ndarray, b: np.ndarray, dy: int) -> tuple[np.ndarray, np.ndarray]:
    if dy >= 0:
        return a[dy:, :], b[: b.shape[0] - dy, :]
    return a[: a.shape[0] + dy, :], b[-dy:, :]


def _score_shift_dense(a: np.ndarray, b: np.ndarray, dy: int) -> float:
    a_part, b_part = _overlap_for_shift(a, b, dy)
    if a_part.size == 0:
        return 1.0
    return float(np.abs(a_part - b_part).mean())


def _score_shift_signature(a: np.ndarray, b: np.ndarray, dy: int) -> float:
    a_part, b_part = _overlap_for_shift(a, b, dy)
    if a_part.size == 0:
        return 1.0
    return float(np.abs(a_part - b_part).mean())


def _row_p90_nearest(values: np.ndarray) -> np.ndarray:
    if values.shape[1] <= 1:
        return values[:, 0]
    kth = int(round((values.shape[1] - 1) * 0.90))
    return np.partition(values, kth, axis=1)[:, kth]


def _row_signature(feature: np.ndarray, coarse_width: int) -> np.ndarray:
    if coarse_width > 0 and feature.shape[1] > coarse_width:
        small = cv2.resize(feature, (coarse_width, feature.shape[0]), interpolation=cv2.INTER_AREA)
    else:
        small = feature

    mean = small.mean(axis=1)
    std = small.std(axis=1)
    p90 = _row_p90_nearest(small)
    signature = np.stack([mean, std, p90], axis=1).astype(np.float32)
    scale = np.percentile(np.abs(signature), 95, axis=0)
    scale[scale < 1e-6] = 1.0
    return signature / scale


def estimate_vertical_transition(
    frame_a: np.ndarray,
    frame_b: np.ndarray,
    frame_index: int,
    bbox: BBox,
    config: AnalyzerConfig,
) -> Transition:
    feat_a = prepare_alignment_feature(frame_a, bbox, config.alignment_max_width)
    feat_b = prepare_alignment_feature(frame_b, bbox, config.alignment_max_width)
    return estimate_vertical_transition_features(feat_a, feat_b, frame_index, config)


def prepare_alignment_feature(frame: np.ndarray, bbox: BBox, max_width: int | None) -> np.ndarray:
    crop = crop_bbox(frame, bbox)
    if max_width is not None and max_width > 0 and crop.shape[1] > max_width:
        crop = cv2.resize(crop, (max_width, crop.shape[0]), interpolation=cv2.INTER_AREA)
    return preprocess_for_alignment(crop)


def prepare_alignment_state(frame: np.ndarray, bbox: BBox, config: AnalyzerConfig) -> AlignmentFeature:
    dense = prepare_alignment_feature(frame, bbox, config.alignment_max_width)
    return AlignmentFeature(dense=dense, row_signature=_row_signature(dense, config.alignment_coarse_width))


def estimate_vertical_transition_features(
    feat_a: AlignmentFeature | np.ndarray,
    feat_b: AlignmentFeature | np.ndarray,
    frame_index: int,
    config: AnalyzerConfig,
) -> Transition:
    if isinstance(feat_a, np.ndarray):
        feat_a = AlignmentFeature(dense=feat_a, row_signature=_row_signature(feat_a, config.alignment_coarse_width))
    if isinstance(feat_b, np.ndarray):
        feat_b = AlignmentFeature(dense=feat_b, row_signature=_row_signature(feat_b, config.alignment_coarse_width))

    height = feat_a.dense.shape[0]
    max_shift = max(1, min(height - 2, int(round(height * config.max_shift_ratio))))
    min_overlap = max(8, int(round(height * config.min_overlap_ratio)))

    coarse_scores: list[tuple[int, float]] = []
    for dy in range(-max_shift, max_shift + 1):
        overlap = height - abs(dy)
        if overlap < min_overlap:
            continue
        score = _score_shift_signature(feat_a.row_signature, feat_b.row_signature, dy)
        coarse_scores.append((dy, score))

    if not coarse_scores:
        return Transition(frame_index, frame_index + 1, 0.0, 1.0, 1.0, 0.0, True)

    coarse_scores.sort(key=lambda item: item[1])
    candidate_shifts: set[int] = {0}
    for dy, _ in coarse_scores[: max(1, config.alignment_candidate_count)]:
        for refined in range(dy - config.alignment_refine_radius, dy + config.alignment_refine_radius + 1):
            if abs(refined) <= max_shift and height - abs(refined) >= min_overlap:
                candidate_shifts.add(refined)

    scores = [
        (dy, _score_shift_dense(feat_a.dense, feat_b.dense, dy))
        for dy in sorted(candidate_shifts)
    ]
    scores.sort(key=lambda item: item[1])
    best_dy, best_score = scores[0]
    second_score = next(
        (score for dy, score in scores[1:] if abs(dy - best_dy) > 2),
        scores[min(1, len(scores) - 1)][1],
    )
    confidence = max(0.0, second_score - best_score)

    if abs(best_dy) < config.min_movement_px and best_score < config.stationary_score_threshold:
        best_dy = 0

    is_cut = best_score > config.cut_score_threshold
    if best_score > config.ambiguous_cut_score_threshold and confidence < config.ambiguous_confidence_threshold:
        is_cut = True
    return Transition(
        from_frame=frame_index,
        to_frame=frame_index + 1,
        dy=float(best_dy),
        score=best_score,
        second_score=float(second_score),
        confidence=float(confidence),
        is_cut=is_cut,
    )
