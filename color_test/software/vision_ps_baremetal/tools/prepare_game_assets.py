"""PC-only export of fixed-size demo assets to headerless top-down BGR888.

Replace the three images together to use authored art. Pillow stays on the PC;
the board reads bytes with stdio and does no image decoding or pose rotation.
"""
import argparse
import hashlib
import json
import struct
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[4]
TYPES = ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")
POSES = (36, 72, 72, 1, 72, 36)
# Reuse the original PC game's RGB palette (its COLORS table is BGR).
COLORS = ("#fae170", "#51b8f9", "#ffa147", "#5de688", "#ff70bb", "#a59a91")


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def geometry_signature(config):
    game = config["board_game"]
    values = [game["width"], game["height"], *game["render"]["scene_rect"],
              *(v for kind in TYPES for v in config["model_sizes"][kind])]
    return fnv(struct.pack("<18f", *values))


def game_pack(directory, config_path):
    """Authored offline art, same geometry/palette as GameView; no physics here.

    Pose angle is clockwise in image coordinates, measured from +X. The center
    anchor is (56,56); SOURCE +X nose, portals solid -X / ring +X, mirror long
    edge +X. Art uses 5-degree steps; only the C solver owns exact geometry.
    """
    config = json.loads(config_path.read_text(encoding="utf-8"))
    game = config["board_game"]
    box = game["render"]["scene_rect"]
    scale = min((box[2]-1)/game["width"], (box[3]-1)/game["height"])
    if max(max(config["model_sizes"][k])*scale for k in TYPES) > 100:
        raise ValueError("configured models exceed 112px pose tiles; revise exporter contract")
    bg = Image.new("RGB", (1280, 800), "#101d2c")
    d = ImageDraw.Draw(bg)
    # Quiet cartoon laboratory: all decoration stays outside the playable plane.
    d.rounded_rectangle((32, 3, 1248, 790), 26, fill="#142538", outline="#314b61", width=2)
    d.rounded_rectangle((978, 188, 1220, 613), 20, fill="#1c3044", outline="#36546c", width=2)
    x, y, w, h = box
    ox = (w-1-game["width"]*scale)/2
    oy = (h-1-game["height"]*scale)/2
    bounds = (round(x+ox), round(y+oy), round(x+ox+game["width"]*scale), round(y+oy+game["height"]*scale))
    d.rectangle((x, y, x+w-1, y+h-1), fill="#142538")
    d.rectangle(bounds, fill="#505965", outline="#f0f0e9", width=3)
    for i in range(1, 20):
        xx = round(bounds[0]+(bounds[2]-bounds[0])*i/20)
        yy = round(bounds[1]+(bounds[3]-bounds[1])*i/20)
        d.line((xx, bounds[1]+3, xx, bounds[3]-3), fill="#56616b")
        d.line((bounds[0]+3, yy, bounds[2]-3, yy), fill="#56616b")
    for xx in (52, 1228):
        for yy in (26, 768):
            d.ellipse((xx-5, yy-5, xx+5, yy+5), fill="#496176", outline="#8ca6b6", width=2)
    entries = [(6, 0, bg, 0, 0)]
    for kind, name in enumerate(TYPES):
        length, width = (v*scale for v in config["model_sizes"][name])
        for pose in range(POSES[kind]):
            # Draw supersampled, rotate offline only, then select a binary mask.
            q, cx, cy = 4, 224, 224
            tile = Image.new("RGBA", (448, 448))
            p = ImageDraw.Draw(tile)
            l, b = length*q/2, width*q/2
            color = COLORS[kind]
            rect = (cx-l, cy-b, cx+l, cy+b)
            if name == "TARGET":
                p.ellipse(rect, fill="#245f46", outline=color, width=9)
                p.ellipse((cx-l*.68, cy-b*.68, cx+l*.68, cy+b*.68), fill=color, outline="#edfff3", width=6)
                p.ellipse((cx-l*.29, cy-b*.29, cx+l*.29, cy+b*.29), fill="#245f46")
            elif name == "SOURCE":
                # Same triangle centroid/tip as Model.vertices and C session.
                p.polygon(((cx+l*4/3, cy), (cx-l*2/3, cy+b), (cx-l*2/3, cy-b)),
                          fill="#843d74", outline=color, width=6)
                p.line((cx-l*.45, cy, cx+l*1.15, cy), fill="#fff4d9", width=7)
            elif name == "MIRROR":
                p.rounded_rectangle((cx-l, cy-b-5, cx+l, cy+b+5), radius=8, fill="#725b38", outline=color, width=5)
                p.line((cx-l, cy, cx+l, cy), fill="#fcffff", width=7)
                for f in (-.6, -.1, .4):
                    p.line((cx+l*f, cy-b, cx+l*f+8, cy+b), fill="#c3f6fc", width=3)
            elif name.startswith("PORTAL"):
                p.rounded_rectangle(rect, radius=12, fill="#244958" if kind == 1 else "#664931", outline=color, width=7)
                p.rounded_rectangle((cx-l*.8, cy-b*.65, cx+l*.8, cy+b*.65), radius=9, outline=color, width=4)
                p.ellipse((cx-l*.85, cy-8, cx-l*.85+16, cy+8), fill=color)
                p.ellipse((cx+l*.65, cy-11, cx+l*.65+22, cy+11), outline="#ffffff", width=5)
                p.line((cx-l*.45, cy, cx+l*.35, cy), fill=color, width=4)
            else:
                p.rounded_rectangle(rect, radius=6, fill="#625f62", outline=color, width=7)
                for f in (-.6, -.2, .2, .6):
                    p.line((cx+l*f, cy-b+5, cx+l*f-14, cy+b-5), fill="#c8c3bd", width=4)
            tile = tile.rotate(-pose*5, resample=Image.Resampling.BICUBIC, center=(cx, cy))
            tile = tile.resize((112, 112), Image.Resampling.LANCZOS)
            entries.append((kind, pose, sprite_rgb(tile), 56, 56))
    payload = bytearray()
    metadata = []
    for kind, pose, image, ax, ay in entries:
        data = image.tobytes("raw", "BGR")
        payload += struct.pack("<8I", kind, pose, image.width, image.height, ax, ay, len(data), 0)
        payload += data
        metadata.append(dict(type="BACKGROUND" if kind == 6 else TYPES[kind], angle_deg=pose*5,
                             width=image.width, height=image.height, anchor=[ax, ay], bytes=len(data)))
    directory.mkdir(parents=True, exist_ok=True)
    header = b"RAYART1\0" + struct.pack("<4I", len(payload), fnv(payload), len(entries), geometry_signature(config))
    pack = header + payload
    (directory/"game_assets.bin").write_bytes(pack)
    bg.save(directory/"background.png")
    # Contact sheet is for review, never decoded at runtime.
    sheet = Image.new("RGB", (112*8, 136*6), "#505965")
    sd = ImageDraw.Draw(sheet)
    for kind, name in enumerate(TYPES):
        sd.text((4, kind*136+2), name, fill=COLORS[kind])
        poses = [e for e in entries if e[0] == kind]
        for i in range(8):
            image = poses[(i*9) % len(poses)][2]
            rgba = image.convert("RGBA")
            import numpy as np
            pixels = np.asarray(image)
            mask = Image.fromarray((np.any(pixels != [255, 0, 255], axis=2)*255).astype("uint8"))
            sheet.paste(rgba, (i*112, kind*136+24), mask)
    sheet.save(directory/"models.png")
    manifest = dict(schema="ray-art-v1", format="top-down packed BGR888", key_rgb="FF00FF",
                    pose_step_degrees=5, pose_counts=list(POSES), geometry_signature=geometry_signature(config),
                    pack_bytes=len(pack), resident_asset_bytes=len(payload), cpu_canvas_bytes=1280*800*3,
                    sha256=hashlib.sha256(pack).hexdigest(), entries=metadata,
                    provenance="Original procedural art, reused pc_vision/game_view.py palette and canonical geometry; no external artwork",
                    coordinates="uncalibrated_preview; image 1280x720, logical 1279x719, uniform letterbox to scene_rect; no A3 calibration")
    (directory/"assets.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(f"Prepared game pack: {len(entries)} images, {len(pack)} bytes, loaded once; {directory}")


def export_sd_bundle(directory, source, config_path):
    """Export the already qualified art without changing pixels or geometry."""
    from check_game_assets import inspect_pack, check_bundle
    import numpy as np

    pack_path = source / "game_assets.bin"
    data, summary, entries = inspect_pack(pack_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    metadata = json.loads((source / "assets.json").read_text(encoding="utf-8"))
    if summary["sha256"] != metadata["sha256"] or summary["geometry_signature"] != geometry_signature(config):
        raise ValueError("existing pack does not match its metadata/current canonical geometry")
    archive = directory.parent / (directory.name + ".zip")
    if directory.exists() or archive.exists():
        raise ValueError("refusing to overwrite an existing SD bundle: " + str(directory))
    directory.mkdir(parents=True)
    (directory / "game_assets.bin").write_bytes(data)
    shutil.copyfile(source / "assets.json", directory / "assets.json")
    shutil.copyfile(Path(__file__).with_name("check_game_assets.py"), directory / "check_assets.py")
    preview = directory / "preview"
    preview.mkdir()
    for entry in entries:
        pixels = data[entry["offset"]:entry["offset"] + entry["bytes"]]
        image = Image.frombytes("RGB", (entry["width"], entry["height"]), pixels, "raw", "BGR")
        if entry["type"] == "BACKGROUND":
            (directory / "background.bgr").write_bytes(pixels)
            image.save(preview / "background.png")
        else:
            folder = preview / entry["type"]
            folder.mkdir(exist_ok=True)
            mask = Image.fromarray((np.any(np.asarray(image) != [255, 0, 255], axis=2) * 255).astype("uint8"))
            rgba = image.convert("RGBA")
            rgba.putalpha(mask)
            rgba.save(folder / ("%03d.png" % entry["angle_deg"]))
    shutil.copyfile(source / "models.png", preview / "models.png")
    references = {"MIRROR": "sample_photo/041.png", "PORTAL_A": "sample_photo/017.png",
                  "PORTAL_B": "sample_photo/029.png", "TARGET": "sample_photo/049.png",
                  "SOURCE": "sample_photo/005.png"}
    readme = """# SD卡素材包

这份素材与075/076/077实板绘制验证所用game_assets.bin逐字节相同；无需重新制作。
六类物体共289个姿态，另有一张1280×800静态背景。风格为已有的程序离线绘制卡通素材，
沿用参考照片的物体类别/形状语义及唯一游戏配置；不是照片抠图或照片背景。

## 复制与调用

1. 解压ZIP，将整个ray_game_assets文件夹复制到SD卡可见分区根目录。
2. 保持目录完整，不要覆盖BOOT.BIN、image.ub、boot.scr或现有系统文件。
3. 板端找到实际挂载路径；例如SD可见分区挂载为/boot时，素材为
   /boot/ray_game_assets/game_assets.bin。
4. 可用python3 /boot/ray_game_assets/check_assets.py核对文件。该命令只读文件，
   不初始化PL、摄像头、显示或DMA；不需要Pillow/OpenCV/PYNQ。
5. 现有C程序直接以此路径加载game_assets.bin，启动时一次读入DDR。
   复制完成后再核准实际SD路径并按原有显示资格/所有权流程调用；本包不自动启动HDMI。

## 内容

| 文件 | 用途 |
| --- | --- |
| game_assets.bin | 板端实际加载的完整素材包，BGR888、色键透明，RAYART1格式 |
| assets.json、sd_manifest.json | 尺寸、姿态、来源与校验清单；不是另一份游戏配置 |
| background.bgr | 同一背景的独立BGR888文件，1280×800、stride3840、3072000字节 |
| preview/background.png、preview/models.png | 背景和六类物体总览，供人工查看 |
| preview/类别/角度.png | 全部289张透明PNG预览；板端运行不逐帧读取或解码PNG |
| check_assets.py | PC/板端通用的纯文件核对程序，Python3.6及以上 |

MIRROR镜面36姿态、PORTAL_A门A72姿态、PORTAL_B门B72姿态、TARGET目标1姿态、
SOURCE光源72姿态、WALL墙36姿态；步长5度。镜面/墙180度周期，目标为圆形。
姿态量化只选图，不改变模型几何、方向或求解结果。

静态面板、灰色白边区域等已在背景中。中文按钮/文字、计时、星级、光线和光标由现有C程序
按当前状态绘制，继续保持背景→模型→光线→UI→光标顺序，不另建渲染器。
sample_photo/001至077没有WALL参考，墙素材沿用现有几何与风格；不宣称其通过实照外形验收。
最终1280×800输出、实时摄像头和完整游戏流程仍是独立验收项。
"""
    (directory / "使用说明.md").write_text(readme, encoding="utf-8")
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = dict(bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    manifest = dict(schema="existing-ray-art-sd-distribution-v1", pack_sha256=summary["sha256"],
                    geometry_signature=summary["geometry_signature"], runtime_file="game_assets.bin",
                    image_generation="reuse_existing_board_verified_art_no_pixel_change",
                    configuration_source="pc_vision/game_config.json",
                    configuration_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
                    reference_photos={kind:dict(path=name, sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest())
                                      for kind, name in references.items()},
                    wall_reference="not present in sample_photo/001..077;existing canonical art only",
                    runtime_ui="existing native C text/buttons/timer/stars/rays/cursor", files=files)
    (directory / "sd_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    checked = check_bundle(directory)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                z.write(path, arcname=directory.name + "/" + path.relative_to(directory).as_posix())
    print(json.dumps(dict(status=checked["status"], directory=str(directory), archive=str(archive),
                         archive_bytes=archive.stat().st_size, pack_sha256=summary["sha256"],
                         images=summary["images"], files_checked=checked["files_checked"]), indent=2))


def demo_images():
    background = Image.new("RGB", (1280, 800), "#e6f2eb")
    draw = ImageDraw.Draw(background)
    draw.rounded_rectangle((32, 32, 1248, 768), 28, fill="#f9fcf4", outline="#416956", width=4)
    draw.text((80, 70), "LIGHT PATH - SPRITE DEMO", fill="#244b3c", font_size=30)
    draw.rounded_rectangle((80, 150, 950, 610), 18, fill="#cbded4", outline="#628b79", width=3)
    for x in range(110, 950, 40):
        draw.line((x, 153, x, 607), fill="#bbd2c5")
    for y in range(180, 610, 40):
        draw.line((83, y, 947, y), fill="#bbd2c5")
    draw.rounded_rectangle((980, 150, 1200, 610), 18, fill="#f5e6ba")
    draw.text((1000, 185), "MIRROR", fill="#5b4a2d", font_size=26)
    draw.text((1000, 245), "POSE 0 / 90", fill="#5b4a2d", font_size=20)
    draw.text((1000, 305), "MOVE + SWITCH", fill="#5b4a2d", font_size=18)
    draw.text((80, 660), "Preview coordinates - uncalibrated", fill="#416956", font_size=24)
    draw.text((80, 710), "Assets stay in memory between updates", fill="#416956", font_size=20)
    pose = Image.new("RGBA", (128, 128))
    draw = ImageDraw.Draw(pose)
    draw.rounded_rectangle((20, 51, 111, 87), 9, fill="#487c78")
    draw.rounded_rectangle((16, 39, 107, 75), 8, fill="#376169")
    draw.rounded_rectangle((21, 43, 102, 67), 5, fill="#93dedf", outline="#f7ffff", width=3)
    draw.line((30, 49, 91, 49), fill="#f7ffff", width=3)
    return background, pose, pose.transpose(Image.Transpose.ROTATE_90)


def sprite_rgb(image):
    image = image.convert("RGBA")
    # Binary mask is chosen offline, including antialiased source art.
    mask = image.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    rgb = image.convert("RGB")
    pixels = rgb.tobytes()
    if any(a and pixels[i * 3:i * 3 + 3] == b"\xff\x00\xff" for i, a in enumerate(mask.tobytes())):
        raise ValueError("opaque magenta conflicts with the reserved transparency key")
    result = Image.new("RGB", image.size, (255, 0, 255))
    result.paste(rgb, mask=mask)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--game", action="store_true", help="Export the full six-model native game pack")
    parser.add_argument("--sd-from", type=Path, help="Export a copy-ready SD bundle from an existing game assets directory")
    parser.add_argument("--config", type=Path, default=ROOT/"pc_vision/game_config.json")
    parser.add_argument("--background", type=Path)
    parser.add_argument("--mirror-000", type=Path)
    parser.add_argument("--mirror-090", type=Path)
    args = parser.parse_args()
    if args.sd_from:
        if args.game or any((args.background, args.mirror_000, args.mirror_090)):
            parser.error("--sd-from cannot be combined with generation/image-input flags")
        export_sd_bundle(args.output, args.sd_from, args.config)
        return
    if args.game:
        game_pack(args.output, args.config)
        return
    inputs = [args.background, args.mirror_000, args.mirror_090]
    if any(inputs) and not all(inputs):
        parser.error("provide all three source images, or none for generated demo art")
    images = []
    if all(inputs):
        for path in inputs:
            with Image.open(path) as source:
                images.append(source.convert("RGBA"))
    else:
        images = list(demo_images())
    if images[0].size != (1280, 800) or any(image.size != (128, 128) for image in images[1:]):
        parser.error("background must be 1280x800; both poses must be 128x128; no implicit stretching")
    if images[0].convert("RGBA").getchannel("A").getextrema() != (255, 255):
        parser.error("background must be opaque")
    images = [images[0].convert("RGB"), *(sprite_rgb(image) for image in images[1:])]
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"format": "top-down packed BGR888", "sprite_rgb_key": "FF00FF", "files": {}}
    for name, image in zip(("background", "mirror_000", "mirror_090"), images):
        data = image.tobytes("raw", "BGR")
        (args.output / f"{name}.bgr").write_bytes(data)
        image.save(args.output / f"{name}.png")
        manifest["files"][f"{name}.bgr"] = dict(width=image.width, height=image.height,
                                                bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    (args.output / "assets.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (args.output / "demo.replay").write_text("420 300 0\n650 360 0\n650 360 90\n", encoding="ascii")
    print(f"Prepared three resident BGR888 assets in {args.output}")


if __name__ == "__main__":
    main()
