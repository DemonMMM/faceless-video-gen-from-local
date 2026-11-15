from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ProjectConfigError(ValueError):
    """Raised when a project file does not satisfy the pipeline contract."""


@dataclass(frozen=True)
class Scene:
    id: str
    narration: str
    image_prompt: str
    image: Path | None
    voice: Path | None
    subtitle: Path | None
    duration: float | None


@dataclass(frozen=True)
class Project:
    title: str
    output: Path
    scenes: tuple[Scene, ...]
    source: Path
    tools: dict[str, tuple[str, ...]]


def workspace_root(source: Path) -> Path:
    for candidate in (source.parent, *source.parents):
        if (candidate / "tools").is_dir() and (candidate / "comfyui").is_dir():
            return candidate
    return source.parent


def _required_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _optional_path(data: dict[str, Any], key: str, root: Path) -> Path | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{key} must be a non-empty path when provided")
    return (root / value).resolve()


def load_project(path: str | Path) -> Project:
    source = Path(path).resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectConfigError(f"Project file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectConfigError(f"Invalid JSON in {source}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ProjectConfigError("Project root must be a JSON object")

    title = _required_string(raw, "title", "project")
    output_value = _required_string(raw, "output", "project")
    raw_scenes = raw.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ProjectConfigError("project.scenes must be a non-empty array")

    scenes: list[Scene] = []
    seen_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scenes):
        context = f"project.scenes[{index}]"
        if not isinstance(raw_scene, dict):
            raise ProjectConfigError(f"{context} must be an object")
        scene_id = _required_string(raw_scene, "id", context)
        if scene_id in seen_ids:
            raise ProjectConfigError(f"Duplicate scene id: {scene_id}")
        seen_ids.add(scene_id)

        duration = raw_scene.get("duration")
        if duration is not None and (
            isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0
        ):
            raise ProjectConfigError(f"{context}.duration must be a positive number")

        scenes.append(
            Scene(
                id=scene_id,
                narration=_required_string(raw_scene, "narration", context),
                image_prompt=_required_string(raw_scene, "image_prompt", context),
                image=_optional_path(raw_scene, "image", source.parent),
                voice=_optional_path(raw_scene, "voice", source.parent),
                subtitle=_optional_path(raw_scene, "subtitle", source.parent),
                duration=float(duration) if duration is not None else None,
            )
        )

    raw_tools = raw.get("tools", {})
    if not isinstance(raw_tools, dict):
        raise ProjectConfigError("project.tools must be an object when provided")
    tools: dict[str, tuple[str, ...]] = {}
    for name, command in raw_tools.items():
        if not isinstance(name, str) or not name.strip():
            raise ProjectConfigError("project.tools names must be non-empty strings")
        if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise ProjectConfigError(f"project.tools.{name} must be a non-empty string array")
        tools[name] = tuple(command)

    return Project(
        title=title,
        output=(source.parent / output_value).resolve(),
        scenes=tuple(scenes),
        source=source,
        tools=tools,
    )
