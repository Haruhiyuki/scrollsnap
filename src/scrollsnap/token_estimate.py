from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from .trace import BBox, compact_trace, frame_crops_for_bbox


@dataclass(frozen=True, slots=True)
class ImageTokenProfile:
    """Tile-based image-token proxy.

    The default profile mirrors the commonly documented high-detail image
    accounting shape: a fixed base cost plus a per-512px-tile cost. Providers
    and models can change accounting, so the profile is deliberately explicit
    and serializable instead of hidden in the estimator.
    """

    name: str = "tile_512_base85_tile170"
    tile_size: int = 512
    base_tokens: int = 85
    tile_tokens: int = 170
    max_dimension: int = 2048
    short_side_target: int = 768
    resize_high_detail: bool = True


DEFAULT_IMAGE_TOKEN_PROFILE = ImageTokenProfile()


@dataclass(slots=True)
class ImageTokenEstimate:
    width: int
    height: int
    billable_width: int
    billable_height: int
    tiles_x: int
    tiles_y: int
    tile_count: int
    image_tokens: int

    def to_jsonable(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class TraceTokenEstimate:
    profile: dict[str, Any]
    raw_viewport_frame_tokens: int
    long_image_tokens: int
    native_long_tile_tokens: int
    tile_image_tokens: int | None
    compact_trace_chars: int
    compact_trace_text_tokens_estimate: int
    query_crop_tokens: int
    query_count: int
    trace_plus_query_tokens: int
    savings_vs_raw_frames: float
    savings_vs_long_images: float
    savings_vs_native_long_tiles: float

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


def estimate_image_tokens(
    width: int,
    height: int,
    profile: ImageTokenProfile = DEFAULT_IMAGE_TOKEN_PROFILE,
) -> ImageTokenEstimate:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    billable_width, billable_height = _billable_dimensions(width, height, profile)
    tiles_x = max(1, math.ceil(billable_width / profile.tile_size))
    tiles_y = max(1, math.ceil(billable_height / profile.tile_size))
    tile_count = tiles_x * tiles_y
    return ImageTokenEstimate(
        width=int(width),
        height=int(height),
        billable_width=int(billable_width),
        billable_height=int(billable_height),
        tiles_x=int(tiles_x),
        tiles_y=int(tiles_y),
        tile_count=int(tile_count),
        image_tokens=int(profile.base_tokens + tile_count * profile.tile_tokens),
    )


def _billable_dimensions(width: int, height: int, profile: ImageTokenProfile) -> tuple[int, int]:
    if not profile.resize_high_detail:
        return int(width), int(height)

    scaled_width = float(width)
    scaled_height = float(height)
    longest = max(scaled_width, scaled_height)
    if profile.max_dimension > 0 and longest > profile.max_dimension:
        scale = profile.max_dimension / longest
        scaled_width *= scale
        scaled_height *= scale

    shortest = min(scaled_width, scaled_height)
    if profile.short_side_target > 0 and shortest > profile.short_side_target:
        scale = profile.short_side_target / shortest
        scaled_width *= scale
        scaled_height *= scale

    return max(1, int(round(scaled_width))), max(1, int(round(scaled_height)))


def estimate_text_tokens(chars: int, chars_per_token: float = 4.0) -> int:
    if chars <= 0:
        return 0
    return int(math.ceil(chars / chars_per_token))


def default_query_bboxes(
    trace: dict[str, Any],
    *,
    windows_per_segment: int = 3,
    window_height: int = 720,
) -> list[tuple[int, BBox]]:
    """Select representative evidence windows for token budgeting."""

    queries: list[tuple[int, BBox]] = []
    for segment in trace.get("segments", []):
        segment_index = int(segment["segment_index"])
        width = int(segment["long_width"])
        height = int(segment["long_height"])
        crop_h = min(int(window_height), height)
        if crop_h <= 0:
            continue
        if windows_per_segment <= 1 or height <= crop_h:
            y_values = [0]
        else:
            max_y = height - crop_h
            y_values = [
                int(round(max_y * index / (windows_per_segment - 1)))
                for index in range(windows_per_segment)
            ]
        for y in dict.fromkeys(y_values):
            queries.append((segment_index, (0, int(y), width, crop_h)))
    return queries


def _sum_segment_image_tokens(trace: dict[str, Any], profile: ImageTokenProfile) -> int:
    total = 0
    for segment in trace.get("segments", []):
        total += estimate_image_tokens(int(segment["long_width"]), int(segment["long_height"]), profile).image_tokens
    return total


def _native_tile_profile(profile: ImageTokenProfile) -> ImageTokenProfile:
    return ImageTokenProfile(
        name=f"{profile.name}_native_no_resize",
        tile_size=profile.tile_size,
        base_tokens=profile.base_tokens,
        tile_tokens=profile.tile_tokens,
        max_dimension=profile.max_dimension,
        short_side_target=profile.short_side_target,
        resize_high_detail=False,
    )


def _sum_tile_image_tokens(trace: dict[str, Any], profile: ImageTokenProfile) -> int | None:
    tiles = trace.get("tiles", [])
    if not tiles:
        return None
    total = 0
    for tile in tiles:
        _, _, width, height = tile["bbox_in_long"]
        total += estimate_image_tokens(int(width), int(height), profile).image_tokens
    return total


def _sum_query_crop_tokens(
    trace: dict[str, Any],
    queries: list[tuple[int, BBox]],
    profile: ImageTokenProfile,
    crops_per_query: int,
) -> int:
    total = 0
    for segment_index, bbox in queries:
        crops = frame_crops_for_bbox(trace, segment_index, bbox, limit=crops_per_query)
        if crops:
            for crop in crops:
                _, _, width, height = crop["crop_bbox_in_frame"]
                total += estimate_image_tokens(int(width), int(height), profile).image_tokens
        else:
            _, _, width, height = bbox
            total += estimate_image_tokens(int(width), int(height), profile).image_tokens
    return total


def estimate_trace_tokens(
    trace: dict[str, Any],
    *,
    queries: list[tuple[int, BBox]] | None = None,
    profile: ImageTokenProfile = DEFAULT_IMAGE_TOKEN_PROFILE,
    crops_per_query: int = 1,
) -> TraceTokenEstimate:
    _, _, viewport_width, viewport_height = trace["viewport_bbox"]
    frame_count = int(trace["frame_count"])
    per_frame = estimate_image_tokens(int(viewport_width), int(viewport_height), profile).image_tokens
    raw_tokens = frame_count * per_frame
    long_tokens = _sum_segment_image_tokens(trace, profile)
    native_long_tokens = _sum_segment_image_tokens(trace, _native_tile_profile(profile))
    tile_tokens = _sum_tile_image_tokens(trace, profile)

    selected_queries = queries if queries is not None else default_query_bboxes(trace)
    compact = compact_trace(trace)
    compact_chars = len(json.dumps(compact, separators=(",", ":")))
    compact_text_tokens = estimate_text_tokens(compact_chars)
    query_tokens = _sum_query_crop_tokens(trace, selected_queries, profile, crops_per_query)
    trace_plus_query = compact_text_tokens + query_tokens

    return TraceTokenEstimate(
        profile=asdict(profile),
        raw_viewport_frame_tokens=int(raw_tokens),
        long_image_tokens=int(long_tokens),
        native_long_tile_tokens=int(native_long_tokens),
        tile_image_tokens=int(tile_tokens) if tile_tokens is not None else None,
        compact_trace_chars=int(compact_chars),
        compact_trace_text_tokens_estimate=int(compact_text_tokens),
        query_crop_tokens=int(query_tokens),
        query_count=len(selected_queries),
        trace_plus_query_tokens=int(trace_plus_query),
        savings_vs_raw_frames=1.0 - (trace_plus_query / raw_tokens if raw_tokens else 0.0),
        savings_vs_long_images=1.0 - (trace_plus_query / long_tokens if long_tokens else 0.0),
        savings_vs_native_long_tiles=1.0 - (trace_plus_query / native_long_tokens if native_long_tokens else 0.0),
    )
