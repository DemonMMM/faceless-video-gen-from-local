#!/usr/bin/env python3
"""Generate speech locally with Kokoro."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError as exc:
        raise SystemExit(
            "Kokoro adapter requires the local 'kokoro' and 'soundfile' packages"
        ) from exc

    pipeline = KPipeline(lang_code="a")
    audio_chunks = [audio for _, _, audio in pipeline(args.text, voice=args.voice, speed=args.speed)]
    if not audio_chunks:
        raise SystemExit("Kokoro returned no audio")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, np.concatenate(audio_chunks), 24000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
