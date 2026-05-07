from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from .openclaw_adapter import analyze_scroll_recording, parse_scroll_region, query_scroll_crop
from .trace import BBox, compact_trace, load_trace
from .vision import NoopVisualParser


def _bbox(value: list[int] | tuple[int, int, int, int]) -> BBox:
    if len(value) != 4:
        raise ValueError("bbox must contain exactly four integers: x,y,w,h")
    x, y, w, h = [int(item) for item in value]
    if w <= 0 or h <= 0:
        raise ValueError("bbox width and height must be positive")
    return (x, y, w, h)


def _tool_result(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2),
            }
        ],
        "isError": False,
    }


def _analyze_video(args: dict[str, Any]) -> dict[str, Any]:
    result = analyze_scroll_recording(
        video_path=args["video_path"],
        out_dir=args["out_dir"],
        stream=bool(args.get("stream", True)),
        images=bool(args.get("images", False)),
        sample_fps=args.get("sample_fps"),
        max_frames=args.get("max_frames"),
    )
    return _tool_result(result)


def _query_crops(args: dict[str, Any]) -> dict[str, Any]:
    result = query_scroll_crop(
        trace_path=args["trace_path"],
        segment_index=int(args["segment_index"]),
        bbox=_bbox(args["bbox"]),
        video_path=args.get("video_path"),
        out_dir=args.get("out_dir"),
        limit=int(args.get("limit", 3)),
    )
    return _tool_result(result)


def _compact_trace(args: dict[str, Any]) -> dict[str, Any]:
    return _tool_result(compact_trace(load_trace(args["trace_path"])))


def _parse_region(args: dict[str, Any]) -> dict[str, Any]:
    result = parse_scroll_region(
        trace_path=args["trace_path"],
        video_path=args["video_path"],
        out_dir=args["out_dir"],
        segment_index=int(args["segment_index"]),
        bbox=_bbox(args["bbox"]),
        parser=NoopVisualParser(),
        limit=int(args.get("limit", 2)),
    )
    return _tool_result(result)


TOOLS: dict[str, dict[str, Any]] = {
    "scrollsnap_analyze_video": {
        "description": "Analyze a scroll recording and write trace.json.",
        "handler": _analyze_video,
        "inputSchema": {
            "type": "object",
            "required": ["video_path", "out_dir"],
            "properties": {
                "video_path": {"type": "string"},
                "out_dir": {"type": "string"},
                "stream": {"type": "boolean", "default": True},
                "images": {"type": "boolean", "default": False},
                "sample_fps": {"type": "number"},
                "max_frames": {"type": "integer"},
            },
        },
    },
    "scrollsnap_query_crops": {
        "description": "Find source-frame crops covering a long-image bbox, optionally extracting PNG crops.",
        "handler": _query_crops,
        "inputSchema": {
            "type": "object",
            "required": ["trace_path", "segment_index", "bbox"],
            "properties": {
                "trace_path": {"type": "string"},
                "segment_index": {"type": "integer"},
                "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                "video_path": {"type": "string"},
                "out_dir": {"type": "string"},
                "limit": {"type": "integer", "default": 3},
            },
        },
    },
    "scrollsnap_compact_trace": {
        "description": "Return the compact model-routing subset of trace.json.",
        "handler": _compact_trace,
        "inputSchema": {
            "type": "object",
            "required": ["trace_path"],
            "properties": {"trace_path": {"type": "string"}},
        },
    },
    "scrollsnap_parse_region": {
        "description": "Extract minimal crops for a long-image bbox and return Noop parser payloads.",
        "handler": _parse_region,
        "inputSchema": {
            "type": "object",
            "required": ["trace_path", "video_path", "out_dir", "segment_index", "bbox"],
            "properties": {
                "trace_path": {"type": "string"},
                "video_path": {"type": "string"},
                "out_dir": {"type": "string"},
                "segment_index": {"type": "integer"},
                "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                "limit": {"type": "integer", "default": 2},
            },
        },
    },
}


def tool_list() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        }
        for name, spec in TOOLS.items()
    ]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = TOOLS.get(name)
    if spec is None:
        raise ValueError(f"Unknown tool: {name}")
    handler: Callable[[dict[str, Any]], dict[str, Any]] = spec["handler"]
    return handler(arguments)


def _reply(message_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    payload = {"jsonrpc": "2.0", "id": message_id}
    if error is None:
        payload["result"] = result
    else:
        payload["error"] = error
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "scrollsnap", "version": "0.1.0"},
        }
    if method == "tools/list":
        return {"tools": tool_list()}
    if method == "tools/call":
        return call_tool(params["name"], params.get("arguments") or {})
    if method and method.startswith("notifications/"):
        return None
    raise ValueError(f"Unsupported MCP method: {method}")


def serve_stdio() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            result = handle_message(message)
            if "id" in message and result is not None:
                _reply(message["id"], result=result)
        except Exception as error:  # noqa: BLE001
            message_id = None
            try:
                message_id = json.loads(line).get("id")
            except Exception:
                pass
            _reply(
                message_id,
                error={
                    "code": -32000,
                    "message": str(error),
                    "data": traceback.format_exc(),
                },
            )
    return 0


def main() -> int:
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
