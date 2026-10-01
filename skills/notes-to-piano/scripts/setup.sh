#!/usr/bin/env bash
# notes-to-piano setup: build a music21 venv and download a CC-BY piano soundfont.
# Idempotent — safe to re-run. System tools fluidsynth + ffmpeg must exist.
set -euo pipefail

DATA_DIR="${HOME}/.local/share/notes-to-piano"
VENV="${DATA_DIR}/venv"
SF_DIR="${DATA_DIR}/soundfonts"
BASE="https://freepats.zenvoid.org/Piano"

# CC-BY 3.0 piano soundfonts from FreePats:
YDP_URL="${BASE}/YDP-GrandPiano/YDP-GrandPiano-SF2-20160804.tar.bz2"          # ~37 MB (default)
SALAMANDER_URL="${BASE}/SalamanderGrandPiano/SalamanderGrandPiano-SF2-V3+20200602.tar.xz"  # ~310 MB

WANT_SALAMANDER=0
[[ "${1:-}" == "--salamander" || "${1:-}" == "--full" ]] && WANT_SALAMANDER=1

echo "== notes-to-piano setup =="

# 1. system tool check (do not install silently; just report) -----------------
missing=()
for t in fluidsynth ffmpeg; do command -v "$t" >/dev/null 2>&1 || missing+=("$t"); done
if ((${#missing[@]})); then
  echo "!! missing system tools: ${missing[*]}"
  echo "   install them with your package manager, e.g.:"
  echo "     Debian/Ubuntu: sudo apt install fluidsynth ffmpeg"
  echo "     Arch/Manjaro:  sudo pacman -S fluidsynth ffmpeg"
  exit 1
fi
echo "ok: fluidsynth, ffmpeg present"

# 2. python venv with music21 -------------------------------------------------
if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "creating venv at ${VENV}"
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/python" -m pip install --quiet --upgrade pip
"${VENV}/bin/python" -m pip install --quiet "music21>=9.1"
echo "ok: music21 installed in venv"

# 3. piano soundfont ----------------------------------------------------------
mkdir -p "${SF_DIR}"
have_sf2=$(find "${SF_DIR}" -maxdepth 1 \( -iname '*.sf2' -o -iname '*.sf3' \) | head -1 || true)

download_and_extract() {
  local url="$1" tmp
  tmp="$(mktemp -d)"
  echo "downloading: ${url##*/}"
  wget -q --show-progress -O "${tmp}/sf.archive" "${url}"
  echo "extracting…"
  case "${url}" in
    *.tar.xz)  tar -xJf "${tmp}/sf.archive" -C "${tmp}" ;;
    *.tar.bz2) tar -xjf "${tmp}/sf.archive" -C "${tmp}" ;;
    *.zip)     unzip -q "${tmp}/sf.archive" -d "${tmp}" ;;
  esac
  find "${tmp}" \( -iname '*.sf2' -o -iname '*.sf3' \) -exec cp {} "${SF_DIR}/" \;
  rm -rf "${tmp}"
}

if ((WANT_SALAMANDER)); then
  download_and_extract "${SALAMANDER_URL}"
elif [[ -z "${have_sf2}" ]]; then
  download_and_extract "${YDP_URL}"
else
  echo "ok: soundfont already present: $(basename "${have_sf2}")"
fi

echo
echo "== done =="
echo "soundfonts: ${SF_DIR}"
ls -1sh "${SF_DIR}" 2>/dev/null || true
echo
echo "Render a score:"
echo "  ${VENV}/bin/python $(cd "$(dirname "$0")" && pwd)/to_piano.py SCORE.mxl -o OUT --mp3"
