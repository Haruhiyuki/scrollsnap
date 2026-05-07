from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator

import cv2
import numpy as np


def _sample_stride(native_fps: float, sample_fps: float | None) -> int:
    if sample_fps is not None and sample_fps > 0 and native_fps > sample_fps:
        return max(1, int(round(native_fps / sample_fps)))
    return 1


def read_video_frames(
    path: str | Path,
    sample_fps: float | None = None,
    max_frames: int | None = None,
) -> tuple[list[np.ndarray], float, list[float]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")

    native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    stride = _sample_stride(native_fps, sample_fps)
    effective_fps = native_fps / stride

    frames: list[np.ndarray] = []
    times: list[float] = []
    index = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if index % stride == 0:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            frames.append(rgb)
            times.append(index / native_fps)
            if max_frames is not None and len(frames) >= max_frames:
                break
        index += 1
    cap.release()
    return frames, effective_fps, times


def iter_video_frames(
    path: str | Path,
    sample_fps: float | None = None,
    max_frames: int | None = None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")

    native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    stride = _sample_stride(native_fps, sample_fps)
    accepted_index = 0
    native_index = 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if native_index % stride == 0:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                yield accepted_index, native_index / native_fps, rgb
                accepted_index += 1
                if max_frames is not None and accepted_index >= max_frames:
                    break
            native_index += 1
    finally:
        cap.release()


def video_effective_fps(path: str | Path, sample_fps: float | None = None) -> float:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")
    native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.release()
    return native_fps / _sample_stride(native_fps, sample_fps)


def read_video_viewport_samples(
    path: str | Path,
    sample_count: int,
    sample_fps: float | None = None,
    max_frames: int | None = None,
) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")
    native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    stride = _sample_stride(native_fps, sample_fps)
    native_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    if native_total > 0:
        accepted_total = (native_total + stride - 1) // stride
        if max_frames is not None:
            accepted_total = min(accepted_total, max_frames)
        target_count = min(sample_count, accepted_total)
        targets = set(np.linspace(0, accepted_total - 1, target_count).round().astype(int).tolist())
    else:
        targets = set(range(sample_count))

    samples: list[np.ndarray] = []
    for accepted_index, _, frame in iter_video_frames(path, sample_fps=sample_fps, max_frames=max_frames):
        if native_total > 0:
            if accepted_index in targets:
                samples.append(frame)
        else:
            samples.append(frame)
            if len(samples) >= sample_count:
                break
    return samples


def write_video(path: str | Path, frames: list[np.ndarray], fps: float) -> None:
    if not frames:
        raise ValueError("Cannot write an empty video")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise ValueError(f"Could not open video writer: {path}")
    for frame in frames:
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        writer.write(bgr)
    writer.release()
