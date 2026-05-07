from __future__ import annotations

import json
from io import BytesIO
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .types import BBox
from .video import write_video


@dataclass(slots=True)
class SyntheticTruth:
    scenario: str
    fps: float
    frame_size: tuple[int, int]
    viewport_bbox: BBox
    offsets: list[int]
    segment_ids: list[int]
    document_heights: list[int]

    def to_jsonable(self) -> dict:
        payload = asdict(self)
        payload["frame_size"] = list(self.frame_size)
        payload["viewport_bbox"] = list(self.viewport_bbox)
        return payload


@dataclass(slots=True)
class SyntheticRecording:
    frames: list[np.ndarray]
    truth: SyntheticTruth


def _font(size: int = 15) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("Arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def make_document(width: int, height: int, seed: int, label: str) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", (width, height), (248, 249, 250))
    draw = ImageDraw.Draw(image)
    font = _font(15)
    small = _font(11)

    palette = [
        (232, 246, 244),
        (255, 244, 224),
        (239, 242, 255),
        (245, 238, 248),
        (234, 246, 226),
        (253, 238, 232),
    ]

    y = 0
    section = 0
    while y < height:
        band_h = int(rng.integers(76, 142))
        color = palette[(section + seed) % len(palette)]
        draw.rectangle([0, y, width, min(height, y + band_h)], fill=color)
        draw.line([0, y, width, y], fill=(196, 202, 208), width=1)

        title = f"{label} section {section:02d}"
        draw.text((18, y + 10), title, fill=(31, 41, 55), font=font)
        for row in range(3):
            row_y = y + 36 + row * 23
            if row_y + 12 >= y + band_h:
                break
            line_w = int(rng.integers(width // 3, width - 48))
            shade = int(rng.integers(95, 165))
            draw.rounded_rectangle(
                [18, row_y, 18 + line_w, row_y + 9],
                radius=3,
                fill=(shade, shade + 12 if shade < 225 else shade, shade + 20 if shade < 215 else shade),
            )
            dot_x = width - 34 - int(rng.integers(0, 40))
            draw.ellipse([dot_x, row_y - 2, dot_x + 13, row_y + 11], fill=(80 + section * 9 % 140, 112, 180))
        draw.text((width - 76, y + band_h - 20), f"y={y:04d}", fill=(75, 85, 99), font=small)
        y += band_h
        section += 1

    for x in range(0, width, 40):
        draw.line([x, 0, x, height], fill=(235, 237, 240), width=1)
    return image


def make_repeated_document(width: int, height: int, seed: int, label: str) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    font = _font(14)
    small = _font(10)
    y = 0
    row = 0
    while y < height:
        fill = (255, 255, 255) if row % 2 == 0 else (241, 245, 249)
        draw.rectangle([0, y, width, min(height, y + 64)], fill=fill)
        draw.line([0, y, width, y], fill=(203, 213, 225), width=1)
        draw.text((16, y + 12), f"{label} item {row:03d}", fill=(30, 41, 59), font=font)
        base = 92 + (row * 13 + seed) % 26
        for col in range(3):
            line_y = y + 38 + col * 7
            line_w = int(width * (0.52 + 0.08 * col)) + int(rng.integers(-12, 12))
            draw.rectangle([92, line_y, min(width - 54, 92 + line_w), line_y + 4], fill=(base, base + 11, base + 19))
        draw.text((width - 62, y + 40), f"y{y:04d}", fill=(71, 85, 105), font=small)
        y += 64
        row += 1
    return image


def make_sparse_document(width: int, height: int, seed: int, label: str) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", (width, height), (252, 253, 255))
    draw = ImageDraw.Draw(image)
    font = _font(15)
    small = _font(10)
    y = 0
    section = 0
    while y < height:
        band_h = int(rng.integers(150, 260))
        draw.rectangle([0, y, width, min(height, y + band_h)], fill=(252, 253, 255))
        draw.line([0, y, width, y], fill=(226, 232, 240), width=1)
        marker = 18 + (section * 37 + seed) % max(36, width - 80)
        draw.rounded_rectangle([marker, y + 28, marker + 44, y + 72], radius=5, fill=(226, 232, 240))
        draw.text((18, y + 28), f"{label} sparse {section:02d}", fill=(55, 65, 81), font=font)
        draw.text((width - 68, y + band_h - 22), f"y{y:04d}", fill=(100, 116, 139), font=small)
        if section % 3 == 1:
            for row in range(3):
                row_y = y + 95 + row * 18
                draw.rectangle([24, row_y, width - 42, row_y + 3], fill=(235, 240, 246))
        y += band_h
        section += 1
    for x in range(0, width, 96):
        draw.line([x, 0, x, height], fill=(246, 248, 251), width=1)
    return image


def make_form_document(width: int, height: int, seed: int, label: str) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", (width, height), (247, 249, 252))
    draw = ImageDraw.Draw(image)
    font = _font(14)
    small = _font(10)
    y = 0
    group = 0
    while y < height:
        band_h = int(rng.integers(118, 178))
        draw.rectangle([0, y, width, min(height, y + band_h)], fill=(255, 255, 255))
        draw.line([0, y, width, y], fill=(209, 216, 226), width=1)
        draw.text((18, y + 12), f"{label} form group {group:02d}", fill=(30, 41, 59), font=font)
        for col in range(2):
            field_x = 18 + col * ((width - 48) // 2)
            field_y = y + 44
            field_w = (width - 66) // 2
            draw.text((field_x, field_y - 15), f"field {group:02d}-{col}", fill=(100, 116, 139), font=small)
            draw.rounded_rectangle([field_x, field_y, field_x + field_w, field_y + 30], radius=4, outline=(190, 199, 213), fill=(248, 250, 252))
            fill_w = int(field_w * float(rng.uniform(0.35, 0.84)))
            draw.rectangle([field_x + 9, field_y + 12, field_x + fill_w, field_y + 16], fill=(148, 163, 184))
        if group % 4 == 2:
            draw.rounded_rectangle([18, y + 88, width - 18, y + 118], radius=4, fill=(239, 246, 255), outline=(191, 219, 254))
            draw.text((30, y + 96), "inline validation and assistant hint", fill=(30, 64, 175), font=small)
        draw.text((width - 62, y + band_h - 20), f"y{y:04d}", fill=(71, 85, 105), font=small)
        y += band_h
        group += 1
    return image


def _degrade_frame(frame: np.ndarray, rng: np.random.Generator, noise_sigma: float, jpeg_quality: int) -> np.ndarray:
    noisy = frame.astype(np.float32)
    if noise_sigma > 0:
        noisy += rng.normal(0.0, noise_sigma, size=noisy.shape).astype(np.float32)
    noisy = np.clip(noisy, 0, 255).astype(np.uint8)
    buffer = BytesIO()
    Image.fromarray(noisy).save(buffer, format="JPEG", quality=jpeg_quality)
    buffer.seek(0)
    return np.asarray(Image.open(buffer).convert("RGB"), dtype=np.uint8)


def _ease_offsets(max_offset: int, count: int, reverse: bool = False, pauses: bool = False) -> list[int]:
    if count <= 1:
        return [0]
    if reverse:
        half = max(2, count // 2)
        down = _ease_offsets(max_offset, half, reverse=False, pauses=False)
        up = list(reversed(down))
        values = (down + up)[0:count]
        while len(values) < count:
            values.append(values[-1])
        return values
    moving_count = count
    prefix = suffix = []
    if pauses and count >= 18:
        pause = max(3, count // 8)
        prefix = [0] * pause
        suffix = [max_offset] * pause
        moving_count = count - len(prefix) - len(suffix)
    t = np.linspace(0.0, 1.0, moving_count)
    eased = 3 * t**2 - 2 * t**3
    values = [int(round(max_offset * item)) for item in eased]
    return list(prefix) + values + list(suffix)


def _micro_offsets(max_offset: int, count: int) -> list[int]:
    if count <= 1:
        return [0]
    target = min(max_offset, max(80, count * 2))
    t = np.linspace(0.0, 1.0, count)
    eased = 0.5 - 0.5 * np.cos(np.pi * t)
    return [int(round(target * item)) for item in eased]


def _bursty_offsets(max_offset: int, count: int) -> list[int]:
    if count <= 1:
        return [0]
    rng = np.random.default_rng(2026 + count + max_offset)
    offsets = [0]
    current = 0
    while len(offsets) < count:
        pause = int(rng.integers(2, 6))
        offsets.extend([current] * min(pause, count - len(offsets)))
        if len(offsets) >= count:
            break
        burst = int(rng.integers(5, 11))
        target = min(max_offset, current + int(rng.integers(90, 240)))
        start = current
        for index in range(1, burst + 1):
            if len(offsets) >= count:
                break
            t = index / burst
            value = int(round(start + (target - start) * (3 * t**2 - 2 * t**3)))
            offsets.append(value)
        current = offsets[-1]
        if current >= max_offset:
            offsets.extend([current] * (count - len(offsets)))
    return offsets[:count]


def _paint_shell(frame_size: tuple[int, int], viewport: BBox, scenario: str) -> Image.Image:
    width, height = frame_size
    image = Image.new("RGB", frame_size, (229, 233, 238))
    draw = ImageDraw.Draw(image)
    font = _font(13)
    x, y, w, h = viewport
    draw.rectangle([0, 0, width, 54], fill=(34, 42, 53))
    draw.text((18, 17), f"scrollsnap synthetic: {scenario}", fill=(241, 245, 249), font=font)
    draw.rectangle([0, 54, 42, height], fill=(213, 218, 226))
    draw.rectangle([x - 1, y - 1, x + w, y + h], outline=(117, 128, 143), width=1)
    draw.rectangle([x + w + 8, y, x + w + 13, y + h], fill=(205, 211, 220))
    draw.rectangle([0, height - 34, width, height], fill=(245, 247, 250))
    return image


def _compose_frame(
    doc: Image.Image,
    offset: int,
    frame_size: tuple[int, int],
    viewport: BBox,
    scenario: str,
    sticky_height: int = 0,
) -> np.ndarray:
    shell = _paint_shell(frame_size, viewport, scenario)
    draw = ImageDraw.Draw(shell)
    x, y, w, h = viewport
    moving_y = y
    moving_h = h
    if sticky_height:
        moving_y += sticky_height
        moving_h -= sticky_height
        draw.rectangle([x, y, x + w, y + sticky_height], fill=(255, 255, 255))
        draw.line([x, y + sticky_height - 1, x + w, y + sticky_height - 1], fill=(193, 199, 208))
        draw.text((x + 14, y + 10), "Sticky in-page toolbar", fill=(17, 24, 39), font=_font(14))
    crop = doc.crop((0, offset, w, offset + moving_h))
    shell.paste(crop, (x, moving_y))
    max_offset = max(1, doc.height - moving_h)
    thumb_h = max(28, int(moving_h * moving_h / doc.height))
    thumb_y = moving_y + int((moving_h - thumb_h) * offset / max_offset)
    draw.rounded_rectangle([x + w + 8, thumb_y, x + w + 13, thumb_y + thumb_h], radius=3, fill=(90, 100, 116))
    return np.asarray(shell, dtype=np.uint8)


def _add_fixed_overlay(frame: np.ndarray, viewport: BBox, label: str) -> np.ndarray:
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    x, y, w, h = viewport
    overlay_w = min(178, w - 28)
    overlay_h = 58
    ox = x + w - overlay_w - 18
    oy = y + h - overlay_h - 20
    draw.rounded_rectangle([ox, oy, ox + overlay_w, oy + overlay_h], radius=7, fill=(255, 255, 255), outline=(177, 190, 205))
    draw.text((ox + 12, oy + 11), label, fill=(15, 23, 42), font=_font(12))
    draw.rectangle([ox + 12, oy + 34, ox + overlay_w - 16, oy + 39], fill=(203, 213, 225))
    return np.asarray(image, dtype=np.uint8)


def generate_synthetic_recording(
    scenario: str = "static_chrome",
    frame_count: int = 72,
    fps: float = 12.0,
    seed: int = 11,
) -> SyntheticRecording:
    frame_size = (540, 520)
    viewport: BBox = (58, 82, 410, 344)
    sticky_height = 0

    if scenario == "nested":
        frame_size = (680, 560)
        viewport = (184, 92, 420, 348)
    elif scenario == "sticky":
        sticky_height = 42
    elif scenario == "mobile":
        frame_size = (430, 760)
        viewport = (54, 86, 330, 584)
    elif scenario == "large_viewport":
        frame_size = (1120, 820)
        viewport = (216, 96, 760, 600)

    x, y, w, h = viewport
    moving_viewport = (x, y + sticky_height, w, h - sticky_height)

    doc_h = 1620
    if scenario == "fast":
        doc_h = 1900
    if scenario == "long_page":
        doc_h = 3600
    if scenario == "large_viewport":
        doc_h = 3200
    if scenario == "mobile":
        doc_h = 2600
    if scenario == "repeated":
        doc_a = make_repeated_document(viewport[2], doc_h, seed, "R")
    elif scenario == "sparse":
        doc_a = make_sparse_document(viewport[2], doc_h, seed, "S")
    elif scenario == "form":
        doc_a = make_form_document(viewport[2], doc_h, seed, "F")
    else:
        doc_a = make_document(viewport[2], doc_h, seed, "A")

    if scenario == "jump":
        first = frame_count // 2
        second = frame_count - first
        doc_b = make_document(viewport[2], doc_h, seed + 19, "B")
        h = moving_viewport[3]
        offsets_a = _ease_offsets(doc_h - h, first, pauses=True)
        offsets_b = _ease_offsets(doc_h - h, second, pauses=True)
        offsets = offsets_a + offsets_b
        segment_ids = [0] * first + [1] * second
        docs = [doc_a] * first + [doc_b] * second
    else:
        h = moving_viewport[3]
        reverse = scenario == "reverse"
        pauses = scenario in {
            "pauses",
            "sticky",
            "nested",
            "static_chrome",
            "noisy",
            "repeated",
            "sparse",
            "form",
            "mobile",
            "large_viewport",
            "long_page",
            "fixed_overlay",
        }
        if scenario == "micro_scroll":
            offsets = _micro_offsets(doc_h - h, frame_count)
        elif scenario == "bursty":
            offsets = _bursty_offsets(doc_h - h, frame_count)
        else:
            offsets = _ease_offsets(doc_h - h, frame_count, reverse=reverse, pauses=pauses)
        segment_ids = [0] * frame_count
        docs = [doc_a] * frame_count

    frames = [
        _compose_frame(
            doc=docs[index],
            offset=offsets[index],
            frame_size=frame_size,
            viewport=viewport,
            scenario=scenario,
            sticky_height=sticky_height,
        )
        for index in range(frame_count)
    ]
    if scenario == "noisy":
        rng = np.random.default_rng(seed + 101)
        frames = [_degrade_frame(frame, rng, noise_sigma=4.5, jpeg_quality=58) for frame in frames]
    if scenario == "fixed_overlay":
        frames = [_add_fixed_overlay(frame, viewport, "Fixed assistant panel") for frame in frames]
    truth = SyntheticTruth(
        scenario=scenario,
        fps=fps,
        frame_size=frame_size,
        viewport_bbox=moving_viewport,
        offsets=offsets,
        segment_ids=segment_ids,
        document_heights=[doc_h] if scenario != "jump" else [doc_h, doc_h],
    )
    return SyntheticRecording(frames=frames, truth=truth)


def write_synthetic_recording(recording: SyntheticRecording, video_path: str | Path) -> None:
    video_path = Path(video_path)
    write_video(video_path, recording.frames, recording.truth.fps)
    truth_path = video_path.with_suffix(".truth.json")
    truth_path.write_text(json.dumps(recording.truth.to_jsonable(), indent=2), encoding="utf-8")


def load_synthetic_truth(path: str | Path) -> SyntheticTruth:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return SyntheticTruth(
        scenario=payload["scenario"],
        fps=float(payload["fps"]),
        frame_size=tuple(payload["frame_size"]),
        viewport_bbox=tuple(payload["viewport_bbox"]),
        offsets=[int(item) for item in payload["offsets"]],
        segment_ids=[int(item) for item in payload["segment_ids"]],
        document_heights=[int(item) for item in payload["document_heights"]],
    )
