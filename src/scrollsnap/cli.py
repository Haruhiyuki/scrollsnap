from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .analyzer import analyze_frames, analyze_video, write_analysis_outputs
from .benchmark import benchmark_scenarios
from .browser_scenarios import generate_browser_recording, write_browser_recording
from .config import AnalyzerConfig
from .metrics import evaluate_analysis
from .media import extract_frame_crops_for_bbox
from .openclaw_adapter import (
    analyze_scroll_recording,
    openclaw_tool_manifest,
    parse_scroll_region,
    query_scroll_crop,
)
from .release_report import generate_release_report
from .release_report import SYNTHETIC_SCENARIOS
from .synthetic import generate_synthetic_recording, load_synthetic_truth, write_synthetic_recording
from .token_estimate import default_query_bboxes, estimate_trace_tokens
from .trace import BBox, compact_trace, frame_crops_for_bbox, load_trace, tiles_for_bbox
from .vision import CommandVisualParser, NoopVisualParser


def _config_from_args(args: argparse.Namespace) -> AnalyzerConfig:
    return AnalyzerConfig(
        sample_fps=getattr(args, "sample_fps", None),
        tile_height=getattr(args, "tile_height", 960),
        tile_overlap=getattr(args, "tile_overlap", 80),
        max_frames=getattr(args, "max_frames", None),
        build_mosaics=not getattr(args, "no_images", False),
        stream_video=getattr(args, "stream", False),
    )


def cmd_synth(args: argparse.Namespace) -> int:
    recording = generate_synthetic_recording(
        scenario=args.scenario,
        frame_count=args.frames,
        fps=args.fps,
        seed=args.seed,
    )
    write_synthetic_recording(recording, args.out)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    if args.stream and not args.no_images:
        raise SystemExit("--stream currently requires --no-images")
    config = _config_from_args(args)
    result = analyze_video(args.video, config)
    write_analysis_outputs(result, args.out, config)
    if args.print_trace:
        print(json.dumps(result.to_jsonable(), indent=2))
    else:
        summary = {
            "trace_path": str(Path(args.out) / "trace.json"),
            "frame_count": result.frame_count,
            "viewport_bbox": list(result.viewport_bbox),
            "segments": [asdict(segment) for segment in result.segments],
            "tile_count": len(result.tiles),
            "quality": result.quality,
        }
        print(json.dumps(summary, indent=2))
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scenarios = list(SYNTHETIC_SCENARIOS)
    evaluations = []
    config = _config_from_args(args)
    for scenario in scenarios:
        recording = generate_synthetic_recording(scenario=scenario, frame_count=args.frames, fps=args.fps)
        video_path = out / f"{scenario}.mp4"
        write_synthetic_recording(recording, video_path)
        result = analyze_frames(recording.frames, fps=recording.truth.fps, config=config)
        write_analysis_outputs(result, out / scenario, config)
        evaluation = evaluate_analysis(result, recording.truth)
        evaluations.append(evaluation)
        print(json.dumps(asdict(evaluation), indent=2))
    report = {
        "passed": all(item.passed for item in evaluations),
        "evaluations": [asdict(item) for item in evaluations],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


def cmd_benchmark(args: argparse.Namespace) -> int:
    config = AnalyzerConfig(alignment_max_width=args.alignment_max_width)
    results = benchmark_scenarios(args.scenarios, args.frames, args.fps, args.repeats, config)
    payload = [item.to_jsonable() for item in results]
    print(json.dumps(payload, indent=2))
    return 0 if all(item.passed_accuracy for item in results) else 1


def cmd_browser_selftest(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    config = _config_from_args(args)
    evaluations = []
    for scenario in args.scenarios:
        recording = generate_browser_recording(scenario, frame_count=args.frames, fps=args.fps)
        video_path = out / f"{scenario}.mp4"
        write_browser_recording(recording, video_path)
        result = analyze_frames(recording.frames, fps=recording.truth.fps, config=config)
        write_analysis_outputs(result, out / scenario, config)
        evaluation = evaluate_analysis(result, recording.truth)
        evaluations.append(evaluation)
        print(json.dumps(asdict(evaluation), indent=2))
    report = {
        "passed": all(item.passed for item in evaluations),
        "evaluations": [asdict(item) for item in evaluations],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    result = analyze_video(args.video, config)
    if args.out:
        write_analysis_outputs(result, args.out, config)
    truth = load_synthetic_truth(args.truth)
    evaluation = evaluate_analysis(result, truth)
    payload = asdict(evaluation)
    payload["quality"] = result.quality
    print(json.dumps(payload, indent=2))
    return 0 if evaluation.passed else 1


def _parse_bbox(value: str) -> BBox:
    parts = [int(item.strip()) for item in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be formatted as x,y,w,h")
    if parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("bbox width and height must be positive")
    return (parts[0], parts[1], parts[2], parts[3])


def cmd_query_crop(args: argparse.Namespace) -> int:
    trace = load_trace(args.trace)
    result = {
        "trace_path": args.trace,
        "segment_index": args.segment,
        "bbox_in_long": list(args.bbox),
        "tiles": tiles_for_bbox(trace, args.segment, args.bbox),
        "frame_crops": frame_crops_for_bbox(trace, args.segment, args.bbox, limit=args.limit),
    }
    if args.video and args.out:
        result["extracted_crops"] = extract_frame_crops_for_bbox(
            video_path=args.video,
            trace=trace,
            segment_index=args.segment,
            bbox_in_long=args.bbox,
            out_dir=args.out,
            limit=args.limit,
            prefix="query",
        )
    print(json.dumps(result, indent=2))
    return 0


def cmd_parse_region(args: argparse.Namespace) -> int:
    parser = CommandVisualParser(args.vision_command) if args.vision_command else NoopVisualParser()
    result = parse_scroll_region(
        trace_path=args.trace,
        segment_index=args.segment,
        bbox=args.bbox,
        video_path=args.video,
        out_dir=args.out,
        parser=parser,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_openclaw_manifest(args: argparse.Namespace) -> int:
    print(json.dumps(openclaw_tool_manifest(), indent=2))
    return 0


def cmd_openclaw_analyze(args: argparse.Namespace) -> int:
    result = analyze_scroll_recording(
        video_path=args.video,
        out_dir=args.out,
        stream=not args.no_stream,
        images=args.images,
        sample_fps=args.sample_fps,
        max_frames=args.max_frames,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_openclaw_query(args: argparse.Namespace) -> int:
    result = query_scroll_crop(
        trace_path=args.trace,
        segment_index=args.segment,
        bbox=args.bbox,
        video_path=args.video,
        out_dir=args.out,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_compact_trace(args: argparse.Namespace) -> int:
    print(json.dumps(compact_trace(load_trace(args.trace)), indent=2))
    return 0


def cmd_estimate_tokens(args: argparse.Namespace) -> int:
    trace = load_trace(args.trace)
    queries = default_query_bboxes(
        trace,
        windows_per_segment=args.windows_per_segment,
        window_height=args.window_height,
    )
    result = estimate_trace_tokens(trace, queries=queries, crops_per_query=args.crops_per_query)
    print(json.dumps(result.to_jsonable(), indent=2))
    return 0


def cmd_release_report(args: argparse.Namespace) -> int:
    payload = generate_release_report(
        args.out,
        synthetic_frames=args.synthetic_frames,
        synthetic_repeats=args.synthetic_repeats,
        browser_input_dir=args.browser_input_dir,
    )
    print(json.dumps({"out": args.out, "summary": payload["summary"]}, indent=2))
    return 0 if payload["summary"]["synthetic_passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrollsnap")
    subparsers = parser.add_subparsers(dest="command", required=True)

    synth = subparsers.add_parser("synth", help="Generate a synthetic scroll recording")
    synth.add_argument("--scenario", default="static_chrome")
    synth.add_argument("--out", required=True)
    synth.add_argument("--frames", type=int, default=72)
    synth.add_argument("--fps", type=float, default=12.0)
    synth.add_argument("--seed", type=int, default=11)
    synth.set_defaults(func=cmd_synth)

    analyze = subparsers.add_parser("analyze", help="Analyze a scroll recording")
    analyze.add_argument("video")
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--sample-fps", type=float, default=None)
    analyze.add_argument("--tile-height", type=int, default=960)
    analyze.add_argument("--tile-overlap", type=int, default=80)
    analyze.add_argument("--max-frames", type=int, default=None)
    analyze.add_argument("--print-trace", action="store_true")
    analyze.add_argument("--no-images", action="store_true", help="Write trace.json only; skip mosaics and tiles")
    analyze.add_argument("--stream", action="store_true", help="Trace-only two-pass streaming analysis for lower memory use")
    analyze.set_defaults(func=cmd_analyze)

    compact = subparsers.add_parser("compact-trace", help="Print the model-routing subset of a trace")
    compact.add_argument("trace")
    compact.set_defaults(func=cmd_compact_trace)

    token = subparsers.add_parser("estimate-tokens", help="Estimate visual-token budgets from a trace")
    token.add_argument("trace")
    token.add_argument("--windows-per-segment", type=int, default=3)
    token.add_argument("--window-height", type=int, default=720)
    token.add_argument("--crops-per-query", type=int, default=1)
    token.set_defaults(func=cmd_estimate_tokens)

    query = subparsers.add_parser("query-crop", help="Find tiles/source-frame crops for a long-image bbox")
    query.add_argument("trace")
    query.add_argument("--segment", type=int, required=True)
    query.add_argument("--bbox", type=_parse_bbox, required=True, help="x,y,w,h in long-image coordinates")
    query.add_argument("--video", default=None)
    query.add_argument("--out", default=None)
    query.add_argument("--limit", type=int, default=3)
    query.set_defaults(func=cmd_query_crop)

    parse = subparsers.add_parser("parse-region", help="Extract minimal crops and call an optional vision command")
    parse.add_argument("trace")
    parse.add_argument("--video", required=True)
    parse.add_argument("--out", required=True)
    parse.add_argument("--segment", type=int, required=True)
    parse.add_argument("--bbox", type=_parse_bbox, required=True, help="x,y,w,h in long-image coordinates")
    parse.add_argument("--limit", type=int, default=2)
    parse.add_argument("--vision-command", default=None, help="Command template using {image} and {context_json}")
    parse.set_defaults(func=cmd_parse_region)

    evaluate = subparsers.add_parser("evaluate", help="Analyze a video and compare it with a truth JSON file")
    evaluate.add_argument("video")
    evaluate.add_argument("--truth", required=True)
    evaluate.add_argument("--out", default=None)
    evaluate.add_argument("--sample-fps", type=float, default=None)
    evaluate.add_argument("--tile-height", type=int, default=960)
    evaluate.add_argument("--tile-overlap", type=int, default=80)
    evaluate.add_argument("--max-frames", type=int, default=None)
    evaluate.add_argument("--no-images", action="store_true")
    evaluate.add_argument("--stream", action="store_true")
    evaluate.set_defaults(func=cmd_evaluate)

    selftest = subparsers.add_parser("selftest", help="Run synthetic scenarios end to end")
    selftest.add_argument("--out", required=True)
    selftest.add_argument("--frames", type=int, default=72)
    selftest.add_argument("--fps", type=float, default=12.0)
    selftest.add_argument("--sample-fps", type=float, default=None)
    selftest.add_argument("--tile-height", type=int, default=960)
    selftest.add_argument("--tile-overlap", type=int, default=80)
    selftest.add_argument("--max-frames", type=int, default=None)
    selftest.set_defaults(func=cmd_selftest)

    benchmark = subparsers.add_parser("benchmark", help="Measure synthetic analysis throughput")
    benchmark.add_argument("--frames", type=int, default=160)
    benchmark.add_argument("--fps", type=float, default=12.0)
    benchmark.add_argument("--repeats", type=int, default=3)
    benchmark.add_argument("--alignment-max-width", type=int, default=360)
    benchmark.add_argument(
        "--scenarios",
        nargs="+",
        default=list(SYNTHETIC_SCENARIOS),
    )
    benchmark.set_defaults(func=cmd_benchmark)

    browser = subparsers.add_parser("browser-selftest", help="Run local Chromium-rendered scroll scenarios")
    browser.add_argument("--out", required=True)
    browser.add_argument("--frames", type=int, default=72)
    browser.add_argument("--fps", type=float, default=12.0)
    browser.add_argument("--sample-fps", type=float, default=None)
    browser.add_argument("--tile-height", type=int, default=960)
    browser.add_argument("--tile-overlap", type=int, default=80)
    browser.add_argument("--max-frames", type=int, default=None)
    browser.add_argument(
        "--scenarios",
        nargs="+",
        default=["browser_article", "browser_dashboard", "browser_table"],
    )
    browser.set_defaults(func=cmd_browser_selftest)

    release = subparsers.add_parser("release-report", help="Generate release benchmark JSON and Markdown reports")
    release.add_argument("--out", required=True)
    release.add_argument("--synthetic-frames", type=int, default=160)
    release.add_argument("--synthetic-repeats", type=int, default=3)
    release.add_argument("--browser-input-dir", default="artifacts/browser_selftest")
    release.set_defaults(func=cmd_release_report)

    openclaw = subparsers.add_parser("openclaw-manifest", help="Print OpenClaw-style tool manifest")
    openclaw.set_defaults(func=cmd_openclaw_manifest)

    openclaw_analyze = subparsers.add_parser("openclaw-analyze", help="OpenClaw-style scroll recording analyzer")
    openclaw_analyze.add_argument("video")
    openclaw_analyze.add_argument("--out", required=True)
    openclaw_analyze.add_argument("--sample-fps", type=float, default=None)
    openclaw_analyze.add_argument("--max-frames", type=int, default=None)
    openclaw_analyze.add_argument("--images", action="store_true")
    openclaw_analyze.add_argument("--no-stream", action="store_true")
    openclaw_analyze.set_defaults(func=cmd_openclaw_analyze)

    openclaw_query = subparsers.add_parser("openclaw-query", help="OpenClaw-style crop query")
    openclaw_query.add_argument("trace")
    openclaw_query.add_argument("--segment", type=int, required=True)
    openclaw_query.add_argument("--bbox", type=_parse_bbox, required=True)
    openclaw_query.add_argument("--video", default=None)
    openclaw_query.add_argument("--out", default=None)
    openclaw_query.add_argument("--limit", type=int, default=3)
    openclaw_query.set_defaults(func=cmd_openclaw_query)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
