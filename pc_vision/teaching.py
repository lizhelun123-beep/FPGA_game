"""电脑教学接收与受限代码生成；复用串口所有者，不向C游戏注入场景。"""
import copy
import json
import math

from pynq_vision.teaching_protocol import TeachingParser
from pynq_vision.teaching_features import infer_rule


def pair(value, limit=4096):
    if (not isinstance(value, list) or len(value)!=2 or
            any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>limit for v in value)):
        raise ValueError('invalid teaching vector')


def validate(document):
    if (document.get('schema')!='pynq-teaching-v1' or
        document.get('coordinate_space')!='camera_px_1280x720' or document.get('transform')!='identity-v1' or
        document.get('game_valid') is not False or document.get('template_id')!='object-1'):
        raise ValueError('invalid teaching schema')
    layers=document.get('annotation_layers')
    if layers is not None and layers!=dict(outline='red',features='green',rays='yellow'):
        raise ValueError('invalid teaching annotation layers')
    stage=document.get('annotation_stage')
    if stage is not None:
        outline=document.get('outline_confirmed'); features=document.get('features_confirmed')
        if (stage not in ('OUTLINE','FEATURE','RAYS') or type(outline)is not bool or type(features)is not bool or
                (features and not outline) or (stage=='OUTLINE' and (outline or features)) or
                (stage=='FEATURE' and (not outline or features)) or (not features and document.get('cases')) or
                (stage=='RAYS' and not features) or (outline and document.get('model') is None)):
            raise ValueError('invalid teaching stage')
    session=document.get('session')
    if not isinstance(session,str) or len(session)!=16 or not 0<int(session,16)<1<<64:
        raise ValueError('invalid teaching session')
    if type(document.get('revision')) is not int or not 0<document['revision']<1<<32:
        raise ValueError('invalid teaching revision')
    if not isinstance(document.get('status'),str) or len(document['status'])>128: raise ValueError('bad teaching status')
    model=document.get('model'); cases=document.get('cases')
    if not isinstance(cases,list) or len(cases)>16: raise ValueError('bad teaching cases')
    if model is not None:
        if not isinstance(model,dict): raise ValueError('bad model')
        for key in ('center','axis','size'): pair(model.get(key))
        if not 0<=model['center'][0]<1280 or not 0<=model['center'][1]<720: raise ValueError('bad center')
        if abs(math.hypot(*model['axis'])-1)>.001 or min(model['size'])<=0: raise ValueError('bad geometry')
        outline=model.get('outline_local'); markers=model.get('markers_local',[])
        if not isinstance(outline,list) or not 3<=len(outline)<=128: raise ValueError('bad outline')
        if not isinstance(markers,list) or len(markers)>12: raise ValueError('bad markers')
        for p in outline: pair(p)
        for line in markers:
            if not isinstance(line,list) or len(line)>32: raise ValueError('bad marker stroke')
            for p in line: pair(p)
        color=model.get('color_bgr')
        if not isinstance(color,list) or len(color)!=3 or any(type(v)is not int or not 0<=v<=255 for v in color): raise ValueError('bad color')
        if model.get('semantic_type')!='UNASSIGNED': raise ValueError('teaching type cannot claim a game identity')
        stamp=document.get('reference')
        if not isinstance(stamp,dict) or any(not isinstance(stamp.get(k),str) or not stamp[k].isdigit() or not 0<int(stamp[k])<1<<64 for k in ('generation','sequence','captured_ms')): raise ValueError('bad provenance')
    elif cases: raise ValueError('cases without object')
    for case in cases:
        if not isinstance(case,dict): raise ValueError('bad ray case')
        for key in ('start','entry','exit','end','incoming','outgoing'): pair(case.get(key))
        for key in ('incoming','outgoing'):
            if abs(math.hypot(*case[key])-1)>.001: raise ValueError('bad ray direction')
    if document.get('rule') != infer_rule(cases): raise ValueError('rule does not match recorded cases')
    return document


class TeachingReceiver:
    def __init__(self):
        self.parser=TeachingParser(); self.latest=None; self.rejected=0

    def feed(self, data):
        changed=False
        for doc in self.parser.feed(data):
            try:
                validate(doc)
                if self.latest and doc['session']==self.latest['session'] and doc['revision']<=self.latest['revision']: continue
                self.latest=doc; changed=True
            except (ValueError,KeyError,TypeError,OverflowError): self.rejected+=1
        return changed

    def snapshot(self):
        return copy.deepcopy(self.latest)


def object_source(document):
    model=document.get('model')
    if model is None: raise ValueError('no analyzed object')
    return ('# 教学物块模板：像素坐标，未指定游戏类别，不自动参与碰撞或计分。\n'
            'VIRTUAL_OBJECT = '+repr(model)+'\n')


def rule_source(document):
    rule=document['rule']
    return '''# 示教样本的局部二维候选规律；静态导出，不自动加载到权威C游戏。
import math
RULE = %s

def propagate(entry, incoming):
    if not RULE.get('accepted'):
        raise ValueError('需要更多一致且不同方向的示例')
    if len(entry)!=2 or len(incoming)!=2 or not all(math.isfinite(v) for v in (*entry,*incoming)):
        raise ValueError('nonfinite or invalid point/direction')
    x, y = incoming
    length = math.hypot(x, y)
    if length <= 1e-8: raise ValueError('zero direction')
    x, y = x / length, y / length
    kind = RULE['kind']
    if kind == 'REFLECT':
        a = 2 * RULE['tangent_rad']; c, s = math.cos(a), math.sin(a)
        outgoing = (c*x+s*y, s*x-c*y)
    elif kind == 'ROTATE':
        a = RULE['rotation_rad']; c, s = math.cos(a), math.sin(a)
        outgoing = (c*x-s*y, s*x+c*y)
    elif kind == 'FIXED_DIRECTION': outgoing = tuple(RULE['fixed_direction'])
    elif kind == 'PASS_THROUGH': outgoing = (x, y)
    else: raise ValueError('unknown rule')
    position = RULE['position']
    if position['kind'] == 'SAME_POINT': exit_point = tuple(entry)
    elif position['kind'] == 'FIXED_LOCAL': exit_point = tuple(position['value'])
    elif position['kind'] == 'OFFSET_LOCAL': exit_point = tuple(entry[i]+position['value'][i] for i in (0,1))
    else: raise ValueError('unknown exit position')
    return exit_point, outgoing
''' % repr(rule)


def c_rule_source(document):
    rule=document['rule']
    prefix='\ufeff/* 教学候选规则，物块局部像素坐标；尚未接入正式有限边界和C游戏。 */\n#include <math.h>\n'
    body='int teaching_propagate(double ex,double ey,double ix,double iy,double *ox,double *oy,double *dx,double *dy) {\n'
    if not rule.get('accepted'):
        return prefix+body+'    (void)ex; (void)ey; (void)ix; (void)iy; (void)ox; (void)oy; (void)dx; (void)dy;\n    return -1; /* UNKNOWN：禁止猜测 */\n}\n'
    body+='    double n=hypot(ix,iy);\n    if (!ox||!oy||!dx||!dy||!isfinite(ex)||!isfinite(ey)||!isfinite(n)||n<1e-8) return -1;\n    ix/=n; iy/=n;\n'
    kind=rule['kind']
    if kind in ('REFLECT','ROTATE'):
        angle=2*rule['tangent_rad'] if kind=='REFLECT' else rule['rotation_rad']
        c,s=math.cos(angle),math.sin(angle)
        body+='    *dx=%.12g*ix%+.12g*iy; *dy=%.12g*ix%+.12g*iy;\n' % (c,s if kind=='REFLECT' else -s,s,-c if kind=='REFLECT' else c)
    elif kind=='FIXED_DIRECTION': body+='    *dx=%.12g; *dy=%.12g;\n' % tuple(rule['fixed_direction'])
    else: body+='    *dx=ix; *dy=iy;\n'
    pos=rule['position']
    if pos['kind']=='SAME_POINT': body+='    *ox=ex; *oy=ey;\n'
    elif pos['kind']=='FIXED_LOCAL': body+='    *ox=%.12g; *oy=%.12g;\n' % tuple(pos['value'])
    else: body+='    *ox=ex%+.12g; *oy=ey%+.12g;\n' % tuple(pos['value'])
    return prefix+body+'    return 0;\n}\n'


def exports(document):
    validate(document)
    result={'teaching.json':json.dumps(document,ensure_ascii=False,allow_nan=False,indent=2),
            'ray_rule.py':rule_source(document),'ray_rule.c':c_rule_source(document)}
    if document.get('model') is not None: result['object_template.py']=object_source(document)
    return result
