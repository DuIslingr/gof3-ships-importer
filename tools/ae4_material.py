"""Read a GoF3 .ae4material (AM4A) parameter block: table of [len u32][name][offset u32][0 u32][type u8]
(type 1 bool, 4 u32, 7 i32, 8 float, 11 vec4), the values right after the table; texture slots T1..T4/Cube at the end."""
import struct, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ae4unpack import unpack

def read(path):
    d = unpack(open(path, "rb").read())
    params, end = [], 0
    for m in re.finditer(rb"([\x03-\x40])\x00\x00\x00([A-Z][A-Za-z0-9_]+)", d):
        n = m.group(2)[:m.group(1)[0]]
        if len(n) != m.group(1)[0]:
            continue
        e = m.start(2) + len(n)
        off, z = struct.unpack_from("<II", d, e)
        if z == 0 and off < 0x1000 and d[e + 8] in (1, 4, 7, 8, 11):
            params.append((n.decode(), off, d[e + 8])); end = e + 9
    base = end
    vals = {}
    for n, off, t in params:
        o = base + off
        vals[n] = {1: lambda: bool(d[o]), 4: lambda: struct.unpack_from("<I", d, o)[0], 7: lambda: struct.unpack_from("<i", d, o)[0],
                   8: lambda: struct.unpack_from("<f", d, o)[0], 11: lambda: struct.unpack_from("<4f", d, o)}[t]()
    slots = {}
    for m in re.finditer(rb"TextureSlots_(T\d|Cube)", d):
        slots[m.group(1).decode()] = d[m.end():m.end() + 8].hex()
    return vals, slots

if __name__ == "__main__":
    v, s = read(sys.argv[1])
    for k in sorted(v): print(k, v[k])
    print(s)
