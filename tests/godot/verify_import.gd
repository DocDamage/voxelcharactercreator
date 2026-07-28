extends SceneTree

const REQUIRED_ACTIONS = ["idle", "walk", "run", "heavy_sword_attack_1"]

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var resource = ResourceLoader.load("res://imported/character.glb")
	if resource == null or not resource is PackedScene:
		fail("GODOT_GLTF_NOT_LOADABLE", "Imported GLB is not a loadable PackedScene")
		return
	var instance = resource.instantiate()
	root.add_child(instance)
	var skeletons: Array[Node] = []
	var players: Array[Node] = []
	var meshes: Array[Node] = []
	collect(instance, skeletons, players, meshes)
	if skeletons.is_empty() or skeletons[0].get_bone_count() < 16:
		fail("GODOT_SKELETON_INVALID", "Expected an imported humanoid Skeleton3D")
		return
	var actions: Dictionary = {}
	for player in players:
		for action in player.get_animation_list(): actions[String(action).get_file()] = true
	for required in REQUIRED_ACTIONS:
		if not actions.has(required):
			fail("GODOT_ACTION_MISSING", "Missing action: " + required)
			return
	var material_count := 0
	var bounds := AABB()
	var first := true
	for mesh_instance in meshes:
		var local: AABB = mesh_instance.get_aabb()
		var world: AABB = mesh_instance.global_transform * local
		bounds = world if first else bounds.merge(world)
		first = false
		for surface in mesh_instance.mesh.get_surface_count():
			if mesh_instance.mesh.surface_get_material(surface) != null: material_count += 1
	if meshes.is_empty() or material_count == 0:
		fail("GODOT_MESH_OR_MATERIAL_MISSING", "No imported mesh materials were found")
		return
	var largest := maxf(bounds.size.x, maxf(bounds.size.y, bounds.size.z))
	if largest < 4.0 or largest > 12.0:
		fail("GODOT_SCALE_INVALID", "Imported bounds are outside the meter-scale pilot profile: " + str(bounds))
		return
	print(JSON.stringify({"status":"passed","skeleton_bones":skeletons[0].get_bone_count(),"actions":actions.keys(),"mesh_count":meshes.size(),"material_count":material_count,"bounds_position":bounds.position,"bounds_size":bounds.size}))
	quit(0)

func collect(node: Node, skeletons: Array[Node], players: Array[Node], meshes: Array[Node]) -> void:
	if node is Skeleton3D: skeletons.append(node)
	if node is AnimationPlayer: players.append(node)
	if node is MeshInstance3D: meshes.append(node)
	for child in node.get_children(): collect(child, skeletons, players, meshes)

func fail(code: String, message: String) -> void:
	printerr(code + ": " + message)
	quit(1)
