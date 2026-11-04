#!/usr/bin/env python3
"""Export the built-in characters as 1-bit PNGs + a manifest for the web app."""

import json
from pathlib import Path

import characters

OUT = Path(__file__).parent / "web" / "characters"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for key, (label, draw, mouth_y) in characters.CHARACTERS.items():
        img = draw().point(lambda v: 255 if v >= 128 else 0).convert("1")
        img.save(OUT / f"{key}.png", optimize=True)
        manifest.append({"key": key, "label": label, "mouthY": mouth_y})
    (OUT / "characters.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(manifest)} characters -> {OUT}")


if __name__ == "__main__":
    main()
