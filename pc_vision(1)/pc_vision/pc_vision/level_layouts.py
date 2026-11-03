"""Author12 seeded random layouts into the unique JSON. No live observations.

The first three levels are preserved verbatim. Layouts contain fixed emitters,
separate visible objects and paired Portals; solvability is deliberately untested.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import random

NAMES = ("林间折光", "双门流转", "光影回廊", "镜面回旋", "穿林寻光", "交错之门",
         "光的岔路", "回环迷径", "星光渡口", "远山映照", "旋光庭院", "寻光终章")


def populate_random_levels(config, seed=20261027):
    result = copy.deepcopy(config)
    game = result["board_game"]
    if [level["id"] for level in game["levels"][:3]] != [1, 2, 3]:
        raise ValueError("Keep the existing first three levels")
    levels = game["levels"][:3]
    rng = random.Random(seed)
    cells = [(x, y) for x in (230, 490, 750, 1010) for y in (145, 355, 565)]
    for level_id in range(4, 16):
        kinds = ["MIRROR", "TARGET"]
        if rng.random() < .65:
            kinds += ["PORTAL_A", "PORTAL_B"]
        if rng.random() < .60:
            kinds.append("WALL")
        objects = []
        for kind, (x, y) in zip(kinds, rng.sample(cells, len(kinds))):
            angle = rng.uniform(-math.pi, math.pi)
            axis = [round(math.cos(angle), 8), round(math.sin(angle), 8)] if kind != "TARGET" else [1, 0]
            objects.append(dict(type=kind, motion="free", center=[x+rng.randint(-10, 10), y+rng.randint(-10, 10)], axis=axis))
        from_right = rng.choice((False, True))
        angle = (math.pi if from_right else 0)+rng.uniform(-.45, .45)
        levels.append(dict(
            id=level_id, name=NAMES[level_id-4], reference=f"generated/level_{level_id:02d}",
            origin="seeded_random_layout", solvability="not_checked", objects=objects,
            emitter=dict(point=[1207 if from_right else 72, rng.randint(120, 599)],
                         direction=[round(math.cos(angle), 8), round(math.sin(angle), 8)],
                         coordinate_space=game["coordinate_space"])))
    game["levels"] = levels
    game["selection"]["random_seed"] = seed
    # The legacy C menu also gets15 bounded buttons, while Godot retains its
    # full5x3 thumbnail page. Keep the legacy scene/start rectangles unobstructed.
    game["menu"]["level_rects"] = [[20+(i % 5)*248, 20+(i//5)*42, 238, 36] for i in range(15)]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("game_config.json"))
    parser.add_argument("--seed", type=int, default=20261027)
    args = parser.parse_args(argv)
    original = json.loads(args.config.read_text(encoding="utf-8"))
    result = populate_random_levels(original, args.seed)
    args.config.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"LEVEL_LAYOUTS_READY total=15 preserved=3 random=12 seed={args.seed} solvability=not_checked")


if __name__ == "__main__":
    main()
