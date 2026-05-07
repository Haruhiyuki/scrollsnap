from __future__ import annotations

import argparse
import json

from scrollsnap.benchmark import benchmark_scenarios
from scrollsnap.config import AnalyzerConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=160)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--alignment-max-width", type=int, default=360)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["static_chrome", "pauses", "nested", "sticky", "reverse", "jump"],
    )
    args = parser.parse_args()
    config = AnalyzerConfig(alignment_max_width=args.alignment_max_width)
    results = benchmark_scenarios(args.scenarios, args.frames, args.fps, args.repeats, config)
    print(json.dumps([item.to_jsonable() for item in results], indent=2))
    return 0 if all(item.passed_accuracy for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

