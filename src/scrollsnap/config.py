from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AnalyzerConfig:
    """Tunable parameters for vertical scroll reconstruction."""

    sample_fps: float | None = None
    max_shift_ratio: float = 0.55
    min_overlap_ratio: float = 0.35
    min_movement_px: int = 1
    stationary_score_threshold: float = 0.018
    cut_score_threshold: float = 0.145
    ambiguous_cut_score_threshold: float = 0.105
    ambiguous_confidence_threshold: float = 0.035
    viewport_min_area_ratio: float = 0.08
    viewport_margin_px: int = 0
    viewport_sample_count: int = 48
    alignment_max_width: int = 256
    alignment_coarse_width: int = 48
    alignment_candidate_count: int = 7
    alignment_refine_radius: int = 5
    build_mosaics: bool = True
    mosaic_min_gap_px: int = 1
    tile_height: int = 960
    tile_overlap: int = 80
    max_frames: int | None = None
    stream_video: bool = False
