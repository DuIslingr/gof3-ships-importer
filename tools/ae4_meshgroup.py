"""Read a GoF3 .ae4meshgroup (GM4A).

Layout: [GM4A][version u32][? u32][section count u32] then the sections, one per material of the model's LOD
(nivelian/208 LOD0: glass then body; terran/003 LOD0: body then glass; vossk/130: one). Each section:
  header at s (s = 0x10 for the first, then one byte past the 0x4000 page that follows the previous section's data):
    s+0x03 index bytes u32, s+0x13 index count u32, s+0x35 vertex bytes u32,
    then the attribute table: [name length u32][name][byte offset u32]... (a_position, a_normal, a_tangent,
    a_bitangent, a_texCoord0, a_vtxColor)
  16-bit indices at the next 0x4000 boundary after s, interleaved vertices at the next boundary after the indices.
read(path) returns the first section (the old behaviour); read_all(path) returns every section."""
import struct, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ae4unpack import unpack

SIZES = {"a_position": 12, "a_normal": 12, "a_tangent": 12, "a_bitangent": 12, "a_texCoord0": 8, "a_texCoord1": 8, "a_vtxColor": 4, "a_pos2dOffset": 8}  # a_vtxColor: 4 x ubyte; a_pos2dOffset: a billboard sprite corner (drone antennas)
PAGE = 0x4000

def _align(o):
    return (o + PAGE - 1) & ~(PAGE - 1)

def _section(d, s):
    ibytes = struct.unpack_from("<I", d, s + 0x03)[0]
    icount = struct.unpack_from("<I", d, s + 0x13)[0]
    vbytes = struct.unpack_from("<I", d, s + 0x35)[0]
    assert d[s] == 4 and ibytes == icount * 2, f"no section header at {s:#x}"
    istart = _align(s + 1)
    attrs = {}
    for m in re.finditer(rb"(.)\x00\x00\x00(a_[A-Za-z0-9]+)", d[s:istart], re.S):
        n = m.group(2)[:m.group(1)[0]].decode()
        attrs[n] = struct.unpack_from("<I", d, s + m.start(2) + len(n))[0]
    stride = max(o + SIZES[n] for n, o in attrs.items())
    assert vbytes % stride == 0, f"vertex bytes {vbytes} not a multiple of stride {stride}"
    vstart = _align(istart + ibytes)
    idx = list(struct.unpack_from("<%dH" % icount, d, istart))
    nv = vbytes // stride
    def col(name, k):
        o = attrs[name]
        if name == "a_vtxColor":
            return [tuple(c / 255 for c in d[vstart + i * stride + o:vstart + i * stride + o + 4]) for i in range(nv)]
        return [struct.unpack_from("<%df" % k, d, vstart + i * stride + o) for i in range(nv)]
    out = {"indices": idx, "count": nv}
    for n in attrs:
        out[n] = col(n, SIZES[n] // 4)
    return out, vstart + vbytes

def read_all(path):
    d = unpack(open(path, "rb").read())
    assert d[:4] == b"GM4A", d[:4]
    count = struct.unpack_from("<I", d, 0x0c)[0]
    sections, s = [], 0x10
    for i in range(count):
        sec, end = _section(d, s)
        sections.append(sec)
        s = _align(end) + 1
    return sections

def read(path):
    return read_all(path)[0]
