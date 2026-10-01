#!/usr/bin/env bash
# One-time setup for the omr-notes skill: OMR venv + Audiveris (bundled JRE).
# Idempotent — safe to re-run. Installs into ~/.local/share/omr-notes.
set -euo pipefail

OMR_HOME="${OMR_HOME:-$HOME/.local/share/omr-notes}"
VENV="$OMR_HOME/venv"
AUD="$OMR_HOME/audiveris"
AUD_URL="https://github.com/Audiveris/audiveris/releases/download/5.11.0/Audiveris-5.11.0-ubuntu24.04-x86_64.deb"

mkdir -p "$OMR_HOME"

# --- Python venv -------------------------------------------------------------
# onnxruntime>=1.19 breaks oemer's ONNX models (negative-pad ShapeInferenceError);
# py3.12 has no onnxruntime<1.17 -> pin 1.17.0. oemer needs numpy<2.
if [ ! -x "$VENV/bin/python" ]; then
  echo ">> creating venv at $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q "numpy<2" "onnxruntime==1.17.0" oemer \
      verovio cairosvg opencv-python-headless pillow
else
  echo ">> venv already present, skipping"
fi
"$VENV/bin/python" -c "import oemer, onnxruntime, verovio, cv2, cairosvg" \
  && echo ">> venv OK"

# --- Audiveris (extract .deb, no system install; ships its own JRE) ----------
if [ ! -x "$AUD/bin/Audiveris" ]; then
  echo ">> installing Audiveris to $AUD"
  tmp="$(mktemp -d)"
  curl -L -C - --retry 5 -o "$tmp/audiveris.deb" "$AUD_URL"
  ( cd "$tmp" && ar x audiveris.deb && tar xf data.tar.* )
  cp -r "$tmp/opt/audiveris" "$AUD"
  rm -rf "$tmp"
else
  echo ">> Audiveris already present, skipping"
fi
[ -x "$AUD/bin/Audiveris" ] && echo ">> Audiveris OK"

echo ">> setup complete. Try: python3 scripts/omr.py IMG.jpg -o out --render --debug"
