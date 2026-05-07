# ScrollSnap OpenClaw Adapter

This directory contains a lightweight OpenClaw-style integration description.
The actual callable adapter lives in `scrollsnap.openclaw_adapter`.

Recommended skill workflow:

1. Record a scroll interaction with OpenClaw computer/browser tooling.
2. Call `analyze_scroll_recording` with `stream=True` and `images=False`.
3. Route agent questions to `query_scroll_crop` using long-page coordinates.
4. Pass extracted crops to the preferred OpenClaw visual module or external
   parser through `parse_scroll_region`.

CLI example:

```bash
PYTHONPATH=src python3 -m scrollsnap.cli openclaw-manifest
```
