"""Export static art references through the existing C ray solver; no game input."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pc_vision.board_native import NativeBoardGame
from pc_vision.board_pose import PoseFrame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/build/pc_art/references")
    args = parser.parse_args()
    config = json.loads((ROOT / "pc_vision/game_config.json").read_text(encoding="utf-8"))
    board = config["board_game"]
    args.output.mkdir(parents=True, exist_ok=True)
    native = NativeBoardGame()
    try:
        for index, level in enumerate(board["levels"]):
            now = 1000*(index+1)
            selected = native.command(f"select {now} {level['id']}")
            models = tuple(dict(item, size=config["model_sizes"][item["type"]]) for item in level["objects"])
            # Explicit authored layout fixture, never sent to a live receiver.
            reference = PoseFrame(1, 1, 1, now+1, now+2, True, "OK", 0, 0, 0, models)
            state = native.frame(now+2, selected["generation"], reference, now+1)
            if not state["valid"]:
                raise RuntimeError("C rejected reference layout")
            # These are authored reference positions, not observed camera scenes.
            # Do not invent freshness, capture clocks, generations or completion.
            snapshot = dict(origin="config_reference_art_preview", generation=None,
                            sequence=None, captured_ms=None, level_id=level["id"],
                            state="ART_PREVIEW", models=state["models"],
                            segments=state["segments"], ray_termination=state["termination"])
            path = args.output / f"level_{level['id']}.json"
            path.write_text(json.dumps(snapshot, indent=2)+"\n", encoding="utf-8")
            print(f"ART_REFERENCE level={level['id']} models={len(models)} "
                  f"C_segments={len(state['segments'])} termination={state['termination']}")
    finally:
        native.close()
    # Caller-supplied display sample only; there is no scoring calculation here.
    (args.output / "result_layout.json").write_text(json.dumps(dict(
        origin="art_layout_sample", outcome="挑战成功", elapsed_ms=42000, stars=3),
        ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Static layout references: {args.output}")


if __name__ == "__main__":
    main()
