"""Generate the original CC0 Heavy Sword Hero voxel source corpus.

This is source-content generation, not a build cache: it creates the small,
deterministic `.vox` files and SVG thumbnails tracked under `assets/original/`.
Run with `--check` in CI to detect accidental edits to the public pilot assets.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets" / "original" / "heavy_sword_hero"

# ID, kind, semantic tag, dimensions, placement (all voxel units), palette color.
SPECS = [
    ("hsh_head", "body_part", "head", (8, 7, 8), (-4, -3, 21), "D8A175"),
    ("hsh_torso", "body_part", "torso", (12, 7, 10), (-6, -3, 12), "27354A"),
    ("hsh_pelvis", "body_part", "pelvis", (10, 6, 4), (-5, -3, 9), "1B2232"),
    ("hsh_upper_arm_l", "body_part", "upper_arm_l", (4, 5, 8), (6, -2, 14), "27354A"),
    ("hsh_upper_arm_r", "body_part", "upper_arm_r", (4, 5, 8), (-10, -2, 14), "27354A"),
    ("hsh_lower_arm_l", "body_part", "lower_arm_l", (4, 4, 7), (8, -2, 8), "6A7481"),
    ("hsh_lower_arm_r", "body_part", "lower_arm_r", (4, 4, 7), (-12, -2, 8), "6A7481"),
    ("hsh_hand_l", "body_part", "hand_l", (4, 4, 3), (8, -2, 5), "D8A175"),
    ("hsh_hand_r", "body_part", "hand_r", (4, 4, 3), (-12, -2, 5), "D8A175"),
    ("hsh_upper_leg_l", "body_part", "upper_leg_l", (5, 6, 8), (1, -3, 1), "27354A"),
    ("hsh_upper_leg_r", "body_part", "upper_leg_r", (5, 6, 8), (-6, -3, 1), "27354A"),
    ("hsh_lower_leg_l", "body_part", "lower_leg_l", (5, 5, 7), (1, -3, -6), "6A7481"),
    ("hsh_lower_leg_r", "body_part", "lower_leg_r", (5, 5, 7), (-6, -3, -6), "6A7481"),
    ("hsh_foot_l", "body_part", "foot_l", (5, 8, 3), (1, -5, -9), "171C26"),
    ("hsh_foot_r", "body_part", "foot_r", (5, 8, 3), (-6, -5, -9), "171C26"),
    ("hsh_hair", "hair", "hair", (10, 8, 5), (-5, -4, 28), "D6A935"),
    ("hsh_coat", "garment", "coat", (14, 8, 9), (-7, -4, 11), "5E2936"),
    ("hsh_glove_l", "garment", "glove_l", (4, 4, 3), (8, -2, 4), "171C26"),
    ("hsh_glove_r", "garment", "glove_r", (4, 4, 3), (-12, -2, 4), "171C26"),
    ("hsh_boot_l", "garment", "boot_l", (5, 8, 3), (1, -5, -10), "171C26"),
    ("hsh_boot_r", "garment", "boot_r", (5, 8, 3), (-6, -5, -10), "171C26"),
    ("hsh_pauldron_l", "accessory", "pauldron_l", (6, 8, 3), (4, -4, 21), "8A919C"),
    ("hsh_pauldron_r", "accessory", "pauldron_r", (6, 8, 3), (-10, -4, 21), "8A919C"),
    ("hsh_heavy_sword", "weapon", "heavy_sword", (4, 2, 17), (-18, -1, 3), "C8D1D8"),
]

LEGACY_COMBINED_ASSETS = ("hsh_gloves", "hsh_boots", "hsh_pauldrons")


def _chunk(chunk_id: bytes, content: bytes) -> bytes:
    return chunk_id + struct.pack("<II", len(content), 0) + content


def _dictionary(values: dict[str, str]) -> bytes:
    result = [struct.pack("<i", len(values))]
    for key, value in values.items():
        for item in (key, value):
            raw = item.encode("utf-8")
            result.append(struct.pack("<i", len(raw)) + raw)
    return b"".join(result)


def vox_bytes(name: str, size: tuple[int, int, int], color: str) -> bytes:
    x_size, y_size, z_size = size
    # Join keeps the source intentionally obvious and byte-order deterministic.
    voxels = b"".join(bytes((x, y, z, 1)) for z in range(z_size) for y in range(y_size) for x in range(x_size))
    xyzi = struct.pack("<I", x_size * y_size * z_size) + voxels
    rgba = bytearray(1024)
    red, green, blue = bytes.fromhex(color)
    rgba[:4] = bytes((red, green, blue, 255))
    shape = struct.pack("<i", 1) + _dictionary({"_name": name}) + struct.pack("<i", 1) + struct.pack("<i", 0) + _dictionary({})
    transform = struct.pack("<i", 0) + _dictionary({"_name": name}) + struct.pack("<iiii", 1, -1, -1, 1) + _dictionary({"_t": "0 0 0"})
    children = b"".join((_chunk(b"SIZE", struct.pack("<III", *size)), _chunk(b"XYZI", xyzi), _chunk(b"RGBA", bytes(rgba)), _chunk(b"nTRN", transform), _chunk(b"nSHP", shape)))
    return b"VOX " + struct.pack("<I", 150) + b"MAIN" + struct.pack("<II", 0, len(children)) + children


def thumbnail_svg(asset_id: str, color: str) -> bytes:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160"><rect width="160" height="160" fill="#10131b"/><rect x="38" y="25" width="84" height="110" rx="8" fill="#{color}"/><path d="M50 55h60M50 83h60M50 111h60" stroke="#fff" opacity=".25" stroke-width="6"/><text x="80" y="151" fill="#fff" font-family="sans-serif" font-size="11" text-anchor="middle">{asset_id}</text></svg>'''.encode("utf-8")


def write_or_check(path: Path, content: bytes, check: bool) -> bool:
    if path.is_file() and path.read_bytes() == content:
        return True
    if check:
        print(f"out of date: {path.relative_to(ROOT)}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    valid = True
    for asset_id in LEGACY_COMBINED_ASSETS:
        for path in (ASSET_ROOT / f"{asset_id}.vox", ASSET_ROOT / "thumbnails" / f"{asset_id}.svg"):
            if path.exists():
                if arguments.check:
                    print(f"obsolete paired asset: {path.relative_to(ROOT)}")
                    valid = False
                else:
                    path.unlink()
    for asset_id, _kind, semantic, size, _placement, color in SPECS:
        valid &= write_or_check(ASSET_ROOT / f"{asset_id}.vox", vox_bytes(semantic, size, color), arguments.check)
        valid &= write_or_check(ASSET_ROOT / "thumbnails" / f"{asset_id}.svg", thumbnail_svg(asset_id, color), arguments.check)
    if valid:
        digest = hashlib.sha256(b"".join(vox_bytes(semantic, size, color) for _id, _kind, semantic, size, _placement, color in SPECS)).hexdigest()
        print(f"Heavy Sword Hero assets are current ({len(SPECS)} sources; corpus {digest[:12]}).")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
