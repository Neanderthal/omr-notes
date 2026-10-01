# Setup & environment pitfalls

Run `scripts/setup.sh` once. Manual notes and the reasons behind the pins:

## Python venv (`~/.local/share/omr-notes/venv`)
- **Do NOT `pip install oemer` into a shared/system env** — pip pulls
  `onnxruntime-gpu` (fails with GPU out-of-memory on large pages) and bumps
  numpy/onnxruntime, breaking other tools (aider, deepfilternet, …). Always an
  isolated venv.
- Pins: `numpy<2` (oemer needs it), `onnxruntime==1.17.0`.
  - onnxruntime **≥1.19** rejects oemer's ONNX models:
    `ShapeInferenceError: pads must not contain negative values`.
  - Python 3.12 has **no** onnxruntime `<1.17`, so 1.17.0 is the floor.
- Force CPU at runtime with `CUDA_VISIBLE_DEVICES=""` (the pipeline does this) to
  avoid the GPU-OOM path even if a GPU build sneaks in.
- oemer downloads ~230 MB of model checkpoints into its package dir on first run.

## Audiveris (`~/.local/share/omr-notes/audiveris`)
- No Arch/Manjaro binary; the AUR build under Java 26 is risky and needs sudo.
- Instead extract the Ubuntu `.deb` from GitHub releases — it bundles its own JRE
  (`lib/runtime`), so the host Java version is irrelevant, no system install:
  `ar x audiveris.deb && tar xf data.tar.*` → `opt/audiveris/bin/Audiveris`.
- Batch CLI: `bin/Audiveris -batch -export -output DIR image` → `.mxl`.
- **Rejects low-resolution images** at the SCALE step
  (`interline value too low … try 300 DPI`). Phone photos must be upscaled first
  — the splitter does 3× by default (`--scale`). Symptom if skipped:
  `Could not export since transcription did not complete successfully`.

## Rendering check
- `verovio` + `cairosvg` render MusicXML/.mxl → PNG so you can eyeball accuracy
  without opening MuseScore. verovio reads both `.musicxml` and `.mxl`.
