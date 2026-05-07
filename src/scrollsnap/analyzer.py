from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .alignment import estimate_vertical_transition_features, prepare_alignment_state
from .config import AnalyzerConfig
from .imaging import save_rgb
from .mosaic import build_segment_mosaic
from .tiles import write_tiles
from .types import AnalysisResult, FramePlacement, SegmentResult, Transition
from .video import iter_video_frames, read_video_frames, read_video_viewport_samples, video_effective_fps
from .viewport import detect_scroll_viewport


def analyze_video(path: str | Path, config: AnalyzerConfig | None = None) -> AnalysisResult:
    config = config or AnalyzerConfig()
    if config.stream_video:
        return analyze_video_streaming(path, config)
    frames, fps, times = read_video_frames(path, sample_fps=config.sample_fps, max_frames=config.max_frames)
    return analyze_frames(frames, fps=fps, times=times, config=config)


def analyze_video_streaming(path: str | Path, config: AnalyzerConfig | None = None) -> AnalysisResult:
    config = config or AnalyzerConfig(stream_video=True, build_mosaics=False)
    if config.build_mosaics:
        raise ValueError("Streaming video analysis currently supports trace-only mode; set build_mosaics=False")

    viewport_samples = read_video_viewport_samples(
        path,
        sample_count=config.viewport_sample_count,
        sample_fps=config.sample_fps,
        max_frames=config.max_frames,
    )
    viewport = detect_scroll_viewport(viewport_samples, config)
    fps = video_effective_fps(path, sample_fps=config.sample_fps)

    times: list[float] = []
    transitions: list[Transition] = []
    previous_feature = None
    previous_index = None

    for accepted_index, time_sec, frame in iter_video_frames(path, sample_fps=config.sample_fps, max_frames=config.max_frames):
        times.append(float(time_sec))
        current_feature = prepare_alignment_state(frame, viewport, config)
        if previous_feature is not None and previous_index is not None:
            transitions.append(estimate_vertical_transition_features(previous_feature, current_feature, previous_index, config))
        previous_feature = current_feature
        previous_index = accepted_index

    if not times:
        raise ValueError("At least one frame is required")

    _apply_contextual_cuts(transitions, viewport[3], config)
    return _build_result_from_transitions(
        frame_count=len(times),
        fps=fps,
        times=times,
        viewport=viewport,
        transitions=transitions,
        frames=None,
        config=config,
    )


def analyze_frames(
    frames: list[np.ndarray],
    fps: float,
    times: list[float] | None = None,
    config: AnalyzerConfig | None = None,
) -> AnalysisResult:
    config = config or AnalyzerConfig()
    if not frames:
        raise ValueError("At least one frame is required")
    if times is None:
        times = [index / fps for index in range(len(frames))]
    if len(times) != len(frames):
        raise ValueError("times must have the same length as frames")

    viewport = detect_scroll_viewport(frames, config)
    transitions = []

    previous_feature = prepare_alignment_state(frames[0], viewport, config)
    for index in range(len(frames) - 1):
        current_feature = prepare_alignment_state(frames[index + 1], viewport, config)
        transition = estimate_vertical_transition_features(previous_feature, current_feature, index, config)
        transitions.append(transition)
        previous_feature = current_feature

    _apply_contextual_cuts(transitions, viewport[3], config)

    return _build_result_from_transitions(
        frame_count=len(frames),
        fps=fps,
        times=times,
        viewport=viewport,
        transitions=transitions,
        frames=frames,
        config=config,
    )


def _select_mosaic_placements(placements: list[FramePlacement], min_gap_px: int) -> list[FramePlacement]:
    if len(placements) <= 2 or min_gap_px <= 0:
        return placements
    selected = [placements[0]]
    last_y = placements[0].y_in_long
    for placement in placements[1:-1]:
        if abs(placement.y_in_long - last_y) >= min_gap_px:
            selected.append(placement)
            last_y = placement.y_in_long
    if selected[-1].frame_index != placements[-1].frame_index:
        selected.append(placements[-1])
    return selected


def _build_result_from_transitions(
    frame_count: int,
    fps: float,
    times: list[float],
    viewport: tuple[int, int, int, int],
    transitions: list[Transition],
    frames: list[np.ndarray] | None,
    config: AnalyzerConfig,
) -> AnalysisResult:
    segment_index = 0
    raw_y = 0.0
    placement_states: list[tuple[int, int, float]] = [(0, segment_index, raw_y)]
    for transition in transitions:
        if transition.is_cut:
            segment_index += 1
            raw_y = 0.0
        else:
            raw_y += transition.dy
        placement_states.append((transition.to_frame, segment_index, raw_y))

    raw_by_segment: dict[int, list[float]] = defaultdict(list)
    for _, seg, y in placement_states:
        raw_by_segment[seg].append(y)
    min_by_segment = {seg: min(values) for seg, values in raw_by_segment.items()}

    placements: list[FramePlacement] = []
    for frame_index, seg, y in placement_states:
        y_in_long = int(round(y - min_by_segment[seg]))
        placements.append(
            FramePlacement(
                frame_index=frame_index,
                time_sec=float(times[frame_index]),
                segment_index=seg,
                raw_y=float(y),
                y_in_long=y_in_long,
                source_bbox=viewport,
            )
        )

    grouped: dict[int, list[FramePlacement]] = defaultdict(list)
    for placement in placements:
        grouped[placement.segment_index].append(placement)

    segments: list[SegmentResult] = []
    mosaics: dict[int, np.ndarray] = {}
    _, _, viewport_width, viewport_height = viewport
    for seg in sorted(grouped):
        seg_placements = grouped[seg]
        long_height = max(item.y_in_long for item in seg_placements) + viewport_height
        segments.append(
            SegmentResult(
                segment_index=seg,
                frame_start=seg_placements[0].frame_index,
                frame_end=seg_placements[-1].frame_index,
                long_width=viewport_width,
                long_height=int(long_height),
            )
        )
        if config.build_mosaics and frames is not None:
            mosaics[seg] = build_segment_mosaic(frames, _select_mosaic_placements(seg_placements, config.mosaic_min_gap_px))

    return AnalysisResult(
        frame_count=frame_count,
        fps=float(fps),
        viewport_bbox=viewport,
        transitions=transitions,
        placements=placements,
        segments=segments,
        quality=_build_quality_report(transitions, segments, config),
        mosaics=mosaics,
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float32), percentile))


def _build_quality_report(
    transitions: list[Transition],
    segments: list[SegmentResult],
    config: AnalyzerConfig,
) -> dict[str, float | int | bool]:
    scores = [float(item.score) for item in transitions]
    confidences = [float(item.confidence) for item in transitions]
    dy_values = [abs(float(item.dy)) for item in transitions]
    corrected_count = sum(1 for item in transitions if item.was_corrected)
    low_confidence_count = sum(
        1
        for item in transitions
        if item.confidence < config.ambiguous_confidence_threshold
        and item.score > config.stationary_score_threshold
    )
    cut_count = sum(1 for item in transitions if item.is_cut)
    score_p95 = _percentile(scores, 95)
    score_max = max(scores) if scores else 0.0
    has_quality_risk = (
        score_p95 > config.ambiguous_cut_score_threshold
        or score_max > config.cut_score_threshold
        or low_confidence_count > max(5, len(transitions) // 10)
    )
    return {
        "transition_count": len(transitions),
        "segment_count": len(segments),
        "cut_count": cut_count,
        "score_median": _percentile(scores, 50),
        "score_p95": score_p95,
        "score_max": score_max,
        "confidence_p05": _percentile(confidences, 5),
        "confidence_median": _percentile(confidences, 50),
        "low_confidence_count": low_confidence_count,
        "corrected_outlier_count": corrected_count,
        "max_abs_dy": max(dy_values) if dy_values else 0.0,
        "has_quality_risk": bool(has_quality_risk),
    }


def _nearby_motion(transitions: list[Transition], start: int, end: int) -> float:
    start = max(0, start)
    end = min(len(transitions), end)
    if end <= start:
        return 0.0
    values = [abs(item.dy) for item in transitions[start:end] if not item.is_cut]
    return max(values) if values else 0.0


def _nearby_signed_motion(transitions: list[Transition], start: int, end: int) -> list[float]:
    start = max(0, start)
    end = min(len(transitions), end)
    if end <= start:
        return []
    return [float(item.dy) for item in transitions[start:end] if not item.is_cut]


def _same_direction(values: list[float], tolerance: float) -> bool:
    moving = [value for value in values if abs(value) > tolerance]
    if len(moving) < 2:
        return False
    return all(value > 0 for value in moving) or all(value < 0 for value in moving)


def _apply_isolated_outlier_corrections(
    transitions: list[Transition],
    viewport_height: int,
    config: AnalyzerConfig,
) -> None:
    for index, transition in enumerate(transitions):
        if transition.is_cut:
            continue
        previous_values = _nearby_signed_motion(transitions, index - 4, index)
        next_values = _nearby_signed_motion(transitions, index + 1, index + 5)
        if len(previous_values) < 2 or len(next_values) < 2:
            continue

        neighbors = previous_values[-3:] + next_values[:3]
        if not _same_direction(neighbors, tolerance=max(1.0, config.min_movement_px)):
            continue

        neighbor_median = float(np.median(np.asarray(neighbors, dtype=np.float32)))
        deviation = abs(float(transition.dy) - neighbor_median)
        isolated_low_confidence = (
            transition.confidence < config.ambiguous_confidence_threshold
            and deviation > max(viewport_height * 0.16, 24.0)
            and abs(float(transition.dy)) > max(abs(neighbor_median) * 3.0, viewport_height * 0.18)
        )
        sign_flip = (
            transition.confidence < config.ambiguous_confidence_threshold * 1.4
            and abs(neighbor_median) > max(2.0, config.min_movement_px)
            and float(transition.dy) * neighbor_median < 0
            and deviation > max(viewport_height * 0.12, 18.0)
        )
        if isolated_low_confidence or sign_flip:
            transition.dy = float(round(neighbor_median))
            transition.was_corrected = True


def _apply_contextual_cuts(transitions: list[Transition], viewport_height: int, config: AnalyzerConfig) -> None:
    _apply_isolated_outlier_corrections(transitions, viewport_height, config)
    for index, transition in enumerate(transitions):
        if transition.is_cut:
            continue
        large_uncertain = (
            abs(transition.dy) > viewport_height * 0.38
            and transition.score > config.stationary_score_threshold * 4.0
            and transition.confidence < config.ambiguous_confidence_threshold
        )
        if not large_uncertain:
            continue
        previous_motion = _nearby_motion(transitions, index - 3, index)
        next_motion = _nearby_motion(transitions, index + 1, index + 4)
        pause_like = max(previous_motion, next_motion) <= max(config.min_movement_px * 3, viewport_height * 0.03)
        if pause_like:
            transition.is_cut = True


def write_analysis_outputs(result: AnalysisResult, out_dir: str | Path, config: AnalyzerConfig | None = None) -> None:
    config = config or AnalyzerConfig()
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    tiles = []
    for segment in result.segments:
        image = result.mosaics.get(segment.segment_index)
        if image is None:
            continue
        image_path = out_path / f"segment_{segment.segment_index:03d}.png"
        save_rgb(image_path, image)
        segment.image_path = str(image_path)
        placements = [item for item in result.placements if item.segment_index == segment.segment_index]
        tiles.extend(
            write_tiles(
                image=image,
                placements=placements,
                segment_index=segment.segment_index,
                out_dir=out_path / "tiles",
                tile_height=config.tile_height,
                overlap=config.tile_overlap,
            )
        )

    result.tiles = tiles
    trace_path = out_path / "trace.json"
    trace_path.write_text(json.dumps(result.to_jsonable(), indent=2), encoding="utf-8")
