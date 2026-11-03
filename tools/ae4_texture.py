"""Decode a GoF3 .ae4texture (ET4A) to PNG: the top mip at 0x4000, the format id at 0x0c.
  12 PVRTC 4bpp (the iOS files in assets/)       16 ETC2 RGB  (Switch romfs, 4bpp)
  17 ETC2 RGBA8 (Switch romfs, 8bpp)             1  RGBA8 uncompressed
Other ids (9 / 10 / 11, a few old iOS files) are still read as PVRTC 4bpp, as before.
Takes the old zstd-packed files and the romfs's decompressed ones alike.
Needs texture2ddecoder + Pillow (a venv). Usage: ae4_texture.py in.ae4texture out.png"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ae4unpack import MAGIC, unpack
import texture2ddecoder as t
from PIL import Image

def dimensions(path):
    """Read the dimensions without decoding pixels; legacy-packed files still get unpacked."""
    with open(path, "rb") as f:
        header = f.read(32)
        if header[:4] == MAGIC:
            header = unpack(header + f.read())
    assert header[:4] == b"ET4A", header[:4]
    return struct.unpack_from("<H", header, 0x1a)[0], struct.unpack_from("<H", header, 0x1e)[0]


def resized(im, size, resample=Image.BICUBIC):
    """im scaled to size with its alpha kept apart. Pillow resizes RGBA / LA premultiplied, so a colour under alpha 0 came out
    black: GoF3's alpha is often a mask (emission, gloss, specular), not opacity (2026-11-02: the hangar's tech panels, its
    alpha the emissive mask, baked black but for their lamps)."""
    size = tuple(size)
    if im.size == size: return im
    if im.mode not in ("RGBA", "LA"): return im.resize(size, resample)
    return Image.merge(im.mode, [b.resize(size, resample) for b in im.split()])


def decode(path):
    d = unpack(open(path, "rb").read())
    assert d[:4] == b"ET4A", d[:4]
    fmt = struct.unpack_from("<I", d, 0x0c)[0]
    w = struct.unpack_from("<H", d, 0x1a)[0]
    h = struct.unpack_from("<H", d, 0x1e)[0]
    bw, bh = (w + 3) // 4 * 4, (h + 3) // 4 * 4
    top = d[0x4000:]
    if fmt == 1:
        return Image.frombytes("RGBA", (w, h), top[:w * h * 4], "raw", "RGBA")
    if fmt == 16:
        px = t.decode_etc2(top[:bw * bh // 2], w, h)
    elif fmt == 17:
        px = t.decode_etc2a8(top[:bw * bh], w, h)
    else:
        px = t.decode_pvrtc(top[:max(w, 8) * max(h, 8) // 2], w, h, False)
    return Image.frombytes("RGBA", (w, h), px, "raw", "BGRA")

if __name__ == "__main__":
    decode(sys.argv[1]).save(sys.argv[2])
