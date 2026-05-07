from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BBox = tuple[int, int, int, int]


def load_trace(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _overlap_1d(a0: int, a1: int, b0: int, b1: int) -> bool:
    return max(a0, b0) < min(a1, b1)


def _overlap_bbox(a: BBox, b: BBox) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return _overlap_1d(ax, ax + aw, bx, bx + bw) and _overlap_1d(ay, ay + ah, by, by + bh)


def tiles_for_bbox(trace: dict[str, Any], segment_index: int, bbox: BBox) -> list[dict[str, Any]]:
    return [
        tile
        for tile in trace.get("tiles", [])
        if tile.get("segment_index") == segment_index and _overlap_bbox(tuple(tile["bbox_in_long"]), bbox)
    ]


def frames_for_y_range(trace: dict[str, Any], segment_index: int, y: int, height: int) -> list[dict[str, Any]]:
    y0 = y
    y1 = y + height
    frames = []
    for placement in trace.get("placements", []):
        if placement.get("segment_index") != segment_index:
            continue
        _, _, _, source_h = placement["source_bbox"]
        py0 = int(placement["y_in_long"])
        py1 = py0 + int(source_h)
        if _overlap_1d(y0, y1, py0, py1):
            frames.append(placement)
    return frames


def frame_crops_for_bbox(
    trace: dict[str, Any],
    segment_index: int,
    bbox: BBox,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Rank source-frame crops by how much of a long-image bbox they cover."""

    x, y, w, h = bbox
    target = (x, y, w, h)
    candidates = []
    for placement in trace.get("placements", []):
        if placement.get("segment_index") != segment_index:
            continue
        source_x, source_y, source_w, source_h = placement["source_bbox"]
        frame_long_bbox = (0, int(placement["y_in_long"]), int(source_w), int(source_h))
        if not _overlap_bbox(target, frame_long_bbox):
            continue

        overlap_x0 = max(x, frame_long_bbox[0])
        overlap_y0 = max(y, frame_long_bbox[1])
        overlap_x1 = min(x + w, frame_long_bbox[0] + frame_long_bbox[2])
        overlap_y1 = min(y + h, frame_long_bbox[1] + frame_long_bbox[3])
        overlap_w = overlap_x1 - overlap_x0
        overlap_h = overlap_y1 - overlap_y0
        if overlap_w <= 0 or overlap_h <= 0:
            continue

        crop_in_frame = (
            int(source_x + overlap_x0),
            int(source_y + overlap_y0 - frame_long_bbox[1]),
            int(overlap_w),
            int(overlap_h),
        )
        candidates.append(
            {
                "frame_index": placement["frame_index"],
                "time_sec": placement["time_sec"],
                "crop_bbox_in_frame": list(crop_in_frame),
                "overlap_bbox_in_long": [int(overlap_x0), int(overlap_y0), int(overlap_w), int(overlap_h)],
                "coverage_area": int(overlap_w * overlap_h),
            }
        )

    candidates.sort(key=lambda item: (-item["coverage_area"], item["frame_index"]))
    if limit is not None:
        return candidates[:limit]
    return candidates


def compact_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Return the small subset typically needed by a model-routing layer."""

    return {
        "trace_schema_version": trace.get("trace_schema_version"),
        "frame_count": trace.get("frame_count"),
        "fps": trace.get("fps"),
        "viewport_bbox": trace.get("viewport_bbox"),
        "segments": trace.get("segments", []),
        "tiles": trace.get("tiles", []),
        "quality": trace.get("quality", {}),
    }
