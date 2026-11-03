"""板端示教分析：轮廓/原图颜色、物体局部坐标和有界规则拟合。

这是确定性的轻量统计学习，没有安装大模型或声称训练神经网络。
numpy 在明确进入教学分析时导入；模块导入本身不访问硬件。
"""
import math


def local(point, model):
    x, y = point[0]-model['center'][0], point[1]-model['center'][1]
    ax, ay = model['axis']
    return [round(x*ax+y*ay, 3), round(-x*ay+y*ax, 3)]


def unit(v):
    length = math.hypot(*v)
    if length < 1e-8: raise ValueError('ZERO_DIRECTION')
    return [v[0]/length, v[1]/length]


def polygon_model(points, frame):
    import numpy as np
    if len(points)>4096: raise ValueError('OUTLINE_POINT_LIMIT_REDRAW')
    if len(points) < 4 or math.hypot(points[-1][0]-points[0][0], points[-1][1]-points[0][1]) > 16:
        raise ValueError('CLOSE_OUTLINE_WITHIN_16PX')
    p = np.asarray(points[:-1], dtype=float)
    # 去掉密集相邻点，不把停留时间当作形状的权重。
    keep = [0]
    for i in range(1, len(p)):
        if np.linalg.norm(p[i]-p[keep[-1]]) >= 3: keep.append(i)
    p = p[keep]
    if len(p) < 3: raise ValueError('OUTLINE_TOO_SMALL')
    if len(p)>128:
        p=p[np.linspace(0,len(p)-1,128).astype(int)]
    # 自交轮廓不能代表单个可填充的物块；分析阶段有界检查。
    def cross2(a,b): return a[...,0]*b[...,1]-a[...,1]*b[...,0]
    for i in range(len(p)):
        indices = [j for j in range(i+2,len(p)) if not (i==0 and j==len(p)-1)]
        if not indices: continue
        a,b=p[i],p[(i+1)%len(p)]; c=p[indices]; d=p[(np.asarray(indices)+1)%len(p)]
        if ((cross2(b-a,c-a)*cross2(b-a,d-a)<-1e-6)&(cross2(d-c,a-c)*cross2(d-c,b-c)<-1e-6)).any():
            raise ValueError('SELF_INTERSECTING_OUTLINE')
    cross = p[:, 0]*np.roll(p[:, 1], -1)-np.roll(p[:, 0], -1)*p[:, 1]
    signed = float(cross.sum())/2
    if abs(signed) < 100: raise ValueError('OUTLINE_TOO_SMALL')
    center = ((p+np.roll(p, -1, axis=0))*cross[:, None]).sum(axis=0)/(6*signed)
    # 用内部均匀像素求主轴，避免鼠标采样密度影响方向；同一掩码用于颜色。
    x0, y0 = np.floor(p.min(axis=0)).astype(int); x1, y1 = np.ceil(p.max(axis=0)).astype(int)
    if x0 < 0 or y0 < 0 or x1 >= 1280 or y1 >= 720: raise ValueError('OUTLINE_OUTSIDE_IMAGE')
    yy, xx = np.mgrid[y0:y1+1:3, x0:x1+1:3]; inside = np.zeros(xx.shape, dtype=bool)
    for a, b in zip(p, np.roll(p, -1, axis=0)):
        if abs(b[1]-a[1]) < 1e-9: continue
        inside ^= ((a[1] > yy) != (b[1] > yy)) & (xx < (b[0]-a[0])*(yy-a[1])/(b[1]-a[1])+a[0])
    pts = np.column_stack((xx[inside], yy[inside]))
    if len(pts) < 12: raise ValueError('OUTLINE_TOO_SMALL')
    values, vectors = np.linalg.eigh(np.cov(pts.T)); axis = vectors[:, -1]
    # 正方形/圆没有可靠有向轴，用图像+x作固定参考，且明确标记。
    ambiguous = values[-1] < 1.15*max(values[0], 1e-6)
    if ambiguous: axis = np.array([1., 0.])
    if axis[0] < 0: axis = -axis
    normal = np.array([-axis[1], axis[0]])
    uv = np.column_stack(((p-center).dot(axis), (p-center).dot(normal)))
    size = uv.max(axis=0)-uv.min(axis=0)
    # 原始 BGR 独立 CPU 副本，不从红线/光标画布取色。
    raw = np.frombuffer(frame.bgr, dtype=np.uint8)
    offsets = pts[:, 1].astype(int)*frame.stride + pts[:, 0].astype(int)*3
    colors = raw[offsets[:, None]+np.arange(3)]
    bgr = np.median(colors, axis=0)
    hsv = []
    import colorsys
    for color in colors[::max(1, len(colors)//512)]:
        h, s, v = colorsys.rgb_to_hsv(color[2]/255., color[1]/255., color[0]/255.)
        hsv.append([h*360., s, v])
    hsv = np.asarray(hsv)
    # 色相为环形值：保存圆均值与离散度，不能在0/360处线性平均。
    angles = np.deg2rad(hsv[:, 0]); weights = hsv[:, 1]
    hx = float((np.cos(angles)*weights).sum()); hy = float((np.sin(angles)*weights).sum())
    hue = math.degrees(math.atan2(hy, hx)) % 360
    perimeter = float(np.linalg.norm(p-np.roll(p, -1, axis=0), axis=1).sum())
    circularity = min(1., 4*math.pi*abs(signed)/(perimeter*perimeter))
    shape = 'round' if circularity > .88 and max(size)/max(1., min(size)) < 1.3 else 'polygon'
    # 轮廓最多128点，保留形状而不是把包围盒当作碰撞边界。
    step = max(1, int(math.ceil(len(uv)/128.)))
    return dict(center=np.round(center, 3).tolist(), axis=np.round(axis, 6).tolist(),
        size=np.round(size, 3).tolist(), outline_local=np.round(uv[::step], 3).tolist(),
        shape=shape, axis_ambiguous=bool(ambiguous), area_px2=round(abs(signed), 2),
        color_bgr=np.round(bgr).astype(int).tolist(),
        color_hsv=dict(hue_deg=round(hue, 2), saturation=round(float(np.median(hsv[:, 1])), 3),
                       value=round(float(np.median(hsv[:, 2])), 3)),
        confidence=None, confidence_kind='NOT_CALIBRATED', semantic_type='UNASSIGNED', coordinate_space='camera_px_1280x720')


def ray_case(incoming, outgoing, model):
    def line(points):
        if len(points) < 2: raise ValueError('DRAW_IN_AND_OUT')
        a, b = local(points[0], model), local(points[-1], model)
        d = unit([b[0]-a[0], b[1]-a[1]])
        length = math.hypot(b[0]-a[0], b[1]-a[1])
        if length < 24: raise ValueError('RAY_TOO_SHORT')
        residual = max(abs((local(p, model)[0]-a[0])*d[1]-(local(p, model)[1]-a[1])*d[0]) for p in points)
        if residual > max(4., length*.06): raise ValueError('DRAW_STRAIGHT_RAYS')
        return a, b, d
    start, entry, u = line(incoming); exit_, end, w = line(outgoing)
    # 每组都明确方向：IN从远处画向物块，OUT从物块画向远处。
    half = [v/2+20 for v in model['size']]
    for point in (entry, exit_):
        if abs(point[0]) > half[0] or abs(point[1]) > half[1]:
            raise ValueError('RAY_ENDPOINT_NOT_ON_OBJECT')
    return dict(start=start, entry=entry, exit=exit_, end=end,
                incoming=[round(v, 6) for v in u], outgoing=[round(v, 6) for v in w])


def _angle(v): return math.atan2(v[1], v[0])
def _diff(a, b): return abs(math.atan2(math.sin(a-b), math.cos(a-b)))
def _mean(angles): return math.atan2(sum(math.sin(v) for v in angles), sum(math.cos(v) for v in angles))


def infer_rule(cases):
    """至少三种相隔20度方向；比较有限假设，不能拟合则拒绝泛化。"""
    unknown = dict(kind='UNKNOWN', accepted=False, samples=len(cases), reason='NEED_THREE_DIRECTIONS')
    angles = [_angle(c['incoming']) for c in cases]
    diverse = []
    for a in angles:
        if all(_diff(a, b) >= math.radians(20) for b in diverse): diverse.append(a)
    if len(diverse) < 3: return unknown
    outgoing = [_angle(c['outgoing']) for c in cases]
    delta = _mean([b-a for a, b in zip(angles, outgoing)])
    tangent = _mean([a+b for a, b in zip(angles, outgoing)])/2
    fixed = _mean(outgoing)
    candidates = [('ROTATE', max(_diff(a+delta, b) for a, b in zip(angles, outgoing))),
                  ('REFLECT', max(_diff(2*tangent-a, b) for a, b in zip(angles, outgoing))),
                  ('FIXED_DIRECTION', max(_diff(fixed, b) for b in outgoing))]
    candidates.sort(key=lambda x:x[1]); kind, error = candidates[0]
    if error > math.radians(5) or candidates[1][1]-error < math.radians(2):
        unknown['reason'] = 'INCONSISTENT_OR_AMBIGUOUS'; return unknown
    if kind == 'ROTATE' and abs(delta) < math.radians(5): kind = 'PASS_THROUGH'; delta = 0.
    gaps = [[c['exit'][i]-c['entry'][i] for i in (0, 1)] for c in cases]
    mean_exit = [sum(c['exit'][i] for c in cases)/len(cases) for i in (0, 1)]
    mean_gap = [sum(g[i] for g in gaps)/len(gaps) for i in (0, 1)]
    if max(math.hypot(*g) for g in gaps) <= 16:
        position = dict(kind='SAME_POINT')
    elif max(math.hypot(c['exit'][0]-mean_exit[0], c['exit'][1]-mean_exit[1]) for c in cases) <= 10:
        position = dict(kind='FIXED_LOCAL', value=[round(v, 3) for v in mean_exit])
    elif max(math.hypot(g[0]-mean_gap[0], g[1]-mean_gap[1]) for g in gaps) <= 10:
        position = dict(kind='OFFSET_LOCAL', value=[round(v, 3) for v in mean_gap])
    else:
        unknown['reason'] = 'EXIT_POSITION_UNKNOWN'; return unknown
    return dict(kind=kind, accepted=True, samples=len(cases), direction_count=len(diverse),
                max_error_deg=round(math.degrees(error), 3), confidence=round(1-error/math.radians(10), 3),
                confidence_kind='FIT_RESIDUAL_ONLY',
                rotation_rad=round(delta, 8), tangent_rad=round(tangent, 8),
                fixed_direction=[round(math.cos(fixed), 8), round(math.sin(fixed), 8)], position=position,
                scope='LOCAL_2D_TEMPLATE_ONLY')
