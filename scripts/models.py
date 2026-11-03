"""Fetch or audit the exact Comfy-Org model files used by each workflow."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "assets/models.lock.json"


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["t2v", "r2v", "both"])
    parser.add_argument("--action", choices=["plan", "fetch", "verify"], default="plan")
    parser.add_argument("--cache", type=Path, default=Path(os.getenv("H3_CACHE", "/opt/ms-minimax-h3")))
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text())
    entries = [f for f in lock["files"] if args.mode == "both" or args.mode in f["modes"]]
    target = args.cache.resolve() / "models"
    print(f"{args.mode}: {len(entries)} files, {sum(f['bytes'] for f in entries)/1e9:.2f} GB -> {target}", flush=True)
    for entry in entries:
        print(f"  {entry['bytes']/1e9:7.2f} GB  {entry['path']}", flush=True)
    if args.action == "plan":
        return

    missing = []
    for entry in entries:
        path = target / entry["path"]
        if not path.exists():
            missing.append(entry)
        elif path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise SystemExit(f"Unexpected size/hash: {path}. Inspect and quarantine this file before retrying.")
        else:
            print("Verified existing", entry["path"], flush=True)
    if missing and args.action == "verify":
        raise SystemExit("Missing: " + ", ".join(f["path"] for f in missing))
    if missing:
        from modelscope.hub.file_download import model_file_download
        target.mkdir(parents=True, exist_ok=True)
        reserve = max(f["bytes"] for f in missing) + (8 << 30)
        if shutil.disk_usage(target).free < sum(f["bytes"] for f in missing) + reserve:
            raise SystemExit("Insufficient cache space including staging headroom. Check H3_CACHE.")
        for entry in missing:
            print("Fetching", entry["path"], flush=True)
            dest = Path(model_file_download(lock["repository"], entry["path"],
                        revision=entry["revision"], local_dir=str(target)))
            if dest.resolve() != (target / entry["path"]).resolve():
                raise RuntimeError(f"Unexpected SDK destination: {dest}")
            if dest.stat().st_size != entry["bytes"] or digest(dest) != entry["sha256"]:
                raise RuntimeError(f"Download integrity check failed: {dest}")
            print("Verified download", entry["path"], flush=True)


if __name__ == "__main__":
    main()
