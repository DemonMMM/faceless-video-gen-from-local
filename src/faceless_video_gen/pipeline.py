from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Project, Scene


@dataclass(frozen=True)
class WorkUnit:
    scene_id: str
    image_prompt: str
    narration: str
    image_path: Path | None
    voice_path: Path | None
    duration: float | None


def build_plan(project: Project) -> tuple[WorkUnit, ...]:
    return tuple(
        WorkUnit(
            scene_id=scene.id,
            image_prompt=scene.image_prompt,
            narration=scene.narration,
            image_path=scene.image,
            voice_path=scene.voice,
            duration=scene.duration,
        )
        for scene in project.scenes
    )


def format_plan(project: Project, units: tuple[WorkUnit, ...]) -> str:
    lines = [
        f"Project: {project.title}",
        f"Output: {project.output}",
        f"Scenes: {len(units)}",
        "",
    ]
    for number, unit in enumerate(units, start=1):
        lines.extend(
            [
                f"{number}. {unit.scene_id}",
                f"   image: {unit.image_path or '[not generated]'}",
                f"   voice: {unit.voice_path or '[not generated]'}",
                f"   duration: {unit.duration or '[from voice or renderer]'}",
                f"   prompt: {unit.image_prompt}",
            ]
        )
    return "\n".join(lines)
