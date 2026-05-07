# scrollsnap-core

Traceable reconstruction of scroll recordings for model-efficient GUI agents.

Languages: [English](README.md) | [简体中文](README.zh-CN.md)

## Abstract

`scrollsnap-core` turns a vertical scroll recording into a compact, queryable
trace: the moving scroll viewport, page/scene boundaries, per-frame long-page
coordinates, optional long-image mosaics, local tiles, and source-frame crop
provenance. The library is designed for agent pipelines, not for end-user
screenshot capture. Its purpose is to avoid sending redundant scroll-video
frames to a vision model when a small trace plus a few exact crops is enough.

The current release is Python-first, deterministic, and built around a stable
`trace.json` contract. It exposes a CLI, Python API, OpenClaw-style adapter,
external visual-parser adapter, and a dependency-light stdio MCP-style server.

## Installation

Install from PyPI:

```bash
pip install scrollsnap-core
```

Local source install:

```bash
python3 -m pip install -e ".[dev]"
scrollsnap --help
```

Optional browser-backed scenario tests:

```bash
python3 -m pip install -e ".[browser]"
python3 -m playwright install chromium
```

The production core is Python/OpenCV/Pillow. An npm wrapper is intentionally
not shipped in this release because a wrapper that silently depends on an
unmanaged Python runtime would not be production-grade.

## Quick Start

Trace-only analysis for model pipelines:

```bash
scrollsnap analyze recording.mp4 --out run/scrollsnap --stream --no-images
scrollsnap compact-trace run/scrollsnap/trace.json
scrollsnap query-crop run/scrollsnap/trace.json \
  --segment 0 --bbox 0,1200,760,640 --video recording.mp4 --out run/crops
scrollsnap estimate-tokens run/scrollsnap/trace.json
```

Full long-image and tile output:

```bash
scrollsnap analyze recording.mp4 --out run/full
```

Validation commands:

```bash
scrollsnap selftest --out artifacts/selftest --frames 96
scrollsnap benchmark --frames 160 --repeats 3
scrollsnap release-report --out reports/release
```

## Python API

```python
from scrollsnap import analyze_scroll_recording, query_scroll_crop

analysis = analyze_scroll_recording(
    "recording.mp4",
    "run/scrollsnap",
    stream=True,
    images=False,
)

crops = query_scroll_crop(
    analysis["trace_path"],
    segment_index=0,
    bbox=(0, 1200, 760, 640),
    video_path="recording.mp4",
    out_dir="run/crops",
    limit=2,
)
```

Trace query helpers:

```python
from scrollsnap.trace import load_trace, tiles_for_bbox, frames_for_y_range, frame_crops_for_bbox

trace = load_trace("run/scrollsnap/trace.json")
tiles = tiles_for_bbox(trace, segment_index=0, bbox=(0, 1200, 760, 640))
frames = frames_for_y_range(trace, segment_index=0, y=1200, height=640)
source_crops = frame_crops_for_bbox(trace, segment_index=0, bbox=(0, 1200, 760, 640), limit=2)
```

## Agent Integration

OpenClaw-style tools:

```bash
scrollsnap openclaw-manifest
scrollsnap openclaw-analyze recording.mp4 --out run/scrollsnap
scrollsnap openclaw-query run/scrollsnap/trace.json \
  --segment 0 --bbox 0,1200,760,640 --video recording.mp4 --out run/crops
```

External visual parser:

```bash
scrollsnap parse-region run/scrollsnap/trace.json \
  --video recording.mp4 \
  --out run/parsed \
  --segment 0 \
  --bbox 0,1200,760,640 \
  --vision-command "python3 my_parser.py --image {image} --context {context_json}"
```

MCP-style stdio server:

```bash
scrollsnap-mcp
```

Exposed tools:

- `scrollsnap_analyze_video`
- `scrollsnap_query_crops`
- `scrollsnap_compact_trace`
- `scrollsnap_parse_region`

## Method

The pipeline is deliberately narrow and explainable:

1. Sample frames and detect the dominant moving scroll region with temporal
   motion energy.
2. Snap the viewport to stable container edges when local evidence supports it.
3. Extract alignment features only inside the detected scroll viewport.
4. Estimate vertical frame-to-frame displacement using coarse row signatures
   and dense local refinement.
5. Use score/confidence thresholds plus contextual post-processing to separate
   fast scrolling from page/scene cuts.
6. Integrate displacements into per-segment long-page coordinates.
7. Optionally build long-image mosaics and overlapping tiles.
8. Export a compact trace that downstream agents can query before requesting
   any image evidence.

The hot path is bounded: viewport detection samples frames; streaming mode
keeps only adjacent alignment features; mosaics can be skipped entirely with
`--stream --no-images`.

## Trace Contract

`trace.json` is the stable API surface:

- `trace_schema_version`
- `frame_count`, `fps`
- `viewport_bbox`
- `transitions`: adjacent-frame `dy`, score, confidence, and cut flag
- `placements`: frame index/time to long-page coordinate mapping
- `segments`: reconstructed page/scene spans
- `tiles`: optional local image tiles with source-frame provenance
- `quality`: aggregate risk signals

Image files are derived artifacts. A production agent can keep only
`trace.json`, then extract source-frame crops on demand.

## Release Benchmark

Generated with:

```bash
PYTHONPATH=src python3 -m scrollsnap.cli release-report \
  --out reports/release \
  --synthetic-frames 160 \
  --synthetic-repeats 3
```

Environment in the checked-in report: Python 3.13.5 on macOS arm64.

### Evaluation Summary

The release report is a full evaluation document, not only a timing table. It
covers protocol, acceptance criteria, scenario coverage, quality signals,
token-budget assumptions, evaluation scope, and threats to validity.

Headline results:

- Direct synthetic reconstruction: 17/17 scenarios passed.
- Scenario coverage: desktop baseline, pauses, nested scroll container, sticky
  header, reverse scroll, page jump, fast scroll, noisy compression, repeated
  list rows, micro scroll, bursty trackpad scroll, long page, large viewport,
  mobile aspect ratio, sparse low-texture page, form/settings UI, fixed overlay.
- Throughput: 90.9-255.1 frames/s; median 215.3 frames/s.
- Viewport throughput: 25.4-41.6 viewport MPix/s; median 31.1 MPix/s.
- Coordinate accuracy: median mean y error 0.00 px; worst max y error 1.00 px.
- Viewport boundary accuracy: median L1 2.0 px; max L1 10 px.
- Quality-risk flags: 0 synthetic scenarios, 0 saved-browser scenarios.

Passing requires exact segment count, viewport L1 <= 18 px, mean y error <=
3.5 px, and max y error <= 9 px. The report also records one corrected isolated
low-texture alignment outlier in the `sparse` scenario.

### Chromium Scenario Checks

The checked-in report includes measurements from three Chromium-rendered
browser recordings produced from local HTML fixtures.

| scenario | frames | fps | viewport L1 | segments | cuts | quality risk | saving vs frames | saving vs native long tiles |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| browser_article | 48 | 68.8 | 1 | 1 | 0 | no | 93.4% | 45.9% |
| browser_dashboard | 48 | 61.1 | 4 | 1 | 0 | no | 93.4% | 36.3% |
| browser_table | 48 | 59.7 | 3 | 1 | 0 | no | 94.3% | 33.3% |

Full machine-readable results are in
[`reports/release/release_benchmark.json`](reports/release/release_benchmark.json)
and the professional Markdown report is in
[`reports/release/evaluation_report.md`](reports/release/evaluation_report.md).

## Token Saving Estimate

The token estimator uses an explicit profile based on the common high-detail
tile accounting shape documented by OpenAI image-input docs: constrain image
dimensions for high-detail accounting, then estimate

```text
image_tokens = 85 + 170 * ceil(width / 512) * ceil(height / 512)
```

The release report compares:

- raw viewport frames: every detected scroll viewport frame
- model-resized long image: one long image after model-side downscaling
- native-resolution long tiles: full long-page resolution preserved as tiles
- trace + selected crops: compact trace plus three representative source-frame
  evidence crops per segment

The headline comparison is against raw viewport frames and native-resolution
long tiles. A model-resized long image can look cheap in token count, but it
does not preserve pixel-level evidence for tall pages.

Median saved-Chromium savings in this release:

- 93.4% versus raw viewport frames
- 36.3% versus native-resolution long-page tiles

The raw-frame baseline is conservative because it uses detected viewport crops,
not full-screen frames.

## Evaluation Scope

This release reports only benchmarks that were actually run for the project:
deterministic synthetic recordings with full reconstruction ground truth and
three Chromium-rendered local browser recordings. No external dataset is
claimed as an accuracy benchmark in this release.

## Limitations

- Vertical scroll reconstruction only.
- Camera-captured perspective videos are out of scope.
- Large dynamic overlays inside the scroll region can reduce confidence.
- Very fast scrolls with almost no overlap are inherently ambiguous.
- Horizontal/two-axis canvas-style applications need a separate model.

## Repository Files

- [`CHANGELOG.md`](CHANGELOG.md): version history
- [`LICENSE`](LICENSE): Apache-2.0
- [`CITATION.cff`](CITATION.cff): research citation metadata
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml): test/build workflow

## Sources

- OpenAI image input token accounting:
  https://platform.openai.com/docs/guides/images-vision
