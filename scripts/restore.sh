#!/usr/bin/env bash
# Run on the Linux DSW-AMD instance from a checkout on persistent storage.
set -euo pipefail
if [[ $# != 1 || ! "$1" =~ ^(t2v|r2v|both)$ ]]; then
  echo "Usage: bash scripts/restore.sh {t2v|r2v|both}" >&2
  exit 2
fi
mode=$1
root=$(cd "$(dirname "$0")/.." && pwd -P)
cache=$(realpath -m "${H3_CACHE:-/opt/ms-minimax-h3}")
export H3_CACHE="$cache"
base_python=${H3_PYTHON:-python}
revision=651ca296a73cd21c12a57eb8741d52e40dc6528f
origin=https://github.com/Comfy-Org/ComfyUI.git
state="$root/state"
comfy="$state/ComfyUI"

"$base_python" - <<'PY'
import sys
if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
    raise SystemExit("Select the ModelScope DSW-AMD Python 3.12 interpreter.")
import torch
if not torch.version.hip or not torch.cuda.is_available():
    raise SystemExit("This interpreter does not see a ROCm GPU.")
print("Platform torch:", torch.__version__, "HIP:", torch.version.hip,
      "VRAM GiB:", round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1))
PY
case "$cache/" in
  /mnt/workspace/*) echo "Choose a cache on the instance temporary disk." >&2; exit 1 ;;
esac
mkdir -p "$state" "$cache"
exec 9>"$cache/restore.lock"
flock -n 9 || { echo "Another restore is active for this cache." >&2; exit 1; }
"$base_python" "$root/scripts/models.py" "$mode" --action plan
if [[ ! -e "$comfy" ]]; then
  staging=$(mktemp -d "$state/ComfyUI.new.XXXXXX")
  git -C "$staging" init -q
  git -C "$staging" remote add origin "$origin"
  git -C "$staging" fetch --depth 1 origin "$revision"
  git -C "$staging" checkout -q --detach FETCH_HEAD
  mv -T "$staging" "$comfy"
fi
[[ $(git -C "$comfy" rev-parse --show-toplevel) == "$comfy" && $(git -C "$comfy" rev-parse HEAD) == "$revision" ]] ||
  { echo "Unexpected ComfyUI checkout in $comfy; inspect it." >&2; exit 1; }
git -C "$comfy" diff --quiet HEAD -- ||
  { echo "Tracked ComfyUI files differ from the pinned source; inspect before reuse." >&2; exit 1; }
# A reused cache must still expose the current image's ROCm torch.
if [[ ! -x "$cache/venv/bin/python" ]]; then
  "$base_python" -m venv --system-site-packages "$cache/venv"
fi
py="$cache/venv/bin/python"
"$base_python" - <<'PY' > "$cache/platform-constraints.txt"
from importlib.metadata import version, PackageNotFoundError
for package in ("torch", "torchvision", "torchaudio"):
    try:
        print(f"{package}=={version(package)}")
    except PackageNotFoundError:
        continue
PY
"$py" -m pip install -c "$cache/platform-constraints.txt" -r "$root/assets/requirements-amd.txt"
"$py" -c 'import torch; assert torch.version.hip and torch.cuda.is_available(), "ROCm torch check failed"'
"$py" -m ipykernel install --user --name ms-minimax-h3 --display-name "MiniMax H3 (AMD)"
"$base_python" "$root/scripts/models.py" "$mode" --action fetch
"$py" "$root/scripts/service.py" "$mode"
