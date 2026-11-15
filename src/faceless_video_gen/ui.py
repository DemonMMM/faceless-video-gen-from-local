from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .config import load_project
from .runtime import project_from_request, run_project


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Faceless Video Studio</title>
<style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 20% 0,#22345d,#0b1020 48%,#070a12);color:#f5f7ff}
.shell{width:min(920px,calc(100% - 32px));margin:0 auto;padding:52px 0}
.eyebrow{color:#8ea9ff;font-size:12px;font-weight:800;letter-spacing:.16em;text-transform:uppercase}
h1{font-size:clamp(34px,6vw,64px);line-height:1;margin:12px 0 16px;max-width:720px}
.intro{color:#aab5d4;font-size:17px;max-width:650px;line-height:1.6}
.card{margin-top:30px;padding:24px;border:1px solid #273356;border-radius:20px;background:#11182bdf;box-shadow:0 20px 60px #0005}
label{display:block;color:#d9e0f6;font-weight:700}textarea{display:block;width:100%;min-height:130px;margin-top:10px;padding:16px;border:1px solid #35446f;border-radius:14px;background:#0a1020;color:#fff;font:inherit;line-height:1.5;resize:vertical}
button{margin-top:16px;padding:13px 22px;border:0;border-radius:12px;background:linear-gradient(135deg,#668cff,#956bff);color:#fff;font:inherit;font-weight:800;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}.status{display:flex;align-items:center;gap:12px;margin-top:22px;padding:14px 16px;border-radius:12px;background:#0b1120;color:#b9c5e5}
.dot{width:10px;height:10px;border-radius:50%;background:#73809d}.running .dot{background:#ffcc66;box-shadow:0 0 16px #ffcc66;animation:pulse 1.2s infinite}.done .dot{background:#58e39b}.failed .dot{background:#ff687d}
.result{margin-top:22px}.result a{color:#9db7ff;font-weight:800}.result video{display:block;width:100%;margin-top:18px;border-radius:14px;background:#000}
[hidden]{display:none!important}@keyframes pulse{50%{opacity:.35}}
</style></head><body><main class="shell">
<div class="eyebrow">Local AI video studio</div>
<h1>Turn an idea into a faceless video.</h1>
<p class="intro">Describe your story. The local pipeline creates the 3D scenes, narration, subtitles, and final video while this page reports progress live.</p>
<section class="card"><form>
<label for="request">What should we build?</label>
<textarea id="request" name="request" required>Make a 30 sec video about a lonely cartoon character on a subway.</textarea>
<button id="submit" type="submit">Build video</button>
</form>
<div id="status" class="status"><span class="dot"></span><span id="message">Ready when you are.</span></div>
<div id="result" class="result" hidden><a id="link" href="/output" target="_blank">Open the generated video</a><video id="video" controls></video></div>
</section></main>
<script>
const form=document.querySelector("form"),button=document.querySelector("#submit"),status=document.querySelector("#status");
const message=document.querySelector("#message"),result=document.querySelector("#result"),link=document.querySelector("#link"),video=document.querySelector("#video");
async function refresh(){try{const response=await fetch("/status",{cache:"no-store"});const state=await response.json();status.className="status "+state.status;message.textContent=state.message;button.disabled=state.status==="running";if(state.status==="done"){result.hidden=false;link.href=state.output_url;video.src=state.output_url}else if(state.status==="failed"){result.hidden=true}}catch(error){message.textContent="Waiting for the local UI..."}}
form.addEventListener("submit",async event=>{event.preventDefault();button.disabled=true;result.hidden=true;const body=new URLSearchParams(new FormData(form));await fetch("/",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body});await refresh()});
setInterval(refresh,1000);refresh();
</script></body></html>"""

_state_lock = threading.Lock()
_state = {"status": "idle", "message": "Ready when you are.", "output_url": None}
_last_output: Path | None = None


def _update_state(status: str, message: str, output_url: str | None = None) -> None:
    with _state_lock:
        _state.update({"status": status, "message": message, "output_url": output_url})


def _generate(root: Path, request: str) -> None:
    global _last_output
    try:
        project_path = project_from_request(root, request)
        output = run_project(
            load_project(project_path),
            progress=lambda message: _update_state("running", message),
        )
        _last_output = output
        _update_state("done", "Video complete. Your link is ready.", "/output")
    except (OSError, ValueError, RuntimeError) as exc:
        _update_state("failed", f"Generation failed: {exc}")


class _Handler(BaseHTTPRequestHandler):
    root: Path
    lock = threading.Lock()

    def _respond(self, body: str, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/html") -> None:
        encoded = body.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except BrokenPipeError:
            return

    def do_GET(self) -> None:
        if self.path == "/status":
            with _state_lock:
                body = json.dumps(_state)
            self._respond(body, content_type="application/json")
            return
        if self.path == "/output":
            output = _last_output
            if output is None or not output.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = output.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._respond(_PAGE)

    def do_POST(self) -> None:
        if not self.lock.acquire(blocking=False):
            self._respond(_PAGE)
            return
        try:
            with _state_lock:
                if _state["status"] == "running":
                    self._respond(_PAGE)
                    return
            length = int(self.headers.get("Content-Length", "0"))
            values = parse_qs(self.rfile.read(length).decode("utf-8"))
            request = values.get("request", [""])[0].strip()
            if not request:
                raise ValueError("Describe the video you want to build.")
            _update_state("running", "Planning your scenes...")
            threading.Thread(target=_generate, args=(self.root, request), daemon=True).start()
        except (ValueError, OSError) as exc:
            _update_state("failed", f"Generation failed: {exc}")
        finally:
            self.lock.release()
        self._respond(_PAGE)

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(root: Path, host: str = "127.0.0.1", port: int = 8090) -> None:
    handler = type("FacelessVideoHandler", (_Handler,), {"root": root})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Local UI: http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
