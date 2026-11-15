from __future__ import annotations

import json
import re
import sys
import uuid
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .config import Project, workspace_root
from .generation import generate_project
from .renderer import render_project


class RuntimeError_(RuntimeError):
    """Raised when a managed local runtime cannot start or stop cleanly."""


def _comfyui_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/system_stats", timeout=2):
            return True
    except (OSError, urllib.error.URLError):
        return False


def run_project(
    project: Project,
    *,
    comfyui_python: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8188,
    progress: Callable[[str], None] | None = None,
) -> Path:
    root = workspace_root(project.source)
    image_tool = project.tools.get("image", ())
    needs_comfyui = any("local_image_comfyui.py" in part for part in image_tool)
    executable = comfyui_python or root / "comfyui/.venv/bin/python"
    if needs_comfyui and not executable.is_file():
        raise RuntimeError_(f"ComfyUI Python executable not found: {executable}")

    base_url = f"http://{host}:{port}"
    process: subprocess.Popen[bytes] | None = None
    if needs_comfyui and not _comfyui_ready(base_url):
        log_path = root / "work/support/comfyui.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("wb")
        try:
            process = subprocess.Popen(
                [
                    str(executable),
                    str(root / "comfyui/main.py"),
                    "--listen",
                    host,
                    "--port",
                    str(port),
                    "--disable-auto-launch",
                ],
                cwd=root,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_file.close()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError_(f"ComfyUI exited early; inspect {log_path}")
            if _comfyui_ready(base_url):
                break
            time.sleep(1)
        else:
            process.terminate()
            process.wait(timeout=10)
            raise RuntimeError_(f"ComfyUI did not become ready; inspect {log_path}")

    try:
        if progress is not None:
            progress("Starting local generation")
        generate_project(
            project,
            images=True,
            voices=True,
            subtitles=True,
            progress=progress,
        )
        if progress is not None:
            progress("Assembling video with FFmpeg")
        return render_project(project)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def project_from_request(root: Path, request: str) -> Path:
    duration_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?)\b",
        request,
        flags=re.IGNORECASE,
    )
    duration = 30.0
    if duration_match:
        duration = float(duration_match.group(1))
        if duration_match.group(2).lower().startswith(("minute", "min")):
            duration *= 60
    topic = re.sub(
        r"\bmake\s+(?:a\s+)?\d+(?:\.\d+)?\s*(?:seconds?|secs?|minutes?|mins?)\s*"
        r"(?:video\s+)?(?:about|on)\s+",
        "",
        request,
        flags=re.IGNORECASE,
    ).strip(" .")
    if not topic:
        topic = request.strip()
    scene_count = max(1, min(18, round(duration * 0.6)))
    scene_duration = duration / scene_count
    character = (
        "the same voxel-cartoon character in every scene, blocky square head, "
        "teal hoodie, dark blue pants, red sneakers, simple friendly face, "
        "anime-inspired cel-shaded 3D style, no photorealism"
    )
    beats = (
        "A cinematic establishing shot of {topic}, {character}, no text",
        "A closer moment with {character} connected to {topic}, cinematic lighting, no text",
        "A reflective detail showing {character} in {topic}, shallow depth of field, no text",
        "A wide atmospheric view of {character} in {topic}, cinematic composition, no text",
        "A quiet closing image of {character} connected to {topic}, cinematic lighting, no text",
    )
    if "bank" in topic.lower() and "dollar" in topic.lower():
        narration_beats = (
            "{topic}.",
            "One dollar opened an impossible door.",
            "The building looked ordinary from outside.",
            "Inside, the new owner found secrets.",
            "Old ledgers told a different story.",
            "Every room held another surprise.",
            "The keys felt heavier than expected.",
            "Then the first problem arrived.",
            "Debt, silence, and broken trust.",
            "Everyone wanted the deal to fail.",
            "But the new owner kept moving.",
            "One brave idea changed everything.",
            "The empty bank began to wake.",
            "People returned, one by one.",
            "A strange bargain became a second chance.",
            "Sometimes value hides in plain sight.",
            "One dollar bought more than a building.",
            "It bought a future.",
        )
    else:
        narration_beats = (
            "{topic}.",
            "The world moves, but nothing changes.",
            "Crowds pass without noticing.",
            "A familiar place feels different.",
            "Small details reveal a hidden story.",
            "Every sound becomes part of it.",
            "The moment slowly starts to change.",
            "A single thought returns, quietly.",
            "Even silence can feel crowded.",
            "The journey continues through the night.",
            "One small choice changes the mood.",
            "The character looks ahead, still waiting.",
            "Outside, the city keeps moving.",
            "Inside, a new feeling takes shape.",
            "Being alone is not the same as lost.",
            "Sometimes quiet moments teach us most.",
            "The ordinary becomes unforgettable.",
            "And the journey finally feels like home.",
        )
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    support_dir = root / "work/support" / run_id
    support_dir.mkdir(parents=True, exist_ok=True)
    scenes = []
    for index in range(scene_count):
        scene_id = f"scene-{index + 1:02d}"
        scenes.append(
            {
                "id": scene_id,
                "narration": narration_beats[index % len(narration_beats)].format(topic=topic),
                "image_prompt": beats[index % len(beats)].format(topic=topic, character=character),
                "image": f"{scene_id}.png",
                "voice": f"{scene_id}.wav",
                "subtitle": f"{scene_id}.srt",
                "duration": (
                    round(scene_duration, 2)
                    if index < scene_count - 1
                    else round(duration - round(scene_duration, 2) * (scene_count - 1), 2)
                ),
            }
        )
    project_path = support_dir / "project.json"
    project_path.write_text(
        json.dumps(
            {
                "title": topic[:80].title(),
                "output": f"../../videos/{run_id}.mp4",
                "scenes": scenes,
                "tools": {
                    "image": [
                        "node",
                        "three-renderer/render_scene.mjs",
                        "--scene-id",
                        "{scene_id}",
                        "--prompt",
                        "{prompt}",
                        "--seed",
                        "1337",
                        "--output",
                        "{output}",
                    ],
                    "voice": [
                        sys.executable,
                        "tools/local_voice_piper.py",
                        "--model",
                        "models/piper/en_US-lessac-high.onnx",
                        "--piper",
                        str(Path(sys.executable).with_name("piper")),
                        "--text",
                        "{text}",
                        "--output",
                        "{output}",
                    ],
                    "subtitle": [
                        sys.executable,
                        "tools/local_subtitle_faster_whisper.py",
                        "--audio",
                        "{audio}",
                        "--model-dir",
                        "models/whisper",
                        "--output",
                        "{output}",
                    ],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_path
