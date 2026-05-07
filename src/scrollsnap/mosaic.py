from __future__ import annotations

import numpy as np

from .imaging import crop_bbox
from .types import FramePlacement


def build_segment_mosaic(frames: list[np.ndarray], placements: list[FramePlacement]) -> np.ndarray:
    if not placements:
        raise ValueError("Cannot build a mosaic with no placements")

    x, y, width, height = placements[0].source_bbox
    long_height = max(item.y_in_long for item in placements) + height

    accum = np.zeros((long_height, width, 3), dtype=np.float32)
    weights = np.zeros((long_height, width, 1), dtype=np.float32)

    for placement in placements:
        crop = crop_bbox(frames[placement.frame_index], placement.source_bbox).astype(np.float32)
        top = placement.y_in_long
        bottom = top + crop.shape[0]
        accum[top:bottom, :, :] += crop
        weights[top:bottom, :, :] += 1.0

    empty = weights[:, :, 0] == 0
    weights[weights == 0] = 1.0
    image = np.clip(accum / weights, 0, 255).astype(np.uint8)
    image[empty] = 255
    return image

