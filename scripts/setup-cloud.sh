#!/usr/bin/env bash
set -euo pipefail
cd /workspace/my-jellyfin
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
mkdir -p .local
QT_QPA_PLATFORM=offscreen .venv/bin/python -m lumen --smoke --data-dir .local/onboarding-smoke
