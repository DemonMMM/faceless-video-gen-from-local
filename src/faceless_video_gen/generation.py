from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

from .config import Project, Scene, workspace_root


class GenerationError(RuntimeError):
    """Raised when a configured local generation command fails."""


def _run_tool(project: Project, tool_name: str, values: dict[str, str]) -> None:
    command = project.tools.get(tool_name)
    if command is None:
        raise GenerationError(
            f"No local '{tool_name}' tool configured. Add project.tools.{tool_name} "
            "as a command array."
        )
    try:
        rendered = [part.format(**values) for part in command]
    except KeyError as exc:
        raise GenerationError(
            f"Tool '{tool_name}' uses unsupported placeholder: {exc.args[0]}"
        ) from exc
    try:
        subprocess.run(rendered, check=True, cwd=workspace_root(project.source))
    except FileNotFoundError as exc:
        raise GenerationError(f"Local executable not found: {rendered[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise GenerationError(
            f"Local '{tool_name}' tool failed with exit code {exc.returncode}: "
            f"{shlex.join(rendered)}"
        ) from exc


def generate_scene_image(project: Project, scene: Scene) -> Path:
    if scene.image is None:
        raise GenerationError(f"Scene {scene.id} needs an image output path")
    scene.image.parent.mkdir(parents=True, exist_ok=True)
    _run_tool(
        project,
        "image",
        {"scene_id": scene.id, "prompt": scene.image_prompt, "output": str(scene.image)},
    )
    if not scene.image.is_file():
        raise GenerationError(f"Image tool completed but did not create {scene.image}")
    return scene.image


def generate_scene_voice(project: Project, scene: Scene) -> Path:
    if scene.voice is None:
        raise GenerationError(f"Scene {scene.id} needs a voice output path")
    scene.voice.parent.mkdir(parents=True, exist_ok=True)
    _run_tool(
        project,
        "voice",
        {"scene_id": scene.id, "text": scene.narration, "output": str(scene.voice)},
    )
    if not scene.voice.is_file():
        raise GenerationError(f"Voice tool completed but did not create {scene.voice}")
    return scene.voice


def generate_scene_subtitle(project: Project, scene: Scene) -> Path:
    if scene.subtitle is None:
        raise GenerationError(f"Scene {scene.id} needs a subtitle output path")
    if scene.voice is None or not scene.voice.is_file():
        raise GenerationError(f"Scene {scene.id} needs a generated voice file first")
    scene.subtitle.parent.mkdir(parents=True, exist_ok=True)
    _run_tool(
        project,
        "subtitle",
        {
            "scene_id": scene.id,
            "audio": str(scene.voice),
            "text": scene.narration,
            "output": str(scene.subtitle),
        },
    )
    if not scene.subtitle.is_file():
        raise GenerationError(f"Subtitle tool completed but did not create {scene.subtitle}")
    return scene.subtitle


def generate_project(
    project: Project,
    *,
    images: bool,
    voices: bool,
    subtitles: bool,
    progress: Callable[[str], None] | None = None,
) -> None:
    for scene in project.scenes:
        if images:
            generate_scene_image(project, scene)
            if progress is not None:
                progress(f"{scene.id}: image complete")
        if voices:
            generate_scene_voice(project, scene)
            if progress is not None:
                progress(f"{scene.id}: narration complete")
        if subtitles:
            generate_scene_subtitle(project, scene)
            if progress is not None:
                progress(f"{scene.id}: subtitles complete")
