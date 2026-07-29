extends Node3D

var config: Dictionary
var character: Node3D
var camera: Camera3D
var parts: Array[Node] = []
var skeleton: Skeleton3D
var player: AnimationPlayer
var part_list: ItemList
var bone_list: OptionButton
var action_list: OptionButton
var fields: Dictionary = {}
var socket_name: OptionButton
var status: Label
var orbit_yaw := 0.7
var orbit_pitch := -0.25
var distance := 7.0

func _ready() -> void:
	config = JSON.parse_string(FileAccess.get_file_as_string("res://editor_config.json"))
	var packed = load("res://imported/character.glb")
	if packed == null: push_error("EDITOR_GLTF_MISSING"); get_tree().quit(2); return
	character = packed.instantiate(); add_child(character); _collect(character)
	if OS.get_cmdline_user_args().has("--validate"):
		if parts.is_empty() or skeleton == null or player == null:push_error("EDITOR_SCENE_CONTRACT_INVALID");get_tree().quit(3);return
		print(JSON.stringify({"status":"passed","parts":parts.size(),"bones":skeleton.get_bone_count(),"actions":player.get_animation_list().size()}));get_tree().quit();return
	_setup_world(); _setup_ui(); _frame_camera(); _load_existing()

func _collect(node: Node) -> void:
	if node is MeshInstance3D and not "_LOD" in node.name: parts.append(node)
	if node is Skeleton3D and skeleton == null: skeleton = node
	if node is AnimationPlayer and player == null: player = node
	for child in node.get_children(): _collect(child)

func _setup_world() -> void:
	camera=Camera3D.new();add_child(camera);camera.current=true
	var light=DirectionalLight3D.new();light.rotation_degrees=Vector3(-50,-30,0);light.light_energy=1.8;add_child(light)
	var environment=WorldEnvironment.new();var env=Environment.new();env.background_mode=Environment.BG_COLOR;env.background_color=Color("18202b");env.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR;env.ambient_light_color=Color.WHITE;env.ambient_light_energy=0.7;environment.environment=env;add_child(environment)

func _setup_ui() -> void:
	var panel=PanelContainer.new();panel.set_anchors_and_offsets_preset(Control.PRESET_LEFT_WIDE);panel.custom_minimum_size=Vector2(330,0);add_child(panel)
	var column=VBoxContainer.new();panel.add_child(column)
	var title=Label.new();title.text="3D Character Editor — "+str(config.get("job_id","character"));title.add_theme_font_size_override("font_size",20);column.add_child(title)
	part_list=ItemList.new();part_list.custom_minimum_size=Vector2(310,210);column.add_child(part_list)
	for part in parts:part_list.add_item(part.name)
	part_list.item_selected.connect(_select_part)
	var grid=GridContainer.new();grid.columns=4;column.add_child(grid)
	for label in ["X","Y","Z"]:var spacer=Label.new();spacer.text=label;grid.add_child(spacer)
	var blank=Label.new();grid.add_child(blank);grid.move_child(blank,0)
	for group in ["location","rotation_degrees","scale"]:
		var heading=Label.new();heading.text=group;grid.add_child(heading)
		for axis in range(3):var box=SpinBox.new();box.min_value=-100 if group!="scale" else 0.01;box.max_value=100;box.step=0.01 if group!="rotation_degrees" else 1;box.value=1 if group=="scale" else 0;fields[group+str(axis)]=box;grid.add_child(box)
	var apply=Button.new();apply.text="Apply part transform";apply.pressed.connect(_apply_transform);column.add_child(apply)
	var bone_label=Label.new();bone_label.text="Rig / socket parent";column.add_child(bone_label);bone_list=OptionButton.new();column.add_child(bone_list)
	if skeleton:
		for index in skeleton.get_bone_count():bone_list.add_item(skeleton.get_bone_name(index))
	socket_name=OptionButton.new();column.add_child(socket_name)
	if skeleton:
		for index in range(skeleton.get_bone_count()):
			var candidate=skeleton.get_bone_name(index)
			if "socket" in candidate or candidate.ends_with("_root"):socket_name.add_item(candidate)
	var socket=Button.new();socket.text="Author socket at selected part";socket.pressed.connect(_author_socket);column.add_child(socket)
	action_list=OptionButton.new();column.add_child(action_list)
	if player:
		for action in player.get_animation_list():action_list.add_item(action)
	var play=Button.new();play.text="Play / preview animation";play.pressed.connect(_play);column.add_child(play)
	var save=Button.new();save.text="Validate and save changes";save.pressed.connect(_save);column.add_child(save)
	status=Label.new();status.text="Drag viewport to orbit; wheel to zoom.";status.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART;column.add_child(status)

func _load_existing() -> void:
	var transforms: Dictionary=config.get("part_transforms",{})
	for part in parts:
		var value: Dictionary=transforms.get(part.name,{})
		if not value.is_empty():part.position=_vec(value.get("location",[0,0,0]));part.rotation_degrees=_vec(value.get("rotation_degrees",[0,0,0]));part.scale=_vec(value.get("scale",[1,1,1]))
	if not parts.is_empty():part_list.select(0);_select_part(0)

func _vec(value:Array)->Vector3:return Vector3(float(value[0]),float(value[1]),float(value[2]))
func _array(value:Vector3)->Array:return [value.x,value.y,value.z]
func _select_part(index:int)->void:
	var part=parts[index]
	for axis in range(3):fields["location"+str(axis)].value=part.position[axis];fields["rotation_degrees"+str(axis)].value=part.rotation_degrees[axis];fields["scale"+str(axis)].value=part.scale[axis]
	status.text="Part: "+part.name
func _apply_transform()->void:
	if part_list.get_selected_items().is_empty():return
	var part=parts[part_list.get_selected_items()[0]]
	part.position=Vector3(fields.location0.value,fields.location1.value,fields.location2.value);part.rotation_degrees=Vector3(fields.rotation_degrees0.value,fields.rotation_degrees1.value,fields.rotation_degrees2.value);part.scale=Vector3(fields.scale0.value,fields.scale1.value,fields.scale2.value);status.text="Applied transform to "+part.name
func _author_socket()->void:
	if socket_name.item_count==0 or part_list.get_selected_items().is_empty() or bone_list.item_count==0:status.text="Choose a part and existing socket.";return
	var name=socket_name.get_item_text(socket_name.selected);var sockets:Dictionary=config.get("socket_overrides",{});var part=parts[part_list.get_selected_items()[0]];sockets[name]={"bone":bone_list.get_item_text(bone_list.selected),"offset":_array(part.position)};config.socket_overrides=sockets;status.text="Socket authored: "+name
func _play()->void:
	if player and action_list.item_count:player.play(action_list.get_item_text(action_list.selected));status.text="Previewing "+action_list.get_item_text(action_list.selected)
func _save()->void:
	var transforms:Dictionary={}
	for part in parts:transforms[part.name]={"location":_array(part.position),"rotation_degrees":_array(part.rotation_degrees),"scale":_array(part.scale)}
	var result={"schema_version":1,"part_transforms":transforms,"socket_overrides":config.get("socket_overrides",{})}
	var file=FileAccess.open("res://editor_result.json",FileAccess.WRITE);file.store_string(JSON.stringify(result,"  "));file.close();get_tree().quit()
func _frame_camera()->void:
	_update_camera()
func _update_camera()->void:
	var target=Vector3(0,1,0);camera.position=target+Vector3(cos(orbit_yaw)*cos(orbit_pitch),sin(orbit_pitch),sin(orbit_yaw)*cos(orbit_pitch))*distance;camera.look_at(target,Vector3.UP)
func _unhandled_input(event:InputEvent)->void:
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):orbit_yaw-=event.relative.x*.01;orbit_pitch=clamp(orbit_pitch-event.relative.y*.01,-1.3,1.3);_update_camera()
	elif event is InputEventMouseButton and event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP,MOUSE_BUTTON_WHEEL_DOWN]:distance=clamp(distance+(-.5 if event.button_index==MOUSE_BUTTON_WHEEL_UP else .5),1.5,30.0);_update_camera()
