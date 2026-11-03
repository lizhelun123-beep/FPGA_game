"""教学闭环的合成CPU夹具；不连接真实相机/鼠标/UART。"""
import ast
import copy
import math
import unittest

from pynq_vision.beam_runtime import CapturedFrame, FRAME_BYTES, run, DisplayFault
from pynq_vision.teaching_features import polygon_model, ray_case, infer_rule
from pynq_vision.teaching_mode import TeachingSession, erase, join_strokes
from pynq_vision.teaching_mouse import LinuxMouse
from pynq_vision.teaching_protocol import encode_document, TeachingParser, cobs_encode, cobs_decode
from pc_vision.teaching import TeachingReceiver, exports, validate
from pc_vision import board_wire


def frame(stride=3840):
    return CapturedFrame(bytes([30,80,180])*(stride*720//3), 7, 11, 1000, stride)


def teacher():
    s=TeachingSession(session='1234567890abcdef'); s.frame=frame(); s.reference_frame=s.frame
    s.red=[[(300,300),(500,300),(500,400),(300,400),(300,300)]]
    s.action('CONFIRM'); s.action('CONFIRM')
    return s


def cases(kind='REFLECT', count=3):
    out=[]
    for i in range(count):
        a=math.radians(15+i*35); u=[math.cos(a),math.sin(a)]
        if kind=='REFLECT': w=[u[0],-u[1]]
        elif kind=='ROTATE': w=[-u[1],u[0]]
        elif kind=='FIXED_DIRECTION': w=[0.,1.]
        else: w=u
        out.append(dict(start=[-80*u[0],-80*u[1]],entry=[0.,0.],exit=[0.,0.],
                        end=[80*w[0],80*w[1]],incoming=u,outgoing=w))
    return out


class FeatureTests(unittest.TestCase):
    def test_object_shape_and_raw_color_with_stride(self):
        s=teacher(); m=s.model
        self.assertEqual(m['center'],[400.,350.]); self.assertEqual(m['size'],[200.,100.])
        self.assertEqual(m['color_bgr'],[30,80,180]); self.assertEqual(m['semantic_type'],'UNASSIGNED')
        other=polygon_model(s.red[0],frame(5760)); self.assertEqual(other['color_bgr'],m['color_bgr'])

    def test_unclosed_and_self_intersecting_contours_refuse(self):
        with self.assertRaises(ValueError): polygon_model([(300,300),(500,300),(500,400),(400,400)],frame())
        with self.assertRaisesRegex(ValueError,'SELF_INTERSECTING'):
            polygon_model([(300,300),(500,400),(300,400),(500,300),(300,300)],frame())

    def test_object_local_rotation(self):
        model=dict(center=[400,350],axis=[0.,1.],size=[200,100])
        c=ray_case([(400,250),(400,350)],[(400,350),(350,350)],model)
        self.assertEqual(c['incoming'],[1.,0.]); self.assertEqual(c['outgoing'],[0.,1.])

    def test_curved_or_reversed_endpoint_not_on_object_refuses(self):
        model=teacher().model
        with self.assertRaises(ValueError): ray_case([(100,100),(200,100)],[(200,100),(220,120)],model)
        with self.assertRaises(ValueError): ray_case([(300,350),(350,400),(400,350)],[(400,350),(450,350)],model)

    def test_three_different_directions_fit_each_finite_family(self):
        for kind in ('REFLECT','ROTATE','FIXED_DIRECTION','PASS_THROUGH'):
            with self.subTest(kind=kind): self.assertEqual(infer_rule(cases(kind))['kind'],kind)

    def test_three_repeated_directions_are_insufficient(self):
        self.assertFalse(infer_rule([cases()[0]]*3)['accepted'])
        self.assertFalse(infer_rule(cases()[:2])['accepted'])

    def test_noisy_inconsistent_cases_are_unknown(self):
        cs=cases(); cs[1]['outgoing']=[0.,-1.]
        self.assertEqual(infer_rule(cs)['kind'],'UNKNOWN')

    def test_transmission_position_is_explicit(self):
        cs=cases('ROTATE')
        for c in cs: c['exit']=[30.,20.]
        self.assertEqual(infer_rule(cs)['position']['kind'],'FIXED_LOCAL')
        for i,c in enumerate(cs): c['entry']=[i*30.,0.]; c['exit']=[i*30.+30.,20.]
        self.assertEqual(infer_rule(cs)['position']['kind'],'OFFSET_LOCAL')


class TeachingTests(unittest.TestCase):
    def test_left_hold_red_and_release(self):
        s=TeachingSession(); s.frame=frame(); s.cursor=[300,300]
        s.report(0,0,True); s.report(50,0,True); s.report(0,50,True); s.report(-50,0,True); s.report(0,-50,True); s.report(0,0,False)
        self.assertEqual(len(s.red),1); s.action('ANALYZE'); self.assertIsNotNone(s.model)

    def test_eraser_removes_middle_without_reconnecting(self):
        split=erase([[(100,200),(300,200)]],(200,200))
        self.assertEqual(len(split),2)
        self.assertLess(max(p[0] for p in split[0]),185)
        self.assertGreater(min(p[0] for p in split[1]),215)

    def test_erasing_object_invalidates_virtual_template(self):
        s=teacher(); s.cases=cases(); s.rule=infer_rule(s.cases)
        s.action('OUTLINE'); s.tool='ERASER'; s.cursor=[400,300]; s.report(0,0,True); s.report(0,0,False)
        self.assertIsNone(s.model); self.assertEqual(s.cases,[]); self.assertFalse(s.rule['accepted'])
        validate(s.document())

    def test_erased_outline_can_be_repaired_without_guessing_gap(self):
        s=teacher(); s.action('OUTLINE'); s.red=erase(s.red,(400,300))
        with self.assertRaises(ValueError): s.action('ANALYZE')
        s.red.append([(380,300),(420,300)])
        s.action('ANALYZE'); self.assertAlmostEqual(s.model['area_px2'],20000,delta=100)

    def test_closed_green_feature_never_changes_outline_geometry(self):
        s=teacher(); original=copy.deepcopy(s.model)
        s.green=[[(200,200),(600,200),(600,500),(200,500),(200,200)]]
        s.action('FEATURE'); s.action('ANALYZE')
        for key in ('center','axis','size','area_px2','outline_local','color_bgr'):
            self.assertEqual(s.model[key],original[key])
        self.assertEqual(len(s.model['markers_local']),1)
        self.assertEqual(s.document()['annotation_layers'],dict(outline='red',features='green',rays='yellow'))

    def test_left_hold_feature_routes_only_to_green_strokes(self):
        s=teacher(); red=copy.deepcopy(s.red); s.action('FEATURE'); s.cursor=[350,330]
        s.report(0,0,True); s.report(50,0,True); s.report(0,0,False)
        self.assertEqual(s.red,red); self.assertEqual(len(s.green),1)
        self.assertIsNotNone(s.model); self.assertFalse(s.features_confirmed); s.action('ANALYZE')
        self.assertEqual(s.model['size'],[200.,100.]); self.assertEqual(len(s.model['markers_local']),1)

    def test_green_closed_feature_cannot_replace_missing_red_outline(self):
        s=teacher(); s.action('OUTLINE'); s.green=s.red; s.red=[]
        with self.assertRaisesRegex(ValueError,'DRAW RED OUTLINE'): s.action('CONFIRM')
        with self.assertRaisesRegex(ValueError,'CONFIRM_RED_OUTLINE'): s.action('FEATURE')

    def test_multiple_closed_red_contours_are_ambiguous(self):
        s=teacher(); s.action('OUTLINE'); s.red.append([(350,320),(450,320),(450,380),(350,380),(350,320)])
        with self.assertRaisesRegex(ValueError,'ONE_COMPLETE_RED_OUTLINE'): s.action('ANALYZE')

    def test_eraser_only_changes_selected_red_or_green_layer_at_overlap(self):
        for mode in ('OUTLINE','FEATURE'):
            with self.subTest(mode=mode):
                s=teacher(); s.green=[[(350,300),(450,300)]]
                s.yellow={'IN':[[(350,300),(450,300)]],'OUT':[]}
                red,green,yellow=copy.deepcopy(s.red),copy.deepcopy(s.green),copy.deepcopy(s.yellow)
                s.action(mode); s.tool='ERASER'; s.cursor=[400,300]
                s.report(0,0,True); s.report(0,0,False)
                self.assertEqual(s.yellow,yellow)
                if mode=='OUTLINE': self.assertEqual(s.green,green); self.assertNotEqual(s.red,red)
                else: self.assertEqual(s.red,red); self.assertNotEqual(s.green,green)

    def test_clear_and_new_keep_layer_semantics(self):
        s=teacher(); s.green=[[(350,320),(450,320)]]
        red=copy.deepcopy(s.red); s.action('FEATURE'); s.action('CLEAR')
        self.assertEqual(s.red,red); self.assertEqual(s.green,[])
        s.green=[[(350,320),(450,320)]]; s.action('OUTLINE'); s.action('CLEAR')
        self.assertEqual(s.red,[]); self.assertTrue(s.green)
        s.action('NEW'); self.assertEqual(s.green,[]); self.assertEqual(s.mode,'OUTLINE')

    def test_yellow_roles_save_and_undo(self):
        s=teacher(); s.action('RAYS')
        s.yellow={'IN':[[(280,350),(400,350)]],'OUT':[[(400,350),(450,400)]]}
        s.action('SAVE'); self.assertEqual(len(s.cases),1); self.assertEqual(s.yellow,{'IN':[],'OUT':[]})
        s.action('UNDO'); self.assertEqual(s.cases,[])

    def test_toolbar_does_not_draw(self):
        s=teacher(); s.cursor=[350,10]; s.report(0,0,True); s.update(frame()); s.report(0,0,False)
        self.assertEqual(s.mode,'RAYS'); self.assertEqual(len(s.red),1)

    def test_cancelled_input_drops_active_stroke_until_release(self):
        s=TeachingSession(); s.frame=frame(); s.report(0,0,True); s.report(20,0,True)
        s.report(0,0,False,True); s.report(30,0,True); self.assertEqual(s.active,[])
        s.report(0,0,False); self.assertFalse(s.blocked)

    def test_mouse_native_value_is_signed(self):
        data=LinuxMouse.EVENT.pack(1,2,2,0,-17)
        self.assertEqual(LinuxMouse.EVENT.unpack(data)[-1],-17)

    def test_composition_only_shows_current_stage_and_keeps_clean_input(self):
        s=teacher(); s.green=[[(350,330),(450,330)]]; s.yellow={'IN':[[(500,500),(600,500)]],'OUT':[]}; s.dirty=True
        clean=frame().bgr; before=bytes(clean)
        pixels=[(350,300),(400,330),(550,500)]; base=b'\x1e\x50\xb4'
        for stage,colors in [('OUTLINE',[b'\x00\x00\xff',base,base]),
                             ('FEATURE',[base,b'\x00\xff\x00',base]),('RAYS',[base,base,b'\x00\xff\xff'])]:
            s.mode=stage; s.dirty=True; result=s.compose(clean)
            self.assertEqual(clean,before); self.assertEqual(len(result),FRAME_BYTES)
            for (x,y),color in zip(pixels,colors): self.assertEqual(result[(y*1280+x)*3:(y*1280+x)*3+3],color)

    def test_stages_cannot_be_skipped_and_confirm_advances_in_order(self):
        s=TeachingSession(); s.frame=s.reference_frame=frame()
        for action in ('FEATURE','RAYS','IN','OUT'):
            with self.assertRaises(ValueError): s.action(action)
            self.assertEqual(s.mode,'OUTLINE')
        s.red=[[(300,300),(500,300),(500,400),(300,400),(300,300)]]
        s.action('CONFIRM'); self.assertEqual(s.mode,'FEATURE'); self.assertTrue(s.outline_confirmed)
        with self.assertRaisesRegex(ValueError,'CONFIRM_GREEN_FEATURES'): s.action('RAYS')
        s.action('CONFIRM'); self.assertEqual(s.mode,'RAYS'); self.assertTrue(s.features_confirmed)

    def test_confirm_and_next_stroke_in_same_mouse_batch_use_new_stage(self):
        s=TeachingSession(); s.frame=s.reference_frame=frame(); s.cursor=[1025,10]
        s.red=[[(300,300),(500,300),(500,400),(300,400),(300,300)]]
        class Mouse:
            error=None
            def poll(self): return [(0,0,True,False),(0,0,False,False),(-675,320,False,False),
                                    (0,0,True,False),(40,0,True,False),(0,0,False,False)]
        s.mouse=Mouse(); s.update(frame())
        self.assertEqual(s.mode,'FEATURE'); self.assertEqual(len(s.red),1); self.assertEqual(len(s.green),1)

    def test_unclosed_outline_warns_on_release_and_blocks_next_stage(self):
        s=TeachingSession(); s.frame=frame(); s.cursor=[300,300]
        s.report(0,0,True); s.report(100,0,True); s.report(0,100,True); s.report(0,0,False)
        self.assertIn('OUTLINE OPEN GAP',s.status)
        rendered=s.compose(frame().bgr); index=(300*1280+306)*3
        self.assertEqual(rendered[index:index+3],b'\xff\xff\xff')
        with self.assertRaisesRegex(ValueError,'OUTLINE OPEN GAP'): s.action('CONFIRM')
        with self.assertRaises(ValueError): s.action('FEATURE')
        self.assertEqual(s.mode,'OUTLINE'); self.assertFalse(s.outline_confirmed)

    def test_returning_to_outline_invalidates_later_confirmations(self):
        s=teacher(); s.cases=cases(); s.rule=infer_rule(s.cases); s.action('OUTLINE')
        self.assertFalse(s.outline_confirmed); self.assertFalse(s.features_confirmed)
        self.assertIsNone(s.model); self.assertEqual(s.cases,[])

    def test_first_point_uses_previously_displayed_frame(self):
        s=TeachingSession(); old=frame(); s.frame=old
        class Mouse:
            error=None
            def poll(self): return [(0,0,True,False)]
        s.mouse=Mouse(); new=CapturedFrame(old.bgr,7,12,1100); s.update(new)
        self.assertEqual(s.reference_frame.sequence,11)


class ProtocolTests(unittest.TestCase):
    def test_all_byte_cobs_roundtrip(self):
        data=bytes(range(256))*2; self.assertEqual(cobs_decode(cobs_encode(data)),data)

    def test_fragmented_snapshot_interleaved_with_v3_and_text(self):
        s=teacher(); s.cases=cases(); s.rule=infer_rule(s.cases); s._changed()
        doc=s.document(); side=encode_document(doc); receiver=TeachingReceiver(); v3=board_wire.BinaryParser()
        existing=board_wire.encode_sync('12345678'); parser=board_wire.PacketParser()
        for packet in side:
            stream=b'LOG\n'+packet+existing
            for i in range(0,len(stream),7): receiver.feed(stream[i:i+7]); v3.feed(stream[i:i+7])
            self.assertEqual(parser.feed(packet),[])
        self.assertEqual(receiver.snapshot(),doc); self.assertEqual(receiver.rejected,0)
        self.assertEqual(v3.framing.rejected,0)

    def test_missing_corrupt_and_oversize_do_not_publish(self):
        packets=encode_document(teacher().document()); self.assertGreater(len(packets),2)
        for broken in (b''.join(packets[1:]), packets[0]+packets[-1], b'\x00\xfe'+b'X'*999+b'\x00'):
            p=TeachingParser(); self.assertEqual(p.feed(broken),[])
        p=TeachingParser(); bad=bytearray(packets[0]); bad[20]^=4
        self.assertEqual(p.feed(bytes(bad)+b''.join(packets[1:])),[])

    def test_duplicate_revision_is_idempotent_and_new_revision_replaces(self):
        s=teacher(); r=TeachingReceiver(); wire=b''.join(encode_document(s.document()))
        self.assertTrue(r.feed(wire)); self.assertFalse(r.feed(wire))
        s.action('NEW'); self.assertTrue(r.feed(b''.join(encode_document(s.document()))))
        self.assertIsNone(r.snapshot()['model'])

    def test_invalid_geometry_and_forged_rule_rejected(self):
        for mutate in (lambda d:d['model'].update(axis=[0,0]), lambda d:d.update(rule={'kind':'REFLECT','accepted':True})):
            doc=teacher().document(); mutate(doc); r=TeachingReceiver()
            self.assertFalse(r.feed(b''.join(encode_document(doc)))); self.assertIsNone(r.latest)

    def test_pc_rejects_cases_claimed_before_feature_confirmation(self):
        s=teacher(); doc=s.document(); doc.update(annotation_stage='FEATURE',features_confirmed=False,cases=cases())
        doc['rule']=infer_rule(doc['cases']); r=TeachingReceiver()
        self.assertFalse(r.feed(b''.join(encode_document(doc)))); self.assertIsNone(r.latest)

    def test_generated_code_is_syntax_valid_and_fits_unseen_direction(self):
        s=teacher(); s.cases=cases(); s.rule=infer_rule(s.cases); output=exports(s.document())
        ast.parse(output['object_template.py']); ast.parse(output['ray_rule.py'])
        # 只在离线测试执行受限生成器产物；产品从不exec接收的数据。
        namespace={}; exec(compile(output['ray_rule.py'],'generated','exec'),namespace)
        p,d=namespace['propagate']([2,3],[.6,.8]); self.assertEqual(p,(2,3))
        self.assertAlmostEqual(d[0],.6,places=6); self.assertAlmostEqual(d[1],-.8,places=6)
        self.assertIn('teaching_propagate',output['ray_rule.c'])
        with self.assertRaises(ValueError): namespace['propagate']([0,0],[float('nan'),1])

    def test_unknown_generated_rule_refuses_execution(self):
        output=exports(teacher().document()); namespace={}; exec(output['ray_rule.py'],namespace)
        with self.assertRaises(ValueError): namespace['propagate']([0,0],[1,0])


class RuntimeTests(unittest.TestCase):
    def test_teaching_keeps_original_frame_ticket_and_safe_drain(self):
        events=[]; source=frame(); s=teacher()
        class Owner:
            first_fault=None
            def prepare(self): pass
            def capture_cpu(self): return source
            def check_capture(self): pass
            def submit_cpu(self,canvas,result): events.append(('submit',result.ticket,len(canvas)))
            def display_retired(self,ticket): events.append(('retire',ticket)); return True
            def stop(self): events.append(('stop',))
            def can_exit(self): return True
        class Beam:
            def receive(self,data): return []
            def frame(self,captured):
                self.seen=captured
                return type('Result',(),{'ticket':17})(),bytes(FRAME_BYTES),b'pose'
            def submitted(self,ticket): events.append(('submitted',ticket))
            def retired(self,ticket): return b'ready'
            def close(self): events.append(('beam_close',))
        class UART:
            def read(self): return b''
            def write_packet(self,data): events.append(('tx',data[:2]))
            def close(self): events.append(('uart_close',))
        beam=Beam(); run(Owner(),beam,UART(),lambda:any(e[0]=='retire' for e in events),teaching=s)
        self.assertIs(beam.seen,source); self.assertIn(('submit',17,FRAME_BYTES),events)
        self.assertEqual(events[-3:],[('stop',),('uart_close',),('beam_close',)])
        self.assertLess(events.index(('tx',b're')),events.index(('tx',b'\x00\xfe')))


if __name__=='__main__': unittest.main()
