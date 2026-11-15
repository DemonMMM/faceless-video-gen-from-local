#!/usr/bin/env python3
"""Create an SRT file locally with faster-whisper."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def _timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--model-dir", type=Path, default=Path("models/whisper"))
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper adapter requires the local 'faster-whisper' package"
        ) from exc

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("FFmpeg is required to decode audio for faster-whisper")
    device = "cpu" if args.device == "auto" else args.device
    args.model_dir.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(
        args.model,
        device=device,
        compute_type="int8",
        download_root=str(args.model_dir.resolve()),
    )
    try:
        decoded = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(args.audio),
                "-f",
                "s16le",
                "-ac",
                "1",
                "-ar",
                "16000",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"FFmpeg could not decode {args.audio}: {exc.stderr.decode()}") from exc
    audio = np.frombuffer(decoded.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = model.transcribe(audio)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                f"{_timestamp(segment.start)} --> {_timestamp(segment.end)}",
                segment.text.strip(),
                "",
            ]
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
