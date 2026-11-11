"""Turns the frames of web/scripts/showcase.mjs into GIFs under 3 MB.

    FRAMES=/tmp/frames OUT=docs/images uv run --with pillow python scripts/frames_to_gif.py

Each folder of numbered PNGs in FRAMES becomes OUT/showcase-<folder>.gif. If a GIF is
too big, it is made again with fewer colours, then smaller, then with fewer frames.
"""

import json
import os
from pathlib import Path

from PIL import Image

FRAMES = Path(os.environ["FRAMES"])
OUT = Path(os.environ.get("OUT", "docs/images"))
LIMIT = 3 * 1024 * 1024
ATTEMPTS = [(880, 64, 1), (880, 32, 1), (720, 32, 1), (720, 32, 2), (640, 24, 2)]


def build(frames: list[Path], durations: list[int], path: Path, *, width: int, colours: int) -> int:
    images = []
    for frame in frames:
        image = Image.open(frame).convert("RGB")
        height = round(image.height * width / image.width)
        images.append(image.resize((width, height), Image.LANCZOS))
    reduced = [
        image.quantize(colors=colours, method=Image.MEDIANCUT, dither=Image.NONE)
        for image in images
    ]
    reduced[0].save(
        path, save_all=True, append_images=reduced[1:], duration=durations, loop=0, optimize=True
    )
    return path.stat().st_size


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for folder in sorted(p for p in FRAMES.iterdir() if p.is_dir()):
        frames = sorted(folder.glob("*.png"))
        durations = json.loads((folder / "durations.json").read_text())
        path = OUT / f"showcase-{folder.name}.gif"
        for width, colours, step in ATTEMPTS:
            kept = frames[::step]
            merged = [sum(durations[i : i + step]) for i in range(0, len(frames), step)]
            size = build(kept, merged, path, width=width, colours=colours)
            note = f"{len(kept)} frames, {width}px, {colours} colours, {size / 1e6:.2f} MB"
            print(f"{path.name}: {note}")
            if size <= LIMIT:
                break
        else:
            raise SystemExit(f"{path.name} is still over 3 MB")


if __name__ == "__main__":
    main()
