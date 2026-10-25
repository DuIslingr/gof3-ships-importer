"""A GoF3 sky (skyboxes/materials/skybox_<name>.ae4material) as the remake's 6:1 cube-face strip.

The material names its cubemap by resource id (ae4_ids); the cubemap .ae4texture holds six faces of one mip back to back
after the 0x4000 header (format 16 ETC2 RGB / 17 ETC2 RGBA8 / 1 RGBA8): the top, then the four sides round the horizon left
to right (the second of them in front), then the bottom, each upright as seen from inside (found by matching the faces'
edges: 0's bottom edge meets 2's top, 1-2-3-4 meet side by side, 5's top meets 2's bottom). STRIP puts them in the remake's
order +X, -X, +Y, -Y, +Z, -Z. The material's
Colorize tints the sky by Colorize_Color1 (a grey on most), applied here.

sky_strip.convert(material_path, out_png, assets) -> the cubemap's path (None when the material names none)."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_ids, ae4_material
from ae4unpack import unpack
import texture2ddecoder as t


STRIP = [3, 1, 0, 5, 2, 4]


def cubemap_of(material_path, assets):
    d = unpack(open(material_path, "rb").read())
    idx = ae4_ids.index(assets)
    for o in range(len(d) - 8):
        p = idx.get(int.from_bytes(d[o:o + 8], "little"))
        if p and "/cubemap_" in p.replace("\\", "/"): return p
    return None


def faces(path):
    d = unpack(open(path, "rb").read())
    fmt = struct.unpack_from("<I", d, 0x0c)[0]
    w = struct.unpack_from("<H", d, 0x1a)[0]; h = struct.unpack_from("<H", d, 0x1e)[0]
    per = {16: w * h // 2, 17: w * h, 1: w * h * 4}[fmt]
    out = []
    for f in range(6):
        raw = d[0x4000 + f * per:0x4000 + (f + 1) * per]
        if fmt == 1: out.append(Image.frombytes("RGBA", (w, h), raw, "raw", "RGBA"))
        else:
            px = t.decode_etc2(raw, w, h) if fmt == 16 else t.decode_etc2a8(raw, w, h)
            out.append(Image.frombytes("RGBA", (w, h), px, "raw", "BGRA"))
    return out


def convert(material_path, out_png, assets, flips=None):
    cube = cubemap_of(material_path, assets)
    if cube is None: return None
    vals, _ = ae4_material.read(material_path)
    tint = np.array(vals.get("Colorize_Color1", (1, 1, 1, 1))[:3], np.float32) if vals.get("Colorize_Enabled") else np.ones(3, np.float32)
    fs = faces(cube)
    w = fs[0].size[0]
    strip = Image.new("RGB", (w * 6, w))
    for i, src in enumerate(STRIP):
        f = fs[src].convert("RGB")
        op = (flips or {}).get(i)
        if op: f = f.transpose(op)
        strip.paste(f, (i * w, 0))
    a = np.asarray(strip).astype(np.float32) * tint
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(out_png)
    return cube


if __name__ == "__main__":
    print(convert(sys.argv[1], sys.argv[2], sys.argv[3]))
