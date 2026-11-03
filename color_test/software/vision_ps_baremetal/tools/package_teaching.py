"""离线打包教学源码/运行依赖；不访问设备或安装依赖。"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[4]


def package(output, name, files):
    archive=output/name
    manifest={p:hashlib.sha256(data).hexdigest() for p,data in files.items()}
    files=dict(files)
    files['TEACHING_FILES.json']=(json.dumps(manifest,indent=2)+'\n').encode('utf-8')
    with zipfile.ZipFile(str(archive),'w',zipfile.ZIP_DEFLATED) as z:
        for path,data in sorted(files.items()): z.writestr(path,data)
    with zipfile.ZipFile(str(archive)) as z:
        assert z.testzip() is None
        with tempfile.TemporaryDirectory(prefix='teaching_verify_') as temp:
            # 短路径逐文件恢复，兼容Windows路径长度限制。
            for i,(path,data) in enumerate(files.items()):
                restored=Path(temp)/str(i); restored.write_bytes(z.read(path))
                assert restored.read_bytes()==data
    return dict(archive=name,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                files=len(files),crc='PASS',restore='PASS')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    board={}
    names=['__init__.py','constants.py','registers.py','vdma.py','live_capture.py','ov5640.py',
           'beam_runtime.py','beam_admission.py','beam_memory.py','beam_hardware.py','beam_launcher.py',
           'teaching_mouse.py','teaching_mode.py','teaching_features.py','teaching_protocol.py',
           'TEACHING_MODE.md','notebooks/beam_v14_pynq.ipynb','notebooks/beam_teaching_pynq.ipynb']
    for name in names: board['pynq_vision/'+name]=(ROOT/'pynq_vision'/name).read_bytes()
    for name in ('hardware.json','system_wrapper.bit','system_wrapper.hwh','libbeam_pynq.so'):
        p=ROOT/'output/build/game_app/pynq_beam_hardware_5'/name
        board[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    p=ROOT/'color_test/software/vision_ps_baremetal/PYNQ_BEAM.md'; board[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    # 复核输入制品，拒绝把不匹配的ARM库/BIT当作教学运行包。
    import sys
    sys.path.insert(0,str(ROOT))
    from pynq_vision.beam_admission import inspect_bundle
    bundle=ROOT/'output/build/game_app/pynq_beam_hardware_5'
    inspect_bundle(bundle/'hardware.json',bundle/'system_wrapper.bit',bundle/'libbeam_pynq.so')
    source=dict(board)
    for folder in ('pynq_vision/tests','color_test/software/vision_ps_baremetal/src',
                   'color_test/software/vision_ps_baremetal/tools','color_test/software/vision_ps_baremetal/tests'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and p.suffix in ('.py','.c','.h','.tcl','.bat','.md'):
                source[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    for folder in ('pc_vision','pc_vision(1)/pc_vision'):
        for p in (ROOT/folder).iterdir():
            if p.is_file() and p.suffix in ('.py','.c','.json','.ps1','.txt','.md'):
                source[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    web=ROOT/'pc_vision(1)/pc_vision/web'
    for p in web.iterdir():
        if p.is_file(): source[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    # 复用工程中已有Three.js依赖，不联网安装、不纳入缓存。
    for p in (web/'node_modules/three').rglob('*'):
        if p.is_file(): source[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    units=0
    for name,data in board.items():
        if name.endswith('.py'):
            ast.parse(data.decode('utf-8-sig'),feature_version=(3,6));units+=1
        elif name.endswith('.ipynb'):
            for cell in json.loads(data)['cells']:
                if cell['cell_type']=='code':
                    assert cell['execution_count'] is None and cell['outputs']==[]
                    ast.parse(''.join(cell['source']),feature_version=(3,6));units+=1
    receipts=[package(args.output,'pynq_teaching_runtime.zip',board),
              package(args.output,'pynq_teaching_source_project.zip',source)]
    result=dict(packages=receipts,python36_grammar_units=units,hardware_execution='NOT_RUN',hardware_operations=0)
    (args.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__': main()
