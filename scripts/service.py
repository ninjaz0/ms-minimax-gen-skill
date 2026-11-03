"""Start the pinned ComfyUI on loopback, or verify the service for this checkout."""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["both", "t2v", "r2v"])
    args = parser.parse_args()
    state = ROOT / "state"
    cache = Path(os.getenv("H3_CACHE", "/opt/ms-minimax-h3")).resolve()
    port = int(os.getenv("H3_PORT", "8188"))
    url = f"http://127.0.0.1:{port}"
    source = state / "ComfyUI"
    config = cache / "extra-models.yaml"
    models = cache / "models"
    folders = ["diffusion_models", "text_encoders", "vae", "loras"]
    config_data = {"ms_h3": {"base_path": str(models), **{p: p for p in folders}}}
    config.write_text(yaml.safe_dump(config_data))
    output = state / "outputs"
    for d in (output, state / "inputs", state / "user", state / "logs"):
        d.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(source / "main.py"), "--listen", "127.0.0.1",
               "--port", str(port), "--extra-model-paths-config", str(config),
               "--output-directory", str(output), "--input-directory", str(state / "inputs"),
               "--user-directory", str(state / "user"), "--use-pytorch-cross-attention",
               "--disable-xformers", "--disable-all-custom-nodes", "--preview-method", "none",
               "--reserve-vram", "8"]
    with socket.socket() as probe:
        occupied = probe.connect_ex(("127.0.0.1", port)) == 0
    process = None
    if not occupied:
        with (state / "logs/comfy.log").open("ab") as log:
            process = subprocess.Popen(command, cwd=source, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(120):
        if process and process.poll() is not None:
            raise SystemExit("ComfyUI exited; inspect state/logs/comfy.log")
        try:
            response = requests.get(url + "/system_stats", timeout=3)
            response.raise_for_status()
            system = response.json()["system"]
            break
        except (requests.RequestException, KeyError, ValueError):
            if occupied:
                raise SystemExit("Port is occupied by another or still-starting service. Inspect it or choose H3_PORT.")
            time.sleep(1)
    else:
        raise SystemExit("Service readiness timed out; inspect the log before restarting.")
    if system.get("comfyui_version") != "0.38.0" or system.get("argv") != command[1:]:
        raise SystemExit("Port belongs to a different configuration. Select another H3_PORT.")
    required = {"t2v": "MiniMaxH3ImageToVideo", "r2v": "MiniMaxH3ReferenceToVideo"}
    for mode, node in required.items():
        if args.mode in (mode, "both"):
            response = requests.get(url + "/object_info/" + node, timeout=20)
            response.raise_for_status()
            if node not in response.json():
                raise SystemExit(f"Missing native node: {node}")
    print(f"Ready: {url} ({args.mode})")


if __name__ == "__main__":
    main()
