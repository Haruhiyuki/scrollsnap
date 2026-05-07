from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import ImageFont

from scrollsnap.analyzer import analyze_frames, write_analysis_outputs
from scrollsnap.benchmark import benchmark_scenarios
from scrollsnap.browser_scenarios import generate_browser_recording
from scrollsnap.config import AnalyzerConfig
from scrollsnap.mcp_server import call_tool, tool_list
from scrollsnap.metrics import evaluate_analysis
from scrollsnap.openclaw_adapter import analyze_scroll_recording, openclaw_tool_manifest, parse_scroll_region, query_scroll_crop
from scrollsnap.synthetic import generate_synthetic_recording
from scrollsnap.token_estimate import default_query_bboxes, estimate_image_tokens, estimate_trace_tokens
from scrollsnap.trace import frame_crops_for_bbox, frames_for_y_range, load_trace, tiles_for_bbox
from scrollsnap.vision import NoopVisualParser


def _run_scenario(scenario: str, tmp_path: Path):
    recording = generate_synthetic_recording(scenario=scenario, frame_count=64, fps=12.0)
    config = AnalyzerConfig(tile_height=420, tile_overlap=50)
    result = analyze_frames(recording.frames, fps=recording.truth.fps, config=config)
    write_analysis_outputs(result, tmp_path / scenario, config)
    return evaluate_analysis(result, recording.truth), result


def test_static_chrome_reconstructs_scroll_trace(tmp_path: Path) -> None:
    evaluation, result = _run_scenario("static_chrome", tmp_path)
    assert evaluation.passed, evaluation
    assert result.tiles
    assert (tmp_path / "static_chrome" / "trace.json").exists()
    trace = load_trace(tmp_path / "static_chrome" / "trace.json")
    assert trace["quality"]["transition_count"] > 0
    assert not trace["quality"]["has_quality_risk"]
    assert tiles_for_bbox(trace, 0, (0, 120, 410, 260))
    assert frames_for_y_range(trace, 0, 120, 260)
    crop = frame_crops_for_bbox(trace, 0, (0, 120, 410, 260), limit=1)[0]
    assert crop["coverage_area"] > 0
    assert crop["crop_bbox_in_frame"][2] <= result.viewport_bbox[2]


def test_pauses_do_not_create_false_pages(tmp_path: Path) -> None:
    evaluation, _ = _run_scenario("pauses", tmp_path)
    assert evaluation.passed, evaluation


def test_nested_scroll_region_is_detected(tmp_path: Path) -> None:
    evaluation, _ = _run_scenario("nested", tmp_path)
    assert evaluation.passed, evaluation


def test_sticky_header_is_excluded_from_moving_region(tmp_path: Path) -> None:
    evaluation, result = _run_scenario("sticky", tmp_path)
    assert evaluation.passed, evaluation
    assert result.viewport_bbox[1] > 100


def test_reverse_scroll_keeps_consistent_coordinates(tmp_path: Path) -> None:
    evaluation, _ = _run_scenario("reverse", tmp_path)
    assert evaluation.passed, evaluation


def test_page_jump_splits_segments(tmp_path: Path) -> None:
    evaluation, result = _run_scenario("jump", tmp_path)
    assert evaluation.passed, evaluation
    assert len(result.segments) == 2


@pytest.mark.parametrize(
    "scenario",
    ["fast", "noisy", "repeated", "micro_scroll", "bursty", "long_page", "mobile", "sparse", "form", "fixed_overlay"],
)
def test_stress_synthetic_scenarios(scenario: str, tmp_path: Path) -> None:
    evaluation, _ = _run_scenario(scenario, tmp_path)
    assert evaluation.passed, evaluation


def test_repeated_viewport_is_stable_with_default_pil_font(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scrollsnap.synthetic as synthetic

    monkeypatch.setattr(synthetic, "_font", lambda size=15: ImageFont.load_default())
    evaluation, result = _run_scenario("repeated", tmp_path)
    assert evaluation.passed, (evaluation, result.viewport_bbox)


def test_benchmark_reports_throughput() -> None:
    results = benchmark_scenarios(
        scenarios=["static_chrome"],
        frame_count=24,
        fps=12.0,
        repeats=1,
        config=AnalyzerConfig(),
    )
    assert results[0].passed_accuracy
    assert results[0].frames_per_second > 0
    assert results[0].segment_count_actual == results[0].segment_count_expected


def test_streaming_trace_matches_in_memory_video(tmp_path: Path) -> None:
    from scrollsnap.analyzer import analyze_video
    from scrollsnap.synthetic import load_synthetic_truth, write_synthetic_recording

    recording = generate_synthetic_recording(scenario="fast", frame_count=36, fps=12.0)
    video_path = tmp_path / "fast.mp4"
    write_synthetic_recording(recording, video_path)
    loaded_truth = load_synthetic_truth(tmp_path / "fast.truth.json")
    assert loaded_truth.offsets == recording.truth.offsets
    normal = analyze_video(video_path, AnalyzerConfig(build_mosaics=False))
    streamed = analyze_video(video_path, AnalyzerConfig(build_mosaics=False, stream_video=True))

    assert streamed.viewport_bbox == normal.viewport_bbox
    assert [segment.long_height for segment in streamed.segments] == [segment.long_height for segment in normal.segments]
    assert [placement.y_in_long for placement in streamed.placements] == [placement.y_in_long for placement in normal.placements]


def test_openclaw_adapter_extracts_and_parses_minimal_crops(tmp_path: Path) -> None:
    from scrollsnap.synthetic import write_synthetic_recording

    recording = generate_synthetic_recording(scenario="static_chrome", frame_count=32, fps=12.0)
    video_path = tmp_path / "recording.mp4"
    write_synthetic_recording(recording, video_path)

    analysis = analyze_scroll_recording(video_path, tmp_path / "analysis", stream=True, images=False)
    assert analysis["compact_trace"]["segments"]
    assert not analysis["quality"]["has_quality_risk"]

    trace_path = tmp_path / "analysis" / "trace.json"
    query = query_scroll_crop(
        trace_path,
        segment_index=0,
        bbox=(0, 120, 410, 260),
        video_path=video_path,
        out_dir=tmp_path / "crops",
        limit=2,
    )
    assert query["crops"]
    assert Path(query["crops"][0]["path"]).exists()

    parsed = parse_scroll_region(
        trace_path,
        segment_index=0,
        bbox=(0, 120, 410, 260),
        video_path=video_path,
        out_dir=tmp_path / "parsed",
        parser=NoopVisualParser(),
        limit=1,
    )
    assert parsed["parsed"][0]["parser"] == "noop"


def test_openclaw_manifest_and_mcp_tools() -> None:
    manifest = openclaw_tool_manifest()
    assert {tool["name"] for tool in manifest["tools"]} >= {
        "analyze_scroll_recording",
        "query_scroll_crop",
        "parse_scroll_region",
    }
    tools = tool_list()
    assert {tool["name"] for tool in tools} >= {
        "scrollsnap_analyze_video",
        "scrollsnap_query_crops",
        "scrollsnap_compact_trace",
    }


def test_token_estimator_reports_savings(tmp_path: Path) -> None:
    recording = generate_synthetic_recording(scenario="static_chrome", frame_count=24, fps=12.0)
    result = analyze_frames(recording.frames, fps=recording.truth.fps, config=AnalyzerConfig(tile_height=420, tile_overlap=50))
    write_analysis_outputs(result, tmp_path / "analysis", AnalyzerConfig(tile_height=420, tile_overlap=50))
    trace = load_trace(tmp_path / "analysis" / "trace.json")
    queries = default_query_bboxes(trace, windows_per_segment=2, window_height=260)
    estimate = estimate_trace_tokens(trace, queries=queries)

    assert estimate_image_tokens(410, 344).image_tokens > 0
    assert estimate.query_count == 2
    assert estimate.raw_viewport_frame_tokens > estimate.trace_plus_query_tokens
    assert estimate.savings_vs_raw_frames > 0.0


def test_mcp_compact_trace_tool(tmp_path: Path) -> None:
    recording = generate_synthetic_recording(scenario="static_chrome", frame_count=24, fps=12.0)
    result = analyze_frames(recording.frames, fps=recording.truth.fps, config=AnalyzerConfig(tile_height=420, tile_overlap=50))
    write_analysis_outputs(result, tmp_path / "analysis", AnalyzerConfig(tile_height=420, tile_overlap=50))
    response = call_tool("scrollsnap_compact_trace", {"trace_path": str(tmp_path / "analysis" / "trace.json")})
    assert response["content"]
    assert "viewport_bbox" in response["content"][0]["text"]


@pytest.mark.browser
def test_browser_article_scenario_when_enabled(tmp_path: Path) -> None:
    if os.environ.get("SCROLLSNAP_RUN_BROWSER_TESTS") != "1":
        pytest.skip("set SCROLLSNAP_RUN_BROWSER_TESTS=1 to run Chromium-backed browser tests")
    pytest.importorskip("playwright.sync_api")
    recording = generate_browser_recording("browser_article", frame_count=28, fps=12.0)
    config = AnalyzerConfig(tile_height=520, tile_overlap=60)
    result = analyze_frames(recording.frames, fps=recording.truth.fps, config=config)
    evaluation = evaluate_analysis(result, recording.truth)
    assert evaluation.passed, evaluation
