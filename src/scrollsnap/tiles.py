from __future__ import annotations

from pathlib import Path

import numpy as np

from .imaging import save_rgb
from .types import BBox, FramePlacement, TileMetadata


def _overlap_1d(a0: int, a1: int, b0: int, b1: int) -> bool:
    return max(a0, b0) < min(a1, b1)


def write_tiles(
    image: np.ndarray,
    placements: list[FramePlacement],
    segment_index: int,
    out_dir: str | Path,
    tile_height: int,
    overlap: int,
) -> list[TileMetadata]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    height, width = image.shape[:2]
    step = max(1, tile_height - overlap)

    tiles: list[TileMetadata] = []
    y = 0
    index = 0
    while y < height:
        bottom = min(height, y + tile_height)
        top = max(0, bottom - tile_height) if bottom == height else y
        crop = image[top:bottom, :, :]
        tile_name = f"segment_{segment_index:03d}_tile_{index:03d}.png"
        tile_path = out_path / tile_name
        save_rgb(tile_path, crop)

        source_frames = [
            placement.frame_index
            for placement in placements
            if _overlap_1d(top, bottom, placement.y_in_long, placement.y_in_long + placement.source_bbox[3])
        ]
        bbox: BBox = (0, top, width, bottom - top)
        tiles.append(
            TileMetadata(
                segment_index=segment_index,
                tile_index=index,
                path=str(tile_path),
                bbox_in_long=bbox,
                source_frames=source_frames,
            )
        )

        if bottom == height:
            break
        y += step
        index += 1

    return tiles

