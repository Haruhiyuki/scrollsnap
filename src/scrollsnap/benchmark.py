from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass

from .analyzer import analyze_frames
from .config import AnalyzerConfig
from .metrics import evaluate_analysis
from .synthetic import generate_synthetic_recording


@dataclass(slots=True)
class ScenarioBenchmark:
    scenario: str
    frames: int
    viewport_pixels: int
    seconds_median: float
    frames_per_second: float
    viewport_megapixels_per_second: float
    segment_count_expected: int
    segment_count_actual: int
    cut_count: int
    corrected_outlier_count: int
    score_p95: float
    confidence_p05: float
    max_abs_dy: float
    has_quality_risk: bool
    mean_abs_y_error: float
    max_abs_y_error: float
    viewport_l1_error: int
    passed_accuracy: bool

    def to_jsonable(self) -> dict:
        return asdict(self)


def benchmark_scenarios(
    scenarios: list[str],
    frame_count: int,
    fps: float,
    repeats: int,
    config: AnalyzerConfig | None = None,
) -> list[ScenarioBenchmark]:
    config = config or AnalyzerConfig()
    results: list[ScenarioBenchmark] = []
    for scenario in scenarios:
        recording = generate_synthetic_recording(scenario=scenario, frame_count=frame_count, fps=fps)
        timings = []
        last_result = None
        for _ in range(repeats):
            start = time.perf_counter()
            last_result = analyze_frames(recording.frames, fps=recording.truth.fps, config=config)
            timings.append(time.perf_counter() - start)
        assert last_result is not None
        evaluation = evaluate_analysis(last_result, recording.truth)
        seconds = statistics.median(timings)
        _, _, width, height = last_result.viewport_bbox
        viewport_pixels = width * height
        results.append(
            ScenarioBenchmark(
                scenario=scenario,
                frames=frame_count,
                viewport_pixels=viewport_pixels,
                seconds_median=float(seconds),
                frames_per_second=float(frame_count / seconds),
                viewport_megapixels_per_second=float((frame_count * viewport_pixels / 1_000_000) / seconds),
                segment_count_expected=evaluation.segment_count_expected,
                segment_count_actual=evaluation.segment_count_actual,
                cut_count=int(last_result.quality.get("cut_count", 0)),
                corrected_outlier_count=int(last_result.quality.get("corrected_outlier_count", 0)),
                score_p95=float(last_result.quality.get("score_p95", 0.0)),
                confidence_p05=float(last_result.quality.get("confidence_p05", 0.0)),
                max_abs_dy=float(last_result.quality.get("max_abs_dy", 0.0)),
                has_quality_risk=bool(last_result.quality.get("has_quality_risk", False)),
                mean_abs_y_error=evaluation.mean_abs_y_error,
                max_abs_y_error=evaluation.max_abs_y_error,
                viewport_l1_error=evaluation.viewport_l1_error,
                passed_accuracy=evaluation.passed,
            )
        )
    return results
