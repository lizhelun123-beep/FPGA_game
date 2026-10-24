"""Offline audit of the saved physical EDID for this HDMI experiment.

This bounded reader expands only the VICs present in the saved EDID using the
Linux v6.12 DRM CTA table; unfamiliar timing declarations fail for review.
It never imports PYNQ or accesses devices, clocks, display settings or Vivado.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/drm_edid.c#L726"
# VIC: clock kHz, H active/start/end/total, V active/start/end/total,
# interlace, pixel repetition, H/V positive, picture aspect.
CTA = {
    1: (25175, 640, 656, 752, 800, 480, 490, 492, 525, False, 1, False, False, "4:3"),
    2: (27000, 720, 736, 798, 858, 480, 489, 495, 525, False, 1, False, False, "4:3"),
    3: (27000, 720, 736, 798, 858, 480, 489, 495, 525, False, 1, False, False, "16:9"),
    4: (74250, 1280, 1390, 1430, 1650, 720, 725, 730, 750, False, 1, True, True, "16:9"),
    5: (74250, 1920, 2008, 2052, 2200, 1080, 1084, 1094, 1125, True, 1, True, True, "16:9"),
    7: (13500, 720, 739, 801, 858, 480, 488, 494, 525, True, 2, False, False, "16:9"),
    16: (148500, 1920, 2008, 2052, 2200, 1080, 1084, 1089, 1125, False, 1, True, True, "16:9"),
    22: (13500, 720, 732, 795, 864, 576, 580, 586, 625, True, 2, False, False, "16:9"),
}


def mode(clock, h, v, interlace, hp, vp, **extra):
    assert all(x > 0 for x in h + v)
    assert h[0] < h[1] < h[2] < h[3] and v[0] < v[1] < v[2] < v[3]
    return dict(pixel_hz=clock, h_active_front_sync_back_total=[h[0], h[1]-h[0], h[2]-h[1], h[3]-h[2], h[3]],
                v_active_front_sync_back_total=[v[0], v[1]-v[0], v[2]-v[1], v[3]-v[2], v[3]],
                interlaced=interlace, frame_hz=clock/(h[3]*v[3]),
                field_hz=clock/(h[3]*v[3])*(2 if interlace else 1),
                h_positive=hp, v_positive=vp, **extra)


def dtd(data, offset, native=False):
    b = data[offset:offset+18]
    if b[:2] == b"\0\0":
        return None
    clock = int.from_bytes(b[:2], "little")*10000
    ha, hb = b[2]+((b[4] >> 4) << 8), b[3]+((b[4] & 15) << 8)
    va, vb = b[5]+((b[7] >> 4) << 8), b[6]+((b[7] & 15) << 8)
    hf, hs = b[8]+((b[11] >> 6) << 8), b[9]+(((b[11] >> 4) & 3) << 8)
    vf, vs = (b[10] >> 4)+(((b[11] >> 2) & 3) << 4), (b[10] & 15)+((b[11] & 3) << 4)
    separate = b[17] & 0x18 == 0x18
    return mode(clock, [ha, ha+hf, ha+hf+hs, ha+hb], [va, va+vf, va+vf+vs, va+vb],
                bool(b[17] & 128), bool(b[17] & 2) if separate else None,
                bool(b[17] & 4) if separate else None, origin="DTD", byte_offset=offset,
                native=native, sync_flags=hex(b[17]), digital_separate_sync=separate)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT/"output/build/game_app/hdmi_compat_20261019")
    args = p.parse_args()
    q = json.loads((ROOT/"output/build/game_app/game_linux_display_qualification.json").read_text(encoding="utf-8"))
    stored = q["pc_display_observation"]["edid"]
    b = bytes.fromhex(stored["raw_hex"])
    assert len(b) == 128*(1+b[126]) and b[:8] == bytes.fromhex("00ffffffffffff00")
    assert hashlib.sha256(b).hexdigest() == stored["sha256"]
    assert all(sum(b[n:n+128]) % 256 == 0 for n in range(0, len(b), 128))
    # All established/standard fields are unused in this particular EDID.
    assert b[35:38] == b"\0\0\0" and b[38:54] == b"\x01\x01"*8
    modes = [m for off in range(54, 126, 18) for m in [dtd(b, off)] if m]
    blocks = []
    for base in range(128, len(b), 128):
        assert b[base] == 2 and b[base+1] == 3
        end, pos = base+b[base+2], base+4
        while pos < end:
            tag, size = b[pos] >> 5, b[pos] & 31
            assert pos+1+size <= end
            data = b[pos+1:pos+1+size]
            blocks.append(dict(offset=pos, tag=tag, hex=data.hex()))
            if tag == 2:
                for svd in data:
                    vic = svd & 127
                    assert vic in CTA, "Unreviewed advertised VIC " + str(vic)
                    t = CTA[vic]
                    modes.append(mode(t[0]*1000, list(t[1:5]), list(t[5:9]), t[9], t[11], t[12],
                                      origin="CTA SVD", vic=vic, native=bool(svd & 128),
                                      repetition=t[10], aspect=t[13], timing_source=SOURCE))
            elif tag == 3:
                # Saved HDMI VSDB has physical address only; no HDMI-VIC list.
                assert data == bytes.fromhex("030c001000")
            else:
                assert tag in (1, 4), "Unreviewed CTA timing-capable data block"
            pos += size+1
        count = 0
        for off in range(end, base+127-17, 18):
            m = dtd(b, off, native=count < (b[base+3] & 15))
            if m:
                modes.append(m)
                count += 1
    assert len(modes) == 10  # two copies of the native timing, eight SVDs
    native = next(m for m in modes if m["origin"] == "DTD" and m["digital_separate_sync"])
    assert native["h_active_front_sync_back_total"] == [1280,110,40,220,1650]
    assert native["v_active_front_sync_back_total"] == [800,5,5,20,830]
    assert any(m.get("vic") == 4 for m in modes)
    selected = dict(native, pixel_hz=82000000, frame_hz=82000000/(1650*830),
                    field_hz=82000000/(1650*830), role="first physical compatibility test",
                    validated_on_board=False, clock_reference_hz=100000000,
                    multiplier=41, divider=5, serial_output_divider=2,
                    serial_hz=410000000, vco_hz=820000000,
                    signed_error_percent=(82000000/82170000-1)*100)
    result = dict(edid_sha256=stored["sha256"], source="saved physical-display EDID; no fresh DDC read",
                  established_modes=[], standard_modes=[], data_blocks=blocks, modes=modes,
                  selected=selected, fallback_vic=4, controller_model_required=False,
                  compatibility="PENDING_PHYSICAL_TEST", linux_binding_qualified=False,
                  interlace_note="V coordinates are full-frame DRM modelines; alternate fields require half-line timing. Repetition=2 doubles HDMI sample clock/horizontal counts.")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"edid_modes.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print("PASS physical EDID checksum/hash, all10 timing declarations, VIC4 support and 82MHz arithmetic; no hardware acceptance")


if __name__ == "__main__":
    main()
