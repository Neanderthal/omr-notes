#!/usr/bin/env bash
# One-time setup for the TrOMR fallback engine (NetEase/Polyphonic-TrOMR).
# TrOMR is a transformer single-staff OMR; pretrained weights ship IN the repo.
# It has its OWN env (old pinned deps) separate from the Audiveris/oemer venv.
set -euo pipefail

HOME_DIR="${TROMR_HOME:-$HOME/.local/share/tromr}"
mkdir -p "$HOME_DIR"
cd "$HOME_DIR"

# 1. repo (bundles the 83 MB checkpoint under tromr/workspace/checkpoints/)
if [ ! -d Polyphonic-TrOMR ]; then
  git clone --depth 1 https://github.com/NetEase/Polyphonic-TrOMR.git
fi

# 2. venv — Python 3.8 preferred (deps are pinned to old versions).
#    NOTE: torch 1.11 (the repo's pin) FAILS to load on modern kernels
#    ("libtorch_cpu.so: cannot enable executable stack"), so we use torch 2.4.1,
#    which runs the bundled checkpoint fine.
PY=""
for c in python3.8 "$HOME/.pyenv/versions/3.8.20/bin/python" python3.9 python3.10; do
  command -v "$c" >/dev/null 2>&1 && PY="$c" && break
  [ -x "$c" ] && PY="$c" && break
done
[ -n "$PY" ] || { echo "need python3.8-3.10 (old TrOMR deps); install one"; exit 1; }
echo "using $($PY --version) for the TrOMR venv"

"$PY" -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q \
  torch==2.4.1 numpy==1.23.5 timm==0.6.5 transformers==4.20.1 \
  x-transformers==0.29.2 einops==0.4.1 albumentations==1.2.0 \
  omegaconf opencv-python-headless music21

venv/bin/python -c "import torch,music21,cv2,x_transformers; print('TrOMR env OK, torch', torch.__version__)"
echo
echo "done. Run the fallback with:"
echo "  $HOME_DIR/venv/bin/python <skill>/scripts/tromr_omr.py STAFF_OR_SYSTEM.png -o OUT.musicxml"
