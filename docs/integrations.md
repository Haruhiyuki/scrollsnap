# Integrations

## OpenClaw-Style Adapter

`scrollsnap.openclaw_adapter` exposes skill-friendly functions:

- `analyze_scroll_recording(video_path, out_dir, stream=True, images=False)`
- `query_scroll_crop(trace_path, segment_index, bbox, video_path=None, out_dir=None)`
- `parse_scroll_region(trace_path, segment_index, bbox, video_path, out_dir, parser=None)`
- `openclaw_tool_manifest()`

The intended OpenClaw flow is:

1. Use computer-use/browser tooling to record or collect a scroll video.
2. Call `analyze_scroll_recording` to produce `trace.json`.
3. Use `query_scroll_crop` to select minimal source-frame crops for a long-page
   coordinate range.
4. Send those crops to OpenClaw's visual module, OCR, OmniParser, or a VLM.
5. Return compact parsed evidence to the agent instead of full video/long image.

CLI equivalents:

```bash
PYTHONPATH=src python3 -m scrollsnap.cli openclaw-manifest
PYTHONPATH=src python3 -m scrollsnap.cli openclaw-analyze recording.mp4 --out run/scrollsnap
PYTHONPATH=src python3 -m scrollsnap.cli openclaw-query run/scrollsnap/trace.json \
  --segment 0 --bbox 0,1200,760,640 --video recording.mp4 --out run/crops
```

Installed-package equivalents:

```bash
scrollsnap openclaw-analyze recording.mp4 --out run/scrollsnap
scrollsnap openclaw-query run/scrollsnap/trace.json \
  --segment 0 --bbox 0,1200,760,640 --video recording.mp4 --out run/crops
```

## Vision Adapter

`scrollsnap.vision` defines a small parser interface:

```python
class VisualParser:
    def parse_image(self, image_path: str, context: dict) -> dict:
        ...
```

Included adapters:

- `NoopVisualParser`: returns crop/context metadata; useful for integration checks.
- `CommandVisualParser`: calls an external command with `{image}` and
  `{context_json}` placeholders, then parses stdout as JSON when possible.

Example:

```bash
PYTHONPATH=src python3 -m scrollsnap.cli parse-region run/scrollsnap/trace.json \
  --video recording.mp4 \
  --out run/parsed-crops \
  --segment 0 \
  --bbox 0,1200,760,640 \
  --vision-command "python3 my_parser.py --image {image} --context {context_json}"
```

## MCP Server

The repository includes a dependency-free stdio JSON-RPC MCP-style server:

```bash
PYTHONPATH=src python3 -m scrollsnap.mcp_server
```

Installed script name:

```bash
scrollsnap-mcp
```

Exposed tools:

- `scrollsnap_analyze_video`
- `scrollsnap_query_crops`
- `scrollsnap_compact_trace`
- `scrollsnap_parse_region`

The server uses newline-delimited JSON-RPC messages over stdio. It is kept
small intentionally; if an environment requires the official MCP Python SDK,
the tool handlers in `scrollsnap.mcp_server` can be reused behind that transport.

## Token Budgeting

Use `estimate-tokens` to quantify the visual-token budget implied by a trace:

```bash
scrollsnap estimate-tokens run/scrollsnap/trace.json
```

The estimator reports raw viewport-frame cost, model-resized long-image cost,
native-resolution long-image tile cost, and `trace + selected crops` cost. The
native-resolution long-image tile baseline is the relevant comparison when a
pipeline needs pixel-level evidence instead of a downscaled full-page preview.
