# Architecture

## Goal

The primary product is a compact, machine-readable trace for model pipelines.
Images are derived artifacts. A downstream agent should be able to ask for a
small crop by page coordinate, frame index, or tile id instead of sending a full
video or full long screenshot to a vision model.

## Pipeline

1. Decode or receive RGB frames.
2. Sample frames to detect the dominant moving scroll region.
3. Snap the moving region to stable visual edges when available.
4. Stream through frames and estimate vertical displacement in the detected
   region with coarse-to-fine row-signature alignment.
5. Mark transitions as cuts after contextual post-processing, so fast scrolls
   are not confused with page jumps.
6. Integrate displacements into per-segment long-image coordinates.
7. Average overlapping crops into segment mosaics.
8. Export model-sized tiles with source-frame provenance.

## Trace contract

`trace.json` contains:

- `viewport_bbox`: source-frame crop used for reconstruction
- `transitions`: adjacent-frame displacement, score, confidence, cut flag
- `placements`: mapping from `frame_index` and time to long-image y coordinate
- `segments`: page/document slices after cut detection
- `tiles`: local crops and the source frames that cover them
- `quality`: aggregate confidence, score, cut, and max-motion diagnostics

This is the stable API surface. The image files can be regenerated.

## Performance design

- Viewport detection uses a bounded frame sample.
- Alignment is constrained to the detected region.
- Alignment features are downsampled in x only, preserving y-pixel coordinates.
- Feature extraction is streamed with a one-frame cache.
- Mosaics can be skipped with `--no-images` for trace-only analysis.
- `--stream --no-images` avoids retaining full frames for low-memory trace
  generation.
- The benchmark command reports accuracy and throughput together.

Release benchmark command: `PYTHONPATH=src python3 -m scrollsnap.cli release-report --out reports/release --synthetic-frames 160 --synthetic-repeats 3`.

Current checked-in results:

- 17/17 direct synthetic reconstruction scenarios passed
- 90.9-255.1 analyzed FPS; median 215.3 FPS
- 25.4-41.6 viewport MPix/s; median 31.1 MPix/s
- 0.00 px median mean y error on the current synthetic set
- 1.00 px worst max y error on the current synthetic set
- 2.0 px median viewport L1 error; 10 px max viewport L1 error
- 1 isolated low-texture alignment outlier corrected and reported in `quality`
- 93.4% median estimated image-token saving versus raw viewport frames on saved Chromium recordings
- 36.3% median estimated image-token saving versus native-resolution long-page tiles on saved Chromium recordings

Offline analysis of saved Chromium-rendered scenarios:

- `browser_article`: viewport L1 1, one segment, no false cuts
- `browser_dashboard`: viewport L1 4, one segment, no false cuts
- `browser_table`: viewport L1 3, one segment, no false cuts

## Known hard cases

- Large repetitive lists where false overlaps are visually plausible.
- Very fast scrolls with little or no overlap between adjacent frames.
- Dynamic overlays inside the scroll area.
- Horizontal or two-axis scroll.
- Perspective/camera-captured scroll videos.
- Pages with large blank margins where the useful content bounds and widget
  viewport bounds differ.

## Test strategy

There does not appear to be a standard benchmark specifically for "scroll
recording to traceable long-page reconstruction". Existing UI datasets are
useful for visual diversity but usually provide screenshots/actions rather than
scroll-video ground truth. This repo therefore starts with deterministic
synthetic recordings that include exact offsets and page ids.

The direct synthetic scenarios are:

- `static_chrome`: desktop chrome around one scrolling region
- `pauses`: stationary frames before and after movement
- `nested`: scroll region offset inside a larger app shell
- `sticky`: in-page sticky header excluded from the moving region
- `reverse`: down and up scroll in one segment
- `jump`: visual page switch requiring a new segment
- `fast`: high scroll velocity with smaller temporal overlap
- `noisy`: JPEG compression and sensor-like noise
- `repeated`: repeated list rows with weak local uniqueness
- `micro_scroll`: subtle one-to-few-pixel movement
- `bursty`: trackpad-like bursts separated by pauses
- `long_page`: larger coordinate range
- `large_viewport`: wide desktop viewport and larger pixel area
- `mobile`: narrow/tall mobile-like aspect ratio
- `sparse`: low-texture bands with sparse anchors
- `form`: form/settings UI with repeated controls
- `fixed_overlay`: small fixed overlay occluding the scroll content

Chromium-backed scenarios are also available when local browser execution is
allowed:

```bash
PYTHONPATH=src python3 -m scrollsnap.cli browser-selftest --out artifacts/browser_selftest --frames 48
SCROLLSNAP_RUN_BROWSER_TESTS=1 python3 -m pytest -m browser
```

These render local HTML in Chromium and cover article pages, nested dashboard
scroll containers, and sticky table headers.
