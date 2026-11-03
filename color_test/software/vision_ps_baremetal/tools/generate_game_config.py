"""Generate a C table only; game rules/physics live in the canonical C core.

No detector, OpenCV, hardware or runtime Python dependency. The JSON is the
single hand-maintained authority, including C-detector-derived preview anchors.
"""
import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
TYPES = ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")
MOTIONS = {"fixed": "GAME_FIXED", "rotate_only": "GAME_ROTATE_ONLY", "free": "GAME_FREE"}


def scalar(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite number")
    text = format(value, ".10g")
    return text + ("f" if "." in text or "e" in text else ".0f")


def integer(value):
    if type(value) is not int or not 0 < value <= 2**63-1:
        raise ValueError("Expected a positive integer")
    return value


def point(value):
    if len(value) != 2:
        raise ValueError("Expected a 2D point")
    return "{" + ", ".join(scalar(v) for v in value) + "}"


def emitter_config(level, game):
    emitter = level.get("emitter")
    if emitter is None:
        return False, "{0}"
    if not isinstance(emitter, dict) or type(emitter.get("enabled", True)) is not bool:
        raise ValueError("Invalid logical emitter")
    if not emitter.get("enabled", True):
        return False, "{0}"
    if emitter.get("coordinate_space") != game["coordinate_space"]:
        raise ValueError("Emitter and scene coordinate spaces must match")
    origin, direction = emitter["point"], emitter["direction"]
    origin_c, direction_c = point(origin), point(direction)
    if (not 0 <= origin[0] <= game["width"] or
            not 0 <= origin[1] <= game["height"] or
            abs(math.hypot(*direction)-1) > 0.001):
        raise ValueError("Emitter needs an in-scene point and unit direction")
    return True, "{.enabled = 1, .point = " + origin_c + ", .direction = " + direction_c + "}"


def generate(config):
    game = config["board_game"]
    if config["version"] != 1 or game["version"] != 1:
        raise ValueError("Unsupported game configuration version")
    portal_side = game.get("portal_b_exit_side", 0)
    if type(portal_side) is not int or portal_side not in (-1, 0, 1):
        raise ValueError("Invalid game Portal B exit side")
    if game["coordinate_space"] != "uncalibrated_preview":
        raise ValueError("Default photo anchors require uncalibrated_preview; do not invent mm mapping")
    levels = game["levels"]
    if not 1 <= len(levels) <= 15 or len({level["id"] for level in levels}) != len(levels):
        raise ValueError("Invalid or duplicate levels")
    if set(config["model_sizes"]) != set(TYPES):
        raise ValueError("Expected all six canonical model sizes")
    lines = ["/* GENERATED from pc_vision/game_config.json; do not edit. */",
             '#include "game_pump.h"', '#include "game_render.h"', "const GameConfig game_default_config = {",
             "    .version = GAME_CONFIG_VERSION,",
             f"    .portal_b_exit_side = {portal_side},",
             '    .coordinate_space = "uncalibrated_preview",',
             f'    .width = {scalar(game["width"])}, .height = {scalar(game["height"])},',
             f'    .physics_scale = {scalar(config["physics_scale"])},',
             f'    .max_models = {integer(game["max_models"])},',
             f'    .render_max_ray_segments = {integer(game["render_max_ray_segments"])},',
             f'    .scene_max_age_ms = {integer(game["scene_max_age_ms"])}ULL,',
             f'    .duration_ms = {integer(game["duration_ms"])}ULL,',
             "    .star_threshold_ms = {" + ", ".join(str(integer(v))+"ULL" for v in game["star_threshold_ms"]) + "},",
             "    .model_sizes = {"]
    if len(game["star_threshold_ms"]) != 2:
        raise ValueError("Expected two star boundaries")
    for kind in TYPES:
        lines.append(f'        [RAY_OBJECT_{kind}] = {point(config["model_sizes"][kind])},')
    lines += ["    },", f"    .level_count = {len(levels)},", "    .levels = {"]
    for level in levels:
        objects = level["objects"]
        kinds = [obj["type"] for obj in objects]
        logical_emitter, emitter = emitter_config(level, game)
        if (not 1 <= len(objects) <= min(6, game["max_models"])-int(logical_emitter) or
                len(set(kinds)) != len(kinds) or
                not set(kinds) <= set(TYPES)):
            raise ValueError("Invalid/duplicate template classes")
        if (logical_emitter == ("SOURCE" in kinds) or "TARGET" not in kinds or
                (("PORTAL_A" in kinds) != ("PORTAL_B" in kinds))):
            raise ValueError("Physical classes must match the level emitter and Portal pair")
        # Reject non-path/control characters before emitting a C string.
        reference = level["reference"]
        if not reference or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-()" for c in reference):
            raise ValueError("Invalid reference path")
        lines += [f'        {{.id = {integer(level["id"])}U, .reference = "{reference}",',
                  f"         .emitter = {emitter},",
                  f"         .object_count = {len(objects)}, .objects = {{"]
        for obj in objects:
            kind = obj["type"]
            geometry = obj.get("geometry")
            if geometry not in (None, "portal_template", "marker_template"):
                raise ValueError("Unknown object geometry mode")
            use_template = {None: 0, "portal_template": 1, "marker_template": 2}[geometry]
            if use_template == 1 and (kind not in ("PORTAL_A", "PORTAL_B") or obj["motion"] != "free"):
                raise ValueError("Portal template geometry requires a free Portal")
            if use_template == 2 and (kind not in ("MIRROR", "WALL", "TARGET") or obj["motion"] != "free"):
                raise ValueError("Marker template geometry requires a free Mirror, Wall or Target")
            lines += ["            {.anchor = {" + f".type = RAY_OBJECT_{kind},",
                      f'                .center = {point(obj["center"])}, .axis = {point(obj["axis"])},',
                      f'                .direction_valid = {int(kind == "SOURCE")}' + "},",
                      f'             .motion = {MOTIONS[obj["motion"]]},',
                      f'             .use_template_geometry = {int(use_template)}' + "},"]
        lines += ["         }},"]
    lines += ["    }", "};", ""]
    menu = game["menu"]
    width, height = integer(menu["width"]), integer(menu["height"])
    if menu["version"] != 1 or max(width, height) > 2**31-1:
        raise ValueError("Invalid menu version/dimensions")
    rects = menu["level_rects"] + [menu["start_rect"]]
    if len(menu["level_rects"]) != len(levels):
        raise ValueError("One menu rectangle is required per configured level")
    for i, r in enumerate(rects):
        if (len(r) != 4 or any(type(v) is not int for v in r) or
                min(r[:2]) < 0 or min(r[2:]) <= 0 or
                r[0]+r[2] > width or r[1]+r[3] > height):
            raise ValueError("Menu rectangle outside display")
        for b in rects[:i]:
            if r[0] < b[0]+b[2] and b[0] < r[0]+r[2] and r[1] < b[1]+b[3] and b[1] < r[1]+r[3]:
                raise ValueError("Overlapping menu rectangles")
    def rect(values):
        return "{" + ", ".join(map(str, values)) + "}"
    render = game["render"]
    scene = render["scene_rect"]
    if (render["version"] != 1 or len(scene) != 4 or
            any(type(v) is not int for v in scene) or min(scene[:2]) < 0 or
            min(scene[2:]) < 2 or scene[0]+scene[2] > width or scene[1]+scene[3] > height):
        raise ValueError("Invalid render viewport")
    for b in rects:
        if scene[0] < b[0]+b[2] and b[0] < scene[0]+scene[2] and scene[1] < b[1]+b[3] and b[1] < scene[1]+scene[3]:
            raise ValueError("Render viewport overlaps menu")
    lines += ["const GameMenuLayout game_default_menu_layout = {",
              "    .version = GAME_MENU_VERSION,",
              f"    .width = {width}, .height = {height}, .level_count = {len(levels)},",
              "    .levels = {"]
    for level, r in zip(levels, menu["level_rects"]):
        lines.append(f'        {{.level_id = {integer(level["id"])}U, .rect = {rect(r)}}},')
    return "\n".join(lines + ["    },", f'    .start = {rect(menu["start_rect"])}', "};",
                              "const GamePumpConfig game_default_pump_config = {",
                              f'    .tick_ms = {integer(game["pump_tick_ms"])}ULL', "};",
                              "const GameRenderConfig game_default_render_config = {",
                              f'    .version = GAME_RENDER_VERSION, .scene = {rect(scene)}', "};", ""])


def generate_beam(config, age_override=None, support_gap_override=None):
    """One configured detector/beam profile; no level table or fake SOURCE."""
    real = config["real_scene"]
    beam = real["beam"]
    max_age_ms = beam["max_age_ms"] if age_override is None else age_override
    allowed_age = (0, 250, 600) if age_override is not None else (0, 250)
    if type(max_age_ms) is not int or max_age_ms not in allowed_age:
        raise ValueError("Beam age policy is outside the selected build contract")
    profile = beam.get("detector_profile", "apriltag")
    if profile not in ("restored_markers", "apriltag"):
        raise ValueError("Unknown beam detector profile")
    if beam["width"] != 1280 or beam["height"] != 720 or beam["stability_algorithm"] not in ("A", "B"):
        raise ValueError("Invalid beam dimensions/stability algorithm")
    origin, direction = beam["emitter_point"], beam["emitter_direction"]
    origin_c, direction_c = point(origin), point(direction)
    if not (0 <= origin[0] <= 1279 and 0 <= origin[1] <= 719) or abs(math.hypot(*direction)-1) > .001:
        raise ValueError("Invalid beam emitter")
    side = beam.get("portal_b_exit_side", 0)
    timeout, dropout = beam.get("display_timeout_ms", 0), beam.get("display_dropout_ms", 0)
    if type(side) is not int or side not in (-1, 0, 1):
        raise ValueError("Invalid Portal B exit side")
    if (type(timeout) is not int or not 0 <= timeout <= 6000 or
            type(dropout) is not int or not 0 <= dropout <= min(timeout, 250)):
        raise ValueError("Invalid display retention")
    profile_c = "VISION_PROFILE_RESTORED" if profile == "restored_markers" else "VISION_PROFILE_TAGS"
    support_gap = beam.get("stability_support_gap_ms", 250)
    if type(support_gap) is not int or support_gap not in (250, 350):
        raise ValueError("Beam stability support gap must be 250 or 350 ms")
    # PYNQ 单独选择支持间隔，裸板配置和原有时序算法继续使用原参数。
    if support_gap_override is not None:
        if type(support_gap_override) is not int or support_gap_override not in (250, 350, 500):
            raise ValueError("PYNQ stability support gap must be 250, 350 or 500 ms")
        support_gap = support_gap_override
    lines = ['/* GENERATED from pc_vision/game_config.json; do not edit. */',
             '#include "game_beam_config.h"',
             'const GameBeamConfig game_beam_default_config = {',
             f'    GAME_BEAM_CONFIG_VERSION,1280,720,{origin_c},{direction_c},{max_age_ms},VISION_STABILITY_{beam["stability_algorithm"]},',
             f'    {profile_c},{timeout},{dropout},{side},{support_gap}', '};']
    if profile == "restored_markers":
        return '\n'.join(lines)+ '\n'
    templates = real["portal_templates"]
    physical = real["physical_geometry_mm"]
    lines += ['const VisionPortalTemplate game_beam_portals[2] = {']
    for name, ids in (("PORTAL_A", [10, 11, 12]), ("PORTAL_B", [20, 21, 22])):
        model = templates[name]
        corners = model["corners"]
        if (model["ids"] != ids or model["unit"] != "mm" or
                len(corners) != 3 or any(len(c) != 4 for c in corners) or
                model["body_size"] != [80, 25] or
                model["image_handedness"] not in (-1, 1) or
                model["reference_scale_px_per_mm"] <= 0 or
                abs(math.hypot(*model["axis"])-1) > .001):
            raise ValueError("Invalid measured Portal template: " + name)
        size = model["effective_size"]
        if len(size) != 2 or not 0 < size[1] < size[0] <= 80 or size[1] > 25:
            raise ValueError("Invalid Portal effective boundary")
        lines += ['    {.corners = {']
        for tag in corners:
            lines += ['        {' + ', '.join(point(corner) for corner in tag) + '},']
        lines += ['    }, .center = ' + point(model["center"]) +
                  ', .axis = ' + point(model["axis"]) + ',',
                  '    .length = ' + scalar(size[0]) + ', .width = ' + scalar(size[1]) + ',',
                  '    .reference_scale = ' + scalar(model["reference_scale_px_per_mm"]) +
                  ', .handedness = ' + scalar(model["image_handedness"]) + '},']
    mirror, wall = physical["MIRROR"], physical["WALL"]
    if (mirror["body_size"] != [80, 25] or wall["body_size"] != [80, 25] or
            physical["TARGET"]["diameter"] != 30):
        raise ValueError("Measured Mirror/Wall/Target geometry differs from the beam contract")
    mirror_span = 2*mirror["black_dot_center_offset"]
    wall_span = wall["body_size"][0]-2*(wall["white_mark_end_gap"]+wall["white_mark_width"]/2)
    if min(mirror_span, wall_span, wall["white_mark_span"]) <= 0:
        raise ValueError("Invalid measured marker span")
    ratios = [mirror["reflective_line_length"]/mirror_span,
              mirror["body_size"][0]/mirror_span, mirror["body_size"][1]/mirror_span,
              wall["body_size"][0]/wall_span, wall["body_size"][1]/wall["white_mark_span"]]
    lines += ['};', 'const VisionRealSceneGeometry game_beam_marker_geometry = {',
              '    ' + ', '.join(scalar(v) for v in ratios), '};', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT/"pc_vision/game_config.json")
    parser.add_argument("--output", type=Path, required=True, help="Generated .h (with a companion .c table)")
    parser.add_argument("--profile", choices=("game", "beam"), default="game")
    parser.add_argument("--pynq", action="store_true",
                        help="生成 PYNQ 场景时限与其专用连续观测支持间隔")
    args = parser.parse_args()
    if args.output.suffix != ".h":
        parser.error("--output must end in .h")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.pynq and args.profile != "beam":
        parser.error("--pynq requires --profile beam")
    support_gap = None
    if args.pynq:
        beam = config["real_scene"]["beam"]
        support_gap = beam.get("pynq_stability_support_gap_ms", beam.get("stability_support_gap_ms", 250))
    data = generate_beam(config, 600 if args.pynq else None, support_gap) if args.profile == "beam" else generate(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.profile == "beam":
        args.output.write_text('''/* GENERATED declaration; do not edit. */
#ifndef GENERATED_GAME_BEAM_CONFIG_H
#define GENERATED_GAME_BEAM_CONFIG_H
#include "game_beam.h"
#include "vision_portal.h"
extern const GameBeamConfig game_beam_default_config;
extern const VisionPortalTemplate game_beam_portals[2];
extern const VisionRealSceneGeometry game_beam_marker_geometry;
#endif
''', encoding="utf-8")
        args.output.with_suffix(".c").write_text(data, encoding="utf-8")
        return
    args.output.write_text('''/* GENERATED declaration; do not edit. */
#ifndef GENERATED_GAME_CONFIG_H
#define GENERATED_GAME_CONFIG_H
#include "game_pump.h"
#include "game_render.h"
#ifdef __cplusplus
extern "C" {
#endif
extern const GameConfig game_default_config;
extern const GameMenuLayout game_default_menu_layout;
extern const GamePumpConfig game_default_pump_config;
extern const GameRenderConfig game_default_render_config;
#ifdef __cplusplus
}
#endif
#endif
''', encoding="utf-8")
    args.output.with_suffix(".c").write_text(data, encoding="utf-8")


if __name__ == "__main__":
    main()
