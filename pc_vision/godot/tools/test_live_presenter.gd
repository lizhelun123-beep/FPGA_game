extends SceneTree
## Software fixtures only. Does not open a UART or certify a camera scene.
var commands: Array = []

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var presenter = load("res://main.tscn").instantiate()
	root.add_child(presenter)
	await process_frame
	presenter.set_process(false)
	var cards := 0
	var disabled := 0
	var previews := 0
	for child in presenter.ui.get_children():
		if child is Node2D:
			assert(child.reference and child.objects.size() >= 3)
			previews += 1
		if child is Label:
			assert(not child.text.contains("待配置") and not child.text.contains("等待配置"))
		if child is Button and child.size == Vector2(230, 138):
			cards += 1
			if child.disabled:
				disabled += 1
	assert(cards == 15 and previews == 15 and disabled == 0)
	presenter._select_level(1)
	presenter._select_level(14)
	assert(presenter.selected_index == 14)
	presenter._select_level(15)
	assert(presenter.selected_index == 14)
	presenter.live_mode = true
	presenter.command_requested.connect(func(action, context): commands.append([action, context]))
	presenter._preview_game()
	assert(commands[-1] == ["select", {"level_id": 15}])
	var packet := {"generation": 3, "sequence": 10, "captured_ms": 9000, "level_id": 2,
		"game_state": 1, "state": "LIVE", "screen": "game", "remaining_ms": 180000,
		"display_status": "软件定位样例", "ready": true,
		"models": [{"type": "PORTAL_A", "center": [600, 300], "axis": [0, 1], "size": [164, 56]}],
		"segments": [[10, 300, 570, 300]]}
	presenter._receive_packet(packet)
	assert(presenter.screen == "game")
	assert(presenter.game_board.objects.size() == 1)
	assert(not presenter.start_button.disabled)
	packet["state"] = "STALE"
	packet["board_ready"] = true
	presenter._receive_packet(packet)
	assert(not presenter.start_button.disabled) # READY does not require pre-start POSE2.
	packet["board_ready"] = false
	presenter._receive_packet(packet)
	assert(presenter.start_button.disabled)
	var observed_models = packet["models"]
	packet["models"] = []
	presenter._receive_packet(packet)
	assert(presenter.scene_data["models"].is_empty())
	assert(presenter.game_board.objects.size() == 1 and presenter.game_board.objects[0]["type"] == "SOURCE")
	packet["models"] = observed_models
	packet["board_ready"] = true
	packet["state"] = "LIVE"
	presenter._receive_packet(packet)
	presenter.start_button.pressed.emit()
	assert(commands[-1][0] == "start")
	var button = presenter.start_button
	for sequence in range(11, 30):
		packet["sequence"] = sequence
		presenter._receive_packet(packet)
	assert(button == presenter.start_button) # Receiving a pose never replaces a pressed button.
	var bytes := (JSON.stringify(packet) + "\n").to_utf8_buffer()
	for split in range(bytes.size() + 1):
		presenter._consume_bridge_bytes(bytes.slice(0, split))
		presenter._consume_bridge_bytes(bytes.slice(split))
		assert(presenter.scene_data["display_status"] == "软件定位样例")
	packet["state"] = "HELD"
	presenter._receive_packet(packet)
	assert(presenter.game_board.stale and presenter.start_button.disabled)
	packet["game_state"] = 2
	packet["board_started"] = true
	packet["valid"] = false
	presenter._receive_packet(packet)
	var retained_scene: Dictionary = presenter.scene_data.duplicate(true)
	presenter._mark_bridge_gap(false)
	assert(presenter._keep_running_scene())
	assert(presenter.game_board.objects == retained_scene["models"])
	assert(presenter.game_board.rays == retained_scene["segments"])
	presenter._mark_bridge_gap(true)
	assert(presenter.game_board.objects == retained_scene["models"])
	assert(presenter.game_board.rays == retained_scene["segments"])
	assert(not presenter.scene_data["valid"] and not presenter.scene_data["success"])
	assert(presenter.scene_data["captured_ms"] == retained_scene["captured_ms"])
	# A complete replacement changes objects and rays together, without an
	# empty scene between the retained frame and the new frame.
	packet["sequence"] = 40
	packet["models"] = [{"type": "PORTAL_B", "center": [650, 330], "axis": [1, 0], "size": [164, 56]}]
	packet["segments"] = [[20, 330, 620, 330]]
	packet["state"] = "LIVE"
	packet["valid"] = true
	presenter._receive_packet(packet)
	assert(presenter.game_board.objects == packet["models"])
	assert(presenter.game_board.rays == packet["segments"])
	assert(not presenter.game_board.stale)
	packet["screen"] = "result"
	packet["result"] = {"elapsed_ms": 61000, "stars": 2, "outcome": "软件结算样例"}
	presenter._receive_packet(packet)
	assert(presenter.screen == "result" and presenter.result_data["stars"] == 2)
	presenter._return_menu()
	assert(commands[-1][0] == "menu")
	print("PASS_GODOT_15_CONTENT_CARDS_ALL_ENABLED_RANDOM_LEVELS_COMMANDS_ATOMIC_POSES_RESULT")
	quit()
