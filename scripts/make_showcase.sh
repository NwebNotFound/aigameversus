#!/usr/bin/env bash
# Records the GIFs and screenshots of the README against a running stack.
#
#   docker compose up --build --wait           # a stack with an empty or demo database
#   scripts/make_showcase.sh                   # writes docs/images/showcase-*
#
# WEB_URL (default http://127.0.0.1:3100) and ARENA_URL (default http://127.0.0.1:8100)
# point at another stack. It starts a few bot matches (random bots, no model, no cost),
# opens only public pages, and needs Node (web/node_modules and Playwright's Chromium)
# and uv (Pillow is fetched on the fly).
set -euo pipefail
cd "$(dirname "$0")/.."

export FRAMES="$(mktemp -d)"
export OUT="$PWD/docs/images"
trap 'rm -rf "$FRAMES"' EXIT

(cd web && node scripts/showcase.mjs)
PYTHONIOENCODING=utf-8 uv run --with pillow python scripts/frames_to_gif.py
