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
FAMILY_MOVES = {
    "heavy_sword": ("heavy_sword_attack_1", "heavy_sword_attack_2", "heavy_sword_attack_3", "heavy_sword_charge", "heavy_sword_overhead_smash", "heavy_sword_wide_sweep", "heavy_sword_launcher", "heavy_sword_limit_break"),
    "sword_shield": ("sword_shield_attack_1", "sword_combo", "shield_bash", "shield_counter", "sword_thrust", "shield_rush", "spinning_slash", "heroic_finish"),
    "spear": ("spear_attack_1", "spear_thrust", "spear_sweep", "spear_vault_strike", "spear_double_thrust", "spear_spin_guard", "dragoon_jump", "spear_impale_finish"),
    "staff": ("staff_attack_1", "staff_combo", "staff_channel", "staff_magic_burst", "staff_sweep", "staff_parry", "staff_heal_cast", "staff_meteor_cast"),
    "katana": ("katana_attack_1", "katana_quick_draw", "katana_combo", "katana_iaijutsu", "katana_rising_slash", "katana_parry", "katana_blade_dance", "katana_final_cut"),
    "gunblade": ("gunblade_attack_1", "gunblade_trigger_slash", "gunblade_combo", "gunblade_burst", "gunblade_aimed_shot", "gunblade_recoil_slash", "gunblade_explosive_round", "gunblade_limit_burst"),
    "firearm": ("firearm_attack_1", "firearm_aimed_shot", "firearm_burst_fire", "firearm_reload", "firearm_hip_fire", "firearm_dodge_shot", "firearm_grenade_toss", "firearm_overdrive"),
    "caster": ("caster_attack_1", "caster_quick_cast", "caster_heavy_cast", "caster_channel", "caster_heal", "caster_barrier", "caster_area_cast", "caster_ultimate_cast"),
}
TRAVERSAL_NAMES = (
    "slide", "dodge_roll", "double_jump", "airborne_idle",
    "air_attack_light", "air_attack_heavy", "air_attack_spin", "air_attack_plunge",
    "dash", "ladder_idle", "ladder_climb", "wall_hang", "wall_jump", "wall_climb",
    "swim_idle", "swim_forward", "rope_swing", "rope_release",
    "grapple_fire", "grapple_pull", "grapple_swing", "grapple_release",
    "ledge_grab", "ledge_climb",
)
SHARED_PACK_ACTIONS = {
    "directional_locomotion": ("walk_backward","strafe_left","strafe_right","run_backward","run_strafe_left","run_strafe_right","sprint","sprint_start","sprint_stop","turn_left_90","turn_right_90","turn_left_180","turn_right_180","crouch_enter","crouch_walk","crouch_exit"),
    "traversal_transitions": ("jump_start","fall_sustain","land_soft","land_hard","ladder_mount","ladder_dismount","wall_hang_enter","wall_corner_left","wall_corner_right","wall_climb_exit","swim_dive","swim_surface","swim_turn_left","swim_turn_right","swim_exit","grapple_land"),
    "interaction_core": ("weapon_draw","weapon_sheath","weapon_swap","pickup","item_use","interact","push","pull","carry_idle","carry_walk","lever_use","door_open"),
    "combat_reactions": ("hit_front","hit_back","hit_left","hit_right","block_break","parry","stagger","stun_enter","stun_idle","stun_recover","knockback","launch_react","air_hit","ground_hit","recover_quick","recover_slow"),
}


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


def _action(name, end, required, poses, events=(), *, loop=False, root_motion="none"):
    return {"name":name,"frame_start":1,"frame_end":end,"loop":loop,"root_motion":root_motion,"required_bones":required,"events":[{"name":event,"frame":frame} for event,frame in events],"poses":[{"frame":frame,"bones":bones} for frame,bones in poses]}


def _combat_action(name, index, family):
    amplitude = .38 + index * .14
    if family in {"firearm", "caster"}:
        events = (("cast_start" if family == "caster" else "aim_start", 6), ("projectile_spawn", 14), ("cast_end" if family == "caster" else "muzzle_flash", 16))
    elif "reload" in name:
        events = (("reload_start", 5), ("reload_complete", 24))
    else:
        events = (("trail_start", 9), ("hit_start", 14), ("hit_end", 19), ("trail_end", 22))
    return _action(name, 30, ["root","spine","upper_arm.L","upper_arm.R","forearm.R","hand.R","weapon_socket.R","effect_socket"], [
        (1,{"spine":[0,0,0],"upper_arm.R":[0,0,.1]}),
        (10,{"spine":[0,-.16,-.18],"upper_arm.R":[-amplitude,.08,amplitude]}),
        (18,{"spine":[0,.22,.28],"upper_arm.R":[amplitude,0,-amplitude],"forearm.R":[.2,0,-.25]}),
        (30,{"spine":[0,0,0],"upper_arm.R":[0,0,.1]}),
    ], events)


def actions(family):
    common = [
        {"name":"idle","frame_start":1,"frame_end":40,"loop":True,"root_motion":"none","required_bones":["root","spine","head"],"events":[],"poses":[{"frame":1,"bones":{"spine":[0,-.02,0]}},{"frame":20,"bones":{"spine":[0,.02,0]}},{"frame":40,"bones":{"spine":[0,-.02,0]}}]},
        {"name":"walk","frame_start":1,"frame_end":24,"loop":True,"root_motion":"in_place","required_bones":["root","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"],"events":[{"name":"footstep_l","frame":6},{"name":"footstep_r","frame":18}],"poses":[{"frame":1,"bones":{"thigh.L":[.35,0,0],"thigh.R":[-.35,0,0]}},{"frame":12,"bones":{"thigh.L":[-.35,0,0],"thigh.R":[.35,0,0]}},{"frame":24,"bones":{"thigh.L":[.35,0,0],"thigh.R":[-.35,0,0]}}]},
        {"name":"run","frame_start":1,"frame_end":18,"loop":True,"root_motion":"in_place","required_bones":["root","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"],"events":[{"name":"footstep_l","frame":5},{"name":"footstep_r","frame":14}],"poses":[{"frame":1,"bones":{"thigh.L":[.6,0,0],"thigh.R":[-.6,0,0]}},{"frame":9,"bones":{"thigh.L":[-.6,0,0],"thigh.R":[.6,0,0]}},{"frame":18,"bones":{"thigh.L":[.6,0,0],"thigh.R":[-.6,0,0]}}]},
        _action("jump",24,["root","pelvis","thigh.L","thigh.R","shin.L","shin.R"],[(1,{"pelvis":[-.15,0,0],"thigh.L":[.25,0,0],"thigh.R":[.25,0,0]}),(8,{"pelvis":[.1,0,0],"thigh.L":[-.2,0,0],"thigh.R":[-.2,0,0]}),(16,{"pelvis":[.08,0,0],"thigh.L":[.15,0,0],"thigh.R":[.15,0,0]}),(24,{"pelvis":[0,0,0]})],(("takeoff",6),("land",22))),
        _action("dodge",20,["root","pelvis","spine","thigh.L","thigh.R"],[(1,{"spine":[0,0,0]}),(7,{"spine":[0,.15,.55],"pelvis":[.15,0,0]}),(14,{"spine":[0,-.1,-.35],"pelvis":[-.1,0,0]}),(20,{"spine":[0,0,0]})],(("invulnerable_start",4),("invulnerable_end",15))),
        _action("guard",30,["root","spine","upper_arm.L","upper_arm.R","forearm.L","forearm.R"],[(1,{"spine":[0,-.08,0],"upper_arm.L":[-.35,0,-.2],"upper_arm.R":[-.35,0,.2]}),(15,{"spine":[0,-.1,0],"upper_arm.L":[-.38,0,-.2],"upper_arm.R":[-.38,0,.2]}),(30,{"spine":[0,-.08,0],"upper_arm.L":[-.35,0,-.2],"upper_arm.R":[-.35,0,.2]})],loop=True),
        _action("guard_hit",14,["root","spine","upper_arm.L","upper_arm.R"],[(1,{"spine":[0,-.08,0]}),(7,{"spine":[0,.18,0],"upper_arm.L":[.2,0,0],"upper_arm.R":[.2,0,0]}),(14,{"spine":[0,-.08,0]})],(("guard_impact",7),)),
        _action("damage_light",14,["root","spine","head"],[(1,{"spine":[0,0,0]}),(6,{"spine":[0,.22,.12],"head":[0,-.15,0]}),(14,{"spine":[0,0,0]})],(("damage_react",6),)),
        _action("damage_heavy",22,["root","pelvis","spine","head"],[(1,{"spine":[0,0,0]}),(9,{"spine":[.12,.4,.18],"head":[-.15,-.2,0],"pelvis":[-.12,0,0]}),(22,{"spine":[0,0,0]})],(("damage_react",9),)),
        _action("knockdown",30,["root","pelvis","spine","head","thigh.L","thigh.R"],[(1,{"spine":[0,0,0]}),(14,{"spine":[1.1,0,0],"pelvis":[.35,0,0]}),(30,{"spine":[1.45,0,0],"head":[.25,0,0]})],(("ground_impact",18),)),
        _action("death",45,["root","pelvis","spine","head","upper_arm.L","upper_arm.R"],[(1,{"spine":[0,0,0]}),(20,{"spine":[.7,0,.15],"pelvis":[.2,0,0]}),(45,{"spine":[1.5,0,0],"head":[.35,0,0],"upper_arm.L":[.4,0,0],"upper_arm.R":[.4,0,0]})],(("death_impact",32),)),
        _action("victory",50,["root","spine","head","upper_arm.R","forearm.R","hand.R"],[(1,{"spine":[0,0,0]}),(20,{"spine":[0,-.12,0],"upper_arm.R":[-1.0,0,.2],"forearm.R":[-.6,0,0]}),(35,{"spine":[0,-.08,0],"head":[0,.12,0],"upper_arm.R":[-1.2,0,.2]}),(50,{"spine":[0,0,0]})],(("victory_pose",35),)),
        _action("crouch_idle",30,["root","pelvis","spine","thigh.L","thigh.R","shin.L","shin.R"],[(1,{"pelvis":[-.22,0,0],"spine":[.12,0,0],"thigh.L":[.35,0,0],"thigh.R":[.35,0,0],"shin.L":[-.5,0,0],"shin.R":[-.5,0,0]}),(15,{"pelvis":[-.24,0,0],"spine":[.1,0,0],"thigh.L":[.37,0,0],"thigh.R":[.37,0,0],"shin.L":[-.52,0,0],"shin.R":[-.52,0,0]}),(30,{"pelvis":[-.22,0,0],"spine":[.12,0,0],"thigh.L":[.35,0,0],"thigh.R":[.35,0,0],"shin.L":[-.5,0,0],"shin.R":[-.5,0,0]})],loop=True),
        _action("backstep",18,["root","pelvis","spine","thigh.L","thigh.R"],[(1,{"spine":[0,0,0]}),(7,{"spine":[-.2,0,0],"pelvis":[.12,0,0],"thigh.L":[-.3,0,0],"thigh.R":[-.3,0,0]}),(18,{"spine":[0,0,0]})],(("invulnerable_start",3),("invulnerable_end",12))),
        _action("fall",24,["root","pelvis","spine","upper_arm.L","upper_arm.R","thigh.L","thigh.R"],[(1,{"spine":[0,0,0]}),(12,{"spine":[-.18,0,0],"upper_arm.L":[.35,0,-.2],"upper_arm.R":[.35,0,.2],"thigh.L":[-.12,0,0],"thigh.R":[-.12,0,0]}),(24,{"spine":[-.25,0,0],"upper_arm.L":[.45,0,-.25],"upper_arm.R":[.45,0,.25]})]),
        _action("get_up",32,["root","pelvis","spine","head","upper_arm.L","upper_arm.R"],[(1,{"spine":[1.45,0,0],"head":[.3,0,0]}),(14,{"spine":[.8,0,0],"upper_arm.L":[-.3,0,0],"upper_arm.R":[-.3,0,0]}),(24,{"spine":[.25,0,0],"pelvis":[-.1,0,0]}),(32,{"spine":[0,0,0],"head":[0,0,0]})],(("recovered",32),)),
    ]
    return common + [_combat_action(name, index, family) for index, name in enumerate(FAMILY_MOVES[family], start=1)]


def traversal_actions():
    required = ["root","pelvis","spine","head","upper_arm.L","upper_arm.R","forearm.L","forearm.R","hand.L","hand.R","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"]
    loops = {"airborne_idle", "ladder_idle", "ladder_climb", "wall_hang", "wall_climb", "swim_idle", "swim_forward", "rope_swing", "grapple_swing"}
    events = {
        "slide": (("slide_start",2),("slide_end",24)), "dodge_roll": (("invulnerable_start",3),("invulnerable_end",18)),
        "double_jump": (("double_jump_impulse",8),), "dash": (("dash_start",3),("dash_end",15)),
        "wall_jump": (("wall_jump_impulse",8),), "rope_release": (("rope_release",8),),
        "grapple_fire": (("grapple_fire",7),), "grapple_release": (("grapple_release",8),),
        "ledge_climb": (("ledge_stand",26),),
    }
    result = []
    for index, name in enumerate(TRAVERSAL_NAMES):
        loop = name in loops; end = 30
        middle = 15; sway = .18 + (index % 4) * .08
        first = {"spine":[0,0,0]}; center = {"spine":[sway,0,0]}; last = dict(first)
        if name in {"slide","dodge_roll"}: center = {"spine":[1.15 if name == "dodge_roll" else .45,0,0],"pelvis":[-.28,0,0],"thigh.L":[.45,0,0],"thigh.R":[.45,0,0]}
        elif name in {"double_jump","airborne_idle","wall_jump"}: center = {"spine":[-.12,0,0],"upper_arm.L":[-.45,0,-.3],"upper_arm.R":[-.45,0,.3],"thigh.L":[-.35,0,0],"thigh.R":[-.35,0,0]}
        elif name.startswith("air_attack"): center = {"spine":[0,.25,.4],"upper_arm.R":[.8,0,-.7],"forearm.R":[.35,0,-.25],"thigh.L":[-.2,0,0],"thigh.R":[.2,0,0]}
        elif name == "dash": center = {"spine":[-.38,0,0],"upper_arm.L":[.28,0,0],"upper_arm.R":[.28,0,0]}
        elif name.startswith("ladder") or name.startswith("wall") or name.startswith("ledge"):
            first = {"spine":[.05,0,0],"upper_arm.L":[-1.15,0,-.15],"upper_arm.R":[-1.15,0,.15],"thigh.L":[.25,0,0],"thigh.R":[-.25,0,0]}
            center = {"spine":[-.05,0,0],"upper_arm.L":[-.9,0,-.2],"upper_arm.R":[-1.3,0,.2],"thigh.L":[-.25,0,0],"thigh.R":[.25,0,0]}; last = dict(first)
        elif name.startswith("swim"):
            first = {"spine":[1.35,0,0],"upper_arm.L":[-.5,0,-.3],"upper_arm.R":[-.5,0,.3]}
            center = {"spine":[1.45,0,0],"upper_arm.L":[-.9,0,.4],"upper_arm.R":[-.9,0,-.4],"thigh.L":[.2,0,0],"thigh.R":[-.2,0,0]}; last = dict(first)
        elif name.startswith("rope") or name.startswith("grapple"):
            first = {"spine":[-.12,0,0],"upper_arm.L":[-1.25,0,-.1],"upper_arm.R":[-1.25,0,.1],"forearm.L":[-.45,0,0],"forearm.R":[-.45,0,0]}
            center = {"spine":[.25,0,.18],"upper_arm.L":[-1.35,0,-.1],"upper_arm.R":[-1.35,0,.1],"thigh.L":[-.3,0,0],"thigh.R":[.2,0,0]}; last = dict(first)
        action_events = list(events.get(name, ()))
        if name.startswith("air_attack"): action_events = [("trail_start",8),("hit_start",13),("hit_end",19),("trail_end",22)]
        result.append(_action(name,end,required,[(1,first),(middle,center),(end,last)],action_events,loop=loop,root_motion="in_place" if name in {"slide","dash","dodge_roll","swim_forward","ladder_climb","wall_climb"} else "none"))
    return result


def shared_pack_actions(pack_id):
    required = ["root","pelvis","spine","head","upper_arm.L","upper_arm.R","forearm.L","forearm.R","hand.L","hand.R","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"]
    loops = {"walk_backward","strafe_left","strafe_right","run_backward","run_strafe_left","run_strafe_right","sprint","crouch_walk","fall_sustain","carry_idle","carry_walk","stun_idle"}
    movement = {"walk_backward","strafe_left","strafe_right","run_backward","run_strafe_left","run_strafe_right","sprint","crouch_walk","carry_walk"}
    events = {
        "sprint_start":(("sprint_start",3),), "sprint_stop":(("sprint_stop",18),), "land_soft":(("land",12),), "land_hard":(("land_hard",14),),
        "weapon_draw":(("weapon_ready",18),), "weapon_sheath":(("weapon_stowed",18),), "weapon_swap":(("weapon_swap",14),), "pickup":(("pickup",16),),
        "item_use":(("item_apply",15),), "interact":(("interact",12),), "lever_use":(("interact",14),), "door_open":(("interact",15),),
        "block_break":(("guard_break",10),), "parry":(("parry_window",9),), "stun_enter":(("stun_start",12),), "stun_recover":(("stun_end",18),),
    }
    result = []
    for index, name in enumerate(SHARED_PACK_ACTIONS[pack_id]):
        loop = name in loops; end = 30 if loop else 24; phase = .24 + (index % 3) * .1
        first = {"spine":[0,0,0]}; middle = {"spine":[phase,0,0]}; last = dict(first)
        if name in movement:
            amount = .65 if "run" in name or name == "sprint" else .35
            first = {"thigh.L":[amount,0,0],"thigh.R":[-amount,0,0],"upper_arm.L":[-amount*.5,0,0],"upper_arm.R":[amount*.5,0,0]}
            middle = {"thigh.L":[-amount,0,0],"thigh.R":[amount,0,0],"upper_arm.L":[amount*.5,0,0],"upper_arm.R":[-amount*.5,0,0]}; last = dict(first)
            if "crouch" in name: first["pelvis"]=[-.24,0,0]; middle["pelvis"]=[-.24,0,0]; last["pelvis"]=[-.24,0,0]
        elif name.startswith("turn_"):
            angle = (1.57 if name.endswith("90") else 3.05) * (-1 if "right" in name else 1); middle = {"pelvis":[0,0,angle*.5],"spine":[0,0,angle*.2]}; last = {"pelvis":[0,0,angle],"spine":[0,0,angle*.35]}
        elif name.startswith("crouch_"): middle = {"pelvis":[-.24,0,0],"spine":[.16,0,0],"thigh.L":[.35,0,0],"thigh.R":[.35,0,0]}; last = dict(middle) if name == "crouch_enter" else dict(first)
        elif any(token in name for token in ("ladder","wall_","swim_","grapple_","jump_","fall_","land_")):
            middle = {"spine":[-.18 if "jump" in name else .28,0,0],"upper_arm.L":[-.8,0,-.2],"upper_arm.R":[-.8,0,.2],"thigh.L":[.28,0,0],"thigh.R":[-.28,0,0]}
            if name == "fall_sustain": first = dict(middle); last = dict(middle)
        elif name in {"weapon_draw","weapon_sheath","weapon_swap","item_use","interact","lever_use","door_open","pickup"}:
            middle = {"spine":[0,-.12,0],"upper_arm.R":[-.75,0,.45],"forearm.R":[-.55,0,0],"hand.R":[0,.2,0]}
        elif name in {"push","pull","carry_idle","carry_walk"}:
            first = {"spine":[-.15,0,0],"upper_arm.L":[-.75,0,-.2],"upper_arm.R":[-.75,0,.2],"forearm.L":[-.4,0,0],"forearm.R":[-.4,0,0]}; middle = dict(first); middle["spine"]=[-.28 if name == "push" else .12,0,0]; last = dict(first)
        elif pack_id == "combat_reactions":
            x = -.45 if name in {"hit_front","knockback","launch_react"} else .45 if name == "hit_back" else .12
            z = .5 if name == "hit_left" else -.5 if name == "hit_right" else 0
            middle = {"spine":[x,0,z],"head":[-x*.4,0,-z*.3],"upper_arm.L":[.3,0,0],"upper_arm.R":[.3,0,0]}
            if name == "stun_idle":
                first = {"spine":[.08,0,-.06],"head":[-.03,0,.04],"upper_arm.L":[.26,0,0],"upper_arm.R":[.34,0,0]}
                last = dict(first)
        action_events = list(events.get(name, ()))
        if name.startswith("hit_") or name in {"stagger","knockback","launch_react","air_hit","ground_hit"}: action_events = [("damage_react",12)]
        result.append(_action(name,end,required,[(1,first),(end//2,middle),(end,last)],action_events,loop=loop,root_motion="in_place" if name in movement else "none"))
    return result


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
        job = {"schema_version":2,"id":f"phase6_{base}","name":config["name"],"game":"original","role":"villain" if base == "large_villain" else "hero","body_template":base,"rig_template":config["rig"],"animation_profile":family,"animation_packs":[pack_id,"humanoid_traversal",*SHARED_PACK_ACTIONS],"export_profile":"godot_character","weapon":asset_id,"source":{"mode":"assembly","asset_ids":ids},"asset_assembly":f"phase6_{base}","height_voxels":44,"palette_profile":"phase6_factory","accent_colors":[f"#{color}","#C7CDD4"],"export_formats":["glb"],"render_profile":"character_preview","render_resolution":512,"target_height_meters":config["height"],"settings_overrides":{"secondary_motion":secondary,"optimization":{"lod_ratios":[1.0,.5,.25],"material_batching":"palette_atlas","compression":"engine","incremental_previews":True}},"notes":"Original CC0 Phase 6 reusable-factory acceptance fixture."}
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
    heavy = {"schema_version":1,"pack_id":"heavy_sword_core","frame_rate":30,"compatibility_tags":["humanoid","heavy_sword"],"required_bones":["root","pelvis","spine","head","upper_arm.L","upper_arm.R","forearm.L","forearm.R","hand.L","hand.R","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R","weapon_socket.R","effect_socket"],"actions":actions("heavy_sword")}
    valid &= write_json(ROOT / "config" / "animation_packs" / "heavy_sword_core.v1.json", heavy, args.check)
    traversal = {"schema_version":1,"pack_id":"humanoid_traversal","frame_rate":30,"compatibility_tags":["humanoid","traversal"],"required_bones":["root","pelvis","spine","head","upper_arm.L","upper_arm.R","forearm.L","forearm.R","hand.L","hand.R","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"],"actions":traversal_actions()}
    valid &= write_json(ROOT / "config" / "animation_packs" / "humanoid_traversal.v1.json", traversal, args.check)
    for shared_id in SHARED_PACK_ACTIONS:
        shared = {"schema_version":1,"pack_id":shared_id,"frame_rate":30,"compatibility_tags":["humanoid",shared_id],"required_bones":["root","pelvis","spine","head","upper_arm.L","upper_arm.R","forearm.L","forearm.R","hand.L","hand.R","thigh.L","thigh.R","shin.L","shin.R","foot.L","foot.R"],"actions":shared_pack_actions(shared_id)}
        valid &= write_json(ROOT / "config" / "animation_packs" / f"{shared_id}.v1.json", shared, args.check)
    print(f"Phase 6 corpus {'is current' if valid else 'is out of date'} ({len(ARCHETYPES)} archetypes).")
    return 0 if valid else 1


if __name__ == "__main__": raise SystemExit(main())
