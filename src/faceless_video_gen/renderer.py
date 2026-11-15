from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Project


class RenderError(RuntimeError):
    """Raised when local video assembly cannot complete."""


def _scene_duration(project: Project, index: int, ffprobe: str) -> float:
    scene = project.scenes[index]
    if scene.duration is not None:
        return scene.duration
    if scene.voice is None or not scene.voice.is_file():
        raise RenderError(f"Scene {scene.id} needs duration or a local voice file")
    executable = shutil.which(ffprobe)
    if executable is None:
        raise RenderError(f"FFprobe executable not found: {ffprobe}")
    try:
        result = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(scene.voice),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise RenderError(f"Could not determine duration for scene {scene.id}") from exc
    if duration <= 0:
        raise RenderError(f"Voice duration for scene {scene.id} must be positive")
    return duration


def _subtitle_filter(path: Path) -> str:
    escaped = str(path).replace("\\", "\\\\").replace("'", "\\'")
    style = (
        "FontName=DejaVu Sans,FontSize=26,Bold=1,PrimaryColour=&H00FFFFFF&,"
        "OutlineColour=&H99000000&,BorderStyle=1,Outline=3,Shadow=0,"
        "Alignment=2,MarginV=64,WrapStyle=2"
    )
    return f"subtitles=filename='{escaped}':force_style='{style}'"


def render_project(project: Project, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> Path:
    executable = shutil.which(ffmpeg)
    if executable is None:
        raise RenderError(f"FFmpeg executable not found: {ffmpeg}")

    missing_images = [
        scene.id for scene in project.scenes if scene.image is None or not scene.image.is_file()
    ]
    if missing_images:
        raise RenderError(f"Missing local image assets for scenes: {', '.join(missing_images)}")
    missing_subtitles = [
        scene.id
        for scene in project.scenes
        if scene.subtitle is not None and not scene.subtitle.is_file()
    ]
    if missing_subtitles:
        raise RenderError(f"Missing local subtitle assets for scenes: {', '.join(missing_subtitles)}")

    project.output.parent.mkdir(parents=True, exist_ok=True)
    segment_dir = project.output.parent / ".segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    clip_durations: list[float] = []
    transition_duration = 0.25
    try:
        for index, scene in enumerate(project.scenes):
            duration = _scene_duration(project, index, ffprobe)
            clip_duration = duration + (
                transition_duration if index < len(project.scenes) - 1 else 0
            )
            segment = segment_dir / f"{index:04d}-{scene.id}.mp4"
            command = [
                executable,
                "-y",
                "-loop",
                "1",
                "-i",
                str(scene.image),
            ]
            if scene.voice is not None:
                if not scene.voice.is_file():
                    raise RenderError(f"Missing local voice asset for scene: {scene.id}")
                command.extend(["-i", str(scene.voice)])
            motion_filter = (
                "zoompan="
                "z='min(zoom+0.0015,1.12)':"
                "x='(iw-iw/zoom)/2+(iw-iw/zoom)*0.22*sin(on/45)':"
                "y='(ih-ih/zoom)/2+(ih-ih/zoom)*0.12*cos(on/55)':"
                "d=1:s=768x512:fps=30"
            )
            command.extend(
                [
                    "-t",
                    str(clip_duration),
                    "-map",
                    "0:v:0",
                    "-c:v",
                    "libx264",
                    "-vf",
                    (
                        f"{motion_filter},{_subtitle_filter(scene.subtitle)},format=yuv420p"
                        if scene.subtitle is not None and scene.subtitle.is_file()
                        else f"{motion_filter},format=yuv420p"
                    ),
                    "-r",
                    "30",
                ]
            )
            if scene.voice is not None:
                command.extend(["-map", "1:a:0", "-c:a", "aac", "-af", "apad"])
            else:
                command.extend(["-an"])
            command.append(str(segment))
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as exc:
                details = exc.stderr.strip() or exc.stdout.strip() or "unknown FFmpeg error"
                raise RenderError(f"FFmpeg failed for scene {scene.id}: {details}") from exc
            segments.append(segment)
            clip_durations.append(clip_duration)

        concat_file = segment_dir / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{segment.as_posix()}'\n" for segment in segments),
            encoding="utf-8",
        )
        has_audio = any(scene.voice is not None for scene in project.scenes)
        audio_concat = segment_dir / "audio.m4a"
        total_duration = sum(clip_durations) - transition_duration * (len(segments) - 1)
        if has_audio:
            audio_command = [
                executable,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-vn",
                "-c:a",
                "aac",
                str(audio_concat),
            ]
            try:
                subprocess.run(audio_command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as exc:
                details = exc.stderr.strip() or exc.stdout.strip() or "unknown FFmpeg error"
                raise RenderError(f"FFmpeg failed while joining audio: {details}") from exc

        inputs = [item for segment in segments for item in ("-i", str(segment))]
        filter_parts: list[str] = []
        current_video = "0:v"
        elapsed = clip_durations[0] - transition_duration
        for index in range(1, len(segments)):
            next_video = f"{index}:v"
            output_label = f"v{index}"
            filter_parts.append(
                f"[{current_video}][{next_video}]xfade=transition=fade:"
                f"duration={transition_duration}:offset={elapsed}[{output_label}]"
            )
            current_video = output_label
            elapsed += clip_durations[index] - transition_duration
        command = [executable, "-y", *inputs]
        if has_audio:
            command.extend(["-i", str(audio_concat)])
        if filter_parts:
            command.extend(["-filter_complex", ";".join(filter_parts), "-map", f"[{current_video}]"])
        else:
            command.extend(["-map", "0:v:0"])
        if has_audio:
            command.extend(["-map", f"{len(segments)}:a:0"])
        command.extend(
            [
                "-t",
                str(total_duration),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
            ]
        )
        if has_audio:
            command.extend(["-c:a", "aac"])
        else:
            command.append("-an")
        command.append(str(project.output))
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            details = exc.stderr.strip() or exc.stdout.strip() or "unknown FFmpeg error"
            raise RenderError(f"FFmpeg failed while joining scenes: {details}") from exc
    finally:
        for segment in segments:
            segment.unlink(missing_ok=True)
        (segment_dir / "concat.txt").unlink(missing_ok=True)
        (segment_dir / "audio.m4a").unlink(missing_ok=True)
        try:
            segment_dir.rmdir()
        except OSError:
            pass

    return project.output
