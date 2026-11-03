"""Submit a native H3 graph to this deployment and verify its actual MP4."""
import argparse
import hashlib
import json
import os
import secrets
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"


def save(path, value):
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    staged.replace(path)


def server():
    url = "http://127.0.0.1:" + str(int(os.getenv("H3_PORT", "8188")))
    response = requests.get(url + "/system_stats", timeout=10)
    response.raise_for_status()
    system = response.json()["system"]
    argv = system.get("argv", [])
    if (system.get("comfyui_version") != "0.38.0" or "--output-directory" not in argv
        or argv[argv.index("--output-directory") + 1:][:1] != [str(STATE / "outputs")]):
        raise RuntimeError("Unexpected service; check H3_PORT and the deployment directory.")
    return url


def upload(url, path):
    from PIL import Image
    with Image.open(path) as image:
        suffix = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}.get(image.format)
        image.verify()
    if suffix is None:
        raise ValueError(f"Use a PNG, JPEG or WebP reference: {path.name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open("rb") as stream:
        response = requests.post(url + "/upload/image", data={"type": "input"},
                                 files={"image": (f"h3_{digest}.{suffix}", stream)}, timeout=120)
    response.raise_for_status()
    result = response.json()
    name = str(Path(result.get("subfolder") or "") / result["name"])
    return {"server_name": name, "sha256": digest}


def make_graph(mode, prompt, seed, size, seconds, steps, images, turbo, run_id):
    graph = json.loads((ROOT / "assets" / f"{mode}.json").read_text())
    width, height = {"480p": (864, 480), "768p": (1344, 768)}[size]
    graph["5"]["inputs"].update(prompt=prompt, width=width, height=height,
                                length={5: 124, 10: 243, 15: 362}[seconds])
    for index, image in enumerate(images):
        key = str(21 + index)
        graph[key] = {"class_type": "LoadImage", "inputs": {"image": image["server_name"]}}
        graph["5"]["inputs"][f"ref_images.ref_image_{index}"] = [key, 0]
    if turbo:
        graph["16"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["1", 0], "strength_model": 1.0,
            "lora_name": "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"}}
        for key in ("7", "9"):
            graph[key]["inputs"]["model"] = ["16", 0]
    graph["6"]["inputs"]["noise_seed"] = seed
    graph["9"]["inputs"]["steps"] = steps
    graph["14"]["inputs"]["filename_prefix"] = "h3/" + run_id
    return graph


def verify(path, expected, frame_path):
    import av
    import numpy as np
    with av.open(str(path)) as media:
        video = media.streams.video[0]
        fps = float(video.average_rate)
        duration = media.duration / av.time_base
        dimensions = (video.width, video.height)
        video_codec = video.codec_context.name
        count = 0
        snapshots = []
        for count, frame in enumerate(media.decode(video), 1):
            if count in (1, expected["length"] // 2, expected["length"]):
                picture = frame.to_image()
                if count == 1:
                    picture.save(frame_path)
                snapshots.append(np.asarray(picture.resize((96, 64)), dtype=np.float32))
    samples = 0
    energy = 0.0
    with av.open(str(path)) as media:
        audio = media.streams.audio[0]
        channels = len(audio.codec_context.layout.channels)
        rate = audio.codec_context.sample_rate
        audio_codec = audio.codec_context.name
        for frame in media.decode(audio):
            values = frame.to_ndarray().astype(np.float64)
            samples += values.size
            energy += float(np.square(values).sum())
    if (count != expected["length"] or dimensions != (expected["width"], expected["height"])
            or fps != 24 or channels != 2 or rate != 32000 or not samples
            or video_codec != "h264" or audio_codec != "aac"):
        raise ValueError("Decoded streams differ from the requested H3 MP4 profile")
    audio_duration = samples / (channels * rate)
    video_duration = count / fps
    if abs(duration - video_duration) > 0.15 or abs(audio_duration - video_duration) > 0.15:
        raise ValueError("Decoded audio/video durations do not match the requested frame count")
    motion = max(float(np.abs(a - b).mean()) for a, b in zip(snapshots, snapshots[1:]))
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                width=dimensions[0], height=dimensions[1], frames=count, fps=fps,
                duration_seconds=duration, video_codec=video_codec, audio_codec=audio_codec,
                channels=channels, sample_rate=rate, audio_duration_seconds=audio_duration, audio_rms=(energy / samples)**0.5,
                sampled_frame_difference=motion, first_frame=str(frame_path))


def finish(url, job, timeout):
    ticket = json.loads((job / "submission.json").read_text())
    prompt_id = ticket["prompt_id"]
    graph = json.loads((job / "api.json").read_text())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = requests.get(f"{url}/history/{prompt_id}", timeout=30)
        response.raise_for_status()
        item = response.json().get(prompt_id)
        if item is None:
            time.sleep(5)
            continue
        save(job / "history.json", item)
        if item["status"]["status_str"] != "success":
            raise RuntimeError(f"Generation failed; see {job}/history.json")
        cached = [node for event, detail in item["status"].get("messages", [])
                  if event == "execution_cached" for node in detail.get("nodes", [])]
        output_root = (STATE / "outputs").resolve()
        for group in item["outputs"].get("14", {}).values():
            if not isinstance(group, list):
                continue
            for file in group:
                if not isinstance(file, dict) or not str(file.get("filename", "")).endswith(".mp4"):
                    continue
                path = (output_root / file.get("subfolder", "") / file["filename"]).resolve()
                if not path.is_relative_to(output_root):
                    raise ValueError("Unexpected output location in history")
                report = verify(path, graph["5"]["inputs"], job / "first-frame.png")
                report.update(prompt_id=prompt_id, sampler_cached="10" in cached,
                              seconds_to_observation=round(time.time() - ticket["submitted_at"], 2))
                save(job / "validation.json", report)
                print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
                return
        raise RuntimeError(f"No MP4 returned by SaveVideo; inspect {job}/history.json")
    raise TimeoutError(f"Wait expired; the GPU task may continue. Resume with: generate.py resume {job.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("t2v", "r2v"):
        branch = sub.add_parser(mode)
        branch.add_argument("--prompt", required=True)
        branch.add_argument("--size", choices=["480p", "768p"], default="480p")
        branch.add_argument("--seconds", choices=[5, 10, 15], type=int, default=5)
        branch.add_argument("--seed", type=int, default=None)
        branch.add_argument("--steps", type=int, choices=range(1, 101), metavar="1..100")
        if mode == "r2v":
            branch.add_argument("--image", type=Path, action="append", required=True)
            branch.add_argument("--turbo", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("run_id")
    args = parser.parse_args()
    if args.mode == "resume":
        job = (STATE / "jobs" / args.run_id).resolve()
        if job.parent != (STATE / "jobs").resolve() or not (job / "submission.json").is_file():
            parser.error("Select a job directory containing submission.json under state/jobs")
        finish(server(), job, 3600)
        return
    images = getattr(args, "image", [])
    if not args.prompt.strip() or len(images) > 9 or any(not p.is_file() for p in images):
        parser.error("Provide a non-empty prompt and up to nine existing reference images")
    if args.seed is not None and not 0 <= args.seed < 2**63:
        parser.error("Seed must be between zero and 2^63-1")
    turbo = getattr(args, "turbo", False)
    url = server()
    run_id = args.mode + "-" + uuid.uuid4().hex
    job = STATE / "jobs" / run_id
    job.mkdir(parents=True)
    refs = [upload(url, path) for path in images]
    graph = make_graph(args.mode, args.prompt, secrets.randbits(53) if args.seed is None else args.seed,
                       args.size, args.seconds, args.steps or (4 if turbo else 20), refs, turbo, run_id)
    save(job / "api.json", graph)
    save(job / "references.json", refs)
    print(f"Job directory: {job}", flush=True)
    started = time.time()
    response = requests.post(url + "/prompt", json={"prompt": graph, "client_id": run_id}, timeout=60)
    if not response.ok:
        raise RuntimeError(f"Submission rejected ({response.status_code}): {response.text[:3000]}")
    ticket = response.json()
    save(job / "submission.json", {"prompt_id": ticket["prompt_id"], "submitted_at": started})
    print("Accepted:", ticket["prompt_id"], flush=True)
    finish(url, job, 3600)


if __name__ == "__main__":
    main()
