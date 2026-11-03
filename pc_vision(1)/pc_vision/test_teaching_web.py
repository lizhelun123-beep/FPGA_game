"""教学端点与同一个电脑串口owner的离线HTTP验证。"""
import unittest
from aiohttp.test_utils import TestClient, TestServer
from .web_bridge import WebGame, load_config
from .shared_runtime import canonical_module

TeachingReceiver=canonical_module('teaching').TeachingReceiver
import math
from pynq_vision.teaching_mode import TeachingSession
from pynq_vision.beam_runtime import CapturedFrame
from pynq_vision.teaching_features import infer_rule
from pynq_vision.teaching_protocol import encode_document


class TeachingWebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.game=WebGame(load_config(),preview=True)
        self.client=TestClient(TestServer(self.game.application()))
        await self.client.start_server()

    async def asyncTearDown(self): await self.client.close()

    async def test_preview_without_hardware(self):
        r=await self.client.get('/teaching'); self.assertEqual(r.status,200)
        page=await r.text(); self.assertIn('实景教学预览',page)
        self.assertIn('绿线：物块特征',page); self.assertIn("'#58eb82'",page)
        r=await self.client.get('/api/teaching'); self.assertIsNone((await r.json())['document'])
        self.assertEqual((await self.client.get('/api/teaching/export/ray_rule.py')).status,404)

    async def test_board_features_automatically_become_model_and_downloads(self):
        s=TeachingSession(session='1234567890abcdef')
        s.frame=s.reference_frame=CapturedFrame(bytes([30,80,180])*1280*720,7,11,1000)
        s.red=[[(300,300),(500,300),(500,400),(300,400),(300,300)]]
        s.green=[[(350,330),(450,330)]]; s.action('CONFIRM'); s.action('CONFIRM')
        for angle in (15,50,85):
            x,y=math.cos(math.radians(angle)),math.sin(math.radians(angle))
            s.cases.append(dict(start=[-80*x,-80*y],entry=[0,0],exit=[0,0],end=[80*x,-80*y],incoming=[x,y],outgoing=[x,-y]))
        s.rule=infer_rule(s.cases)
        receiver=TeachingReceiver(); receiver.feed(b''.join(encode_document(s.document())))
        class Worker:
            def teaching_snapshot(self): return dict(document=receiver.snapshot(),connected=True,rejected=0)
            def poll(self): return None,0,True,None,''
        # 替换只读端点的数据源，不启动任何串口线程。
        self.game.worker=Worker()
        r=await self.client.get('/api/teaching'); doc=(await r.json())['document']
        self.assertEqual(doc['model']['size'],[200.,100.]); self.assertEqual(doc['rule']['kind'],'REFLECT')
        self.assertEqual(len(doc['model']['markers_local']),1)
        self.assertEqual(doc['annotation_layers'],dict(outline='red',features='green',rays='yellow'))
        for name in ('teaching.json','object_template.py','ray_rule.py','ray_rule.c'):
            r=await self.client.get('/api/teaching/export/'+name)
            self.assertEqual(r.status,200); self.assertIn('attachment',r.headers['Content-Disposition'])
            self.assertTrue(await r.text())
        self.assertEqual((await self.client.get('/api/teaching/export/BOOT.BIN')).status,404)
        self.game.worker=None


if __name__=='__main__': unittest.main()
