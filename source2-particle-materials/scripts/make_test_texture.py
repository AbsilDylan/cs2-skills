#!/usr/bin/env python3
"""Create owned procedural RGBA TGA test artwork; no engine or image library needed."""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import struct


def tga(width, height, sample):
    # Uncompressed truecolor, 32-bit BGRA, top-left origin, eight alpha bits.
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            alpha = max(0, min(255, round(sample((x + 0.5) / width, (y + 0.5) / height) * 255)))
            pixels.extend((255, 255, 255, alpha))
    return header + pixels


def soft_sprite(u, v):
    radius = math.hypot(2 * u - 1, 2 * v - 1)
    return max(0, 1 - radius * radius) ** 3


def soft_trail(u, v):
    cross_section = max(0, 1 - abs(2 * v - 1)) ** 2
    end_fade = min(1, u * 8, (1 - u) * 8)
    return cross_section * max(0, end_fade)


def ring_frame(phase):
    def sample(u, v):
        radius = math.hypot(2 * u - 1, 2 * v - 1)
        ring = max(0, 1 - abs(radius - (0.15 + phase * 0.55)) / 0.12) ** 2
        return ring * (1 - phase * 0.6)
    return sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New output directory; existing paths are refused")
    parser.add_argument("--kind", choices=("sprite", "trail", "flipbook"), default="sprite")
    parser.add_argument("--size", type=int, default=128, help="Width, 16..2048; trail height is width/4")
    parser.add_argument("--frames", type=int, default=8, help="Flipbook frame count, 2..64")
    parser.add_argument("--fps", type=float, default=24, help="Flipbook source frame display rate, >0..240")
    parser.add_argument("--resource-path", help="Optional lowercase materials/.../name.vtex path; emits the native-tested linear RGBA VTEX definition")
    args = parser.parse_args()
    if not 16 <= args.size <= 2048 or not 2 <= args.frames <= 64 or not math.isfinite(args.fps) or not 0 < args.fps <= 240:
        parser.error("Require size 16..2048, frames 2..64 and finite fps >0..240.")
    frame_display_time = 1.0 / args.fps
    if not math.isfinite(frame_display_time):
        parser.error("fps must produce a finite frame display time.")
    resource = None
    if args.resource_path:
        resource = PurePosixPath(args.resource_path)
        if (not re.fullmatch(r"materials/[a-z0-9_/-]+\.vtex", args.resource_path)
                or any(part in ("", ".", "..") for part in args.resource_path.split("/"))
                or any(PureWindowsPath(part).is_reserved() for part in resource.parts)):
            parser.error("resource-path must be a portable lowercase materials/.../name.vtex path without traversal or reserved names.")
    count = args.frames if args.kind == "flipbook" else 1
    width = args.size
    height = max(4, width // 4) if args.kind == "trail" else width
    if width * height * count > 16 * 1024 * 1024:
        parser.error("Artwork exceeds the aggregate 16 million pixel limit; reduce size or frame count.")
    template = None
    template_path = Path(__file__).resolve().parent.parent / "assets" / "linear-rgba-test.vtex"
    if resource:
        template = template_path.read_bytes()
        if template.count(b"materials/skill_tests/sprite/sprite.tga") != 1:
            parser.error("The native-tested VTEX template has an unexpected input binding.")
    # Reserve the directory atomically. Never merge into or overwrite an asset tree.
    args.output.mkdir(parents=True, exist_ok=False)
    generated = []
    for index in range(count):
        name = f"frame_{index:03d}.tga" if args.kind == "flipbook" else f"{args.kind}.tga"
        sample = ring_frame(index / (count - 1)) if args.kind == "flipbook" else soft_trail if args.kind == "trail" else soft_sprite
        payload = tga(width, height, sample)
        (args.output / name).write_bytes(payload)
        generated.append({"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    if args.kind == "flipbook":
        lines = ["sequence 0", "LOOP"] + [f"frame {row['path']} {frame_display_time:.9f}" for row in generated]
        payload = ("\n".join(lines) + "\n").encode("ascii")
        (args.output / "flipbook.mks").write_bytes(payload)
        generated.append({"path": "flipbook.mks", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    if resource:
        input_name = "flipbook.mks" if args.kind == "flipbook" else f"{args.kind}.tga"
        input_path = str(resource.parent / input_name)
        payload = template.replace(b"materials/skill_tests/sprite/sprite.tga", input_path.encode("ascii"))
        (args.output / resource.name).write_bytes(payload)
        generated.append({"path": resource.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {
        "format": "owned-source2-test-artwork/1", "generator": "make_test_texture.py", "kind": args.kind,
        "width": width, "height": height, "frames": count,
        "alpha": "straight RGBA; neutral white RGB is retained outside visible alpha",
        "sourceArtwork": "Procedural analytic shapes; no external images or Valve payloads",
        "nativeCompilerVerified": False, "nativeRendered": False,
        "vtexResourcePath": str(resource) if resource else None,
        "vtexTemplateSha256": hashlib.sha256(template).hexdigest() if template else None,
        "mksReference": "https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/IO/Extract/TextureExtract.cs" if args.kind == "flipbook" else None,
        "files": generated,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "files": len(generated), "nativeCompilerVerified": False}))


if __name__ == "__main__":
    main()
