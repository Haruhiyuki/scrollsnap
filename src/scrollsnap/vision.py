from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class VisualParser(Protocol):
    def parse_image(self, image_path: str | Path, context: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class NoopVisualParser:
    name: str = "noop"

    def parse_image(self, image_path: str | Path, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "parser": self.name,
            "image_path": str(image_path),
            "context": context,
            "items": [],
        }


@dataclass(slots=True)
class CommandVisualParser:
    """Adapter for external OCR/UI/VLM commands.

    Each command argument can use `{image}` and `{context_json}` placeholders.
    Stdout is parsed as JSON when possible; otherwise it is returned as text.
    """

    command: str | list[str]
    timeout_sec: float = 60.0

    def parse_image(self, image_path: str | Path, context: dict[str, Any]) -> dict[str, Any]:
        context_json = json.dumps(context, separators=(",", ":"))
        if isinstance(self.command, str):
            template = shlex.split(self.command)
        else:
            template = list(self.command)
        argv = [item.format(image=str(image_path), context_json=context_json) for item in template]
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
        )
        stdout = completed.stdout.strip()
        parsed: Any
        try:
            parsed = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            parsed = {"text": stdout}
        return {
            "parser": "command",
            "image_path": str(image_path),
            "returncode": completed.returncode,
            "stdout": parsed,
            "stderr": completed.stderr.strip(),
        }

