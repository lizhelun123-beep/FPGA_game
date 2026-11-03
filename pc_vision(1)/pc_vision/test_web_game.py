"""Offline WebSocket integration with the current C/board runtime. No UART."""
import copy
import asyncio
import dataclasses
import json
import threading
import unittest
from unittest.mock import patch
from aiohttp import WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import WSMsgType
from .board_native import NativeBoardGame, ROOT
from .board_pose import PoseFrame, TYPES
from .board_control import ControlFrame
from .board_runtime import BoardInput, BoardGamePresenter
from .shared_runtime import canonical_module
from .web_bridge import WebGame, load_config, wire, WEB
from . import web_bridge
from . import board_wire as binary

# Exercise the original fixtures against the very same imported runtime; keep
# protocol/C/scheduler tests in their canonical source instead of copying them.
SharedProtocolTests = canonical_module('test_board_bridge').ProtocolTests
SharedCGameTests = canonical_module('test_board_bridge').CGameTests
SharedSchedulerTests = canonical_module('test_serial_handshake').SerialHandshakeTests
CONFIG = load_config()


class ExactClock:
    def map(self, captured, now):
        return captured, captured


class FakeInput:
    port = 'FAKE_ONLY'
    def __init__(self):
        self.next = None
        self.connected, self.epoch, self.clock = True, 64, ExactClock()
        self.closed = False
        self.changed = threading.Event()
        self.parser = binary.BinaryParser()
        self.controls, self.events, self.levels, self.starts, self.resets = [], [], [], [], []
        self.thread = threading.Thread(target=lambda: None)

    def poll(self):
        value, self.next = self.next, None
        return value, self.epoch, self.connected, self.clock, ''

    def feed_wire(self, chunk):
        for message in self.parser.feed(chunk):
            if isinstance(message, ControlFrame):
                self.controls.append(message)
            elif isinstance(message, PoseFrame):
                self.next = message
        self.changed.set()

    def poll_controls(self):
        values, self.controls = self.controls, []
        return values

    def poll_transport_events(self):
        values, self.events = self.events, []
        return values

    def queue_level(self, *args):
        self.levels.append(args)

    def queue_start(self, *args):
        self.starts.append(args)

    def queue_reset(self, *args):
        self.resets.append(args)

    def close(self):
        self.closed = True


class WebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1000
        self.worker = FakeInput()
        self.core = NativeBoardGame()
        self.game = WebGame(CONFIG, self.core, self.worker, clock=lambda: self.now)
        self.client = TestClient(TestServer(self.game.application()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.assertTrue(self.worker.closed)

    def control(self, kind):
        presenter = self.game.presenter
        emitter = presenter.selected_emitter
        return ControlFrame(kind, level_id=presenter.selected, generation=self.core.state['generation'],
            nonce=presenter.level_nonce,
            x_milli=round(emitter['point'][0]*1000), y_milli=round(emitter['point'][1]*1000),
            dx_micro=round(emitter['direction'][0]*1000000), dy_micro=round(emitter['direction'][1]*1000000))

    def command(self, action, **fields):
        self.assertTrue(self.game.enqueue(dict(action=action, **fields)))
        return self.game.step()

    def fragmented(self, packet, width=7):
        for start in range(0, len(packet), width):
            self.worker.feed_wire(packet[start:start+width])
            state = self.game.step()
        return state

    def running(self):
        self.command('select', level_id=1)
        self.now += 10
        self.worker.controls.append(self.control('READY2'))
        ready = self.game.step()
        self.assertTrue(ready['board_ready'])
        self.command('start')
        self.now += 10
        self.worker.controls.append(self.control('STARTED2'))
        state = self.game.step()
        self.assertEqual(state['game_state'], 2)
        return state

    def pose(self, sequence=1):
        models = (dict(type='MIRROR', center=[1100,650], axis=[1,0],size=[140,12]),
                  dict(type='TARGET', center=[100,650],axis=[1,0],size=[64,64]))
        return PoseFrame(sequence,1,sequence,self.now,self.now+20,True,'OK',9,0,0,models)

    async def receive(self, ws, predicate):
        for _ in range(100):
            state = await ws.receive_json(timeout=2)
            if predicate(state):
                return state
        self.fail('Expected complete snapshot was not received')

    async def test_runtime_uses_canonical_config_classes_and_c_cache(self):
        shared = canonical_module('godot_bridge')
        self.assertIs(BoardInput, shared.BoardInput)
        self.assertIs(BoardGamePresenter, shared.BoardGamePresenter)
        self.assertIs(binary.BinaryParser, shared.BinaryParser)
        from .board_control import encode_level
        self.assertIs(encode_level, canonical_module('board_wire').encode_level)
        self.assertEqual(CONFIG, json.loads((ROOT/'pc_vision/game_config.json').read_text(encoding='utf-8')))
        self.assertEqual(CONFIG['board_game']['portal_b_exit_side'],1)
        self.assertEqual(CONFIG['board_game']['scene_max_age_ms'],600)
        self.assertTrue(self.core.path.is_relative_to(ROOT/'pc_vision/output/board_native'))
        self.assertEqual(WEB.parent.name,'pc_vision')
        self.assertEqual(WEB.parent.parent.name,'pc_vision(1)')

    async def test_all_fifteen_levels_use_live_level_handshake(self):
        catalog = await (await self.client.get('/api/catalog')).json()
        self.assertEqual(catalog['sceneMaxAgeMs'],600)
        self.assertEqual(catalog['wireProtocol'],3)
        self.assertEqual(catalog['runtimeBuild'],canonical_module('godot_bridge').BRIDGE_BUILD)
        self.assertEqual(len(catalog['levels']),15)
        self.assertTrue(all(level['playable'] for level in catalog['levels']))
        for level in range(1,16):
            state = self.command('select',level_id=level)
            self.assertFalse(state['preview'])
            self.assertEqual(state['board_phase'],'CONFIGURING')
            self.assertEqual(self.worker.levels[-1][0],level)
            self.assertFalse(state['ready'])
        self.assertFalse(self.game.enqueue(dict(action='select',level_id=True)))

    async def test_websocket_handshake_lock_ack_and_first_pose_same_poll(self):
        ws = await self.client.ws_connect('/ws')
        await ws.send_json(dict(action='select',level_id=1))
        await self.receive(ws,lambda s:s.get('board_phase')=='CONFIGURING')
        self.command('start')
        self.assertFalse(self.worker.starts)
        ready = self.control('READY2')
        self.worker.controls.append(dataclasses.replace(ready,nonce=ready.nonce+1))
        self.assertFalse(self.game.step()['ready'])
        self.worker.controls.append(ready)
        state = self.game.step()
        self.assertEqual(state['board_phase'],'READY')
        self.assertTrue(state['ready'])
        self.assertEqual(state['models'],[])  # Ready ACK, not a fabricated scene.
        self.command('start')
        self.assertEqual(self.core.state['game_state'],1)
        self.now += 20
        self.worker.controls.append(self.control('STARTED2'))
        self.worker.next = self.pose()
        state = self.game.step()
        self.assertEqual(state['state'],'LIVE')
        self.assertTrue(state['valid'])
        self.assertGreater(int(state['sequence']),2**53)
        self.assertEqual(state['board_frame']['sequence'],'1')
        await ws.close()

    async def test_wrong_emitter_never_unlocks_start(self):
        self.command('select',level_id=2)
        ready = self.control('READY2')
        self.worker.controls.append(dataclasses.replace(ready,x_milli=ready.x_milli+1))
        state = self.game.step()
        self.assertEqual(state['board_phase'],'ERROR')
        self.command('start')
        self.assertFalse(self.worker.starts)
        self.assertEqual(self.core.state['game_state'],1)

    async def test_no_recognition_timeout_can_return_to_menu(self):
        self.running()
        self.now += 180000
        result = self.game.step()
        self.assertEqual(result['screen'],'result')
        self.assertFalse(result['valid'])
        state = self.command('menu')
        self.assertEqual(state['screen'],'menu')
        self.assertEqual(state['models'],[])
        self.assertEqual(state['segments'],[])
        self.assertTrue(self.worker.resets)

    async def test_quit_releases_uart_and_c_before_acknowledging_closed(self):
        self.running()
        exited = []
        self.game.on_quit = lambda: exited.append(True)
        ws = await self.client.ws_connect('/ws')
        await ws.send_json(dict(action='quit'))
        state = await self.receive(ws,lambda s:s['screen']=='closed')
        self.assertEqual(state['models'],[])
        self.assertFalse(state['valid'])
        self.assertTrue(self.worker.closed)
        self.assertIsNotNone(self.core.process.poll())
        self.assertFalse(self.game.enqueue(dict(action='select',level_id=2)))
        await ws.close()
        await asyncio.sleep(0)
        self.assertEqual(exited,[True])

    async def test_binary_fragmented_handshake_and_pose_reach_web_snapshot(self):
        self.command('select', level_id=1)
        # Logs and old ASCII data never unlock the current binary-only link.
        self.worker.feed_wire(b'BEAM_DIAGNOSTICS version=14\r\n@READY2:old\r\n')
        self.assertFalse(self.game.step()['ready'])
        ready = binary.encode_control(self.control('READY2'))
        for byte in ready[:-1]:
            self.worker.feed_wire(bytes([byte]))
            self.assertFalse(self.game.step()['ready'])
        self.worker.feed_wire(ready[-1:])
        self.assertTrue(self.game.step()['ready'])
        self.command('start')
        self.now += 20
        pose = dataclasses.replace(self.pose(),generation=(1 << 60)+7)
        presenter = self.game.presenter
        packet = (binary.encode_control(self.control('STARTED2')) +
                  binary.encode_pose(pose,1,self.core.state['generation'],presenter.level_nonce))
        state = self.fragmented(packet)
        self.assertEqual(state['serial_protocol'],3)
        self.assertEqual(state['state'],'LIVE')
        self.assertEqual(state['board_frame']['wire_version'],3)
        self.assertEqual(state['board_frame']['generation'],str((1 << 60)+7))
        self.assertEqual(state['board_frame']['captured_ms'],str(self.now))
        self.assertEqual(state['board_frame']['session_generation'],str(self.core.state['generation']))
        self.assertEqual(self.worker.parser.rejected,0)

    async def test_binary_other_sessions_cannot_replace_scene_or_score(self):
        self.running()
        self.now += 10
        presenter = self.game.presenter
        generation, nonce = self.core.state['generation'], presenter.level_nonce
        live = self.fragmented(binary.encode_pose(self.pose(),1,generation,nonce))
        self.assertTrue(live['valid'])
        self.now += 1
        hit = self.pose(2)
        models = copy.deepcopy(list(hit.models))
        a,b,c,d = live['segments'][-1]
        models[1]['center']=[(a+c)/2,(b+d)/2]
        hit = dataclasses.replace(hit,models=tuple(models))
        for level, session, token in ((2,generation,nonce),(1,generation+1,nonce),
                                      (1,generation,nonce ^ 1 or 2)):
            state = self.fragmented(binary.encode_pose(hit,level,session,token))
            self.assertEqual(state['models'],live['models'])
            self.assertEqual(state['sequence'],live['sequence'])
            self.assertEqual(state['game_state'],2)
            self.assertEqual(state['stars'],0)
            self.assertFalse(state['success'])
        pending = dataclasses.replace(self.pose(3),valid=False,status='PENDING',models=(),
                                       raw_mask=0,pending_mask=9,missing_mask=9)
        held = self.fragmented(binary.encode_pose(pending,1,generation,nonce))
        self.assertEqual(held['models'],live['models'])
        self.assertEqual(held['segments'],live['segments'])
        self.assertEqual(held['captured_ms'],live['captured_ms'])
        self.assertTrue(held['display_held'])
        self.assertFalse(held['valid'])
        self.assertFalse(self.core.state['valid'])
        self.assertEqual(self.worker.parser.rejected,0)

    async def test_running_hold_missing_stale_replacement_reconnect_and_menu(self):
        self.running()
        self.now += 10
        self.worker.next = original = self.pose()
        live = self.game.step()
        self.assertTrue(live['models'])
        self.now += 20000
        self.worker.next = dataclasses.replace(original,tx=2,sequence=2,captured_ms=self.now,
            published_ms=self.now+10,valid=False,status='PENDING',models=(),raw_mask=0,missing_mask=9)
        held = self.game.step()
        for key in ('models','segments','sequence','captured_ms','board_frame'):
            self.assertEqual(held[key],live[key])
        self.assertTrue(held['display_held'])
        self.assertFalse(held['valid']);self.assertFalse(held['success'])
        self.assertEqual(self.core.state['stars'],0)
        self.assertEqual(held['display_age_ms'],20000)
        # A changed, old observation cannot replace the accepted picture.
        self.worker.next = dataclasses.replace(self.pose(3),captured_ms=self.now-CONFIG['board_game']['scene_max_age_ms']-1,published_ms=self.now)
        self.assertEqual(self.game.step()['models'],live['models'])
        self.now += 1
        fresh = self.pose(4)
        moved = copy.deepcopy(list(fresh.models));moved[0]['center'][0] -= 50
        self.worker.next = dataclasses.replace(fresh,models=tuple(moved))
        updated = self.game.step()
        self.assertFalse(updated['display_held'])
        self.assertNotEqual(updated['models'],live['models'])
        self.worker.connected=False
        self.assertEqual(self.game.step()['models'],updated['models'])
        self.worker.connected=True;self.worker.epoch+=1
        reconnect=self.game.step()
        self.assertEqual(reconnect['models'],updated['models'])
        self.assertEqual(reconnect['board_phase'],'CONFIGURING')
        menu=self.command('menu')
        self.assertEqual(menu['models'],[]);self.assertEqual(menu['segments'],[])
        self.assertTrue(self.worker.resets)

    async def test_shared_admission_accepts_600_and_rejects_601_ms(self):
        self.running()
        self.now += 1000
        frame = self.pose(1)
        self.worker.next = dataclasses.replace(frame,captured_ms=self.now-600,published_ms=self.now)
        accepted = self.game.step()
        self.assertEqual(accepted['scene_max_age_ms'],600)
        self.assertTrue(accepted['valid'])
        self.assertFalse(accepted['display_held'])
        self.assertTrue(self.core.state['valid'])
        self.now += 10
        self.worker.next = dataclasses.replace(self.pose(2),captured_ms=self.now-601,published_ms=self.now)
        stale = self.game.step()
        self.assertFalse(stale['valid'])
        self.assertFalse(self.core.state['valid'])
        self.assertTrue(stale['display_held'])
        self.assertEqual(stale['models'],accepted['models'])
        self.assertEqual(stale['captured_ms'],accepted['captured_ms'])
        self.assertEqual(stale['game_state'],2)
        self.assertFalse(stale['success'])

    async def test_websocket_reconnect_preserves_c_timer_and_result(self):
        self.running()
        self.now += 10
        self.worker.next = self.pose()
        live = self.game.step()
        ws = await self.client.ws_connect('/ws')
        await self.receive(ws,lambda s:s.get('state')=='LIVE')
        await ws.close()
        self.now += 1000
        ws = await self.client.ws_connect('/ws')
        state = await self.receive(ws,lambda s:s.get('elapsed_ms',0)>=1000)
        self.assertEqual(state['game_state'],2)
        self.assertEqual(state['models'],live['models'])
        hit = self.pose(2)
        models = copy.deepcopy(list(hit.models))
        a,b,c,d = live['segments'][-1]
        models[1]['center']=[(a+c)/2,(b+d)/2]
        self.worker.next = dataclasses.replace(hit,models=tuple(models))
        self.game.step()
        result = await self.receive(ws,lambda s:s['screen']=='result')
        self.assertEqual(result['result']['stars'],3)
        await ws.send_json(dict(action='skip'))
        await self.receive(ws,lambda s:s.get('level_id')==2 and s['screen']=='game')
        await ws.close()

    async def test_static_assets_preview_origin_and_single_controller(self):
        for asset in ['/', '/main.js','/presentation.js','/node_modules/three/build/three.module.js']:
            response = await self.client.get(asset)
            self.assertEqual(response.status,200)
            if not asset.startswith('/node_modules/'):
                self.assertEqual(response.headers['Cache-Control'],'no-store')
        response = await self.client.get('/api/catalog')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        with self.assertRaises(WSServerHandshakeError) as rejected:
            await self.client.ws_connect('/ws',origin='https://example.invalid')
        self.assertEqual(rejected.exception.status,403)
        ws = await self.client.ws_connect('/ws')
        await self.receive(ws,lambda s:s['screen']=='menu')
        ws2 = await self.client.ws_connect('/ws')
        message = await ws.receive(timeout=2)
        while message.type == WSMsgType.TEXT:
            message = await ws.receive(timeout=2)
        self.assertEqual(message.type,WSMsgType.CLOSE)
        self.assertEqual(message.data,4001)
        await ws2.close()
        preview = WebGame(CONFIG,preview=True,clock=lambda:1000)
        for level in range(1,16):
            preview.enqueue(dict(action='select',level_id=level))
            state=preview.step()
            self.assertTrue(state['preview']);self.assertFalse(state['ready'])
            self.assertEqual(state['segments'],[])
        self.assertIsNone(preview.core);self.assertIsNone(preview.worker)
        self.assertEqual(wire({'sequence':2**63})['sequence'],str(2**63))
        self.assertEqual(wire({'session_generation':2**63})['session_generation'],str(2**63))

    async def test_preview_cli_serves_http_without_constructing_uart_or_c(self):
        with patch.object(web_bridge, 'NativeBoardGame', side_effect=AssertionError('No C in preview')), \
                patch.object(web_bridge, 'BoardInput', side_effect=AssertionError('No UART in preview')), \
                patch.object(web_bridge.web, 'run_app') as run:
            self.assertEqual(web_bridge.main(['--preview']),0)
        preview_client = TestClient(TestServer(run.call_args.args[0]))
        async with preview_client:
            catalog = await (await preview_client.get('/api/catalog')).json()
            self.assertEqual(len(catalog['levels']),15)
            ws = await preview_client.ws_connect('/ws')
            await ws.send_json(dict(action='select',level_id=15))
            state = await self.receive(ws,lambda s:s.get('level_id')==15)
            self.assertTrue(state['preview'])
            self.assertFalse(state['valid'])
            self.assertEqual(state['segments'],[])
            await ws.close()


if __name__ == '__main__':
    unittest.main()
