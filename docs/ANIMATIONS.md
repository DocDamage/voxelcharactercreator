# Animation catalog and player

Every animation family contains exactly 24 clips: 16 shared gameplay states and
eight moves tailored to its weapon type. All clips are Animation Pack v1 data,
export as named GLB actions, and may declare frame-based gameplay events.

## Shared clips in every family

1. `idle`
2. `walk`
3. `run`
4. `jump`
5. `dodge`
6. `guard`
7. `guard_hit`
8. `damage_light`
9. `damage_heavy`
10. `knockdown`
11. `death`
12. `victory`
13. `crouch_idle`
14. `backstep`
15. `fall`
16. `get_up`

## Type-specific clips

| Type | Eight moves |
| --- | --- |
| Heavy sword | `heavy_sword_attack_1`, `heavy_sword_attack_2`, `heavy_sword_attack_3`, `heavy_sword_charge`, `heavy_sword_overhead_smash`, `heavy_sword_wide_sweep`, `heavy_sword_launcher`, `heavy_sword_limit_break` |
| Sword/shield | `sword_shield_attack_1`, `sword_combo`, `shield_bash`, `shield_counter`, `sword_thrust`, `shield_rush`, `spinning_slash`, `heroic_finish` |
| Spear | `spear_attack_1`, `spear_thrust`, `spear_sweep`, `spear_vault_strike`, `spear_double_thrust`, `spear_spin_guard`, `dragoon_jump`, `spear_impale_finish` |
| Staff | `staff_attack_1`, `staff_combo`, `staff_channel`, `staff_magic_burst`, `staff_sweep`, `staff_parry`, `staff_heal_cast`, `staff_meteor_cast` |
| Katana | `katana_attack_1`, `katana_quick_draw`, `katana_combo`, `katana_iaijutsu`, `katana_rising_slash`, `katana_parry`, `katana_blade_dance`, `katana_final_cut` |
| Gunblade | `gunblade_attack_1`, `gunblade_trigger_slash`, `gunblade_combo`, `gunblade_burst`, `gunblade_aimed_shot`, `gunblade_recoil_slash`, `gunblade_explosive_round`, `gunblade_limit_burst` |
| Firearm | `firearm_attack_1`, `firearm_aimed_shot`, `firearm_burst_fire`, `firearm_reload`, `firearm_hip_fire`, `firearm_dodge_shot`, `firearm_grenade_toss`, `firearm_overdrive` |
| Caster | `caster_attack_1`, `caster_quick_cast`, `caster_heavy_cast`, `caster_channel`, `caster_heal`, `caster_barrier`, `caster_area_cast`, `caster_ultimate_cast` |

## Using the player

Build a registry character, open **Preview & Validation**, then click
**Play Animations**. The standalone Godot window provides:

- animation selection, play/pause, restart, looping, and timeline scrubbing;
- 0.1×–2.0× playback speed and frame stepping with the arrow keys;
- orbit with the middle/right mouse button and zoom with the wheel;
- authored footstep, hit, trail, projectile, recovery, and state-event markers;
- optional animated skeleton and socket overlays.

The player copies the promoted GLB into an ignored import workspace. It never
changes the source job or exported character.

## Universal traversal pack

Production humanoids also load `humanoid_traversal`, adding 24 actions without
changing the required 24-clip count of any weapon/type pack:

1. `slide`
2. `dodge_roll`
3. `double_jump`
4. `airborne_idle`
5. `air_attack_light`
6. `air_attack_heavy`
7. `air_attack_spin`
8. `air_attack_plunge`
9. `dash`
10. `ladder_idle`
11. `ladder_climb`
12. `wall_hang`
13. `wall_jump`
14. `wall_climb`
15. `swim_idle`
16. `swim_forward`
17. `rope_swing`
18. `rope_release`
19. `grapple_fire`
20. `grapple_pull`
21. `grapple_swing`
22. `grapple_release`
23. `ledge_grab`
24. `ledge_climb`

## Shared production packs

Every production character also composes four reusable packs. Together with one
24-clip type pack and `humanoid_traversal`, they produce 108 uniquely named
actions. Keeping these clips separate lets a character change weapon families
without duplicating locomotion, transitions, interactions, or reactions.

| Pack | Count | Clips |
| --- | ---: | --- |
| `directional_locomotion` | 16 | `walk_backward`, `strafe_left`, `strafe_right`, `run_backward`, `run_strafe_left`, `run_strafe_right`, `sprint`, `sprint_start`, `sprint_stop`, `turn_left_90`, `turn_right_90`, `turn_left_180`, `turn_right_180`, `crouch_enter`, `crouch_walk`, `crouch_exit` |
| `traversal_transitions` | 16 | `jump_start`, `fall_sustain`, `land_soft`, `land_hard`, `ladder_mount`, `ladder_dismount`, `wall_hang_enter`, `wall_corner_left`, `wall_corner_right`, `wall_climb_exit`, `swim_dive`, `swim_surface`, `swim_turn_left`, `swim_turn_right`, `swim_exit`, `grapple_land` |
| `interaction_core` | 12 | `weapon_draw`, `weapon_sheath`, `weapon_swap`, `pickup`, `item_use`, `interact`, `push`, `pull`, `carry_idle`, `carry_walk`, `lever_use`, `door_open` |
| `combat_reactions` | 16 | `hit_front`, `hit_back`, `hit_left`, `hit_right`, `block_break`, `parry`, `stagger`, `stun_enter`, `stun_idle`, `stun_recover`, `knockback`, `launch_react`, `air_hit`, `ground_hit`, `recover_quick`, `recover_slow` |

Enable **Traversal sandbox** in the player to test the reference mechanics.
Use WASD to move, Space to jump/double-jump, Shift to dash, Ctrl to slide, Q to
roll, E near ladders/walls, T near the rope anchor, G to fire/release the
grapple, and 1–4 for the four mid-air attacks. The sandbox includes a wall,
ladder, water marker, rope anchor, and grapple tower.
