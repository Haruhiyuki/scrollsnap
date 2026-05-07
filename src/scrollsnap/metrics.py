from __future__ import annotations

from dataclasses import dataclass

from .types import AnalysisResult
from .synthetic import SyntheticTruth


@dataclass(slots=True)
class Evaluation:
    scenario: str
    segment_count_expected: int
    segment_count_actual: int
    viewport_l1_error: int
    mean_abs_y_error: float
    max_abs_y_error: float

    @property
    def passed(self) -> bool:
        return (
            self.segment_count_actual == self.segment_count_expected
            and self.viewport_l1_error <= 18
            and self.mean_abs_y_error <= 3.5
            and self.max_abs_y_error <= 9.0
        )


def evaluate_analysis(result: AnalysisResult, truth: SyntheticTruth) -> Evaluation:
    expected_segments = len(set(truth.segment_ids))
    actual_segments = len(result.segments)
    viewport_l1 = sum(abs(a - b) for a, b in zip(result.viewport_bbox, truth.viewport_bbox))

    errors = []
    for segment in sorted(set(truth.segment_ids)):
        truth_indices = [idx for idx, seg in enumerate(truth.segment_ids) if seg == segment]
        if not truth_indices:
            continue
        truth_min = min(truth.offsets[idx] for idx in truth_indices)
        actual_by_frame = {
            placement.frame_index: placement
            for placement in result.placements
            if placement.segment_index == segment
        }
        for idx in truth_indices:
            placement = actual_by_frame.get(idx)
            if placement is None:
                errors.append(999.0)
                continue
            expected = truth.offsets[idx] - truth_min
            errors.append(abs(float(placement.y_in_long - expected)))

    mean_error = sum(errors) / len(errors) if errors else 999.0
    max_error = max(errors) if errors else 999.0
    return Evaluation(
        scenario=truth.scenario,
        segment_count_expected=expected_segments,
        segment_count_actual=actual_segments,
        viewport_l1_error=int(viewport_l1),
        mean_abs_y_error=float(mean_error),
        max_abs_y_error=float(max_error),
    )

