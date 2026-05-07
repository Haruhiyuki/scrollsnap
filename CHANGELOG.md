# Changelog

## 0.1.0 - 2026-05-07

Initial public release.

- Detects vertical scroll viewports from motion energy and edge snapping.
- Reconstructs frame-to-long-page coordinates and page/scene boundaries.
- Writes `trace.json`, optional segment mosaics, and local tiles.
- Provides trace-only streaming analysis for low-memory model pipelines.
- Includes crop query helpers for long-image coordinates.
- Exposes CLI, Python API, OpenClaw-style adapter, visual parser adapter, and stdio MCP-style server.
- Adds synthetic and Chromium-rendered benchmark scenarios.
- Adds release benchmark and visual-token budget reporting.
