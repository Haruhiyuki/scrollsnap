from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from .synthetic import SyntheticRecording, SyntheticTruth
from .types import BBox
from .video import write_video


def _ease_offsets(max_offset: int, count: int, pauses: bool = True) -> list[int]:
    if count <= 1:
        return [0]
    if max_offset <= 0:
        return [0] * count
    moving_count = count
    prefix: list[int] = []
    suffix: list[int] = []
    if pauses and count >= 24:
        pause = max(3, count // 10)
        prefix = [0] * pause
        suffix = [max_offset] * pause
        moving_count = count - len(prefix) - len(suffix)
    t = np.linspace(0.0, 1.0, moving_count)
    eased = 3 * t**2 - 2 * t**3
    return prefix + [int(round(max_offset * item)) for item in eased] + suffix


def _png_to_rgb(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(BytesIO(data)).convert("RGB"), dtype=np.uint8)


def _article_html() -> str:
    sections = []
    palettes = ["#f8fafc", "#fff7ed", "#eef2ff", "#f0fdf4", "#fdf2f8"]
    for index in range(28):
        rows = "".join(
            f"<p><span class='k'>#{index:02d}.{row}</span> "
            f"Model-facing pipelines need exact scroll provenance, stable crops, "
            f"and compact evidence windows across dynamic UI surfaces.</p>"
            for row in range(3 + index % 3)
        )
        code = ""
        if index % 5 == 2:
            code = "<pre>trace.lookup(y=1840, height=720)\\ntrace.frame_at(segment=0, y=1840)</pre>"
        sections.append(
            f"<section style='background:{palettes[index % len(palettes)]}'>"
            f"<h2>Operational section {index:02d}</h2>{rows}{code}</section>"
        )
    return f"""
    <html>
    <head>
      <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; background: #e5e7eb; font-family: Arial, sans-serif; color: #111827; }}
        .top {{ position: fixed; inset: 0 0 auto 0; height: 64px; z-index: 5;
          background: #111827; color: white; display: flex; align-items: center; padding: 0 30px;
          font-size: 17px; font-weight: 700; box-shadow: 0 2px 8px rgba(0,0,0,.18); }}
        main {{ width: 760px; margin: 64px auto 0; background: white; border-left: 1px solid #cbd5e1;
          border-right: 1px solid #cbd5e1; }}
        section {{ min-height: 185px; padding: 22px 30px; border-bottom: 1px solid #cbd5e1; }}
        h2 {{ margin: 0 0 14px; font-size: 23px; }}
        p {{ margin: 9px 0; line-height: 1.5; color: #374151; }}
        .k {{ color: #7c3aed; font-weight: 700; }}
        pre {{ background: #111827; color: #d1fae5; padding: 14px; overflow: hidden; }}
      </style>
    </head>
    <body><div class="top">Research Console</div><main>{''.join(sections)}</main></body>
    </html>
    """


def _dashboard_html() -> str:
    cards = []
    for index in range(64):
        stat = f"{(index * 17) % 91 + 7}%"
        rows = "".join(f"<li>queue item {index:02d}-{row}: observed scroll delta and crop span</li>" for row in range(2))
        cards.append(
            f"<article class='card'><div><h3>Run block {index:02d}</h3><strong>{stat}</strong></div>"
            f"<ul>{rows}</ul></article>"
        )
    return f"""
    <html>
    <head>
      <style>
        * {{ box-sizing: border-box; }}
        body {{ margin:0; font-family: Arial, sans-serif; background:#dbe3ea; color:#172033; overflow:hidden; }}
        .side {{ position:fixed; left:0; top:0; bottom:0; width:220px; background:#202938; color:#dce5ee; padding:22px; }}
        .side h1 {{ font-size:18px; margin:0 0 28px; }}
        .side div {{ height:34px; border-bottom:1px solid rgba(255,255,255,.14); padding-top:8px; }}
        .bar {{ position:fixed; left:220px; right:0; top:0; height:64px; background:#f8fafc; border-bottom:1px solid #b9c4d0;
          display:flex; align-items:center; padding:0 24px; font-weight:700; }}
        .main {{ position:absolute; left:220px; right:0; top:64px; bottom:0; overflow:auto; background:#edf2f7;
          border-left:1px solid #b9c4d0; }}
        .grid {{ padding:20px; display:grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap:14px; }}
        .card {{ min-height:132px; background:white; border:1px solid #cbd5e1; border-radius:6px; padding:16px; box-shadow:0 1px 2px rgba(15,23,42,.06); }}
        .card div {{ display:flex; justify-content:space-between; align-items:center; }}
        h3 {{ margin:0; font-size:17px; }}
        strong {{ font-size:23px; color:#0f766e; }}
        li {{ margin:8px 0; color:#4b5563; }}
      </style>
    </head>
    <body>
      <aside class="side"><h1>Ops Surface</h1><div>Inbox</div><div>Agents</div><div>Runs</div><div>Reports</div></aside>
      <div class="bar">Scroll Container: Evaluation Runs</div>
      <main class="main"><div class="grid">{''.join(cards)}</div></main>
    </body>
    </html>
    """


def _table_html() -> str:
    rows = []
    for index in range(96):
        cells = "".join(f"<td>{index:03d}-{col} signal {(index * (col + 3)) % 157}</td>" for col in range(5))
        rows.append(f"<tr><th>Task {index:03d}</th>{cells}</tr>")
    return f"""
    <html>
    <head>
      <style>
        body {{ margin:0; font-family: Arial, sans-serif; background:#f3f4f6; color:#111827; }}
        .toolbar {{ position:sticky; top:0; z-index:4; height:58px; background:#ffffff; border-bottom:1px solid #c7ced8;
          display:flex; align-items:center; gap:16px; padding:0 24px; font-weight:700; }}
        .pill {{ background:#e0f2fe; color:#075985; padding:8px 12px; border-radius:999px; }}
        .wrap {{ width:920px; margin:0 auto; background:white; border-left:1px solid #d1d5db; border-right:1px solid #d1d5db; }}
        table {{ width:100%; border-collapse:collapse; font-size:14px; }}
        thead th {{ position:sticky; top:58px; background:#1f2937; color:white; z-index:3; }}
        th, td {{ border-bottom:1px solid #d1d5db; padding:13px 16px; text-align:left; }}
        tbody tr:nth-child(2n) {{ background:#f8fafc; }}
        tbody th {{ color:#6d28d9; }}
      </style>
    </head>
    <body>
      <div class="toolbar"><span>Trace Table</span><span class="pill">sticky headers</span></div>
      <div class="wrap"><table><thead><tr><th>Name</th><th>A</th><th>B</th><th>C</th><th>D</th><th>E</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table></div>
    </body>
    </html>
    """


def _scenario_html(name: str) -> str:
    if name == "browser_article":
        return _article_html()
    if name == "browser_dashboard":
        return _dashboard_html()
    if name == "browser_table":
        return _table_html()
    raise ValueError(f"Unknown browser scenario: {name}")


def _scenario_target(name: str) -> tuple[tuple[int, int], BBox, str]:
    if name == "browser_article":
        return (900, 640), (70, 64, 760, 576), "window"
    if name == "browser_dashboard":
        return (1000, 700), (220, 64, 780, 636), ".main"
    if name == "browser_table":
        return (1040, 660), (60, 101, 920, 559), "window"
    raise ValueError(f"Unknown browser scenario: {name}")


def generate_browser_recording(name: str, frame_count: int = 72, fps: float = 12.0) -> SyntheticRecording:
    from playwright.sync_api import sync_playwright

    viewport, bbox, scroll_target = _scenario_target(name)
    html = _scenario_html(name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]}, device_scale_factor=1)
        page.set_content(html, wait_until="load")
        if scroll_target == "window":
            max_offset = int(page.evaluate("document.documentElement.scrollHeight - window.innerHeight"))
        else:
            max_offset = int(
                page.eval_on_selector(scroll_target, "el => Math.max(0, el.scrollHeight - el.clientHeight)")
            )
        offsets = _ease_offsets(max_offset, frame_count)
        frames = []
        for offset in offsets:
            if scroll_target == "window":
                page.evaluate("(y) => window.scrollTo(0, y)", offset)
            else:
                page.eval_on_selector(scroll_target, "(el, y) => { el.scrollTop = y; }", offset)
            page.wait_for_timeout(16)
            frames.append(_png_to_rgb(page.screenshot(type="png", animations="disabled")))
        browser.close()

    truth = SyntheticTruth(
        scenario=name,
        fps=fps,
        frame_size=viewport,
        viewport_bbox=bbox,
        offsets=offsets,
        segment_ids=[0] * frame_count,
        document_heights=[max_offset + bbox[3]],
    )
    return SyntheticRecording(frames=frames, truth=truth)


def write_browser_recording(recording: SyntheticRecording, video_path: str | Path) -> None:
    video_path = Path(video_path)
    write_video(video_path, recording.frames, recording.truth.fps)
    video_path.with_suffix(".truth.json").write_text(
        json.dumps(recording.truth.to_jsonable(), indent=2),
        encoding="utf-8",
    )
