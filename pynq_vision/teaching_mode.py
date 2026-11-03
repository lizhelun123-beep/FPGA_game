"""PYNQ实景教学层：独立CPU画布、鼠标工具栏、可撤销示例与版本快照。"""
import math
import time
import uuid
from collections import deque

from .teaching_features import polygon_model, ray_case, infer_rule, local
from .teaching_protocol import encode_document

WIDTH, HEIGHT, TOP = 1280, 720, 96
BUTTONS = [('OUTLINE', 0, 0), ('FEATURE', 1, 0), ('RAYS', 2, 0), ('PEN', 3, 0),
           ('ERASER', 4, 0), ('CLEAR', 5, 0), ('ANALYZE', 6, 0),
           ('IN', 0, 1), ('OUT', 1, 1), ('SAVE', 2, 1), ('UNDO', 3, 1), ('NEW', 4, 1), ('SEND', 5, 1)]
ANNOTATION_LAYERS = dict(outline='red', features='green', rays='yellow')

# 与原 vision_overlay.c 一致的5x7英数位图；不引入字体/桌面依赖。
LETTERS = [(126,17,17,17,126),(127,73,73,73,54),(62,65,65,65,34),(127,65,65,34,28),
 (127,73,73,73,65),(127,9,9,9,1),(62,65,73,73,122),(127,8,8,8,127),(0,65,127,65,0),
 (32,64,65,63,1),(127,8,20,34,65),(127,64,64,64,64),(127,2,12,2,127),(127,4,8,16,127),
 (62,65,65,65,62),(127,9,9,9,6),(62,65,81,33,94),(127,9,25,41,70),(70,73,73,73,49),
 (1,1,127,1,1),(63,64,64,64,63),(31,32,64,32,31),(63,64,56,64,63),(99,20,8,20,99),
 (7,8,112,8,7),(97,81,73,69,67)]
DIGITS = [(62,81,73,69,62),(0,66,127,64,0),(66,97,81,73,70),(33,65,69,75,49),
 (24,20,18,127,16),(39,69,69,69,57),(60,74,73,73,48),(1,113,9,5,3),(54,73,73,73,54),(6,73,73,41,30)]


def text(array, x, y, message, color=(235, 240, 245), scale=2):
    for ch in message.upper():
        glyph = LETTERS[ord(ch)-65] if 'A' <= ch <= 'Z' else DIGITS[ord(ch)-48] if ch.isdigit() and ord(ch)<128 else (0,)*5
        for col, bits in enumerate(glyph):
            for row in range(7):
                if bits & (1 << row): array[y+row*scale:y+(row+1)*scale, x+col*scale:x+(col+1)*scale] = color
        x += 6*scale


def draw(array, points, value, radius=2):
    import numpy as np
    for a, b in zip(points, points[1:]):
        n = max(1, int(math.ceil(math.hypot(b[0]-a[0], b[1]-a[1]))))
        x = np.rint(np.linspace(a[0], b[0], n+1)).astype(int)
        y = np.rint(np.linspace(a[1], b[1], n+1)).astype(int)
        for oy in range(-radius, radius+1):
            for ox in range(-radius, radius+1):
                if ox*ox+oy*oy > radius*radius: continue
                xx, yy = x+ox, y+oy; valid = (xx>=0)&(xx<WIDTH)&(yy>=TOP)&(yy<HEIGHT)
                array[yy[valid], xx[valid]] = value


def erase(strokes, point, radius=18):
    """分段采样后局部擦除；断开的线不再跨过擦除区域自动连线。"""
    result = []
    for stroke in strokes:
        segment = []
        for a, b in zip(stroke, stroke[1:]):
            n = max(1, int(math.ceil(math.hypot(b[0]-a[0], b[1]-a[1])/2)))
            for i in range(n):
                p = (a[0]+(b[0]-a[0])*i/n, a[1]+(b[1]-a[1])*i/n)
                if math.hypot(p[0]-point[0], p[1]-point[1]) <= radius:
                    if len(segment)>1: result.append(segment)
                    segment = []
                else: segment.append(p)
        if stroke and math.hypot(stroke[-1][0]-point[0], stroke[-1][1]-point[1]) > radius: segment.append(stroke[-1])
        if len(segment)>1: result.append(segment)
    if sum(len(p) for p in result) > 16384 or len(result)>64:
        raise ValueError('ANNOTATION_LIMIT_CLEAR_LAYER')
    return result


def join_strokes(strokes):
    # 擦除后允许用新笔划补回轮廓；只拼接8像素内的真实端点，不跨越空缺。
    result=[list(p) for p in strokes if len(p)>1]
    def distance(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
    while True:
        best=None
        for i,a in enumerate(result):
            if distance(a[0],a[-1])<=8: continue
            for j in range(i+1,len(result)):
                b=result[j]
                if distance(b[0],b[-1])<=8: continue
                for reverse_a in (False,True):
                    for reverse_b in (False,True):
                        gap=distance(a[0] if reverse_a else a[-1],b[-1] if reverse_b else b[0])
                        if gap<=8 and (best is None or gap<best[0]): best=(gap,i,j,reverse_a,reverse_b)
        if best is None: return result
        _,i,j,ra,rb=best
        a=result[i][::-1] if ra else result[i]; b=result[j][::-1] if rb else result[j]
        result[i]=a+b; del result[j]


class TeachingSession:
    def __init__(self, mouse=None, session=None):
        self.mouse = mouse; self.session = session or uuid.uuid4().hex[:16]
        self.revision = 0; self.mode = 'OUTLINE'; self.tool = 'PEN'; self.role = 'IN'
        self.cursor = [640., 360.]; self.down = False; self.blocked = False
        self.active = []; self.red = []; self.green = []; self.yellow = {'IN':[], 'OUT':[]}
        self.outline_confirmed = False; self.features_confirmed = False
        self.model = None; self.cases = []; self.rule = infer_rule([])
        self.frame = None; self.reference = None; self.status = 'CLOSE RED OUTLINE THEN ANALYZE'
        self.tx = deque(); self.tx_revision = None
        self.latest_document = None; self.last_sent = 0.; self.dirty = True; self.layers = None

    def _changed(self, object_changed=False):
        if object_changed:
            self.model = None; self.reference = None; self.cases = []; self.rule = infer_rule([])
            self.outline_confirmed = False; self.features_confirmed = False
        self.revision += 1; self.tx.clear(); self.tx_revision = None; self.dirty = True
        self.latest_document = None

    def _features_changed(self):
        self.features_confirmed=False; self.cases=[]; self.rule=infer_rule([])
        if self.model is not None: self.model['markers_local']=[]
        self._changed()

    def _outline_notice(self):
        components=join_strokes(self.red)
        if not components: self.status='DRAW RED OUTLINE THEN CONFIRM'
        elif len(components)!=1: self.status='OUTLINE HAS GAPS JOIN OR ERASE'
        else:
            p=components[0]; gap=math.hypot(p[0][0]-p[-1][0],p[0][1]-p[-1][1])
            self.status=('OUTLINE OPEN GAP %d PX CLOSE BEFORE CONFIRM' % math.ceil(gap)
                         if gap>16 else 'OUTLINE CLOSED PRESS CONFIRM' if len(p)>=4 else 'OUTLINE OPEN KEEP DRAWING')

    def _stamp(self, frame):
        return dict(generation=str(frame.generation), sequence=str(frame.sequence), captured_ms=str(frame.captured_ms))

    def document(self):
        return dict(schema='pynq-teaching-v1', session=self.session, revision=max(1, self.revision),
                    coordinate_space='camera_px_1280x720', transform='identity-v1',
                    template_id='object-1', model=self.model, cases=self.cases, rule=self.rule,
                    annotation_layers=dict(ANNOTATION_LAYERS),
                    annotation_stage=self.mode, outline_confirmed=self.outline_confirmed,
                    features_confirmed=self.features_confirmed,
                    reference=self.reference, status=self.status, game_valid=False)

    def report(self, dx, dy, down, cancelled=False):
        self.cursor = [max(0., min(WIDTH-1., self.cursor[0]+dx)), max(0., min(HEIGHT-1., self.cursor[1]+dy))]
        if cancelled:
            self.active = []; self.down = False; self.blocked = True
            self.status = 'MOUSE INPUT LOST RELEASE BUTTON'; return
        if self.blocked:
            if not down: self.blocked = False
            return
        if down and not self.down:
            self.down = True
            if self.cursor[1] < TOP:
                col, row = int(self.cursor[0]//170), int(self.cursor[1]//32)
                self.blocked = True; self.down = False
                for name, c, r in BUTTONS:
                    if (col, row)==(c, r):
                        # 按输入顺序立即应用确认/切阶段；不能让同一批后续落笔沿用旧阶段。
                        self.action(name)
                        break
                return
            if self.frame is None: self.status='WAIT_CAMERA'; return
            if self.mode=='OUTLINE':
                self.reference_frame=self.frame; self._changed(True)
            elif self.mode=='FEATURE':
                if not self.outline_confirmed: raise ValueError('CONFIRM_RED_OUTLINE_FIRST')
                self._features_changed()
            else:
                if not self.features_confirmed: raise ValueError('CONFIRM_GREEN_FEATURES_FIRST')
                self._changed()
            self.active = [tuple(self.cursor)]
        if down and self.down and self.cursor[1] >= TOP:
            if self.tool == 'PEN':
                if len(self.active) >= 2048: self.status='STROKE_LIMIT_RELEASE'
                elif not self.active or math.hypot(self.active[-1][0]-self.cursor[0], self.active[-1][1]-self.cursor[1])>=2:
                    self.active.append(tuple(self.cursor)); self.dirty=True
            else:
                if self.mode=='OUTLINE': self.red = erase(self.red, self.cursor)
                elif self.mode=='FEATURE': self.green = erase(self.green, self.cursor)
                else:
                    for role in self.yellow: self.yellow[role] = erase(self.yellow[role], self.cursor)
                self.dirty=True
        if not down and self.down:
            self.down = False
            if self.tool=='PEN' and len(self.active)>1:
                target = self.red if self.mode=='OUTLINE' else self.green if self.mode=='FEATURE' else self.yellow[self.role]
                if len(target)<(12 if self.mode=='FEATURE' else 32): target.append(self.active)
                else: self.status='STROKE_LIMIT_CLEAR_LAYER'
            self.active=[]; self.dirty=True
            if self.mode=='OUTLINE': self._outline_notice()

    def action(self, name):
        # OBJECT保留为旧脚本的轮廓入口；新界面显式区分轮廓和特征。
        if name in ('OBJECT','OUTLINE'):
            if self.mode!='OUTLINE': self._changed(True)
            self.mode='OUTLINE'; self._outline_notice()
        elif name=='FEATURE':
            if not self.outline_confirmed: raise ValueError('CONFIRM_RED_OUTLINE_FIRST')
            if self.mode!='FEATURE': self._features_changed()
            self.mode='FEATURE'; self.status='DRAW GREEN FEATURES THEN CONFIRM'
        elif name=='RAYS':
            if not self.features_confirmed: raise ValueError('CONFIRM_GREEN_FEATURES_FIRST')
            self.mode='RAYS'
        elif name in ('PEN','ERASER'): self.tool=name
        elif name in ('IN','OUT'): self.action('RAYS'); self.role=name
        elif name=='NEW':
            self.red=[]; self.green=[]; self.yellow={'IN':[], 'OUT':[]}; self._changed(True)
            self.status='CLOSE RED OUTLINE THEN ANALYZE'; self.mode='OUTLINE'
        elif name=='CLEAR':
            if self.mode=='OUTLINE': self.red=[]; self._changed(True)
            elif self.mode=='FEATURE': self.green=[]; self._features_changed()
            else: self.yellow={'IN':[], 'OUT':[]}; self._changed()
        elif name=='UNDO':
            if self.cases: self.cases.pop(); self.rule=infer_rule(self.cases); self._changed()
        elif name=='SEND': self.tx.clear(); self.last_sent=0.
        elif name in ('ANALYZE','CONFIRM'):
            if self.mode=='RAYS': self.rule=infer_rule(self.cases); self.status=self.rule['kind']; self._changed()
            elif self.mode=='OUTLINE':
                components=join_strokes(self.red)
                closed = [p for p in components if len(p)>=4 and math.hypot(p[0][0]-p[-1][0],p[0][1]-p[-1][1])<=16]
                if not closed:
                    self._outline_notice(); raise ValueError(self.status)
                if len(components)!=1: raise ValueError('ONE_COMPLETE_RED_OUTLINE_REQUIRED')
                outline=closed[0]
                self.model=polygon_model(outline, self.reference_frame)
                self.model['markers_local']=[]
                self.reference=self._stamp(self.reference_frame)
                self.outline_confirmed=True; self.features_confirmed=False; self.mode='FEATURE'
                self.status='OUTLINE CONFIRMED DRAW GREEN THEN CONFIRM'; self._changed()
            else:
                if not self.outline_confirmed or self.model is None: raise ValueError('CONFIRM_RED_OUTLINE_FIRST')
                # 绿色特征不参与轮廓拼接/面积/主轴计算；即使闭合也不会变成外边界。
                self.model['markers_local']=[[local(p,self.model) for p in line[::max(1,int(math.ceil(len(line)/24.)))]] for line in self.green]
                self.features_confirmed=True; self.mode='RAYS'
                self.status='FEATURES CONFIRMED DRAW IN THEN OUT'; self._changed()
        elif name=='SAVE':
            if self.model is None: raise ValueError('ANALYZE_OBJECT_FIRST')
            if self.mode!='RAYS' or not self.features_confirmed: raise ValueError('CONFIRM_GREEN_FEATURES_FIRST')
            if len(self.yellow['IN'])!=1 or len(self.yellow['OUT'])!=1: raise ValueError('ONE_IN_AND_ONE_OUT_REQUIRED')
            if len(self.cases)>=16: raise ValueError('CASE_LIMIT_UNDO_FIRST')
            case=ray_case(self.yellow['IN'][0], self.yellow['OUT'][0], self.model)
            case['reference']=self._stamp(self.frame)
            self.cases.append(case); self.yellow={'IN':[], 'OUT':[]}; self.rule=infer_rule(self.cases)
            self.status=self.rule.get('reason',self.rule['kind']); self._changed()
        self.dirty=True

    def update(self, captured):
        try:
            if self.mouse:
                for report in self.mouse.poll():
                    try: self.report(*report)
                    except ValueError as error:
                        self.status=str(error); self._changed()
                if self.mouse.error: self.status='MOUSE DISCONNECTED'
        except ValueError as error: self.status=str(error); self.dirty=True
        self.frame=captured
        # 只发送完整版本；在绘制中不发布半成品，停止编辑后自动同步。
        if not self.down and self.revision and not self.tx and (self.latest_document is None or time.monotonic()-self.last_sent>3):
            self.latest_document=self.document(); self.tx.extend(encode_document(self.latest_document))
            self.tx_revision=self.revision; self.last_sent=time.monotonic()

    def pop_packet(self):
        return self.tx.popleft() if self.tx else b''

    def compose(self, base, stride=WIDTH*3):
        import numpy as np
        if stride<WIDTH*3 or len(base)<(HEIGHT-1)*stride+WIDTH*3: raise ValueError('complete canvas required')
        canvas=np.ndarray((HEIGHT,WIDTH,3),dtype=np.uint8,buffer=base,strides=(stride,3,1)).copy()
        if self.dirty or self.layers is None:
            self.layers=np.zeros((HEIGHT,WIDTH),dtype=np.uint8)
            if self.mode=='OUTLINE':
                for p in self.red: draw(self.layers,p,1)
            elif self.mode=='FEATURE':
                for p in self.green: draw(self.layers,p,3)
            for role in self.yellow if self.mode=='RAYS' else ():
                for p in self.yellow[role]:
                    draw(self.layers,p,2)
                    if len(p)>1:
                        a,b=p[0],p[-1]; angle=math.atan2(b[1]-a[1],b[0]-a[0])
                        tip=[(b[0]-12*math.cos(angle-.4),b[1]-12*math.sin(angle-.4)),b,
                             (b[0]-12*math.cos(angle+.4),b[1]-12*math.sin(angle+.4))]
                        draw(self.layers,tip,2)
            if self.active: draw(self.layers,self.active,1 if self.mode=='OUTLINE' else 3 if self.mode=='FEATURE' else 2)
            self.dirty=False
        canvas[self.layers==1]=(0,0,255); canvas[self.layers==2]=(0,255,255); canvas[self.layers==3]=(0,255,0)
        canvas[:TOP]=(28,23,19)
        for name,col,row in BUTTONS:
            selected=name in (self.mode,self.tool) or (self.mode=='RAYS' and name==self.role)
            locked=(name=='FEATURE' and not self.outline_confirmed) or (name in ('RAYS','IN','OUT','SAVE') and not self.features_confirmed)
            x,y=col*170+3,row*32+3
            canvas[y:y+27,x:x+164]=(75,65,45) if selected else (32,30,28) if locked else (48,40,33)
            label=('ANALYZE' if self.mode=='RAYS' else 'CONFIRM') if name=='ANALYZE' else name
            text(canvas,x+9,y+6,label,color=(112,112,112) if locked else (235,240,245))
        text(canvas,8,73,(self.status.replace('_',' ')+' CASES '+str(len(self.cases)))[:100],scale=2)
        if self.mode=='OUTLINE':
            for p in join_strokes(self.red):
                if math.hypot(p[0][0]-p[-1][0],p[0][1]-p[-1][1])>16:
                    for px,py in (p[0],p[-1]):
                        ring=[(px+6*math.cos(i*math.pi/12),py+6*math.sin(i*math.pi/12)) for i in range(25)]
                        draw(canvas,ring,(255,255,255),1)
        cx,cy=self.cursor; r=18 if self.tool=='ERASER' else 7
        ring=[(cx+r*math.cos(i*math.pi/16),cy+r*math.sin(i*math.pi/16)) for i in range(33)]
        draw(canvas,ring,(255,255,255),1)
        # 工具栏上的光标也必须可见，draw仅限制教学笔划的有效画面区域。
        x,y=int(cx),int(cy); canvas[max(0,y-2):min(HEIGHT,y+3),max(0,x-2):min(WIDTH,x+3)]=(255,255,255)
        return canvas.tobytes()

    def close(self):
        if self.mouse: self.mouse.close()
