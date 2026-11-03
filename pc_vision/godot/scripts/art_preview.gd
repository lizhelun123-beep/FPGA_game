extends Node2D
## A presentation-only surface. No serial, capture, physics, game timer or scoring.
## Python/C supplies complete scenes and authoritative results through these methods.
signal command_requested(action: String, context: Dictionary)

const DESIGN_SIZE := Vector2(1280, 720)
const INK := Color("#514331")
const MUTED := Color("#7d8067")
const TEAL := Color("#338a78")
const ASSET_ROOT := "res://assets/"
const LEVEL_NAMES := ["镜光初见", "穿越之门", "光的回环"]
const GAME_BOARD_AREA := Rect2(58, 126, 1164, 510)

class BoardArt extends Node2D:
	var presenter
	var area := Rect2()
	var objects: Array = []
	var rays: Array = []
	var stale := false
	var reference := false
	func _draw() -> void:
		if presenter != null:
			presenter.draw_board(self, area, objects, rays, stale, reference)

var config: Dictionary = {}
var board_config: Dictionary = {}
var model_sizes: Dictionary = {}
var levels: Array = []
var textures: Dictionary = {}
var model_art_rects: Dictionary = {}
var font: SystemFont
var ui: Control
var selected_index := 0
var screen := "menu"
var scene_data: Dictionary = {}
var result_data: Dictionary = {}
var startup_error := ""
var scene_file := ""
var result_file := ""
var screenshot_file := ""
var requested_screen := "menu"
var effect_preview := false
var recent_hit_ids: Array[String] = []
var active_sparks: Array[Node2D] = []
var live_mode := false
var bridge_port := 47632
var bridge := StreamPeerTCP.new()
var bridge_buffer := PackedByteArray()
var bridge_retry_ms := 0
var last_packet_ms := 0
var game_board: BoardArt
var timer_label: Label
var status_label: Label
var start_button: Button
var model_nominal_sizes: Dictionary = {}

func _ready() -> void:
	font = SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "sans-serif"])
	font.font_weight = 600
	_parse_arguments()
	_load_config()
	_load_assets()
	if live_mode:
		command_requested.connect(_send_command)
	if not scene_file.is_empty():
		var incoming = _read_json(scene_file)
		if _scene_valid(incoming) or _reference_valid(incoming):
			scene_data = incoming.duplicate(true)
			for index in range(levels.size()):
				if int(levels[index].get("id", 0)) == int(scene_data.get("level_id", 0)):
					selected_index = index
					break
		else:
			startup_error = "正在准备关卡，请稍候"
	if not result_file.is_empty():
		var incoming_result = _read_json(result_file)
		if _result_valid(incoming_result):
			result_data = incoming_result.duplicate(true)
		else:
			startup_error = "正在读取挑战成绩，请稍候"
	_show_screen(requested_screen)
	if effect_preview:
		_preview_spark.call_deferred()
	if not screenshot_file.is_empty():
		_save_screenshot.call_deferred()

func _parse_arguments() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--screen="):
			requested_screen = argument.trim_prefix("--screen=")
		elif argument.begins_with("--scene="):
			scene_file = argument.trim_prefix("--scene=")
		elif argument.begins_with("--result="):
			result_file = argument.trim_prefix("--result=")
		elif argument.begins_with("--screenshot="):
			screenshot_file = argument.trim_prefix("--screenshot=")
		elif argument == "--effect-preview":
			effect_preview = true
		elif argument.begins_with("--bridge=127.0.0.1:"):
			bridge_port = int(argument.trim_prefix("--bridge=127.0.0.1:"))
			live_mode = bridge_port > 0 and bridge_port <= 65535

func _process(_delta: float) -> void:
	if not live_mode:
		return
	bridge.poll()
	var now := Time.get_ticks_msec()
	if bridge.get_status() == StreamPeerTCP.STATUS_NONE or bridge.get_status() == StreamPeerTCP.STATUS_ERROR:
		if not scene_data.is_empty() and scene_data.get("state") != "DISCONNECTED":
			_mark_bridge_gap(true)
		if now >= bridge_retry_ms:
			bridge.disconnect_from_host()
			bridge_buffer.clear()
			bridge.connect_to_host("127.0.0.1", bridge_port)
			bridge_retry_ms = now + 1000
		return
	var available := bridge.get_available_bytes()
	if available > 0:
		var received := bridge.get_data(mini(available, 16384))
		if received[0] != OK:
			bridge.disconnect_from_host()
			return
		_consume_bridge_bytes(received[1])
	var update_window_ms := int(board_config.get("scene_max_age_ms", 350))
	if last_packet_ms > 0 and now - last_packet_ms > update_window_ms and scene_data.get("state") == "LIVE":
		_mark_bridge_gap(false)
	if last_packet_ms > 0 and now - last_packet_ms >= 6000 and not _keep_running_scene() and not scene_data.get("models", []).is_empty():
		scene_data["models"] = []
		scene_data["segments"] = []
		_refresh_live_game()

func _keep_running_scene() -> bool:
	return screen == "game" and int(scene_data.get("game_state", 0)) == 2 and not scene_data.get("models", []).is_empty()

func _mark_bridge_gap(disconnected: bool) -> void:
	# Keep the complete last picture of a running level. It remains stale and
	# cannot emit hit effects; the Python/C authority owns any replacement.
	if not _keep_running_scene() and disconnected:
		scene_data["models"] = []
		scene_data["segments"] = []
	scene_data["state"] = "DISCONNECTED" if disconnected else "STALE"
	scene_data["valid"] = false
	scene_data["success"] = false
	scene_data["display_status"] = "正在连接控制程序，请确认连接程序已启动" if disconnected else "正在更新物块位置"
	if disconnected:
		scene_data["board_ready"] = false
	_clear_sparks()
	_refresh_live_game()

func _consume_bridge_bytes(data: PackedByteArray) -> void:
	bridge_buffer.append_array(data)
	if bridge_buffer.size() > 65536:
		bridge_buffer.clear()
		bridge.disconnect_from_host()
		return
	while bridge_buffer.has(10):
		var end := bridge_buffer.find(10)
		# Decode only complete UTF8 messages; a TCP read may split a Chinese glyph.
		var packet = JSON.parse_string(bridge_buffer.slice(0, end).get_string_from_utf8())
		bridge_buffer = bridge_buffer.slice(end + 1)
		if packet is Dictionary:
			last_packet_ms = Time.get_ticks_msec()
			_receive_packet(packet)
func _send_command(action: String, context: Dictionary) -> void:
	if bridge.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return
	var command := {"action": action}
	command.merge(context)
	bridge.put_data((JSON.stringify(command) + "\n").to_utf8_buffer())

func _receive_packet(packet: Dictionary) -> void:
	if not _scene_valid(packet):
		return
	var next_screen := str(packet.get("screen", "menu"))
	for index in range(levels.size()):
		if int(levels[index].get("id")) == int(packet.get("level_id")):
			selected_index = index
	if next_screen == "result":
		if packet.get("result") is Dictionary and _result_valid(packet["result"]):
			if screen != "result" or packet["result"] != result_data:
				present_result(packet["result"])
		return
	if next_screen != screen:
		scene_data = packet.duplicate(true)
		_show_screen(next_screen)
	else:
		present_scene(packet)

func _refresh_live_game() -> void:
	if screen != "game" or not is_instance_valid(game_board):
		return
	game_board.objects = scene_data.get("models", [])
	game_board.rays = scene_data.get("segments", [])
	game_board.stale = str(scene_data.get("state", "")) not in ["LIVE", "VALID"]
	# The fixed emitter is configuration, so it can be shown before any camera
	# pose exists. Never fill missing physical objects from the level preview.
	if game_board.objects.is_empty() and int(scene_data.get("game_state", 0)) == 1 and scene_data.get("state") != "DISCONNECTED":
		var emitter: Dictionary = levels[selected_index].get("emitter", {})
		if emitter.has("point") and emitter.has("direction"):
			game_board.objects = [{"type": "SOURCE", "center": emitter["point"], "axis": emitter["direction"],
				"size": model_sizes["SOURCE"], "logical_emitter": true}]
			game_board.stale = false
	game_board.queue_redraw()
	if is_instance_valid(timer_label):
		timer_label.text = _format_time(int(scene_data.get("remaining_ms", 180000)))
	if is_instance_valid(status_label):
		status_label.text = str(scene_data.get("display_status", "请摆放本关物块"))
	if is_instance_valid(start_button):
		start_button.visible = int(scene_data.get("game_state", 0)) == 1
		var board_ready := bool(scene_data.get("board_ready", scene_data.get("ready", false)))
		var packet_state := str(scene_data.get("state", ""))
		start_button.disabled = not board_ready or packet_state in ["HELD", "DISCONNECTED"]

func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_error("Cannot open JSON: " + path)
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		push_error("Expected a JSON object: " + path)
		return {}
	return parsed

func _load_config() -> void:
	# The existing hand-edited game_config.json remains the only configuration.
	var config_path = ProjectSettings.globalize_path("res://").path_join("../game_config.json").simplify_path()
	config = _read_json(config_path)
	board_config = config.get("board_game", {})
	model_sizes = config.get("model_sizes", {})
	levels = board_config.get("levels", [])
	if levels.is_empty() or model_sizes.is_empty():
		startup_error = "关卡加载失败，请重新启动游戏"

func _load_assets() -> void:
	for name in ["landscape", "clouds", "foliage"]:
		_load_texture("background/" + name + ".png")
	for name in ["SOURCE", "MIRROR", "WALL", "TARGET", "PORTAL_A", "PORTAL_B"]:
		var path = "models/" + name.to_lower() + ".svg"
		_load_texture(path)
		# SVG viewBox encodes its physics-origin anchor and transparent padding.
		# No duplicated pose atlas or hand-maintained object-size configuration.
		var parser = XMLParser.new()
		if parser.open(ASSET_ROOT + path) == OK:
			while parser.read() == OK:
				if parser.get_node_type() == XMLParser.NODE_ELEMENT and parser.get_node_name() == "svg":
					var values = parser.get_named_attribute_value("viewBox").split(" ", false)
					if values.size() == 4:
						model_art_rects[name] = Rect2(float(values[0]), float(values[1]), float(values[2]), float(values[3]))
						model_nominal_sizes[name] = Vector2(float(parser.get_named_attribute_value("data-model-length")), float(parser.get_named_attribute_value("data-model-width")))
					break
	for role in ["primary", "secondary", "card"]:
		for state in ["normal", "hover", "pressed", "disabled"]:
			_load_texture("ui/" + role + "_" + state + ".svg")
	for name in ["panel", "star_filled", "star_empty"]:
		_load_texture("ui/" + name + ".svg")

func _load_texture(relative_path: String) -> void:
	if ResourceLoader.exists(ASSET_ROOT + relative_path):
		textures[relative_path] = load(ASSET_ROOT + relative_path)

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("#a2dfe9"))
	var background: Texture2D = textures.get("background/landscape.png")
	if background:
		draw_texture_rect(background, Rect2(Vector2.ZERO, DESIGN_SIZE), false)
	else:
		draw_rect(Rect2(0, 470, 1280, 250), Color("#b8dc8a"))
		draw_circle(Vector2(1100, 130), 70, Color("#ffed9c"))
	var clouds: Texture2D = textures.get("background/clouds.png")
	if clouds:
		draw_texture_rect(clouds, Rect2(Vector2.ZERO, DESIGN_SIZE), false)
	var foliage: Texture2D = textures.get("background/foliage.png")
	if foliage:
		draw_texture_rect(foliage, Rect2(Vector2.ZERO, DESIGN_SIZE), false)

func _show_screen(next_screen: String) -> void:
	if next_screen != screen or next_screen != "game":
		_clear_sparks()
	screen = next_screen if next_screen in ["menu", "game", "result"] else "menu"
	if ui != null:
		remove_child(ui)
		ui.queue_free()
	ui = Control.new()
	ui.name = "Presentation"
	ui.size = DESIGN_SIZE
	ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var theme = Theme.new()
	theme.default_font = font
	theme.default_font_size = 22
	ui.theme = theme
	add_child(ui)
	if screen == "menu":
		_build_menu()
	elif screen == "game":
		_build_game()
	else:
		_build_result()
	if not startup_error.is_empty():
		_label(startup_error, Rect2(180, 683, 920, 26), 16, Color("#884d3e"), HORIZONTAL_ALIGNMENT_CENTER)
	queue_redraw()

func _label(text: String, rect: Rect2, size: int = 22, color: Color = INK, align: HorizontalAlignment = HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var label = Label.new()
	label.text = text
	label.position = rect.position
	label.size = rect.size
	label.add_theme_color_override("font_color", color)
	label.add_theme_font_size_override("font_size", size)
	label.horizontal_alignment = align
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(label)
	return label

func _panel(rect: Rect2, asset: String = "panel") -> NinePatchRect:
	var panel = NinePatchRect.new()
	panel.texture = textures.get("ui/" + asset + ".svg")
	panel.position = rect.position
	panel.size = rect.size
	panel.patch_margin_left = 32
	panel.patch_margin_top = 32
	panel.patch_margin_right = 32
	panel.patch_margin_bottom = 32
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(panel)
	return panel

func _style(role: String, state: String) -> StyleBoxTexture:
	var style = StyleBoxTexture.new()
	style.texture = textures.get("ui/" + role + "_" + state + ".svg")
	for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
		style.set_texture_margin(side, 30)
		style.set_content_margin(side, 14)
	return style

func _button(text: String, rect: Rect2, callback: Callable, primary: bool = false) -> Button:
	var button = Button.new()
	button.text = text
	button.position = rect.position
	button.size = rect.size
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	button.add_theme_font_size_override("font_size", 25 if primary else 20)
	button.add_theme_color_override("font_color", INK)
	button.add_theme_color_override("font_hover_color", INK)
	button.add_theme_color_override("font_pressed_color", INK)
	button.add_theme_color_override("font_disabled_color", Color("#96978b"))
	for state in ["normal", "hover", "pressed", "disabled"]:
		button.add_theme_stylebox_override(state, _style("primary" if primary else "secondary", state))
	var focus = StyleBoxFlat.new()
	focus.bg_color = Color.TRANSPARENT
	focus.border_color = TEAL
	focus.set_border_width_all(3)
	focus.set_corner_radius_all(19)
	button.add_theme_stylebox_override("focus", focus)
	button.pressed.connect(callback)
	ui.add_child(button)
	return button

func _build_menu() -> void:
	_label("光路奇旅", Rect2(0, 12, 1280, 65), 46, INK, HORIZONTAL_ALIGNMENT_CENTER)
	_label("转动镜面 · 穿越传送门 · 点亮目标", Rect2(0, 75, 1280, 32), 21, Color("#50775b"), HORIZONTAL_ALIGNMENT_CENTER)
	var selection: Dictionary = board_config.get("selection", {})
	var count := mini(int(selection.get("slot_count", 15)), levels.size())
	var columns := int(selection.get("columns", 5))
	for index in range(count):
		var x := 45.0 + (index % columns) * 240.0
		var y := 118.0 + floori(float(index) / columns) * 148.0
		var card = Button.new()
		card.position = Vector2(x, 219)
		card.position.y = y
		card.size = Vector2(230, 138)
		card.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		for state in ["normal", "hover", "pressed", "disabled"]:
			card.add_theme_stylebox_override(state, _style("card", "pressed" if index == selected_index and state == "normal" else state))
		card.pressed.connect(_select_level.bind(index))
		ui.add_child(card)
		_label("第 %02d 关" % (index + 1), Rect2(x + 15, y + 7, 120, 28), 19, TEAL)
		_add_board(Rect2(x + 14, y + 34, 202, 70), _reference_models(levels[index]), [], false, true)
		var level_name := str(levels[index].get("name", LEVEL_NAMES[index] if index < LEVEL_NAMES.size() else "光路挑战"))
		_label(level_name, Rect2(x + 8, y + 104, 214, 24), 18, INK, HORIZONTAL_ALIGNMENT_CENTER)
		if index == selected_index:
			_label("已选择", Rect2(x + 139, y + 8, 76, 25), 14, TEAL, HORIZONTAL_ALIGNMENT_RIGHT)
	_button("进入关卡", Rect2(470, 577, 340, 67), _preview_game, true)
	_label("选择关卡，开始挑战", Rect2(0, 653, 1280, 28), 18, Color("#4b7259"), HORIZONTAL_ALIGNMENT_CENTER)

func _reference_models(level: Dictionary) -> Array:
	var objects: Array = level.get("objects", []).duplicate(true)
	var emitter: Dictionary = level.get("emitter", {})
	if not emitter.is_empty():
		objects.append({"type": "SOURCE", "center": emitter["point"], "axis": emitter["direction"], "logical_emitter": true})
	return objects

func _select_level(index: int) -> void:
	if index < 0 or index >= levels.size():
		return
	selected_index = index
	_show_screen("menu")

func _selected_level_id() -> int:
	if selected_index >= 0 and selected_index < levels.size():
		return int(levels[selected_index].get("id", selected_index + 1))
	return 0

func _preview_game() -> void:
	if live_mode:
		command_requested.emit("select", {"level_id": _selected_level_id()})
		return
	command_requested.emit("start", {"level_id": _selected_level_id(), "art_preview": true})
	if not scene_data.is_empty() and int(scene_data.get("level_id", 0)) != _selected_level_id():
		scene_data = {}
	_show_screen("game")

func _preview_next() -> void:
	if live_mode:
		command_requested.emit("skip", {})
		return
	command_requested.emit("skip", {"level_id": _selected_level_id(), "art_preview": true})
	if not levels.is_empty():
		selected_index = (selected_index + 1) % levels.size()
	scene_data = {}
	_show_screen("game")

func _build_game() -> void:
	_button("关卡菜单", Rect2(34, 28, 146, 58), _return_menu)
	var level_id = int(scene_data.get("level_id", _selected_level_id()))
	_label("第 %02d 关" % level_id, Rect2(210, 28, 260, 58), 30)
	_panel(Rect2(526, 20, 228, 75))
	var remaining = scene_data.get("remaining_ms", null)
	timer_label = _label(_format_time(int(remaining)) if remaining != null else "--:--", Rect2(536, 24, 208, 60), 38, INK, HORIZONTAL_ALIGNMENT_CENTER)
	_label("剩余时间", Rect2(760, 30, 110, 45), 16, Color("#4d715b"))
	_button("跳过本关", Rect2(1094, 29, 152, 58), _preview_next)
	if live_mode:
		start_button = _button("开始计时", Rect2(881, 29, 185, 58), func(): command_requested.emit("start", {}), true)
	_panel(Rect2(40, 111, 1200, 542))
	if scene_data.is_empty():
		_add_board(GAME_BOARD_AREA, [], [], false, false)
		_label("等待场景准备", Rect2(100, 300, 1080, 68), 34, Color("#789474"), HORIZONTAL_ALIGNMENT_CENTER)
		_label("移动或转动物块，调整光的路线", Rect2(100, 367, 1080, 42), 21, MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	else:
		var stale = str(scene_data.get("state", "")).to_upper() in ["STALE", "DISCONNECTED", "MISSING", "EXPIRED", "HELD"]
		game_board = _add_board(GAME_BOARD_AREA, scene_data["models"], scene_data["segments"], stale, false)
	var status = "请摆放本关物块" if scene_data.is_empty() else str(scene_data.get("display_status", _state_label(str(scene_data.get("state", "")))))
	if scene_data.get("origin", "") == "config_reference_art_preview":
		status = "关卡布局"
	_panel(Rect2(42, 656, 1196, 51))
	status_label = _label(status, Rect2(64, 662, 700, 37), 19, TEAL)
	_label("轻轻转动实物，观察光的方向", Rect2(740, 662, 476, 37), 17, Color("#58745c"), HORIZONTAL_ALIGNMENT_RIGHT)
	if live_mode:
		_refresh_live_game()

func _return_menu() -> void:
	if live_mode:
		command_requested.emit("menu", {})
	else:
		_show_screen("menu")

func _state_label(value: String) -> String:
	match value.to_upper():
		"LIVE", "VALID": return "转动物块，点亮目标"
		"STALE", "HELD": return "正在更新物块位置"
		"DISCONNECTED": return "正在重新连接设备"
		"MISSING", "EXPIRED": return "请将本关物块放入场地"
		"ART_PREVIEW": return "关卡布局"
		_: return "请摆放本关物块"

func _build_result() -> void:
	# The stars and elapsed value are supplied; no threshold/solve logic lives here.
	_panel(Rect2(274, 83, 732, 550))
	var ready = not result_data.is_empty()
	var title = str(result_data.get("outcome", "挑战结算"))
	_label(title, Rect2(320, 117, 640, 65), 42, INK, HORIZONTAL_ALIGNMENT_CENTER)
	var stars = int(result_data.get("stars", -1))
	for index in range(3):
		var star = TextureRect.new()
		star.texture = textures.get("ui/star_filled.svg" if index < stars else "ui/star_empty.svg")
		star.position = Vector2(429 + index * 151, 209 if index != 1 else 190)
		star.size = Vector2(120, 120)
		star.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		star.mouse_filter = Control.MOUSE_FILTER_IGNORE
		ui.add_child(star)
	_label("本关用时", Rect2(390, 362, 200, 40), 23, MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	_label(_format_time(int(result_data["elapsed_ms"])) if ready else "--:--", Rect2(590, 351, 300, 65), 42, INK, HORIZONTAL_ALIGNMENT_CENTER)
	_label("继续挑战，收集更多星星", Rect2(330, 438, 620, 40), 22, TEAL, HORIZONTAL_ALIGNMENT_CENTER)
	_button("关卡菜单", Rect2(352, 531, 250, 67), _return_menu)
	_button("下一关", Rect2(676, 531, 250, 67), _preview_next, true)
	_panel(Rect2(300, 640, 680, 54))
	_label("选择下一关，继续挑战", Rect2(310, 648, 660, 32), 16, Color("#4e745b"), HORIZONTAL_ALIGNMENT_CENTER)

func _format_time(milliseconds: int) -> String:
	var seconds = int(maxi(0, milliseconds) / 1000)
	return "%02d:%02d" % [int(seconds / 60), seconds % 60]

func _add_board(area: Rect2, objects: Array, rays: Array, stale: bool, reference: bool) -> BoardArt:
	var board = BoardArt.new()
	board.presenter = self
	board.area = area
	board.objects = objects
	board.rays = rays
	board.stale = stale
	board.reference = reference
	ui.add_child(board)
	return board

func _world_transform(area: Rect2) -> Transform2D:
	var world = Vector2(float(board_config.get("width", 1279)), float(board_config.get("height", 719)))
	var scale_factor = minf(area.size.x / world.x, area.size.y / world.y)
	var origin = area.position + (area.size - world * scale_factor) * 0.5
	return Transform2D(0, Vector2(scale_factor, scale_factor), 0, origin)

func draw_board(canvas: Node2D, area: Rect2, objects: Array, rays: Array, stale: bool, reference: bool) -> void:
	var transform = _world_transform(area)
	var world = Vector2(float(board_config.get("width", 1279)), float(board_config.get("height", 719)))
	var bounds = Rect2(transform.origin, world * transform.get_scale())
	canvas.draw_rect(bounds, Color("#edf3d7") if reference else Color("#f6f4dc"))
	canvas.draw_style_box(_board_border(), bounds)
	# A single uniform transform applies to centers, axes, art and ray endpoints.
	# The quiet flat board keeps the authoritative geometry readable.
	var geometry_alpha = 1.0 if live_mode else (0.40 if stale else 1.0)
	for object in objects:
		var kind = str(object.get("type", ""))
		var center = _vector(object.get("center", []))
		var axis = _vector(object.get("axis", []))
		var texture: Texture2D = textures.get("models/" + kind.to_lower() + ".svg")
		if texture == null or not model_art_rects.has(kind):
			continue
		var rotation = axis.angle()
		var size := _vector(object.get("size", model_sizes.get(kind, [])))
		var nominal: Vector2 = model_nominal_sizes.get(kind, size)
		if nominal.x <= 0 or nominal.y <= 0 or size.x <= 0 or size.y <= 0:
			continue
		if object.get("logical_emitter", false):
			center -= axis.normalized() * size.x * (2.0 / 3.0)
		var model_transform = transform * Transform2D(rotation, size / nominal, 0, center)
		canvas.draw_set_transform_matrix(model_transform)
		var tint = Color(1, 1, 1, geometry_alpha * (0.6 if object.get("held", false) and not live_mode else 1.0))
		canvas.draw_texture_rect(texture, model_art_rects[kind], false, tint)
	canvas.draw_set_transform_matrix(Transform2D.IDENTITY)
	for ray in rays:
		var endpoints = _ray_points(ray)
		if endpoints.size() != 2:
			continue
		var a = transform * endpoints[0]
		var b = transform * endpoints[1]
		var alpha = 0.30 if stale else 1.0
		canvas.draw_line(a, b, Color(0.96, 0.66, 0.16, 0.11 * alpha), 16, true)
		canvas.draw_line(a, b, Color(0.98, 0.69, 0.17, 0.30 * alpha), 8, true)
		canvas.draw_line(a, b, Color(1, 0.79, 0.22, alpha), 4, true)
		canvas.draw_line(a, b, Color(1, 0.98, 0.79, alpha), 1.5, true)

func _board_border() -> StyleBoxFlat:
	var style = StyleBoxFlat.new()
	style.bg_color = Color.TRANSPARENT
	style.border_color = Color("#c4cba9")
	style.set_border_width_all(1)
	style.set_corner_radius_all(8)
	return style

func _vector(value) -> Vector2:
	if value is Array and value.size() >= 2:
		return Vector2(float(value[0]), float(value[1]))
	return Vector2.ZERO

func _ray_points(ray) -> Array:
	if ray is Array and ray.size() == 4:
		return [Vector2(float(ray[0]), float(ray[1])), Vector2(float(ray[2]), float(ray[3]))]
	if ray is Dictionary and ray.has("start") and ray.has("end"):
		return [_vector(ray["start"]), _vector(ray["end"])]
	return []

func _geometry_valid(snapshot: Dictionary) -> bool:
	# Preserve provenance as supplied. Freshness and acceptance belong to Python/C.
	for key in ["generation", "sequence", "captured_ms", "level_id", "state", "models", "segments"]:
		if not snapshot.has(key):
			return false
	if not snapshot["models"] is Array or not snapshot["segments"] is Array:
		return false
	for model in snapshot["models"]:
		if not model is Dictionary or not model.has("type") or not model.has("center") or not model.has("axis"):
			return false
		if not model_sizes.has(str(model["type"])):
			return false
	for ray in snapshot["segments"]:
		if _ray_points(ray).size() != 2:
			return false
	return true

func _scene_valid(snapshot: Dictionary) -> bool:
	if not _geometry_valid(snapshot) or snapshot.get("origin", "") == "config_reference_art_preview":
		return false
	for key in ["generation", "sequence", "captured_ms"]:
		if snapshot[key] == null:
			return false
	return true

func _reference_valid(snapshot: Dictionary) -> bool:
	if not _geometry_valid(snapshot):
		return false
	return snapshot.get("origin", "") == "config_reference_art_preview" and snapshot.get("state", "") == "ART_PREVIEW" and snapshot["generation"] == null and snapshot["sequence"] == null and snapshot["captured_ms"] == null

func _result_valid(result: Dictionary) -> bool:
	return result.has("elapsed_ms") and result.has("stars") and int(result["stars"]) >= 0 and int(result["stars"]) <= 3

func present_scene(snapshot: Dictionary) -> bool:
	if not _scene_valid(snapshot):
		push_error("Rejected incomplete presentation snapshot")
		return false
	if snapshot.get("generation") != scene_data.get("generation") or snapshot.get("level_id") != scene_data.get("level_id"):
		recent_hit_ids.clear()
	if snapshot.get("sequence") != scene_data.get("sequence") or str(snapshot.get("state", "")).to_upper() not in ["LIVE", "VALID"]:
		_clear_sparks()
	scene_data = snapshot.duplicate(true)
	if screen == "game":
		if live_mode:
			_refresh_live_game()
		else:
			_show_screen("game")
	return true

func present_result(result: Dictionary) -> bool:
	if not _result_valid(result):
		push_error("Result requires externally supplied elapsed_ms and stars 0..3")
		return false
	result_data = result.duplicate(true)
	_show_screen("result")
	return true

func present_hit(event: Dictionary) -> bool:
	# This is decoration of an externally accepted hit, never a hit test or score.
	if screen != "game" or not _scene_valid(scene_data):
		return false
	if str(scene_data.get("state", "")).to_upper() not in ["LIVE", "VALID"]:
		return false
	for key in ["generation", "sequence", "captured_ms", "level_id"]:
		if not event.has(key) or event[key] != scene_data[key]:
			return false
	if not _finite_point(event.get("position")) or not _finite_point(event.get("direction")):
		return false
	var event_id = str(event.get("id", ""))
	if event_id.is_empty():
		return false
	var key = "%s:%s:%s:%s" % [event["generation"], event["level_id"], event["sequence"], event_id]
	if key in recent_hit_ids:
		return false
	recent_hit_ids.append(key)
	if recent_hit_ids.size() > 64:
		recent_hit_ids.pop_front()
	_spawn_spark(_vector(event["position"]), _vector(event["direction"]))
	return true

func _finite_point(value) -> bool:
	if not value is Array or value.size() != 2:
		return false
	for number in value:
		if typeof(number) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(number)):
			return false
	return true

func _spawn_spark(world_position: Vector2, direction: Vector2) -> void:
	var effect: Node2D = load("res://effects/hit_spark.tscn").instantiate()
	effect.position = _world_transform(GAME_BOARD_AREA) * world_position
	effect.z_index = 10
	active_sparks = active_sparks.filter(func(item): return is_instance_valid(item))
	if active_sparks.size() >= 8:
		active_sparks.pop_front().queue_free()
	add_child(effect)
	active_sparks.append(effect)
	effect.burst(direction)

func _clear_sparks() -> void:
	for effect in active_sparks:
		if is_instance_valid(effect):
			effect.queue_free()
	active_sparks.clear()

func _preview_spark() -> void:
	# Explicit CLI-only artwork sample. It never enters present_scene/present_hit.
	if screen != "game" or not _reference_valid(scene_data) or scene_data["segments"].is_empty():
		return
	var segment = _ray_points(scene_data["segments"][0])
	_spawn_spark(segment[1], (segment[1] - segment[0]).normalized())

func _save_screenshot() -> void:
	# A real renderer is required. Headless dummy rendering cannot prove artwork.
	if DisplayServer.get_name() == "headless":
		push_error("Screenshot requires a real rendering backend, not headless dummy rendering")
		get_tree().quit(2)
		return
	await get_tree().process_frame
	await get_tree().process_frame
	if effect_preview:
		await get_tree().create_timer(0.10).timeout
	await RenderingServer.frame_post_draw
	var image = get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		push_error("Screenshot unavailable: use an actual rendering backend, not headless dummy rendering")
		get_tree().quit(2)
		return
	var error = image.save_png(screenshot_file)
	if error != OK:
		push_error("Cannot save screenshot: " + screenshot_file)
		get_tree().quit(3)
		return
	print("ART_PREVIEW_SCREENSHOT " + screenshot_file)
	get_tree().quit()

