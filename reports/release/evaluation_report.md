# ScrollSnap Evaluation Report

Generated: `2026-05-07T01:36:05.178598+00:00`

Environment: Python `3.13.5` on `macOS-26.4-arm64-arm-64bit-Mach-O`.

## Abstract

This report evaluates ScrollSnap as a scroll-video reconstruction component for
model-facing GUI-agent pipelines. The primary target is not screenshot quality;
it is a trace contract that lets an agent map video frames to long-page
coordinates, detect page/scene boundaries, and request the minimum image crops
needed for downstream visual parsing.

## Executive Summary

- Direct synthetic reconstruction: `17/17` scenarios passed (`100.0%`).
- Synthetic throughput range: `90.9`-`255.1` frames/s; median `215.3` frames/s.
- Synthetic viewport throughput range: `25.4`-`41.6` viewport MPix/s; median `31.1` MPix/s.
- Synthetic coordinate error: median mean y error `0.00` px; worst max y error `1.00` px.
- Synthetic viewport boundary error: median L1 `2.0` px; max L1 `10` px.
- Quality-risk flags: `0` synthetic scenarios and `0` saved-browser scenarios.
- Corrected isolated alignment outliers: `1` transitions across all synthetic runs.
- Saved Chromium videos: `3` scenarios, median `61.1` frames/s, max viewport L1 `4` px.
- Median estimated token saving on saved Chromium videos: `93.4%` vs raw viewport frames; `36.3%` vs native-resolution long-page tiles.

## Evaluation Protocol

The direct benchmark uses deterministic recordings with complete ground truth:
source frames, viewport bbox, page/scene segment id per frame, and y-offset per
frame within each segment. Each scenario is run with the same analyzer
configuration. Throughput is reported as the median of repeated in-memory
analyses after fixture generation, so video encoding/decoding does not dominate
the algorithm benchmark.

Saved Chromium videos are evaluated separately because they are realistic
browser renders but do not currently include per-frame y-offset truth files in
the release artifact. They are used for viewport/cut/quality/token-budget
validation, not as the headline y-coordinate accuracy benchmark.

## Acceptance Criteria

| metric | threshold or policy |
| --- | --- |
| segment_count | actual segment count must equal ground truth |
| viewport_l1_error_px | <= 18 |
| mean_abs_y_error_px | <= 3.5 |
| max_abs_y_error_px | <= 9.0 |
| quality_risk | reported but not used as a pass/fail override |

## Scenario Coverage Matrix

| scenario | surface | stressors | expected behavior |
| --- | --- | --- | --- |
| static_chrome | desktop page | baseline scroll viewport, browser chrome, start/end pauses | single segment |
| pauses | desktop page | long stationary prefix/suffix | no false cuts during pauses |
| nested | app shell | scrolling sub-container offset inside static UI | detect nested moving region |
| sticky | desktop page | in-page sticky toolbar | exclude sticky header from moving viewport |
| reverse | desktop page | downward then upward scroll | one coordinate-consistent segment |
| jump | document switch | hard visual page change | two segments |
| fast | desktop page | large adjacent-frame displacement | fast scroll without false cut |
| noisy | compressed video | JPEG artifacts and Gaussian noise | robust alignment under degradation |
| repeated | list | weak local uniqueness, repeated rows | avoid false repeated-row matches |
| micro_scroll | desktop page | subtle one-to-few-pixel motion | retain small displacement precision |
| bursty | desktop page | trackpad-like bursts separated by pauses | no false cuts across burst transitions |
| long_page | long document | large coordinate range and mosaic span | stable coordinate integration |
| large_viewport | wide desktop | large pixel area and long page | throughput remains practical |
| mobile | mobile-like viewport | narrow/tall aspect ratio | viewport detection adapts to mobile layout |
| sparse | low-texture document | large blank bands and sparse anchors | alignment does not overfit blank regions |
| form | form/settings UI | dense controls, repeated fields, inline hints | coordinate stability on operational UI |
| fixed_overlay | desktop page | fixed assistant panel occluding content | robustness to small non-scrolling overlay |

## Synthetic Reconstruction Benchmark

| scenario | surface | stressors | frames | fps | MPix/s | score p95 | conf p05 | viewport L1 | mean abs y | max abs y | max abs dy | segments | cuts | corrected | quality risk | pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| static_chrome | desktop page | baseline scroll viewport, browser chrome, start/end pauses | 160 | 219.6 | 31.1 | 0.0066 | 0.0750 | 2 | 0.00 | 0.00 | 16 | 1/1 | 0 | 0 | no | yes |
| pauses | desktop page | long stationary prefix/suffix | 160 | 213.7 | 30.3 | 0.0066 | 0.0750 | 2 | 0.00 | 0.00 | 16 | 1/1 | 0 | 0 | no | yes |
| nested | app shell | scrolling sub-container offset inside static UI | 160 | 195.4 | 28.7 | 0.0064 | 0.0780 | 2 | 0.00 | 0.00 | 16 | 1/1 | 0 | 0 | no | yes |
| sticky | desktop page | in-page sticky toolbar | 160 | 248.9 | 31.1 | 0.0095 | 0.0678 | 4 | 0.00 | 0.00 | 17 | 1/1 | 0 | 0 | no | yes |
| reverse | desktop page | downward then upward scroll | 160 | 225.2 | 31.9 | 0.0074 | 0.0729 | 2 | 0.00 | 0.00 | 25 | 1/1 | 0 | 0 | no | yes |
| jump | document switch | hard visual page change | 160 | 221.3 | 31.4 | 0.0089 | 0.0671 | 2 | 0.00 | 0.00 | 159 | 2/2 | 1 | 0 | no | yes |
| fast | desktop page | large adjacent-frame displacement | 160 | 212.9 | 30.2 | 0.0075 | 0.0737 | 2 | 0.00 | 0.00 | 15 | 1/1 | 0 | 0 | no | yes |
| noisy | compressed video | JPEG artifacts and Gaussian noise | 160 | 204.3 | 29.0 | 0.0225 | 0.0670 | 2 | 0.00 | 0.00 | 16 | 1/1 | 0 | 0 | no | yes |
| repeated | list | weak local uniqueness, repeated rows | 160 | 215.3 | 30.5 | 0.0084 | 0.0053 | 2 | 0.00 | 0.00 | 16 | 1/1 | 0 | 0 | no | yes |
| micro_scroll | desktop page | subtle one-to-few-pixel motion | 160 | 227.5 | 32.3 | 0.0056 | 0.0761 | 2 | 0.00 | 0.00 | 4 | 1/1 | 0 | 0 | no | yes |
| bursty | desktop page | trackpad-like bursts separated by pauses | 160 | 214.2 | 30.4 | 0.0065 | 0.0858 | 2 | 0.00 | 0.00 | 54 | 1/1 | 0 | 0 | no | yes |
| long_page | long document | large coordinate range and mosaic span | 160 | 226.4 | 32.1 | 0.0082 | 0.0460 | 2 | 0.00 | 0.00 | 42 | 1/1 | 0 | 0 | no | yes |
| large_viewport | wide desktop | large pixel area and long page | 160 | 90.9 | 41.6 | 0.0042 | 0.0839 | 2 | 0.00 | 0.00 | 33 | 1/1 | 0 | 0 | no | yes |
| mobile | mobile-like viewport | narrow/tall aspect ratio | 160 | 131.1 | 25.4 | 0.0042 | 0.1002 | 2 | 0.00 | 0.00 | 26 | 1/1 | 0 | 0 | no | yes |
| sparse | low-texture document | large blank bands and sparse anchors | 160 | 255.1 | 36.0 | 0.0125 | 0.0215 | 0 | 0.58 | 1.00 | 16 | 1/1 | 0 | 1 | no | yes |
| form | form/settings UI | dense controls, repeated fields, inline hints | 160 | 232.9 | 33.7 | 0.0066 | 0.0084 | 10 | 0.00 | 0.00 | 16 | 1/1 | 0 | 0 | no | yes |
| fixed_overlay | desktop page | fixed assistant panel occluding content | 160 | 211.6 | 30.0 | 0.0293 | 0.0688 | 2 | 0.00 | 0.00 | 16 | 1/1 | 0 | 0 | no | yes |

## Saved Chromium Video Benchmark

| scenario | frames | fps | viewport L1 | segments | cuts | max abs dy | quality risk | raw frame tokens | native long tokens | trace+crop tokens | saving vs frames | saving vs native long tiles |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| browser_article | 48 | 68.8 | 1 | 1 | 0 | 314 | no | 36720 | 4505 | 2436 | 93.4% | 45.9% |
| browser_dashboard | 48 | 61.1 | 4 | 1 | 0 | 206 | no | 36720 | 3825 | 2437 | 93.4% | 36.3% |
| browser_table | 48 | 59.7 | 3 | 1 | 0 | 138 | no | 36720 | 3145 | 2097 | 94.3% | 33.3% |

## Evaluation Scope

This report only includes benchmarks that were actually run for this release:
deterministic synthetic recordings with full reconstruction ground truth and
saved Chromium-rendered local browser recordings. No external dataset is
claimed as an accuracy benchmark in this release.

## Token Estimation Method

Token estimates use the explicit `tile_512_base85_tile170` profile. For high
detail accounting it first constrains images to a 2048px longest side and
scales down images whose shortest side remains above 768px, then applies:

`image_tokens = 85 + 170 * ceil(width / 512) * ceil(height / 512)`

The reported minimal-evidence strategy sends the compact trace plus three
representative source-frame evidence crops per segment. The raw baseline sends
every detected viewport frame, not the full screen, so the savings estimate is
conservative for full-screen video-to-image pipelines. The native long-tile
baseline keeps full long-page resolution by disabling model-side long-image
downscaling; it is the fair long-image baseline when exact pixel evidence is
required.

## Threats to Validity

- Synthetic scenarios provide exact labels but cannot cover all live desktop
  rendering behavior.
- Saved Chromium videos are realistic local renders, but this report treats
  them as viewport/cut/token checks unless y-offset truth is available.
- Very low-overlap scrolls remain information-limited; quality flags should be
  monitored by production pipelines.
- Token estimates are model-profile estimates, not billing guarantees.

## Reproduction

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
PYTHONPATH=src python3 -m scrollsnap.cli selftest --out artifacts/release_selftest --frames 96
PYTHONPATH=src python3 -m scrollsnap.cli release-report --out reports/release --synthetic-frames 160 --synthetic-repeats 3
```
