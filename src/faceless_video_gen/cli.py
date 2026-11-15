from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ProjectConfigError, load_project
from .doctor import format_report, inspect_project
from .generation import GenerationError, generate_project
from .pipeline import build_plan, format_plan
from .renderer import RenderError, render_project
from .runtime import RuntimeError_, run_project
from .ui import serve


def _init(path: Path) -> None:
    if path.exists():
        raise ProjectConfigError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "title": "My faceless video",
                "output": "work/output.mp4",
                "scenes": [
                    {
                        "id": "scene-01",
                        "narration": "Replace this narration with your script.",
                        "image_prompt": "A cinematic establishing shot, no text",
                        "image": "assets/scene-01.png",
                        "voice": "assets/scene-01.wav",
                        "subtitle": "assets/scene-01.srt",
                        "duration": 4,
                    },
                ],
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
                        "python",
                        "tools/local_voice_piper.py",
                        "--model",
                        "models/piper/en_US-lessac-high.onnx",
                        "--text",
                        "{text}",
                        "--output",
                        "{output}",
                    ],
                    "subtitle": [
                        "python",
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
    print(f"Created {path}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="faceless-video")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a starter project file")
    init_parser.add_argument("path", nargs="?", type=Path, default=Path("project.json"))

    plan_parser = subparsers.add_parser("plan", help="validate and print a project plan")
    plan_parser.add_argument("path", type=Path)

    render_parser = subparsers.add_parser("render", help="assemble local scene assets with FFmpeg")
    render_parser.add_argument("path", type=Path)
    render_parser.add_argument("--ffmpeg", default="ffmpeg")
    render_parser.add_argument("--ffprobe", default="ffprobe")

    doctor_parser = subparsers.add_parser(
        "doctor", help="check local media tools and configured model commands"
    )
    doctor_parser.add_argument("path", type=Path)

    generate_parser = subparsers.add_parser(
        "generate", help="run configured local image and voice tools"
    )
    generate_parser.add_argument("path", type=Path)
    generate_parser.add_argument("--images-only", action="store_true")
    generate_parser.add_argument("--voices-only", action="store_true")
    generate_parser.add_argument("--subtitles", action="store_true")

    run_parser = subparsers.add_parser(
        "run", help="run the complete local pipeline and stop owned model processes"
    )
    run_parser.add_argument("path", nargs="?", type=Path, default=Path("project.json"))

    ui_parser = subparsers.add_parser("ui", help="start the local browser interface")
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", type=int, default=8090)

    args = parser.parse_args()
    try:
        if args.command == "init":
            _init(args.path)
        elif args.command == "plan":
            project = load_project(args.path)
            print(format_plan(project, build_plan(project)))
        elif args.command == "doctor":
            project = load_project(args.path)
            print(format_report(inspect_project(project)))
        elif args.command == "run":
            print(f"Rendered {run_project(load_project(args.path))}")
        elif args.command == "ui":
            serve(Path.cwd(), args.host, args.port)
        else:
            project = load_project(args.path)
            if args.command == "render":
                print(f"Rendered {render_project(project, args.ffmpeg, args.ffprobe)}")
            else:
                images = not args.voices_only and not args.subtitles
                voices = not args.images_only and not args.subtitles
                if not images and not voices and not args.subtitles:
                    parser.error("Choose a generation mode")
                generate_project(
                    project,
                    images=images,
                    voices=voices,
                    subtitles=args.subtitles,
                )
                print("Local generation completed")
    except (ProjectConfigError, RenderError, GenerationError, RuntimeError_) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
