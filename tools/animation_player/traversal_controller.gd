class_name VCFTraversalController
extends Node

## Reference CharacterBody3D traversal controller used by the animation sandbox.
## It is deliberately engine-native and self-contained so projects can copy or
## replace it without coupling runtime movement to the factory build worker.

var enabled := false
var body: CharacterBody3D
var animator: AnimationPlayer
var view_camera: Camera3D
var state := "ground"
var jump_count := 0
var state_time := 0.0
var state_duration := 0.0
var grapple_anchor := Vector3.ZERO
var rope_anchor := Vector3.ZERO
var rope_length := 0.0
var previous_keys := {}

const MOVE_SPEED := 4.8
const SWIM_SPEED := 3.2
const CLIMB_SPEED := 2.6
const JUMP_SPEED := 6.8
const DASH_SPEED := 12.0
const GRAPPLE_SPEED := 13.0
const GRAVITY := 18.0


func setup(character_body: CharacterBody3D, player: AnimationPlayer, camera: Camera3D) -> void:
	body = character_body; animator = player; view_camera = camera


func set_enabled(value: bool) -> void:
	enabled = value
	if not enabled and body != null:
		body.velocity = Vector3.ZERO; state = "ground"; play_clip("idle")


func _physics_process(delta: float) -> void:
	if not enabled or body == null or animator == null: return
	state_time += delta
	var input := movement_input()
	var direction := camera_direction(input)
	var in_water := nearest_group("water", 5.0) != null
	var ladder := nearest_group("ladder", 2.2)
	var rope := nearest_group("rope_anchor", 12.0)

	if just_pressed(KEY_G): toggle_grapple()
	if just_pressed(KEY_T) and rope != null: attach_rope((rope as Node3D).global_position)
	if just_pressed(KEY_Q) and state not in ["grapple_pull", "rope_swing"]: begin_timed("dodge_roll", .65, direction, 8.5)
	if just_pressed(KEY_SHIFT) and state not in ["ladder", "swim"]: begin_timed("dash", .35, direction, DASH_SPEED)
	if just_pressed(KEY_CTRL) and body.is_on_floor(): begin_timed("slide", .8, direction, 8.0)
	if just_pressed(KEY_1) and not body.is_on_floor(): play_clip("air_attack_light")
	if just_pressed(KEY_2) and not body.is_on_floor(): play_clip("air_attack_heavy")
	if just_pressed(KEY_3) and not body.is_on_floor(): play_clip("air_attack_spin")
	if just_pressed(KEY_4) and not body.is_on_floor(): play_clip("air_attack_plunge")

	if in_water and state not in ["grapple_pull", "rope_swing"]: state = "swim"
	elif ladder != null and key(KEY_E) and state not in ["grapple_pull", "rope_swing"]: state = "ladder"

	match state:
		"dash", "slide", "dodge_roll": update_timed(delta)
		"ladder": update_ladder(input, ladder)
		"swim": update_swim(input, direction)
		"wall_hang": update_wall(delta, input)
		"rope_swing": update_rope(delta, input)
		"grapple_pull": update_grapple(delta)
		"grapple_swing": update_grapple_swing(delta, input)
		_: update_ground_air(delta, input, direction)
	body.move_and_slide()
	remember_keys()


func update_ground_air(delta: float, input: Vector2, direction: Vector3) -> void:
	if body.is_on_floor():
		jump_count = 0; state = "ground"
		body.velocity.x = move_toward(body.velocity.x, direction.x * MOVE_SPEED, MOVE_SPEED)
		body.velocity.z = move_toward(body.velocity.z, direction.z * MOVE_SPEED, MOVE_SPEED)
		if just_pressed(KEY_SPACE): body.velocity.y = JUMP_SPEED; jump_count = 1; state = "air"; play_clip("jump")
		elif input.length() > .15: play_clip("run" if key(KEY_SHIFT) else "walk")
		else: play_clip("idle")
	else:
		state = "air"; body.velocity.y -= GRAVITY * delta
		body.velocity.x = move_toward(body.velocity.x, direction.x * MOVE_SPEED, MOVE_SPEED * delta * 2)
		body.velocity.z = move_toward(body.velocity.z, direction.z * MOVE_SPEED, MOVE_SPEED * delta * 2)
		if just_pressed(KEY_SPACE) and jump_count < 2: body.velocity.y = JUMP_SPEED; jump_count = 2; play_clip("double_jump")
		elif key(KEY_E) and wall_normal() != Vector3.ZERO: state = "wall_hang"; body.velocity = Vector3.ZERO; play_clip("wall_hang")
		elif animator.current_animation not in [&"air_attack_light", &"air_attack_heavy", &"air_attack_spin", &"air_attack_plunge"]: play_clip("airborne_idle")


func update_timed(_delta: float) -> void:
	if state_time >= state_duration: state = "air" if not body.is_on_floor() else "ground"; state_time = 0


func begin_timed(next_state: String, duration: float, direction: Vector3, speed: float) -> void:
	state = next_state; state_time = 0; state_duration = duration; body.velocity = (direction if direction.length() > .1 else -body.global_basis.z) * speed
	body.velocity.y = 0; play_clip(next_state)


func update_ladder(input: Vector2, ladder: Node) -> void:
	if ladder == null or not key(KEY_E): state = "air"; return
	body.velocity = Vector3(0, -input.y * CLIMB_SPEED, 0)
	play_clip("ladder_climb" if absf(input.y) > .1 else "ladder_idle")
	if just_pressed(KEY_SPACE): body.velocity = Vector3(0, JUMP_SPEED, 3); state = "air"; play_clip("wall_jump")


func update_swim(input: Vector2, direction: Vector3) -> void:
	if nearest_group("water", 5.0) == null: state = "air"; return
	body.velocity = direction * SWIM_SPEED; body.velocity.y = (1 if key(KEY_SPACE) else -1 if key(KEY_CTRL) else 0) * SWIM_SPEED
	play_clip("swim_forward" if input.length() > .1 or absf(body.velocity.y) > .1 else "swim_idle")


func update_wall(_delta: float, input: Vector2) -> void:
	var normal := wall_normal()
	if normal == Vector3.ZERO or not key(KEY_E): state = "air"; return
	body.velocity = Vector3(0, -input.y * CLIMB_SPEED, 0); play_clip("wall_climb" if absf(input.y) > .1 else "wall_hang")
	if just_pressed(KEY_SPACE): body.velocity = normal * 5.5 + Vector3.UP * JUMP_SPEED; state = "air"; jump_count = 1; play_clip("wall_jump")


func attach_rope(anchor: Vector3) -> void:
	rope_anchor = anchor; rope_length = maxf(body.global_position.distance_to(anchor), 2.0); state = "rope_swing"; state_time = 0; play_clip("rope_swing")


func update_rope(delta: float, input: Vector2) -> void:
	if just_pressed(KEY_SPACE) or just_pressed(KEY_T): state = "air"; play_clip("rope_release"); return
	body.velocity.y -= GRAVITY * delta
	body.velocity += camera_direction(input) * 3.0 * delta
	var offset := body.global_position - rope_anchor
	if offset.length() > rope_length:
		var radial := offset.normalized(); body.global_position = rope_anchor + radial * rope_length
		body.velocity -= radial * body.velocity.dot(radial)
	play_clip("rope_swing")


func toggle_grapple() -> void:
	if state in ["grapple_pull", "grapple_swing"]: state = "air"; play_clip("grapple_release"); return
	grapple_anchor = grapple_point(); state = "grapple_pull"; state_time = 0; play_clip("grapple_fire")


func update_grapple(_delta: float) -> void:
	var offset := grapple_anchor - body.global_position
	if offset.length() < 1.2 or just_pressed(KEY_SPACE): state = "air"; play_clip("grapple_release"); return
	if key(KEY_E): rope_anchor = grapple_anchor; rope_length = offset.length(); state = "grapple_swing"; play_clip("grapple_swing"); return
	body.velocity = offset.normalized() * GRAPPLE_SPEED
	if state_time > .18: play_clip("grapple_pull")


func update_grapple_swing(delta: float, input: Vector2) -> void:
	if just_pressed(KEY_SPACE) or just_pressed(KEY_G): state = "air"; play_clip("grapple_release"); return
	body.velocity.y -= GRAVITY * delta; body.velocity += camera_direction(input) * 4.0 * delta
	var offset := body.global_position - rope_anchor
	if offset.length() > rope_length:
		var radial := offset.normalized(); body.global_position = rope_anchor + radial * rope_length; body.velocity -= radial * body.velocity.dot(radial)
	play_clip("grapple_swing")


func grapple_point() -> Vector3:
	var origin := view_camera.global_position; var target := origin + -view_camera.global_basis.z * 35.0
	var query := PhysicsRayQueryParameters3D.create(origin, target); query.exclude = [body.get_rid()]
	var hit := body.get_world_3d().direct_space_state.intersect_ray(query)
	return hit.get("position", target)


func wall_normal() -> Vector3:
	var forward := camera_direction(movement_input())
	if forward.length() < .1: forward = -body.global_basis.z
	var query := PhysicsRayQueryParameters3D.create(body.global_position + Vector3.UP, body.global_position + Vector3.UP + forward * 1.2); query.exclude = [body.get_rid()]
	var hit := body.get_world_3d().direct_space_state.intersect_ray(query)
	return hit.get("normal", Vector3.ZERO)


func movement_input() -> Vector2:
	return Vector2(float(key(KEY_D)) - float(key(KEY_A)), float(key(KEY_S)) - float(key(KEY_W))).normalized()


func camera_direction(input: Vector2) -> Vector3:
	var forward := -view_camera.global_basis.z; forward.y = 0; forward = forward.normalized()
	var right := view_camera.global_basis.x; right.y = 0; right = right.normalized()
	return (right * input.x + forward * -input.y).normalized()


func nearest_group(group: StringName, maximum: float) -> Node:
	var nearest: Node = null; var distance := maximum
	for candidate in get_tree().get_nodes_in_group(group):
		if candidate is Node3D:
			var current := body.global_position.distance_to(candidate.global_position)
			if current < distance: nearest = candidate; distance = current
	return nearest


func play_clip(name: StringName) -> void:
	if animator.has_animation(name) and animator.current_animation != name: animator.play(name)


func key(code: Key) -> bool:
	return Input.is_key_pressed(code)


func just_pressed(code: Key) -> bool:
	return key(code) and not bool(previous_keys.get(code, false))


func remember_keys() -> void:
	for code in [KEY_SPACE,KEY_SHIFT,KEY_CTRL,KEY_Q,KEY_E,KEY_G,KEY_T,KEY_1,KEY_2,KEY_3,KEY_4]: previous_keys[code] = key(code)
