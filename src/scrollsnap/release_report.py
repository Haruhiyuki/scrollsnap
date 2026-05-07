from __future__ import annotations

import json
import platform
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analyzer import analyze_video, write_analysis_outputs
from .benchmark import benchmark_scenarios
from .config import AnalyzerConfig
from .token_estimate import default_query_bboxes, estimate_trace_tokens


SYNTHETIC_SCENARIOS = [
    "static_chrome",
    "pauses",
    "nested",
    "sticky",
    "reverse",
    "jump",
    "fast",
    "noisy",
    "repeated",
    "micro_scroll",
    "bursty",
    "long_page",
    "large_viewport",
    "mobile",
    "sparse",
    "form",
    "fixed_overlay",
]

SCENARIO_METADATA = {
    "static_chrome": {
        "surface": "desktop page",
        "stressors": "baseline scroll viewport, browser chrome, start/end pauses",
        "expected": "single segment",
    },
    "pauses": {
        "surface": "desktop page",
        "stressors": "long stationary prefix/suffix",
        "expected": "no false cuts during pauses",
    },
    "nested": {
        "surface": "app shell",
        "stressors": "scrolling sub-container offset inside static UI",
        "expected": "detect nested moving region",
    },
    "sticky": {
        "surface": "desktop page",
        "stressors": "in-page sticky toolbar",
        "expected": "exclude sticky header from moving viewport",
    },
    "reverse": {
        "surface": "desktop page",
        "stressors": "downward then upward scroll",
        "expected": "one coordinate-consistent segment",
    },
    "jump": {
        "surface": "document switch",
        "stressors": "hard visual page change",
        "expected": "two segments",
    },
    "fast": {
        "surface": "desktop page",
        "stressors": "large adjacent-frame displacement",
        "expected": "fast scroll without false cut",
    },
    "noisy": {
        "surface": "compressed video",
        "stressors": "JPEG artifacts and Gaussian noise",
        "expected": "robust alignment under degradation",
    },
    "repeated": {
        "surface": "list",
        "stressors": "weak local uniqueness, repeated rows",
        "expected": "avoid false repeated-row matches",
    },
    "micro_scroll": {
        "surface": "desktop page",
        "stressors": "subtle one-to-few-pixel motion",
        "expected": "retain small displacement precision",
    },
    "bursty": {
        "surface": "desktop page",
        "stressors": "trackpad-like bursts separated by pauses",
        "expected": "no false cuts across burst transitions",
    },
    "long_page": {
        "surface": "long document",
        "stressors": "large coordinate range and mosaic span",
        "expected": "stable coordinate integration",
    },
    "large_viewport": {
        "surface": "wide desktop",
        "stressors": "large pixel area and long page",
        "expected": "throughput remains practical",
    },
    "mobile": {
        "surface": "mobile-like viewport",
        "stressors": "narrow/tall aspect ratio",
        "expected": "viewport detection adapts to mobile layout",
    },
    "sparse": {
        "surface": "low-texture document",
        "stressors": "large blank bands and sparse anchors",
        "expected": "alignment does not overfit blank regions",
    },
    "form": {
        "surface": "form/settings UI",
        "stressors": "dense controls, repeated fields, inline hints",
        "expected": "coordinate stability on operational UI",
    },
    "fixed_overlay": {
        "surface": "desktop page",
        "stressors": "fixed assistant panel occluding content",
        "expected": "robustness to small non-scrolling overlay",
    },
}

BROWSER_EXPECTED_VIEWPORTS = {
    "browser_article": (70, 64, 760, 576),
    "browser_dashboard": (220, 64, 780, 636),
    "browser_table": (60, 101, 920, 559),
}

ACCEPTANCE_CRITERIA = {
    "segment_count": "actual segment count must equal ground truth",
    "viewport_l1_error_px": "<= 18",
    "mean_abs_y_error_px": "<= 3.5",
    "max_abs_y_error_px": "<= 9.0",
    "quality_risk": "reported but not used as a pass/fail override",
}


@dataclass(slots=True)
class BrowserVideoBenchmark:
    scenario: str
    frames: int
    seconds: float
    frames_per_second: float
    viewport_l1_error: int
    segment_count: int
    cut_count: int
    max_abs_dy: float
    has_quality_risk: bool
    token_estimate: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


def _browser_videos(input_dir: Path) -> list[tuple[str, Path]]:
    videos = []
    for scenario in BROWSER_EXPECTED_VIEWPORTS:
        path = input_dir / f"{scenario}.mp4"
        if path.exists():
            videos.append((scenario, path))
    return videos


def benchmark_browser_videos(input_dir: Path, out_dir: Path) -> list[BrowserVideoBenchmark]:
    results: list[BrowserVideoBenchmark] = []
    config = AnalyzerConfig(build_mosaics=False, stream_video=True)
    for scenario, video_path in _browser_videos(input_dir):
        scenario_out = out_dir / scenario
        start = time.perf_counter()
        result = analyze_video(video_path, config)
        seconds = time.perf_counter() - start
        write_analysis_outputs(result, scenario_out, config)
        trace = result.to_jsonable()
        expected = BROWSER_EXPECTED_VIEWPORTS[scenario]
        viewport_l1 = sum(abs(int(actual) - int(want)) for actual, want in zip(result.viewport_bbox, expected))
        token_estimate = estimate_trace_tokens(
            trace,
            queries=default_query_bboxes(trace, windows_per_segment=3, window_height=min(720, result.viewport_bbox[3])),
        )
        results.append(
            BrowserVideoBenchmark(
                scenario=scenario,
                frames=result.frame_count,
                seconds=float(seconds),
                frames_per_second=float(result.frame_count / seconds),
                viewport_l1_error=int(viewport_l1),
                segment_count=len(result.segments),
                cut_count=int(result.quality.get("cut_count", 0)),
                max_abs_dy=float(result.quality.get("max_abs_dy", 0.0)),
                has_quality_risk=bool(result.quality.get("has_quality_risk", False)),
                token_estimate=token_estimate.to_jsonable(),
            )
        )
    return results


def _median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _percent(values: list[float]) -> float:
    return float(100.0 * _median(values)) if values else 0.0


def generate_release_report(
    out_dir: str | Path,
    *,
    synthetic_frames: int = 160,
    synthetic_repeats: int = 3,
    browser_input_dir: str | Path = "artifacts/browser_selftest",
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    config = AnalyzerConfig()
    synthetic = benchmark_scenarios(
        scenarios=SYNTHETIC_SCENARIOS,
        frame_count=synthetic_frames,
        fps=12.0,
        repeats=synthetic_repeats,
        config=config,
    )
    browser = benchmark_browser_videos(Path(browser_input_dir), out / "browser_traces")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "synthetic": [item.to_jsonable() for item in synthetic],
        "browser_videos": [item.to_jsonable() for item in browser],
        "scenario_metadata": SCENARIO_METADATA,
        "acceptance_criteria": ACCEPTANCE_CRITERIA,
        "evaluation_scope": {
            "accuracy_benchmarks": [
                "deterministic synthetic recordings with full viewport, segment, and y-offset ground truth"
            ],
            "real_render_checks": [
                "Chromium-rendered local browser recordings for viewport, cut, quality, and token-budget checks"
            ],
            "external_accuracy_benchmarks": [],
        },
        "summary": {
            "synthetic_scenario_count": len(synthetic),
            "synthetic_passed": all(item.passed_accuracy for item in synthetic),
            "synthetic_pass_count": sum(1 for item in synthetic if item.passed_accuracy),
            "synthetic_pass_rate": sum(1 for item in synthetic if item.passed_accuracy) / len(synthetic)
            if synthetic
            else 0.0,
            "synthetic_fps_median": _median([item.frames_per_second for item in synthetic]),
            "synthetic_fps_min": min((item.frames_per_second for item in synthetic), default=0.0),
            "synthetic_fps_max": max((item.frames_per_second for item in synthetic), default=0.0),
            "synthetic_mpix_s_median": _median([item.viewport_megapixels_per_second for item in synthetic]),
            "synthetic_mpix_s_min": min((item.viewport_megapixels_per_second for item in synthetic), default=0.0),
            "synthetic_mpix_s_max": max((item.viewport_megapixels_per_second for item in synthetic), default=0.0),
            "synthetic_viewport_l1_median": _median([float(item.viewport_l1_error) for item in synthetic]),
            "synthetic_viewport_l1_max": max((item.viewport_l1_error for item in synthetic), default=0),
            "synthetic_mean_abs_y_error_median": _median([item.mean_abs_y_error for item in synthetic]),
            "synthetic_mean_abs_y_error_mean": _mean([item.mean_abs_y_error for item in synthetic]),
            "synthetic_max_abs_y_error_max": max((item.max_abs_y_error for item in synthetic), default=0.0),
            "synthetic_quality_risk_count": sum(1 for item in synthetic if item.has_quality_risk),
            "synthetic_corrected_outlier_count": sum(item.corrected_outlier_count for item in synthetic),
            "browser_available": bool(browser),
            "browser_count": len(browser),
            "browser_viewport_l1_median": _median([float(item.viewport_l1_error) for item in browser]),
            "browser_viewport_l1_max": max((item.viewport_l1_error for item in browser), default=0),
            "browser_fps_median": _median([item.frames_per_second for item in browser]),
            "browser_quality_risk_count": sum(1 for item in browser if item.has_quality_risk),
            "browser_token_savings_vs_raw_median_percent": _percent(
                [item.token_estimate["savings_vs_raw_frames"] for item in browser]
            ),
            "browser_token_savings_vs_long_median_percent": _percent(
                [item.token_estimate["savings_vs_long_images"] for item in browser]
            ),
            "browser_token_savings_vs_native_long_tiles_median_percent": _percent(
                [item.token_estimate["savings_vs_native_long_tiles"] for item in browser]
            ),
        },
    }

    (out / "release_benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown = render_markdown_report(payload)
    (out / "evaluation_report.md").write_text(markdown, encoding="utf-8")
    return payload


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def render_markdown_report(payload: dict[str, Any]) -> str:
    metadata = payload["scenario_metadata"]
    synthetic_rows = [
        [
            item["scenario"],
            metadata.get(item["scenario"], {}).get("surface", ""),
            metadata.get(item["scenario"], {}).get("stressors", ""),
            item["frames"],
            f'{item["frames_per_second"]:.1f}',
            f'{item["viewport_megapixels_per_second"]:.1f}',
            f'{item["score_p95"]:.4f}',
            f'{item["confidence_p05"]:.4f}',
            item["viewport_l1_error"],
            f'{item["mean_abs_y_error"]:.2f}',
            f'{item["max_abs_y_error"]:.2f}',
            f'{item["max_abs_dy"]:.0f}',
            f'{item["segment_count_actual"]}/{item["segment_count_expected"]}',
            item["cut_count"],
            item["corrected_outlier_count"],
            "yes" if item["has_quality_risk"] else "no",
            "yes" if item["passed_accuracy"] else "no",
        ]
        for item in payload["synthetic"]
    ]
    coverage_rows = [
        [
            name,
            spec["surface"],
            spec["stressors"],
            spec["expected"],
        ]
        for name, spec in metadata.items()
        if name in {item["scenario"] for item in payload["synthetic"]}
    ]
    browser_rows = [
        [
            item["scenario"],
            item["frames"],
            f'{item["frames_per_second"]:.1f}',
            item["viewport_l1_error"],
            item["segment_count"],
            item["cut_count"],
            f'{item["max_abs_dy"]:.0f}',
            "yes" if item["has_quality_risk"] else "no",
            item["token_estimate"]["raw_viewport_frame_tokens"],
            item["token_estimate"]["native_long_tile_tokens"],
            item["token_estimate"]["trace_plus_query_tokens"],
            f'{100 * item["token_estimate"]["savings_vs_raw_frames"]:.1f}%',
            f'{100 * item["token_estimate"]["savings_vs_native_long_tiles"]:.1f}%',
        ]
        for item in payload["browser_videos"]
    ]
    summary = payload["summary"]
    browser_table = (
        _markdown_table(
            [
                "scenario",
                "frames",
                "fps",
                "viewport L1",
                "segments",
                "cuts",
                "max abs dy",
                "quality risk",
                "raw frame tokens",
                "native long tokens",
                "trace+crop tokens",
                "saving vs frames",
                "saving vs native long tiles",
            ],
            browser_rows,
        )
        if browser_rows
        else "No saved Chromium videos were available under `artifacts/browser_selftest`."
    )
    acceptance_rows = [[key, value] for key, value in payload["acceptance_criteria"].items()]
    return f"""# ScrollSnap Evaluation Report

Generated: `{payload["generated_at"]}`

Environment: Python `{payload["environment"]["python"]}` on `{payload["environment"]["platform"]}`.

## Abstract

This report evaluates ScrollSnap as a scroll-video reconstruction component for
model-facing GUI-agent pipelines. The primary target is not screenshot quality;
it is a trace contract that lets an agent map video frames to long-page
coordinates, detect page/scene boundaries, and request the minimum image crops
needed for downstream visual parsing.

## Executive Summary

- Direct synthetic reconstruction: `{summary["synthetic_pass_count"]}/{summary["synthetic_scenario_count"]}` scenarios passed (`{100 * summary["synthetic_pass_rate"]:.1f}%`).
- Synthetic throughput range: `{summary["synthetic_fps_min"]:.1f}`-`{summary["synthetic_fps_max"]:.1f}` frames/s; median `{summary["synthetic_fps_median"]:.1f}` frames/s.
- Synthetic viewport throughput range: `{summary["synthetic_mpix_s_min"]:.1f}`-`{summary["synthetic_mpix_s_max"]:.1f}` viewport MPix/s; median `{summary["synthetic_mpix_s_median"]:.1f}` MPix/s.
- Synthetic coordinate error: median mean y error `{summary["synthetic_mean_abs_y_error_median"]:.2f}` px; worst max y error `{summary["synthetic_max_abs_y_error_max"]:.2f}` px.
- Synthetic viewport boundary error: median L1 `{summary["synthetic_viewport_l1_median"]:.1f}` px; max L1 `{summary["synthetic_viewport_l1_max"]}` px.
- Quality-risk flags: `{summary["synthetic_quality_risk_count"]}` synthetic scenarios and `{summary["browser_quality_risk_count"]}` saved-browser scenarios.
- Corrected isolated alignment outliers: `{summary["synthetic_corrected_outlier_count"]}` transitions across all synthetic runs.
- Saved Chromium videos: `{summary["browser_count"]}` scenarios, median `{summary["browser_fps_median"]:.1f}` frames/s, max viewport L1 `{summary["browser_viewport_l1_max"]}` px.
- Median estimated token saving on saved Chromium videos: `{summary["browser_token_savings_vs_raw_median_percent"]:.1f}%` vs raw viewport frames; `{summary["browser_token_savings_vs_native_long_tiles_median_percent"]:.1f}%` vs native-resolution long-page tiles.

## Evaluation Protocol

The direct benchmark uses deterministic recordings with complete ground truth:
source frames, viewport bbox, page/scene segment id per frame, and y-offset per
frame within each segment. Each scenario is run with the same analyzer
configuration. Throughput is reported as the median of repeated in-memory
analyses after fixture generation, so video encoding/decoding does not dominate
the algorithm benchmark.

Saved Chromium videos are evaluated separately because they are realistic
browser renders but do not currently include per-frame y-offset truth files in
the release artifact. They are used for viewport/cut/quality/token-budget
validation, not as the headline y-coordinate accuracy benchmark.

## Acceptance Criteria

{_markdown_table(["metric", "threshold or policy"], acceptance_rows)}

## Scenario Coverage Matrix

{_markdown_table(["scenario", "surface", "stressors", "expected behavior"], coverage_rows)}

## Synthetic Reconstruction Benchmark

{_markdown_table(["scenario", "surface", "stressors", "frames", "fps", "MPix/s", "score p95", "conf p05", "viewport L1", "mean abs y", "max abs y", "max abs dy", "segments", "cuts", "corrected", "quality risk", "pass"], synthetic_rows)}

## Saved Chromium Video Benchmark

{browser_table}

## Evaluation Scope

This report only includes benchmarks that were actually run for this release:
deterministic synthetic recordings with full reconstruction ground truth and
saved Chromium-rendered local browser recordings. No external dataset is
claimed as an accuracy benchmark in this release.

## Token Estimation Method

Token estimates use the explicit `tile_512_base85_tile170` profile. For high
detail accounting it first constrains images to a 2048px longest side and
scales down images whose shortest side remains above 768px, then applies:

`image_tokens = 85 + 170 * ceil(width / 512) * ceil(height / 512)`

The reported minimal-evidence strategy sends the compact trace plus three
representative source-frame evidence crops per segment. The raw baseline sends
every detected viewport frame, not the full screen, so the savings estimate is
conservative for full-screen video-to-image pipelines. The native long-tile
baseline keeps full long-page resolution by disabling model-side long-image
downscaling; it is the fair long-image baseline when exact pixel evidence is
required.

## Threats to Validity

- Synthetic scenarios provide exact labels but cannot cover all live desktop
  rendering behavior.
- Saved Chromium videos are realistic local renders, but this report treats
  them as viewport/cut/token checks unless y-offset truth is available.
- Very low-overlap scrolls remain information-limited; quality flags should be
  monitored by production pipelines.
- Token estimates are model-profile estimates, not billing guarantees.

## Reproduction

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
PYTHONPATH=src python3 -m scrollsnap.cli selftest --out artifacts/release_selftest --frames 96
PYTHONPATH=src python3 -m scrollsnap.cli release-report --out reports/release --synthetic-frames 160 --synthetic-repeats 3
```
"""
