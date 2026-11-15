from __future__ import annotations

import shutil
import importlib.util
from dataclasses import dataclass

from .config import Project, workspace_root


@dataclass(frozen=True)
class Check:
    name: str
    available: bool
    detail: str


def inspect_project(project: Project) -> tuple[Check, ...]:
    checks: list[Check] = []
    for executable in ("ffmpeg", "ffprobe"):
        path = shutil.which(executable)
        checks.append(
            Check(
                name=executable,
                available=path is not None,
                detail=path or "not found on PATH",
            )
        )

    for tool_name, command in sorted(project.tools.items()):
        executable = shutil.which(command[0])
        checks.append(
            Check(
                name=f"tool:{tool_name}",
                available=executable is not None,
                detail=executable or f"executable '{command[0]}' not found on PATH",
            )
        )
        if any("local_voice_piper.py" in part for part in command):
            piper = shutil.which("piper")
            checks.append(
                Check(
                    name="piper",
                    available=piper is not None,
                    detail=piper or "not found on PATH",
                )
            )
            model_index = command.index("--model") + 1 if "--model" in command else -1
            if model_index > 0 and model_index < len(command):
                model_path = (workspace_root(project.source) / command[model_index]).resolve()
                checks.append(
                    Check(
                        name="piper:model",
                        available=model_path.is_file(),
                        detail=str(model_path),
                    )
                )
        required_modules: tuple[str, ...] = ()
        if any("local_voice_kokoro.py" in part for part in command):
            required_modules = ("kokoro", "numpy", "soundfile")
        elif any("local_subtitle_faster_whisper.py" in part for part in command):
            required_modules = ("faster_whisper",)
        for module in required_modules:
            available = importlib.util.find_spec(module) is not None
            checks.append(
                Check(
                    name=f"python:{module}",
                    available=available,
                    detail="installed" if available else "not installed in the active venv",
                )
            )
    return tuple(checks)


def format_report(checks: tuple[Check, ...]) -> str:
    lines = ["Local runtime doctor", ""]
    for check in checks:
        status = "OK" if check.available else "MISSING"
        lines.append(f"[{status:7}] {check.name}: {check.detail}")
    return "\n".join(lines)
