"""Generate the deterministic CC0 Phase 6 archetype and weapon fixture corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from generate_pilot_assets import thumbnail_svg, vox_bytes, write_or_check


ROOT = Path(__file__).resolve().parents[1]
ROLES = ("head", "torso", "pelvis", "upper_arm_l", "upper_arm_r", "lower_arm_l", "lower_arm_r", "hand_l", "hand_r", "upper_leg_l", "upper_leg_r", "lower_leg_l", "lower_leg_r", "foot_l", "foot_r")
ARCHETYPES = {
    "female_heroic": {"prefix": "fhr", "name": "Female Sword Guardian", "rig": "humanoid_female", "weapon": "sword_shield", "scale": (0.90, 0.92, 1.00), "height": 1.76, "color": "8C4E78"},
    "male_heavy": {"prefix": "mhy", "name": "Heavy Spear Vanguard", "rig": "humanoid_heavy", "weapon": "spear", "scale": (1.30, 1.18, 1.05), "height": 2.05, "color": "445B70"},
    "mage_robe": {"prefix": "mgr", "name": "Robe Staff Mage", "rig": "humanoid_mage", "weapon": "staff", "scale": (0.96, 0.96, 1.02), "height": 1.82, "color": "614A8C"},
    "large_villain": {"prefix": "lvr", "name": "Large Katana Villain", "rig": "humanoid_large", "weapon": "katana", "scale": (1.20, 1.12, 1.24), "height": 2.35, "color": "6E2635"},
    "child_small": {"prefix": "csm", "name": "Small Caster", "rig": "humanoid_small", "weapon": "caster", "scale": (0.78, 0.82, 0.72), "height": 1.25, "color": "3A7C70"},
}
BASE = {
    "head": ((8, 7, 8), (-4, -3, 21)), "torso": ((12, 7, 10), (-6, -3, 12)), "pelvis": ((10, 6, 4), (-5, -3, 9)),
    "upper_arm_l": ((4, 5, 8), (6, -2, 14)), "upper_arm_r": ((4, 5, 8), (-10, -2, 14)),
    "lower_arm_l": ((4, 4, 7), (8, -2, 8)), "lower_arm_r": ((4, 4, 7), (-12, -2, 8)),
    "hand_l": ((4, 4, 3), (8, -2, 5)), "hand_r": ((4, 4, 3), (-12, -2, 5)),
    "upper_leg_l": ((5, 6, 8), (1, -3, 1)), "upper_leg_r": ((5, 6, 8), (-6, -3, 1)),
    "lower_leg_l": ((5, 5, 7), (1, -3, -6)), "lower_leg_r": ((5, 5, 7), (-6, -3, -6)),
    "foot_l": ((5, 8, 3), (1, -5, -9)), "foot_r": ((5, 8, 3), (-6, -5, -9)),
}
WEAPON_SHAPES = {"sword_shield": (3, 2, 14), "spear": (2, 2, 22), "staff": (2, 2, 20), "katana": (2, 2, 18), "caster": (4, 4, 8)}
EXTRA_WEAPONS = {"gunblade": (3, 3, 15), "firearm": (7, 3, 4)}


def scaled(values, factors, *, minimum=1):
    return tuple(max(minimum, round(value * factors[index])) for index, value in enumerate(values))


def manifest(asset_id, kind, role, base, relative, content, placement, weapon=False):
    value = {"schema_version": 1, "asset_id": asset_id, "version": "1.0.0", "kind": kind,
        "source_path": str(relative).replace("\\", "/"), "format": "vox", "semantic_tags": [role], "compatible_bases": [base],
        "pivots": {"origin": [0, 0, 0]}, "palette_roles": ["blade" if weapon else "primary"],
        "author": "Voxel Character Factory contributors", "license": "CC0-1.0",
        "provenance": "Original Phase 6 reusable-factory fixture created for this repository; public-domain dedication.",
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "thumbnail_path": str(relative.parent / "thumbnails" / f"{asset_id}.svg").replace("\\", "/"),
        "placement_voxels": list(placement), "scale_metadata": {"voxel_unit_meters": 0.08, "coordinate_system": "right_handed_z_up"}}
    if weapon:
        value["sockets"] = {"primary_grip": [1, 1, 2], "secondary_grip": [1, 1, 4], "back_carry": [1, 1, 8], "waist_carry": [1, 1, 5], "trail_base": [1, 1, 3], "trail_tip": [1, 1, max(4, WEAPON_SHAPES[base if base in WEAPON_SHAPES else "staff"][2])]}
    return value


def actions(attack):
    return [
        {"name":"idle","frame_start":1,"frame_end":40,"loop":True,"root_motion":"none","required_bones":["root","spine","head"],"events":[],"poses":[{"frame":1,"bones":{"spine":[0,-.02,0]}},{"frame":20,"bones":{"spine":[0,.02,0]}},{"frame":40,"bones":{"spine":[0,-.02,0]}}]},
        {"name":"walk","frame_start":1,"frame_end":24,"loop":True,"root_motion":"in_place","required_bones":["root","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"],"events":[{"name":"footstep_l","frame":6},{"name":"footstep_r","frame":18}],"poses":[{"frame":1,"bones":{"thigh.L":[.35,0,0],"thigh.R":[-.35,0,0]}},{"frame":12,"bones":{"thigh.L":[-.35,0,0],"thigh.R":[.35,0,0]}},{"frame":24,"bones":{"thigh.L":[.35,0,0],"thigh.R":[-.35,0,0]}}]},
        {"name":"run","frame_start":1,"frame_end":18,"loop":True,"root_motion":"in_place","required_bones":["root","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"],"events":[{"name":"footstep_l","frame":5},{"name":"footstep_r","frame":14}],"poses":[{"frame":1,"bones":{"thigh.L":[.6,0,0],"thigh.R":[-.6,0,0]}},{"frame":9,"bones":{"thigh.L":[-.6,0,0],"thigh.R":[.6,0,0]}},{"frame":18,"bones":{"thigh.L":[.6,0,0],"thigh.R":[-.6,0,0]}}]},
        {"name":f"{attack}_attack_1","frame_start":1,"frame_end":30,"loop":False,"root_motion":"none","required_bones":["root","spine","upper_arm.L","upper_arm.R","forearm.R","hand.R","weapon_socket.R","effect_socket"],"events":[{"name":"trail_start","frame":9},{"name":"hit_start","frame":14},{"name":"hit_end","frame":19},{"name":"trail_end","frame":22}],"poses":[{"frame":1,"bones":{"spine":[0,0,0]}},{"frame":10,"bones":{"spine":[0,-.2,-.2],"upper_arm.R":[-.5,0,.5]}},{"frame":18,"bones":{"spine":[0,.25,.3],"upper_arm.R":[.6,0,-.6]}},{"frame":30,"bones":{"spine":[0,0,0]}}]},
    ]


def write_json(path, value, check):
    return write_or_check(path, (json.dumps(value, indent=2) + "\n").encode(), check)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args(); valid = True
    for base, config in ARCHETYPES.items():
        prefix, factors, color = config["prefix"], config["scale"], config["color"]
        folder = ROOT / "assets" / "original" / "phase6" / base
        entries, ids = [], []
        for role in ROLES:
            original_size, original_placement = BASE[role]
            size = list(scaled(original_size, factors))
            if role in {"head", "torso", "pelvis"} and size[0] % 2:
                size[0] += 1
            size = tuple(size)
            placement = tuple(round((original_placement[index] + original_size[index] / 2) * factors[index] - size[index] / 2) for index in range(3))
            if role.endswith("_r"):
                left_size, left_placement = BASE[role[:-1] + "l"]
                left_x = round((left_placement[0] + left_size[0] / 2) * factors[0] - size[0] / 2)
                placement = (-left_x - size[0], placement[1], placement[2])
            asset_id = f"{prefix}_{role}"; content = vox_bytes(role, size, color); relative = Path("assets/original/phase6") / base / f"{asset_id}.vox"
            valid &= write_or_check(ROOT / relative, content, args.check); valid &= write_or_check(folder / "thumbnails" / f"{asset_id}.svg", thumbnail_svg(asset_id, color), args.check)
            entries.append(manifest(asset_id, "body_part", role, base, relative, content, placement)); ids.append(asset_id)
        family = config["weapon"]; asset_id = f"{prefix}_{family}"; size = WEAPON_SHAPES[family]; content = vox_bytes("weapon", size, "C7CDD4"); relative = Path("assets/original/phase6") / base / f"{asset_id}.vox"
        valid &= write_or_check(ROOT / relative, content, args.check); valid &= write_or_check(folder / "thumbnails" / f"{asset_id}.svg", thumbnail_svg(asset_id, "C7CDD4"), args.check)
        weapon_entry = manifest(asset_id, "weapon", "weapon", base, relative, content, (-14, -1, 3), True)
        weapon_entry["sockets"]["trail_tip"][2] = size[2]
        entries.append(weapon_entry); ids.append(asset_id)
        if family == "sword_shield":
            shield_id = f"{prefix}_shield"; shield_content = vox_bytes("shield", (7, 2, 9), "8B96A3"); shield_relative = Path("assets/original/phase6") / base / f"{shield_id}.vox"
            valid &= write_or_check(ROOT / shield_relative, shield_content, args.check); valid &= write_or_check(folder / "thumbnails" / f"{shield_id}.svg", thumbnail_svg(shield_id, "8B96A3"), args.check)
            entries.append(manifest(shield_id, "weapon", "shield", base, shield_relative, shield_content, (10, -1, 5))); ids.append(shield_id)
        valid &= write_json(ROOT / "assets" / "manifests" / f"phase6_{base}.assets.v1.json", {"catalog_schema_version":1,"assets":entries}, args.check)
        pack_id = f"{family}_core"
        pack = {"schema_version":1,"pack_id":pack_id,"frame_rate":30,"compatibility_tags":["humanoid",family],"required_bones":["root","pelvis","spine","head","upper_arm.L","upper_arm.R","forearm.L","forearm.R","hand.L","hand.R","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R","weapon_socket.R","effect_socket"],"actions":actions(family)}
        valid &= write_json(ROOT / "config" / "animation_packs" / f"{pack_id}.v1.json", pack, args.check)
        secondary = [{"chain_id":"garment_tail","kind":"robe" if base == "mage_robe" else "coat_tail","segments":["tail.01","tail.02","tail.03"],"parent_bone":"pelvis","stiffness":.65,"damping":.35,"max_angle_degrees":30,"fallback":"rigid"}] if base in {"mage_robe","large_villain"} else []
        job = {"schema_version":2,"id":f"phase6_{base}","name":config["name"],"game":"original","role":"villain" if base == "large_villain" else "hero","body_template":base,"rig_template":config["rig"],"animation_profile":family,"animation_packs":[pack_id],"export_profile":"godot_character","weapon":asset_id,"source":{"mode":"assembly","asset_ids":ids},"asset_assembly":f"phase6_{base}","height_voxels":44,"palette_profile":"phase6_factory","accent_colors":[f"#{color}","#C7CDD4"],"export_formats":["glb"],"render_profile":"character_preview","render_resolution":512,"target_height_meters":config["height"],"settings_overrides":{"secondary_motion":secondary,"optimization":{"lod_ratios":[1.0,.5,.25],"material_batching":"palette_atlas","compression":"engine","incremental_previews":True}},"notes":"Original CC0 Phase 6 reusable-factory acceptance fixture."}
        valid &= write_json(ROOT / "characters" / "original" / f"phase6_{base}.json", job, args.check)
    shared_folder = ROOT / "assets" / "original" / "phase6" / "shared_weapons"
    shared_entries = []
    for family, size in EXTRA_WEAPONS.items():
        asset_id = f"p6_{family}"; content = vox_bytes("weapon", size, "7C8794"); relative = Path("assets/original/phase6/shared_weapons") / f"{asset_id}.vox"
        valid &= write_or_check(ROOT / relative, content, args.check); valid &= write_or_check(shared_folder / "thumbnails" / f"{asset_id}.svg", thumbnail_svg(asset_id, "7C8794"), args.check)
        entry = manifest(asset_id, "weapon", "weapon", "female_heroic", relative, content, (-14, -1, 3), True)
        entry["compatible_bases"] = sorted(ARCHETYPES); entry["sockets"]["trail_tip"][2] = size[2]; shared_entries.append(entry)
        pack = {"schema_version":1,"pack_id":f"{family}_core","frame_rate":30,"compatibility_tags":["humanoid",family],"required_bones":["root","pelvis","spine","head","upper_arm.L","upper_arm.R","forearm.L","forearm.R","hand.L","hand.R","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R","weapon_socket.R","effect_socket"],"actions":actions(family)}
        valid &= write_json(ROOT / "config" / "animation_packs" / f"{family}_core.v1.json", pack, args.check)
    valid &= write_json(ROOT / "assets" / "manifests" / "phase6_shared_weapons.assets.v1.json", {"catalog_schema_version":1,"assets":shared_entries}, args.check)
    print(f"Phase 6 corpus {'is current' if valid else 'is out of date'} ({len(ARCHETYPES)} archetypes).")
    return 0 if valid else 1


if __name__ == "__main__": raise SystemExit(main())
