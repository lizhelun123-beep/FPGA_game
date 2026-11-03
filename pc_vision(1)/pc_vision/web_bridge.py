"""Binary wire-v3 board control/poses -> shared C presenter -> local Three.js."""
import argparse
import asyncio
from contextlib import suppress
import json
import math
from pathlib import Path
import sys
import threading

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiohttp import web, WSMsgType
from pc_vision.board_native import NativeBoardGame, ROOT
from pc_vision.board_runtime import BoardInput, BoardGamePresenter, BRIDGE_BUILD, now_ms
from pc_vision.board_wire import VERSION as WIRE_VERSION
from pc_vision.shared_runtime import canonical_module

teaching_exports = canonical_module('teaching').exports

WEB = Path(__file__).resolve().parent / "web"
WEB_BUILD = "20261101-web-teaching-2"


def load_config():
    return json.loads((ROOT / "pc_vision/game_config.json").read_text(encoding="utf-8"))


def layout_models(level, config):
    """Reference layouts are presentation data, never observations sent to C."""
    models = [dict(obj, size=config["model_sizes"][obj["type"]]) for obj in level["objects"]]
    emitter = level["emitter"]
    axis = emitter["direction"]
    norm = math.hypot(*axis)
    axis = [v / norm for v in axis]
    size = config["model_sizes"]["SOURCE"]
    tip = [p - d * 3 / config["physics_scale"] for p, d in zip(emitter["point"], axis)]
    center = [p - d * size[0] * 2 / 3 for p, d in zip(tip, axis)]
    models.append(dict(type="SOURCE", center=center, axis=axis, size=size,
                       tip=tip, direction=axis, directionValid=True, logical_emitter=True))
    return models


def catalog(config):
    game = config["board_game"]
    return dict(width=game["width"], height=game["height"],
                build=WEB_BUILD, runtimeBuild=BRIDGE_BUILD, wireProtocol=WIRE_VERSION,
                sceneMaxAgeMs=game["scene_max_age_ms"],
                coordinateSpace=game["coordinate_space"],
                maxVisibleSegments=game["render_max_ray_segments"],
                levels=[dict(id=level["id"], name=level.get("name") or f"实验关卡 {level['id']}",
                             playable=level.get("playable", True), reference=level.get("reference", ""),
                             models=layout_models(level, config)) for level in game["levels"]])


def wire(record):
    """Preserve 64-bit identities across JavaScript's 53-bit number boundary."""
    if isinstance(record, dict):
        return {key: str(value) if key in ("generation", "session_generation", "sequence", "captured_ms", "published_ms")
                and isinstance(value, int) else wire(value) for key, value in record.items()}
    if isinstance(record, (list, tuple)):
        return [wire(value) for value in record]
    return record


class WebGame:
    def __init__(self, config, core=None, worker=None, preview=False, clock=now_ms, on_quit=None):
        self.config, self.core, self.worker = config, core, worker
        self.preview, self.clock = preview, clock
        self.on_quit, self.stopping = on_quit, False
        self.presenter = BoardGamePresenter(core, config, transport=worker) if core else None
        self.catalog = catalog(config)
        self.layouts = {level["id"]: level for level in self.catalog["levels"]}
        self.view_level = 0
        self.commands = []
        self.latest = None
        self.changed = asyncio.Event()
        self.wakeup = asyncio.Event()
        self.client = None
        self.task = None
        self.step()

    def enqueue(self, command):
        if (self.stopping or not isinstance(command, dict) or command.get("action") not in ("select", "start", "skip", "menu", "quit")
                or (command.get("action") == "select" and
                    (type(command.get("level_id")) is not int or command["level_id"] not in self.layouts))):
            return False
        if len(self.commands) >= 32:
            return False
        self.commands.append(command)
        self.wakeup.set()
        return True

    def step(self):
        now = self.clock()
        frame, epoch, connected, clock, error = self.worker.poll() if self.worker else (None, 0, False, None, "")
        snapshot = self.presenter.update(frame, epoch, connected, clock, now, error,
            controls=self.worker.poll_controls() if self.worker else (),
            transport_events=self.worker.poll_transport_events() if self.worker else ()) if self.presenter else {}
        commands, self.commands = self.commands, []
        if any(command["action"] == "quit" for command in commands):
            self.stopping = True
            commands = []
        for command in commands:
            action = command["action"]
            if action == "select":
                level = self.layouts[command["level_id"]]
                if self.preview or not level["playable"]:
                    self.view_level = level["id"]
                    if self.presenter:
                        self.presenter.action({"action": "menu"}, now, connected)
                else:
                    self.view_level = 0
                    self.presenter.action(command, now, connected)
            elif action == "menu":
                self.view_level = 0
                if self.presenter:
                    self.presenter.action(command, now, connected)
            elif self.presenter and not self.view_level:
                self.presenter.action(command, now, connected)
        if commands and self.presenter:
            snapshot = self.presenter.update(None, epoch, connected, clock, now, error)
        if self.view_level:
            level = self.layouts[self.view_level]
            snapshot = dict(screen="game", level_id=level["id"], game_state=0, state="PREVIEW",
                            models=level["models"], segments=[], valid=False, ready=False,
                            remaining_ms=180000, elapsed_ms=0, stars=0, success=False,
                            generation=0, sequence=0, captured_ms=0, budget_exceeded=False,
                            display_status="离线布局预览 · 不参与计时与通关" if level["playable"] else
                            "展示关卡 · 固定布局，不接入实物")
        elif not self.presenter:
            snapshot = dict(screen="menu", level_id=0, state="PREVIEW", models=[], segments=[], ready=False)
        if self.stopping:
            snapshot = dict(screen="closed", level_id=0, state="CLOSED", models=[], segments=[],
                            ready=False, valid=False, success=False, display_status="程序已结束")
        snapshot.update(mode="preview" if self.preview else "live", preview=bool(self.view_level),
                        connected=bool(connected), build=WEB_BUILD, runtime_build=BRIDGE_BUILD,
                        serial_protocol=WIRE_VERSION, scene_max_age_ms=self.config["board_game"]["scene_max_age_ms"])
        self.latest = wire(snapshot)
        self.changed.set()
        return self.latest

    async def run(self):
        while True:
            self.wakeup.clear()
            self.step()
            if self.stopping:
                # Release this PC's UART/C owners before confirming exit.
                if self.worker:
                    await asyncio.to_thread(self.worker.close)
                if self.core:
                    self.core.close()
                client = self.client
                if client is not None and not client.closed:
                    with suppress(ConnectionError, RuntimeError):
                        await client.send_json(self.latest, dumps=lambda value: json.dumps(value, ensure_ascii=False))
                        await client.close(code=1000, message=b"Program ended")
                if self.on_quit:
                    asyncio.get_running_loop().call_soon(self.on_quit)
                return
            try:
                await asyncio.wait_for(self.wakeup.wait(), .01)
            except asyncio.TimeoutError:
                pass

    async def websocket(self, request):
        origin = request.headers.get("Origin")
        if origin and origin != f"{request.scheme}://{request.host}":
            raise web.HTTPForbidden(text="Local page origin required")
        ws = web.WebSocketResponse(heartbeat=5, max_msg_size=8192)
        await ws.prepare(request)
        if self.client is not None:
            await self.client.close(code=4001, message=b"Another local page took control")
        self.client = ws
        self.changed.set()

        async def send_latest():
            try:
                while not ws.closed:
                    await self.changed.wait()
                    self.changed.clear()
                    await asyncio.wait_for(ws.send_str(json.dumps(self.latest, ensure_ascii=False, allow_nan=False)), 1)
            except (asyncio.TimeoutError, ConnectionError, RuntimeError):
                await ws.close()

        sender = asyncio.create_task(send_latest())
        try:
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    try:
                        accepted = self.enqueue(json.loads(message.data))
                    except (ValueError, TypeError):
                        accepted = False
                    if not accepted:
                        await ws.close(code=1008, message=b"Invalid game command")
                elif message.type == WSMsgType.ERROR:
                    break
        finally:
            sender.cancel()
            with suppress(asyncio.CancelledError):
                await sender
            if self.client is ws:
                self.client = None
        return ws

    def application(self):
        app = web.Application(client_max_size=8192)
        async def index(request):
            return web.FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})

        async def get_catalog(request):
            return web.json_response(self.catalog, headers={"Cache-Control": "no-store"})

        app.router.add_get("/", index)
        app.router.add_get("/api/catalog", get_catalog)
        app.router.add_get("/ws", self.websocket)
        async def teaching_page(request):
            return web.FileResponse(WEB / 'teaching.html', headers={'Cache-Control':'no-store'})

        async def teaching_data(request):
            state = self.worker.teaching_snapshot() if self.worker else dict(document=None, connected=False, rejected=0)
            return web.json_response(wire(state), headers={'Cache-Control':'no-store'})

        async def teaching_download(request):
            state = self.worker.teaching_snapshot() if self.worker else {}
            doc = state.get('document')
            if doc is None: raise web.HTTPNotFound(text='尚未收到完整教学数据')
            files = teaching_exports(doc)
            name = request.match_info['name']
            if name not in files: raise web.HTTPNotFound()
            return web.Response(body=files[name].encode('utf-8'), content_type='text/plain', charset='utf-8',
                headers={'Content-Disposition':'attachment; filename="'+name+'"', 'Cache-Control':'no-store'})

        app.router.add_get('/teaching', teaching_page)
        app.router.add_get('/api/teaching', teaching_data)
        app.router.add_get('/api/teaching/export/{name}', teaching_download)
        for name in ("index.html", "main.js", "portals.js", "presentation.js", "style.css"):
            async def asset(request, filename=name):
                return web.FileResponse(WEB / filename, headers={"Cache-Control": "no-store"})
            app.router.add_get("/" + name, asset)
        app.router.add_static("/node_modules/three/", WEB / "node_modules/three")

        async def lifetime(app):
            loop = asyncio.get_running_loop()
            if self.worker:
                # Relay the canonical owner's input event into asyncio. The
                # 10ms tick also services timer/commands when no pose arrives.
                relay_stop = threading.Event()
                def relay():
                    while not relay_stop.is_set():
                        if self.worker.changed.wait(.05):
                            self.worker.changed.clear()
                            loop.call_soon_threadsafe(self.wakeup.set)
                relay_thread = threading.Thread(target=relay, daemon=True, name="web-pose-wakeup")
                relay_thread.start()
                self.worker.thread.start()
            self.task = asyncio.create_task(self.run())
            try:
                yield
            finally:
                self.task.cancel()
                try:
                    with suppress(asyncio.CancelledError):
                        await self.task
                finally:
                    if self.client:
                        await self.client.close()
                    if self.worker:
                        relay_stop.set()
                        self.worker.changed.set()
                        await asyncio.to_thread(self.worker.close)
                        await asyncio.to_thread(relay_thread.join, 1)
                    if self.core:
                        self.core.close()
        app.cleanup_ctx.append(lifetime)
        return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--serial", help="Explicit binary-v3 board port; requires version14 BOOT")
    source.add_argument("--preview", action="store_true", help="Layouts only; no UART or game admission")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cc")
    parser.add_argument("--serial-log", type=Path, help="New JSONL actual TX/raw RX trace; never overwritten")
    parser.add_argument("--check", action="store_true", help="Build/check C; no UART or HTTP server")
    args = parser.parse_args(argv)
    if args.baud <= 0 or not 0 <= args.port <= 65535:
        parser.error("Invalid baud/port")
    if not (args.preview or args.serial or args.check):
        parser.error("Use --preview or --serial PORT")
    if args.serial_log and not args.serial:
        parser.error("--serial-log requires --serial")
    if args.serial:
        try:
            import serial  # noqa: F401
        except ImportError:
            parser.error("Install pyserial: python -m pip install pyserial")
    core = NativeBoardGame(args.cc) if not args.preview or args.check else None
    if args.check:
        print("C_GAME_READY", core.path, "NO_UART_NO_HARDWARE")
        core.close()
        return 0
    trace_file = None
    worker = None
    try:
        if args.serial_log:
            args.serial_log.parent.mkdir(parents=True, exist_ok=True)
            trace_file = args.serial_log.open("x", encoding="utf-8")
        def record_serial(event):
            row = json.dumps(event, ensure_ascii=False, allow_nan=False)
            if trace_file is not None:
                trace_file.write(row+"\n")
                trace_file.flush()
            if event["event"] != "RX_BYTES":
                print("UART_TRACE " + row, flush=True)
        worker = BoardInput(args.serial, args.baud, trace=record_serial) if args.serial else None
        def stop_http():
            raise web.GracefulExit()
        game = WebGame(load_config(), core=core, worker=worker, preview=args.preview, on_quit=stop_http)
        print(f"WEB_BRIDGE http://127.0.0.1:{args.port}/ build={WEB_BUILD} runtime={BRIDGE_BUILD} wire_protocol={WIRE_VERSION} scene_max_age_ms={game.config['board_game']['scene_max_age_ms']}", flush=True)
        web.run_app(game.application(), host="127.0.0.1", port=args.port)
    finally:
        if worker:
            worker.close()
        if core:
            core.close()
        if trace_file is not None:
            trace_file.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
