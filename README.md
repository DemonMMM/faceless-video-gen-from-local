# Faceless Video Gen

Local-first orchestration for making faceless videos from generated images, voiceovers, subtitles, and music.

The project intentionally separates:

1. **Planning** - turn a script into ordered scenes.
2. **Generation** - local adapters create images, speech, and transcripts.
3. **Assembly** - FFmpeg combines existing assets into a video.

No hosted API is required by the core. Model runners are configured as local adapters and can be added without changing the pipeline contract.

## Requirements

- Python 3.11+
- FFmpeg on `PATH`
- Local model runtimes installed separately as needed (for example ComfyUI, Ollama, whisper.cpp, Piper, or another local runner)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

faceless-video init
faceless-video plan project.json
faceless-video doctor project.json
```

`plan` validates the project and prints the work units without invoking any model. This keeps the first run safe and makes the local generation steps explicit.
`doctor` checks FFmpeg, FFprobe, and the executable behind every configured local model command.

## Local model commands

Generation is deliberately command-based so every model stays on this computer. Add commands to
the project file using these placeholders:

- `image`: `{scene_id}`, `{prompt}`, `{output}`
- `voice`: `{scene_id}`, `{text}`, `{output}`
- `subtitle`: `{scene_id}`, `{audio}`, `{text}`, `{output}`

Example using local wrapper scripts:

```json
"tools": {
  "image": ["python", "tools/local_image.py", "--prompt", "{prompt}", "--output", "{output}"],
  "voice": ["python", "tools/local_voice.py", "--text", "{text}", "--output", "{output}"],
  "subtitle": ["python", "tools/local_subtitle.py", "--audio", "{audio}", "--output", "{output}"]
}
```

Then run:

```bash
faceless-video generate project.json
faceless-video generate project.json --subtitles
faceless-video render project.json
```

The wrappers can call ComfyUI, Stable Diffusion, Piper, or another installed local
runtime. The core never sends prompts, audio, or scripts over the network.

## Selected local adapters

The project supports these local image paths:

- **UI runs:** Three.js voxel scenes rendered through project-local Chromium.
- **Optional model runs:** ComfyUI at `http://127.0.0.1:8188`. Put an API-format workflow at
  `models/comfyui/workflow.json`; include `{prompt}` in the positive text field and `{seed}` in
  the seed field.
- **Voice:** Piper through `tools/local_voice_piper.py`.
- **Subtitles:** faster-whisper through `tools/local_subtitle_faster_whisper.py`.

These adapters are local-only and fail clearly when their Python packages, model files, workflow,
or local server are unavailable. The project does not download model weights automatically.

Install the transcription and audio packages into the project venv when you are ready:

```bash
python -m pip install numpy soundfile faster-whisper
```

Piper is invoked as a local executable and does not require Kokoro or its Python dependencies.
Place the Piper voice model and its `.json` companion under `models/piper/`. The project does not
download model weights automatically.

The configured `en_US-lessac-high` Piper model is now expected at:

```text
models/piper/en_US-lessac-high.onnx
models/piper/en_US-lessac-high.onnx.json
```

## ComfyUI

ComfyUI source and its Python environment are installed inside `comfyui/`. Start it from the
project root with:

```bash
comfyui/.venv/bin/python comfyui/main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
```

Keep the ComfyUI window running while `faceless-video generate project.json` runs. The image
adapter talks only to `127.0.0.1:8188`. A Stable Diffusion 1.5 checkpoint is stored at
`comfyui/models/checkpoints/v1-5-pruned-emaonly.safetensors`, and the API-format workflow is at
`models/comfyui/workflow.json`.

The faster-whisper adapter stores its model cache under `models/whisper/`, so transcription
weights also remain inside the project.

## First successful run

The starter `project.json` has been run successfully end to end. It generated:

```text
assets/scene-01.png
assets/scene-01.wav
assets/scene-01.srt
work/output.mp4
```

Run the same pipeline again with:

```bash
faceless-video run project.json
```

`run` owns the ComfyUI process it starts and shuts it down in all normal success and failure
paths. It also regenerates the image, high-quality Piper voice, faster-whisper subtitles, and
final video in one command.

## Local interactive UI

Start the browser UI from the project root:

```bash
faceless-video ui
```

Open `http://127.0.0.1:8090`. Enter one natural-language request, for example:

```text
Make a 30 sec video about a man alone on a subway.
```

The local planner extracts the requested duration, creates a multi-scene plan, and runs the same
managed pipeline. The UI server itself does not keep model processes running between requests;
each request starts and stops its owned ComfyUI process.

The studio updates its status live while each scene image, narration, and subtitle completes.
When FFmpeg finishes, the page displays the video player and a direct local video link without
requiring a refresh. Requests are split into multiple visual scenes automatically. For example,
a 30-second request currently creates 18 scenes of about 1.7 seconds each, with a separate
generated image, voiceover, and subtitle file per scene before FFmpeg assembles the final video.

Final videos are written only to `work/videos/`. Run support files are isolated under
`work/support/<run-id>/`, including the request plan, scene images, audio, subtitles, and logs.

The visual planner uses a consistent voxel-cartoon character bible instead of photorealistic
humans: the same blocky character, clothing colors, and style are repeated in every prompt, and
the image seed is fixed across scenes. This improves continuity while remaining fully local.

## 3D frame renderer

UI-generated scenes use the project-local Three.js renderer in `three-renderer/`. It builds a
voxel character, subway carriage, lights, rails, and a scene-specific camera position in a local
headless Chromium page, then saves each frame as PNG before FFmpeg assembles the video. Three.js,
Playwright, Chromium, and their caches are all kept inside this project.

Run ComfyUI separately on the same computer, then verify the project setup:

```bash
faceless-video doctor project.json
```

The doctor checks executables and the Python modules used by the selected adapters. The first run
of each runtime may still need its local model files and, for ComfyUI, a valid API-format workflow.

## Project format

```json
{
  "title": "A short example",
  "output": "work/example.mp4",
  "scenes": [
    {
      "id": "scene-01",
      "narration": "A quiet introduction.",
      "image_prompt": "Minimal cinematic landscape, no text",
      "image": "assets/scene-01.png",
      "voice": "assets/scene-01.wav",
      "subtitle": "assets/scene-01.srt",
      "duration": 4.0
    }
  ]
}
```

Paths are resolved relative to the project file. Generation backends should write their outputs to the paths in the scene records; the assembler will only consume local files.
If a scene has no explicit `duration`, the renderer uses local `ffprobe` to read the voice file
duration. Scenes without a voice file must specify `duration`.

## Architecture

```text
script -> scene plan -> local image/voice/transcript adapters -> FFmpeg assembler
```

Subtitle files are optional per scene; when configured, they must exist and are burned into the video.
A local
subtitle wrapper can call whisper.cpp, faster-whisper, or another installed transcription tool.
The core only executes the configured local command and verifies that it created the expected file.
