extends Node3D

var character: Node3D
var traversal_body: CharacterBody3D
var traversal_controller: VCFTraversalController
var animation_player: AnimationPlayer
var skeleton: Skeleton3D
var camera: Camera3D
var selector: OptionButton
var play_button: Button
var loop_toggle: CheckBox
var timeline: HSlider
var time_label: Label
var speed_slider: HSlider
var event_label: Label
var skeleton_toggle: CheckBox
var socket_toggle: CheckBox
var sandbox_toggle: CheckBox
var debug_mesh: ImmediateMesh
var config := {"character":"character", "frame_rate":30, "actions":[]}
var orbit_yaw := 0.65
var orbit_pitch := -0.18
var orbit_distance := 7.0
var orbit_target := Vector3(0, 1.5, 0)
var updating_timeline := false


func _ready() -> void:
	load_config()
	setup_world()
	setup_ui()
	load_character()
	if "--validate" in OS.get_cmdline_user_args():
		print(JSON.stringify({"status":"passed", "animations":animation_player.get_animation_list(), "character":config["character"]}))
		get_tree().quit()


func load_config() -> void:
	var file := FileAccess.open("res://imported/player_config.json", FileAccess.READ)
	if file != null:
		var parsed = JSON.parse_string(file.get_as_text())
		if parsed is Dictionary: config = parsed


func setup_world() -> void:
	camera = Camera3D.new(); add_child(camera); camera.current = true
	var key := DirectionalLight3D.new(); key.rotation_degrees = Vector3(-48, -32, 0); key.light_energy = 1.4; add_child(key)
	var fill := DirectionalLight3D.new(); fill.rotation_degrees = Vector3(35, 145, 0); fill.light_energy = 0.55; add_child(fill)
	var floor_mesh := PlaneMesh.new(); floor_mesh.size = Vector2(30, 30)
	var floor := MeshInstance3D.new(); floor.mesh = floor_mesh
	var material := StandardMaterial3D.new(); material.albedo_color = Color(0.09, 0.11, 0.15); material.roughness = 0.9
	floor.material_override = material; add_child(floor)
	var floor_body := StaticBody3D.new(); var floor_shape := CollisionShape3D.new(); var floor_box := BoxShape3D.new(); floor_box.size = Vector3(30,.2,30); floor_shape.shape = floor_box; floor_shape.position.y = -.1; floor_body.add_child(floor_shape); add_child(floor_body)
	setup_reference_course()
	debug_mesh = ImmediateMesh.new()
	var debug_instance := MeshInstance3D.new(); debug_instance.mesh = debug_mesh
	var debug_material := StandardMaterial3D.new(); debug_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; debug_material.albedo_color = Color(0.25, 1.0, 0.55); debug_material.vertex_color_use_as_albedo = true
	debug_instance.material_override = debug_material; add_child(debug_instance)
	update_camera()


func setup_ui() -> void:
	var layer := CanvasLayer.new(); add_child(layer)
	var panel := PanelContainer.new(); panel.position = Vector2(18, 18); panel.size = Vector2(390, 700); layer.add_child(panel)
	var box := VBoxContainer.new(); box.add_theme_constant_override("separation", 10); panel.add_child(box)
	var title := Label.new(); title.text = "Animation Player — " + str(config["character"]); title.add_theme_font_size_override("font_size", 20); box.add_child(title)
	selector = OptionButton.new(); selector.item_selected.connect(select_animation); box.add_child(selector)
	var playback := HBoxContainer.new(); box.add_child(playback)
	play_button = Button.new(); play_button.text = "Play"; play_button.pressed.connect(toggle_play); playback.add_child(play_button)
	var restart := Button.new(); restart.text = "Restart"; restart.pressed.connect(restart_animation); playback.add_child(restart)
	loop_toggle = CheckBox.new(); loop_toggle.text = "Loop"; loop_toggle.toggled.connect(set_loop); playback.add_child(loop_toggle)
	timeline = HSlider.new(); timeline.min_value = 0; timeline.step = 0.001; timeline.value_changed.connect(scrub); box.add_child(timeline)
	time_label = Label.new(); time_label.text = "0.00 / 0.00 s"; box.add_child(time_label)
	var speed_row := HBoxContainer.new(); box.add_child(speed_row)
	var speed_text := Label.new(); speed_text.text = "Speed"; speed_row.add_child(speed_text)
	speed_slider = HSlider.new(); speed_slider.min_value = 0.1; speed_slider.max_value = 2.0; speed_slider.step = 0.1; speed_slider.value = 1.0; speed_slider.custom_minimum_size.x = 220; speed_slider.value_changed.connect(set_speed); speed_row.add_child(speed_slider)
	skeleton_toggle = CheckBox.new(); skeleton_toggle.text = "Skeleton overlay"; box.add_child(skeleton_toggle)
	socket_toggle = CheckBox.new(); socket_toggle.text = "Highlight sockets"; box.add_child(socket_toggle)
	sandbox_toggle = CheckBox.new(); sandbox_toggle.text = "Traversal sandbox"; sandbox_toggle.toggled.connect(toggle_sandbox); box.add_child(sandbox_toggle)
	var events_title := Label.new(); events_title.text = "Animation events"; events_title.add_theme_font_size_override("font_size", 16); box.add_child(events_title)
	event_label = Label.new(); event_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; event_label.custom_minimum_size = Vector2(350, 180); box.add_child(event_label)
	var help := Label.new(); help.text = "Review: Space play/pause, R restart, arrows step\nSandbox: WASD move, Space jump, Shift dash\nCtrl slide, Q roll, E climb/wall or grapple-swing\nT rope, G grapple, air attacks 1–4, mouse orbit/zoom"; help.modulate = Color(0.72, 0.78, 0.88); box.add_child(help)


func load_character() -> void:
	var packed = ResourceLoader.load("res://imported/character.glb")
	if packed == null or not packed is PackedScene:
		show_error("Build/export the character before opening this player."); return
	traversal_body = CharacterBody3D.new(); traversal_body.name = "TraversalCharacter"; add_child(traversal_body)
	character = packed.instantiate(); traversal_body.add_child(character)
	animation_player = find_type(character, "AnimationPlayer") as AnimationPlayer
	skeleton = find_type(character, "Skeleton3D") as Skeleton3D
	if animation_player == null:
		show_error("The GLB contains no AnimationPlayer."); return
	var bounds := character_bounds(character)
	var collision := CollisionShape3D.new(); var capsule := CapsuleShape3D.new(); capsule.radius = maxf(.25, minf(bounds.size.x, bounds.size.z) * .22); capsule.height = maxf(capsule.radius * 2.0, bounds.size.y * .92); collision.shape = capsule; collision.position = bounds.get_center(); traversal_body.add_child(collision)
	traversal_controller = VCFTraversalController.new(); add_child(traversal_controller); traversal_controller.setup(traversal_body, animation_player, camera)
	for animation_name in animation_player.get_animation_list(): selector.add_item(String(animation_name).get_file())
	fit_camera(character)
	if selector.item_count > 0: select_animation(0)


func find_type(node: Node, class_name_value: String) -> Node:
	if node.get_class() == class_name_value: return node
	for child in node.get_children():
		var found := find_type(child, class_name_value)
		if found != null: return found
	return null


func current_animation_name() -> StringName:
	if selector.item_count == 0: return &""
	var wanted := selector.get_item_text(selector.selected)
	for candidate in animation_player.get_animation_list():
		if String(candidate).get_file() == wanted: return candidate
	return &""


func select_animation(index: int) -> void:
	if animation_player == null: return
	selector.select(index)
	var name := current_animation_name(); animation_player.play(name); animation_player.pause(); animation_player.seek(0, true)
	var clip := animation_player.get_animation(name); timeline.max_value = clip.length; timeline.value = 0
	var authored_loop := false
	for action in config.get("actions", []):
		if action.get("name", "") == selector.get_item_text(index): authored_loop = bool(action.get("loop", false))
	clip.loop_mode = Animation.LOOP_LINEAR if authored_loop else Animation.LOOP_NONE
	loop_toggle.set_pressed_no_signal(authored_loop)
	play_button.text = "Play"; update_events(selector.get_item_text(index))


func toggle_play() -> void:
	if animation_player.is_playing(): animation_player.pause(); play_button.text = "Play"
	else: animation_player.play(current_animation_name()); play_button.text = "Pause"


func restart_animation() -> void:
	animation_player.play(current_animation_name()); animation_player.seek(0, true); play_button.text = "Pause"


func set_loop(enabled: bool) -> void:
	var clip := animation_player.get_animation(current_animation_name()); clip.loop_mode = Animation.LOOP_LINEAR if enabled else Animation.LOOP_NONE


func set_speed(value: float) -> void:
	if animation_player != null: animation_player.speed_scale = value


func scrub(value: float) -> void:
	if not updating_timeline and animation_player != null: animation_player.seek(value, true)


func update_events(action_name: String) -> void:
	var lines: Array[String] = []
	for action in config.get("actions", []):
		if action.get("name", "") == action_name:
			for event in action.get("events", []): lines.append("Frame %s — %s" % [event.get("frame", "?"), event.get("name", "event")])
	event_label.text = "No authored events" if lines.is_empty() else "\n".join(lines)


func _process(_delta: float) -> void:
	if animation_player != null and animation_player.current_animation != "":
		updating_timeline = true; timeline.value = animation_player.current_animation_position; updating_timeline = false
		time_label.text = "%.2f / %.2f s" % [animation_player.current_animation_position, animation_player.current_animation_length]
		if not animation_player.is_playing(): play_button.text = "Play"
	if traversal_controller != null and traversal_controller.enabled:
		orbit_target = traversal_body.global_position + Vector3(0, 1.3, 0); update_camera()
	update_debug_overlay()


func toggle_sandbox(value: bool) -> void:
	if traversal_controller == null: return
	traversal_controller.set_enabled(value)
	selector.disabled = value; play_button.disabled = value; timeline.editable = not value
	if not value:
		traversal_body.global_position = Vector3.ZERO; select_animation(selector.selected)


func update_debug_overlay() -> void:
	debug_mesh.clear_surfaces()
	if skeleton == null or (not skeleton_toggle.button_pressed and not socket_toggle.button_pressed): return
	debug_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for index in skeleton.get_bone_count():
		var parent := skeleton.get_bone_parent(index)
		if parent < 0: continue
		var is_socket := "socket" in skeleton.get_bone_name(index).to_lower()
		if (is_socket and not socket_toggle.button_pressed) or (not is_socket and not skeleton_toggle.button_pressed): continue
		var color := Color(1.0, .35, .15) if is_socket else Color(.25, 1.0, .55)
		debug_mesh.surface_set_color(color); debug_mesh.surface_add_vertex(skeleton.global_transform * skeleton.get_bone_global_pose(parent).origin)
		debug_mesh.surface_set_color(color); debug_mesh.surface_add_vertex(skeleton.global_transform * skeleton.get_bone_global_pose(index).origin)
	debug_mesh.surface_end()


func fit_camera(root_node: Node) -> void:
	var bounds := character_bounds(root_node)
	if bounds.size.length() > 0:
		orbit_target = bounds.get_center(); orbit_target.y = maxf(bounds.position.y + bounds.size.y * .48, .5)
		orbit_distance = maxf(bounds.size.length() * .85, 2.5); update_camera()


func character_bounds(root_node: Node) -> AABB:
	var bounds := AABB(); var first := true
	var meshes: Array[MeshInstance3D] = []; collect_meshes(root_node, meshes)
	for mesh in meshes:
		var world := mesh.global_transform * mesh.get_aabb(); bounds = world if first else bounds.merge(world); first = false
	return bounds


func collect_meshes(node: Node, output: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D: output.append(node)
	for child in node.get_children(): collect_meshes(child, output)


func update_camera() -> void:
	var horizontal := cos(orbit_pitch) * orbit_distance
	camera.position = orbit_target + Vector3(sin(orbit_yaw) * horizontal, -sin(orbit_pitch) * orbit_distance, cos(orbit_yaw) * horizontal)
	camera.look_at(orbit_target, Vector3.UP)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and (event.button_mask & (MOUSE_BUTTON_MASK_MIDDLE | MOUSE_BUTTON_MASK_RIGHT)):
		orbit_yaw -= event.relative.x * .008; orbit_pitch = clampf(orbit_pitch + event.relative.y * .006, -1.2, .8); update_camera()
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP: orbit_distance = maxf(1.0, orbit_distance * .9); update_camera()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN: orbit_distance = minf(50.0, orbit_distance * 1.1); update_camera()
	elif sandbox_toggle != null and sandbox_toggle.button_pressed:
		return
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE: toggle_play()
		elif event.keycode == KEY_R: restart_animation()
		elif event.keycode in [KEY_LEFT, KEY_RIGHT]:
			var step := (1.0 / float(config.get("frame_rate", 30))) * (-1 if event.keycode == KEY_LEFT else 1)
			animation_player.seek(clampf(animation_player.current_animation_position + step, 0, animation_player.current_animation_length), true)


func show_error(message: String) -> void:
	var dialog := AcceptDialog.new(); dialog.dialog_text = message; add_child(dialog); dialog.popup_centered()


func setup_reference_course() -> void:
	make_course_box("Wall", Vector3(5,2,0), Vector3(.5,4,8), Color(.25,.28,.36))
	make_course_box("Ladder", Vector3(-4,2,-1), Vector3(.35,4,2), Color(.55,.36,.18), "ladder")
	make_course_box("GrappleTower", Vector3(0,5,-12), Vector3(7,10,1), Color(.22,.25,.32))
	var water := MeshInstance3D.new(); var water_mesh := BoxMesh.new(); water_mesh.size = Vector3(8,.15,7); water.mesh = water_mesh; water.position = Vector3(0,.6,9)
	var water_material := StandardMaterial3D.new(); water_material.albedo_color = Color(0.08,.38,.62,.55); water_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; water.material_override = water_material; water.add_to_group("water"); add_child(water)
	var anchor := MeshInstance3D.new(); var sphere := SphereMesh.new(); sphere.radius = .22; sphere.height = .44; anchor.mesh = sphere; anchor.position = Vector3(0,6,5); anchor.add_to_group("rope_anchor"); add_child(anchor)


func make_course_box(label: String, position_value: Vector3, size_value: Vector3, color: Color, group := "") -> void:
	var body := StaticBody3D.new(); body.name = label; body.position = position_value
	var mesh_instance := MeshInstance3D.new(); var mesh := BoxMesh.new(); mesh.size = size_value; mesh_instance.mesh = mesh
	var material := StandardMaterial3D.new(); material.albedo_color = color; mesh_instance.material_override = material; body.add_child(mesh_instance)
	var collision := CollisionShape3D.new(); var shape := BoxShape3D.new(); shape.size = size_value; collision.shape = shape; body.add_child(collision)
	if group != "": body.add_to_group(group)
	add_child(body)
