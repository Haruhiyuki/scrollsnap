from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

BBox = tuple[int, int, int, int]
TRACE_SCHEMA_VERSION = "0.2.0"


@dataclass(slots=True)
class Transition:
    from_frame: int
    to_frame: int
    dy: float
    score: float
    second_score: float
    confidence: float
    is_cut: bool
    was_corrected: bool = False


@dataclass(slots=True)
class FramePlacement:
    frame_index: int
    time_sec: float
    segment_index: int
    raw_y: float
    y_in_long: int
    source_bbox: BBox


@dataclass(slots=True)
class SegmentResult:
    segment_index: int
    frame_start: int
    frame_end: int
    long_width: int
    long_height: int
    image_path: str | None = None


@dataclass(slots=True)
class TileMetadata:
    segment_index: int
    tile_index: int
    path: str
    bbox_in_long: BBox
    source_frames: list[int]


@dataclass(slots=True)
class AnalysisResult:
    frame_count: int
    fps: float
    viewport_bbox: BBox
    transitions: list[Transition]
    placements: list[FramePlacement]
    segments: list[SegmentResult]
    tiles: list[TileMetadata] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    mosaics: dict[int, Any] = field(default_factory=dict, repr=False)

    def to_jsonable(self) -> dict[str, Any]:
        payload = {
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "viewport_bbox": list(self.viewport_bbox),
            "transitions": [asdict(item) for item in self.transitions],
            "placements": [asdict(item) for item in self.placements],
            "segments": [asdict(item) for item in self.segments],
            "tiles": [asdict(item) for item in self.tiles],
            "quality": self.quality,
        }
        for placement in payload["placements"]:
            placement["source_bbox"] = list(placement["source_bbox"])
        for tile in payload["tiles"]:
            tile["bbox_in_long"] = list(tile["bbox_in_long"])
        return payload
