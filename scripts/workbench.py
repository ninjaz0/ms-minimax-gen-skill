"""Jupyter controls for the two native H3 workflows."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import ipywidgets as widgets
from IPython.display import Video, display

ROOT = Path(__file__).resolve().parents[1]


def show(mode):
    prompt = widgets.Textarea(description="描述", layout=widgets.Layout(width="95%", height="90px"),
        value=("Use <Picture 1> as the subject reference. Keep its appearance, slowly move the camera. Quiet birdsong."
               if mode == "r2v" else "A ginger cat watches a yellow leaf fall outside a sunny window. Quiet garden ambience."))
    uploads = widgets.FileUpload(accept=".png,.jpg,.jpeg,.webp", multiple=True, description="上传参考图")
    size = widgets.Dropdown(options=["480p", "768p"], description="画质")
    duration = widgets.Dropdown(options=[5, 10, 15], description="时长（秒）")
    turbo = widgets.Checkbox(value=False, description="Turbo 4 步")
    run = widgets.Button(description="生成视频", button_style="primary")
    output = widgets.Output()

    def generate(_):
        run.disabled = True
        output.clear_output(wait=True)
        try:
            command = [sys.executable, str(ROOT / "scripts/generate.py"), mode, "--prompt", prompt.value,
                       "--size", size.value, "--seconds", str(duration.value)]
            if mode == "r2v":
                if not 1 <= len(uploads.value) <= 9:
                    raise ValueError("请上传 1–9 张图片，按选择顺序对应 <Picture 1> 等编号。")
                for ref in uploads.value:
                    data = bytes(ref["content"])
                    suffix = Path(ref["name"]).suffix.lower()
                    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
                        raise ValueError("支持 PNG、JPEG 和 WebP。")
                    path = ROOT / "state" / "references" / (hashlib.sha256(data).hexdigest() + suffix)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    command.extend(["--image", str(path)])
                if turbo.value:
                    command.append("--turbo")
            job = None
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, cwd=ROOT) as process:
                tail = []
                for line in process.stdout:
                    if line.startswith("Job directory: "):
                        job = Path(line.removeprefix("Job directory: ").strip())
                        output.append_stdout("已准备任务 " + job.name + "\n")
                    if line.startswith("Accepted:"):
                        output.append_stdout("已提交，等待生成并校验音视频。\n")
                    tail = (tail + [line])[-12:]
                if process.wait() or job is None:
                    raise RuntimeError("".join(tail))
            report = json.loads((job / "validation.json").read_text())
            output.append_display_data(Video(report["path"], embed=True, width=720, html_attributes="controls"))
            output.append_stdout(report["path"] + "\n")
        except Exception as exc:
            output.append_stdout(str(exc) + "\n")
        finally:
            run.disabled = False

    run.on_click(generate)
    controls = [uploads, turbo] if mode == "r2v" else []
    display(widgets.VBox([*controls, prompt, size, duration, run, output]))
