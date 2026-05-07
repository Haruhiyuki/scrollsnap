from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2

from .imaging import clamp_bbox, crop_bbox, save_rgb
from .trace import BBox, frame_crops_for_bbox


def read_video_frame_at_time(video_path: str | Path, time_sec: float):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(time_sec)) * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(time_sec * fps))))
            ok, bgr = cap.read()
        if not ok:
            raise ValueError(f"Could not read frame at {time_sec:.3f}s from {video_path}")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()


def extract_video_crop(
    video_path: str | Path,
    time_sec: float,
    crop_bbox_in_frame: BBox,
    out_path: str | Path,
) -> dict[str, Any]:
    frame = read_video_frame_at_time(video_path, time_sec)
    height, width = frame.shape[:2]
    bbox = clamp_bbox(crop_bbox_in_frame, width, height)
    crop = crop_bbox(frame, bbox)
    save_rgb(out_path, crop)
    return {
        "path": str(out_path),
        "time_sec": float(time_sec),
        "crop_bbox_in_frame": list(bbox),
        "width": int(crop.shape[1]),
        "height": int(crop.shape[0]),
    }


def extract_frame_crops_for_bbox(
    video_path: str | Path,
    trace: dict[str, Any],
    segment_index: int,
    bbox_in_long: BBox,
    out_dir: str | Path,
    limit: int = 3,
    prefix: str = "crop",
) -> list[dict[str, Any]]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    candidates = frame_crops_for_bbox(trace, segment_index=segment_index, bbox=bbox_in_long, limit=limit)
    extracted = []
    for index, candidate in enumerate(candidates):
        crop_path = out_path / f"{prefix}_{index:03d}_frame_{int(candidate['frame_index']):06d}.png"
        metadata = extract_video_crop(
            video_path=video_path,
            time_sec=float(candidate["time_sec"]),
            crop_bbox_in_frame=tuple(candidate["crop_bbox_in_frame"]),
            out_path=crop_path,
        )
        enriched = dict(candidate)
        enriched["path"] = metadata["path"]
        enriched["width"] = metadata["width"]
        enriched["height"] = metadata["height"]
        extracted.append(enriched)
    return extracted

