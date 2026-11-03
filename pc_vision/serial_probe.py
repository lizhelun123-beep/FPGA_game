"""Bounded, explicitly invoked UART light handshake check. Never sends START2."""
import argparse
import json
from pathlib import Path
import secrets

from .board_native import ROOT
from .godot_bridge import BoardInput, now_ms


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--duration", type=float, default=15)
    parser.add_argument("--log", type=Path, required=True, help="New JSONL file; never overwrites")
    args = parser.parse_args(argv)
    if not 0 < args.duration <= 20:
        parser.error("Duration must be in (0,20] seconds")
    config = json.loads((ROOT/"pc_vision/game_config.json").read_text(encoding="utf-8"))
    level = next((item for item in config["board_game"]["levels"] if item["id"] == args.level), None)
    if level is None:
        parser.error("Unknown level")
    expected = [round(v*scale) for values, scale in
                ((level["emitter"]["point"], 1000), (level["emitter"]["direction"], 1000000)) for v in values]
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("x", encoding="utf-8") as output:
        records = []

        def record(event):
            records.append(event)
            row = json.dumps(event, ensure_ascii=False, allow_nan=False)
            output.write(row+"\n")
            output.flush()
            if event["event"] != "RX_BYTES":
                print("UART_TRACE "+row, flush=True)

        worker = BoardInput(args.serial, 115200, trace=record)
        nonce = secrets.randbits(32) or 1
        ready = False
        record(dict(event="PROBE_BEGIN", time_ms=now_ms(), port=args.serial, level_id=args.level,
                    generation=1, nonce=nonce, emitter=expected, maximum_seconds=args.duration,
                    sends_start=False, hardware_reset=False))
        worker.queue_level(args.level, 1, level["emitter"], nonce)
        began = now_ms()
        worker.thread.start()
        try:
            while now_ms()-began < args.duration*1000:
                worker.poll()
                worker.poll_transport_events()
                for control in worker.poll_controls():
                    if (control.kind == "READY2" and
                            (control.level_id, control.generation, control.nonce) == (args.level, 1, nonce) and
                            [control.x_milli, control.y_milli, control.dx_micro, control.dy_micro] == expected):
                        ready = True
                if ready and any(row["event"] == "SYNC_RX" and row["clock_accepted"] for row in records):
                    break
                worker.stop.wait(.05)
        finally:
            worker.close()
        summary = dict(event="PROBE_SUMMARY", time_ms=now_ms(), ready_verified=ready,
                       sync_verified=any(row["event"] == "SYNC_RX" for row in records),
                       clock_verified=any(row["event"] == "SYNC_RX" and row["clock_accepted"] for row in records),
                       tx_level=sum(row["event"] == "TX_SENT" and row["command"] == "LEVEL2" for row in records),
                       tx_sync=sum(row["event"] == "TX_SENT" and row["command"] == "SYNC2" for row in records),
                       rx_bytes=sum(len(row["data_hex"])//2 for row in records if row["event"] == "RX_BYTES"),
                       elapsed_ms=now_ms()-began, start_sent=False)
        record(summary)
    return 0 if summary["ready_verified"] and summary["clock_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
