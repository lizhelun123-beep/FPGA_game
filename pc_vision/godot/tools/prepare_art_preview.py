"""Export static art references through the existing C ray solver; no game input."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pc_vision.game_scene import Model
from pc_vision.native import NativeVision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/build/pc_art/references")
    args = parser.parse_args()
    config = json.loads((ROOT / "pc_vision/game_config.json").read_text(encoding="utf-8"))
    board = config["board_game"]
    args.output.mkdir(parents=True, exist_ok=True)
    native = NativeVision(recognition=False)
    try:
        for level in board["levels"]:
            models = [Model(item["type"], tuple(item["center"]), tuple(item["axis"]),
                            tuple(config["model_sizes"][item["type"]]), 255,
                            item["type"] == "SOURCE") for item in level["objects"]]
            ray = native.trace(models, board["width"], board["height"], config["physics_scale"])
            # These are authored reference positions, not observed camera scenes.
            # Do not invent freshness, capture clocks, generations or completion.
            snapshot = dict(origin="config_reference_art_preview", generation=None,
                            sequence=None, captured_ms=None, level_id=level["id"],
                            state="ART_PREVIEW", models=level["objects"],
                            segments=ray["segments"], ray_termination=ray["termination"])
            path = args.output / f"level_{level['id']}.json"
            path.write_text(json.dumps(snapshot, indent=2)+"\n", encoding="utf-8")
            print(f"ART_REFERENCE level={level['id']} models={len(models)} "
                  f"C_segments={len(ray['segments'])} termination={ray['termination']}")
    finally:
        native.close()
    # Caller-supplied display sample only; there is no scoring calculation here.
    (args.output / "result_layout.json").write_text(json.dumps(dict(
        origin="art_layout_sample", outcome="结算效果预览", elapsed_ms=42000, stars=3),
        ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Static layout references: {args.output}")


if __name__ == "__main__":
    main()
