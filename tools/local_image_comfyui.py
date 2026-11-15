#!/usr/bin/env python3
"""Generate one image through a local ComfyUI API workflow."""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def _request(url: str, *, data: bytes | None = None) -> Any:
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _replace(value: Any, prompt: str, seed: int) -> Any:
    if isinstance(value, str):
        return value.replace("{prompt}", prompt).replace("{seed}", str(seed))
    if isinstance(value, dict):
        return {key: _replace(item, prompt, seed) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, prompt, seed) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    payload = json.dumps(
        {"prompt": _replace(workflow, args.prompt, seed), "client_id": str(uuid.uuid4())}
    ).encode("utf-8")
    try:
        queued = _request(f"{args.server.rstrip('/')}/prompt", data=payload)
        prompt_id = queued["prompt_id"]
        for _ in range(600):
            history = _request(f"{args.server.rstrip('/')}/history/{prompt_id}")
            record = history.get(prompt_id)
            if record and record.get("status", {}).get("completed"):
                break
            time.sleep(1)
        else:
            raise RuntimeError("ComfyUI generation timed out")
        outputs = record.get("outputs", {})
        image = next(
            item
            for node in outputs.values()
            for item in node.get("images", [])
            if item.get("filename")
        )
        query = urllib.parse.urlencode(
            {
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
        )
        with urllib.request.urlopen(f"{args.server.rstrip('/')}/view?{query}", timeout=30) as response:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(response.read())
    except (OSError, KeyError, StopIteration, json.JSONDecodeError) as exc:
        raise SystemExit(f"ComfyUI image generation failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
