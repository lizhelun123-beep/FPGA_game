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


def generate(config):
    game = config["board_game"]
    if config["version"] != 1 or game["version"] != 1:
        raise ValueError("Unsupported game configuration version")
    if game["coordinate_space"] != "uncalibrated_preview":
        raise ValueError("Default photo anchors require uncalibrated_preview; do not invent mm mapping")
    levels = game["levels"]
    if not 1 <= len(levels) <= 3 or len({level["id"] for level in levels}) != len(levels):
        raise ValueError("Invalid or duplicate levels")
    if set(config["model_sizes"]) != set(TYPES):
        raise ValueError("Expected all six canonical model sizes")
    lines = ["/* GENERATED from pc_vision/game_config.json; do not edit. */",
             '#include "game_pump.h"', '#include "game_render.h"', "const GameConfig game_default_config = {",
             "    .version = GAME_CONFIG_VERSION,",
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
        if (not 1 <= len(objects) <= 6 or len(set(kinds)) != len(kinds) or
                not set(kinds) <= set(TYPES)):
            raise ValueError("Invalid/duplicate template classes")
        # Reject non-path/control characters before emitting a C string.
        reference = level["reference"]
        if not reference or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-" for c in reference):
            raise ValueError("Invalid reference path")
        lines += [f'        {{.id = {integer(level["id"])}U, .reference = "{reference}",',
                  f"         .object_count = {len(objects)}, .objects = {{"]
        for obj in objects:
            kind = obj["type"]
            lines += ["            {.anchor = {" + f".type = RAY_OBJECT_{kind},",
                      f'                .center = {point(obj["center"])}, .axis = {point(obj["axis"])},',
                      f'                .direction_valid = {int(kind == "SOURCE")}' + "},",
                      f'             .motion = {MOTIONS[obj["motion"]]}' + "},"]
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT/"pc_vision/game_config.json")
    parser.add_argument("--output", type=Path, required=True, help="Generated .h (with a companion .c table)")
    args = parser.parse_args()
    if args.output.suffix != ".h":
        parser.error("--output must end in .h")
    data = generate(json.loads(args.config.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
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
