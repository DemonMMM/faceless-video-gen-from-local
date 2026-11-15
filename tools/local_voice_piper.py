#!/usr/bin/env python3
"""Generate speech locally with Piper."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--piper", default="piper")
    args = parser.parse_args()

    if not args.model.is_file():
        raise SystemExit(f"Piper model not found: {args.model}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                args.piper,
                "-m",
                str(args.model),
                "-f",
                str(args.output),
            ],
            input=args.text,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit(f"Piper executable not found: {args.piper}") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Piper failed with exit code {exc.returncode}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
