from __future__ import annotations

from pathlib import Path
from typing import Any

from .analyzer import analyze_video, write_analysis_outputs
from .config import AnalyzerConfig
from .media import extract_frame_crops_for_bbox
from .trace import BBox, compact_trace, frame_crops_for_bbox, load_trace
from .vision import NoopVisualParser, VisualParser


def analyze_scroll_recording(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    stream: bool = True,
    images: bool = False,
    sample_fps: float | None = None,
    max_frames: int | None = None,
) -> dict[str, Any]:
    config = AnalyzerConfig(
        sample_fps=sample_fps,
        max_frames=max_frames,
        build_mosaics=images,
        stream_video=stream,
    )
    if stream and images:
        raise ValueError("stream=True requires images=False")
    result = analyze_video(video_path, config)
    write_analysis_outputs(result, out_dir, config)
    trace_path = Path(out_dir) / "trace.json"
    trace = load_trace(trace_path)
    return {
        "trace_path": str(trace_path),
        "video_path": str(video_path),
        "compact_trace": compact_trace(trace),
        "quality": trace.get("quality", {}),
    }


def query_scroll_crop(
    trace_path: str | Path,
    *,
    segment_index: int,
    bbox: BBox,
    video_path: str | Path | None = None,
    out_dir: str | Path | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    trace = load_trace(trace_path)
    crops = frame_crops_for_bbox(trace, segment_index=segment_index, bbox=bbox, limit=limit)
    if video_path is not None and out_dir is not None:
        crops = extract_frame_crops_for_bbox(
            video_path=video_path,
            trace=trace,
            segment_index=segment_index,
            bbox_in_long=bbox,
            out_dir=out_dir,
            limit=limit,
            prefix="openclaw",
        )
    return {
        "trace_path": str(trace_path),
        "segment_index": segment_index,
        "bbox_in_long": list(bbox),
        "crops": crops,
    }


def parse_scroll_region(
    trace_path: str | Path,
    *,
    segment_index: int,
    bbox: BBox,
    video_path: str | Path,
    out_dir: str | Path,
    parser: VisualParser | None = None,
    limit: int = 2,
) -> dict[str, Any]:
    parser = parser or NoopVisualParser()
    crop_result = query_scroll_crop(
        trace_path=trace_path,
        segment_index=segment_index,
        bbox=bbox,
        video_path=video_path,
        out_dir=out_dir,
        limit=limit,
    )
    parsed = []
    for crop in crop_result["crops"]:
        context = {
            "trace_path": str(trace_path),
            "segment_index": segment_index,
            "bbox_in_long": list(bbox),
            "frame_index": crop["frame_index"],
            "time_sec": crop["time_sec"],
            "crop_bbox_in_frame": crop["crop_bbox_in_frame"],
            "overlap_bbox_in_long": crop["overlap_bbox_in_long"],
        }
        parsed.append(parser.parse_image(crop["path"], context))
    return {
        **crop_result,
        "parsed": parsed,
    }


def openclaw_tool_manifest() -> dict[str, Any]:
    return {
        "name": "scrollsnap",
        "description": "Recover traceable long-page coordinates and minimal crops from scroll recordings.",
        "tools": [
            {
                "name": "analyze_scroll_recording",
                "description": "Analyze a scroll recording and write trace.json.",
                "input_schema": {
                    "type": "object",
                    "required": ["video_path", "out_dir"],
                    "properties": {
                        "video_path": {"type": "string"},
                        "out_dir": {"type": "string"},
                        "stream": {"type": "boolean", "default": True},
                        "images": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "query_scroll_crop",
                "description": "Find source-frame crops covering a long-image bbox.",
                "input_schema": {
                    "type": "object",
                    "required": ["trace_path", "segment_index", "bbox"],
                    "properties": {
                        "trace_path": {"type": "string"},
                        "segment_index": {"type": "integer"},
                        "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                        "video_path": {"type": "string"},
                        "out_dir": {"type": "string"},
                        "limit": {"type": "integer", "default": 3},
                    },
                },
            },
            {
                "name": "parse_scroll_region",
                "description": "Extract minimal crops and pass them to a visual parser adapter.",
                "input_schema": {
                    "type": "object",
                    "required": ["trace_path", "video_path", "out_dir", "segment_index", "bbox"],
                    "properties": {
                        "trace_path": {"type": "string"},
                        "video_path": {"type": "string"},
                        "out_dir": {"type": "string"},
                        "segment_index": {"type": "integer"},
                        "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                        "limit": {"type": "integer", "default": 2},
                    },
                },
            },
        ],
    }

