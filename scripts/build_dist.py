from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def _run(argv: list[str]) -> None:
    subprocess.run(argv, cwd=ROOT, check=True)


def main() -> int:
    DIST.mkdir(exist_ok=True)
    for path in DIST.glob("scrollsnap_core-0.1.0*"):
        path.unlink()

    build_module = None
    try:
        import build  # type: ignore

        if hasattr(build, "__file__"):
            module_path = Path(build.__file__).resolve()
            if (module_path.parent / "__main__.py").exists():
                build_module = "build"
    except Exception:
        build_module = None

    if build_module:
        _run([sys.executable, "-m", build_module])
    else:
        _run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "-w", "dist"])
        import setuptools.build_meta as build_meta

        sdist_name = build_meta.build_sdist("dist")
        sdist = DIST / sdist_name
        if not sdist.exists():
            raise FileNotFoundError(sdist)

    wheel = DIST / "scrollsnap_core-0.1.0-py3-none-any.whl"
    sdist = DIST / "scrollsnap_core-0.1.0.tar.gz"
    if not wheel.exists() or not sdist.exists():
        raise FileNotFoundError("Expected wheel and sdist were not created")

    for leftover in DIST.glob(".DS_Store"):
        leftover.unlink()
    for path in ROOT.glob("scrollsnap_core-0.1.0"):
        if path.is_dir():
            shutil.rmtree(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
