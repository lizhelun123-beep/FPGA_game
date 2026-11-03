"""Focused configuration contract checks; no images, compiler or devices."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "generate_game_config", Path(__file__).resolve().parents[1] / "tools/generate_game_config.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def configuration():
    return {
        "version": 1,
        "model_sizes": {kind: [20, 20] for kind in MODULE.TYPES},
        "physics_scale": 100,
        "board_game": {
            "version": 1, "coordinate_space": "uncalibrated_preview",
            "width": 1279, "height": 719, "max_models": 6,
            "render_max_ray_segments": 5, "scene_max_age_ms": 250,
            "duration_ms": 180000, "star_threshold_ms": [60000, 120000],
            "pump_tick_ms": 10,
            "menu": {"version": 1, "width": 1280, "height": 720,
                     "level_rects": [[20, 20, 200, 60]], "start_rect": [20, 640, 200, 60]},
            "render": {"version": 1, "scene_rect": [20, 120, 880, 420]},
            "levels": [{
                "id": 1, "reference": "sample_photo(1)/001.png",
                "emitter": {"point": [100, 300], "direction": [1, 0],
                            "coordinate_space": "uncalibrated_preview"},
                "objects": [{"type": "TARGET", "motion": "free",
                             "center": [600, 100], "axis": [1, 0]}],
            }],
        },
    }


class LogicalEmitterConfigTest(unittest.TestCase):
    def test_beam_support_gap_is_explicit_and_scoped(self):
        config = json.loads((MODULE.ROOT/'pc_vision/game_config.json').read_text(encoding='utf-8'))
        beam = config['real_scene']['beam']
        self.assertEqual(beam['stability_support_gap_ms'], 350)
        text = MODULE.generate_beam(config)
        self.assertRegex(text, r',350\n};\n$')
        del beam['stability_support_gap_ms']
        self.assertRegex(MODULE.generate_beam(config), r',250\n};\n$')
        for value in (0, 249, 351, 500, True, '350'):
            beam['stability_support_gap_ms'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.generate_beam(config)

    def test_game_portal_exit_policy_defaults_and_rejects_invalid_values(self):
        config = configuration()
        self.assertIn('.portal_b_exit_side = 0,', MODULE.generate(config))
        for side in (-1, 0, 1):
            config['board_game']['portal_b_exit_side'] = side
            self.assertIn(f'.portal_b_exit_side = {side},', MODULE.generate(config))
        for side in (-2, 2, True, '1'):
            config['board_game']['portal_b_exit_side'] = side
            with self.assertRaises(ValueError):
                MODULE.generate(config)

    def test_pynq_support_gap_500_does_not_change_baremetal_or_scene_age(self):
        config = json.loads((MODULE.ROOT/'pc_vision/game_config.json').read_text(encoding='utf-8'))
        beam = config['real_scene']['beam']
        self.assertEqual(beam['stability_support_gap_ms'], 350)
        self.assertEqual(beam['pynq_stability_support_gap_ms'], 500)
        self.assertRegex(MODULE.generate_beam(config), r',350\n};\n$')
        text = MODULE.generate_beam(config, 600, beam['pynq_stability_support_gap_ms'])
        self.assertIn(',600,VISION_STABILITY_B,', text)
        self.assertRegex(text, r',500\n};\n$')
        self.assertEqual(config['board_game']['scene_max_age_ms'], 600)
        for value in (0, 499, 501, 600, True, '500', 500.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.generate_beam(config, 600, value)

    def test_emits_level_data_and_physical_count(self):
        text = MODULE.generate(configuration())
        self.assertIn('.reference = "sample_photo(1)/001.png"', text)
        self.assertIn('.emitter = {.enabled = 1, .point = {100.0f, 300.0f}', text)
        self.assertIn('.object_count = 1', text)
        self.assertNotIn('.type = RAY_OBJECT_SOURCE', text)

    def test_source_requirement_matches_emitter(self):
        config = configuration()
        level = config["board_game"]["levels"][0]
        source = {"type": "SOURCE", "motion": "fixed", "center": [100, 300], "axis": [1, 0]}
        level["objects"].append(source)
        with self.assertRaises(ValueError):
            MODULE.generate(config)
        del level["emitter"]
        self.assertIn('.emitter = {0}', MODULE.generate(config))
        level["objects"].pop()
        with self.assertRaises(ValueError):
            MODULE.generate(config)

    def test_disabled_emitter_preserves_legacy_mode(self):
        config = configuration()
        level = config["board_game"]["levels"][0]
        level["emitter"] = {"enabled": False}
        level["objects"].append({"type": "SOURCE", "motion": "fixed",
                                  "center": [100, 300], "axis": [1, 0]})
        self.assertIn('.emitter = {0}', MODULE.generate(config))

    def test_invalid_coordinate_direction_and_origin(self):
        for change in ({"coordinate_space": "mm"}, {"point": [-1, 0]},
                       {"point": [1280, 0]}, {"direction": [2, 0]},
                       {"direction": [0, 0]}, {"direction": [float("nan"), 0]},
                       {"enabled": 1}):
            config = configuration()
            config["board_game"]["levels"][0]["emitter"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                MODULE.generate(config)

    def test_model_capacity_includes_internal_emitter(self):
        config = configuration()
        config["board_game"]["max_models"] = 1
        with self.assertRaises(ValueError):
            MODULE.generate(config)

    def test_pair_and_target_still_required(self):
        config = configuration()
        level = config["board_game"]["levels"][0]
        portal = {"type": "PORTAL_A", "motion": "free", "center": [500, 300], "axis": [1, 0]}
        level["objects"].append(portal)
        with self.assertRaises(ValueError):
            MODULE.generate(config)
        pair = copy.deepcopy(portal)
        pair["type"] = "PORTAL_B"
        level["objects"].append(pair)
        MODULE.generate(config)
        level["objects"].pop(0)
        with self.assertRaises(ValueError):
            MODULE.generate(config)

    def test_portal_geometry_is_explicit_and_portal_only(self):
        config = configuration()
        level = config["board_game"]["levels"][0]
        for kind in ("PORTAL_A", "PORTAL_B"):
            level["objects"].append({"type": kind, "motion": "free",
                "center": [500, 300], "axis": [1, 0], "geometry": "portal_template"})
        text = MODULE.generate(config)
        self.assertEqual(text.count('.use_template_geometry = 1'), 2)
        self.assertEqual(text.count('.use_template_geometry = 0'), 1)
        for change in ({"type": "MIRROR"}, {"type": "TARGET"},
                       {"motion": "fixed"}, {"motion": "rotate_only"},
                       {"geometry": "bbox"}):
            invalid = copy.deepcopy(config)
            if change.get("type") == "TARGET":
                invalid["board_game"]["levels"][0]["objects"][0]["geometry"] = "portal_template"
            elif change.get("type") == "MIRROR":
                invalid["board_game"]["levels"][0]["objects"].append({
                    "type": "MIRROR", "motion": "free", "center": [300, 100],
                    "axis": [1, 0], "geometry": "portal_template"})
            else:
                invalid["board_game"]["levels"][0]["objects"][1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                MODULE.generate(invalid)

    def test_marker_geometry_is_class_specific(self):
        config = configuration()
        level = config["board_game"]["levels"][0]
        level["objects"][0]["geometry"] = "marker_template"
        for kind in ("MIRROR", "WALL"):
            level["objects"].append({"type": kind, "motion": "free",
                "center": [500, 300], "axis": [1, 0], "geometry": "marker_template"})
        self.assertEqual(MODULE.generate(config).count('.use_template_geometry = 2'), 3)
        for motion in ("fixed", "rotate_only"):
            invalid = copy.deepcopy(config)
            invalid["board_game"]["levels"][0]["objects"][1]["motion"] = motion
            with self.subTest(motion=motion), self.assertRaises(ValueError):
                MODULE.generate(invalid)
        invalid = copy.deepcopy(config)
        invalid_level = invalid["board_game"]["levels"][0]
        del invalid_level["emitter"]
        invalid_level["objects"].append({"type": "SOURCE", "motion": "free",
            "center": [100, 300], "axis": [1, 0], "geometry": "marker_template"})
        with self.assertRaises(ValueError):
            MODULE.generate(invalid)
        del invalid_level["objects"][-1]["geometry"]
        MODULE.generate(invalid)
        for kind in ("PORTAL_A", "PORTAL_B"):
            level["objects"].append({"type": kind, "motion": "free",
                "center": [500, 300], "axis": [1, 0], "geometry": "portal_template"})
        MODULE.generate(config)
        level["objects"][-1]["geometry"] = "marker_template"
        with self.assertRaises(ValueError):
            MODULE.generate(config)


if __name__ == "__main__":
    unittest.main()
