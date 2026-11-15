import json

import pytest

from faceless_video_gen.config import ProjectConfigError, load_project
from faceless_video_gen.doctor import format_report, inspect_project
from faceless_video_gen.renderer import RenderError, render_project
from faceless_video_gen.runtime import project_from_request


def test_load_project_resolves_paths_relative_to_project(tmp_path):
    project_file = tmp_path / "project.json"
    project_file.write_text(
        json.dumps(
            {
                "title": "Test",
                "output": "work/out.mp4",
                "scenes": [
                    {
                        "id": "one",
                        "narration": "Hello",
                        "image_prompt": "A mountain",
                        "image": "assets/one.png",
                    }
                ],
                "tools": {"image": ["python", "tools/image.py", "{prompt}"]},
            }
        ),
        encoding="utf-8",
    )

    project = load_project(project_file)

    assert project.output == (tmp_path / "work/out.mp4").resolve()
    assert project.scenes[0].image == (tmp_path / "assets/one.png").resolve()
    assert project.tools["image"] == ("python", "tools/image.py", "{prompt}")


def test_load_project_rejects_duplicate_scene_ids(tmp_path):
    project_file = tmp_path / "project.json"
    project_file.write_text(
        json.dumps(
            {
                "title": "Test",
                "output": "out.mp4",
                "scenes": [
                    {"id": "one", "narration": "A", "image_prompt": "A"},
                    {"id": "one", "narration": "B", "image_prompt": "B"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="Duplicate scene id"):
        load_project(project_file)


def test_render_requires_local_images(tmp_path):
    project_file = tmp_path / "project.json"
    project_file.write_text(
        json.dumps(
            {
                "title": "Test",
                "output": "out.mp4",
                "scenes": [
                    {
                        "id": "one",
                        "narration": "A",
                        "image_prompt": "A",
                        "image": "missing.png",
                        "duration": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RenderError, match="Missing local image assets"):
        render_project(load_project(project_file))


def test_render_requires_configured_subtitle_asset(tmp_path):
    project_file = tmp_path / "project.json"
    project_file.write_text(
        json.dumps(
            {
                "title": "Test",
                "output": "out.mp4",
                "scenes": [
                    {
                        "id": "one",
                        "narration": "A",
                        "image_prompt": "A",
                        "image": "image.png",
                        "subtitle": "missing.srt",
                        "duration": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "image.png").write_bytes(b"image")

    with pytest.raises(RenderError, match="Missing local subtitle assets"):
        render_project(load_project(project_file))


def test_doctor_reports_configured_tool_status(tmp_path):
    project_file = tmp_path / "project.json"
    project_file.write_text(
        json.dumps(
            {
                "title": "Test",
                "output": "out.mp4",
                "scenes": [
                    {"id": "one", "narration": "A", "image_prompt": "A"}
                ],
                "tools": {"image": ["definitely-not-installed"]},
            }
        ),
        encoding="utf-8",
    )

    report = format_report(inspect_project(load_project(project_file)))

    assert "tool:image" in report
    assert "MISSING" in report


def test_project_from_request_stays_relative_to_project(tmp_path):
    project_path = project_from_request(
        tmp_path, "Make a 30 sec video about a man alone on a subway."
    )
    project = load_project(project_path)

    assert project.title == "A Man Alone On A Subway"
    assert len(project.scenes) == 18
    assert sum(scene.duration or 0 for scene in project.scenes) == 30
    assert project.output.parent == (tmp_path / "work/videos").resolve()
    assert project.output.suffix == ".mp4"
