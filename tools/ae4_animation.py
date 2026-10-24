"""Read a GoF3 .ae4animation (NA4A): the clip's name, then per animated node "<clip>@<node>" (twice) and a u16 channel
count, then each channel as [count u32][count x (value f32, time f32 ms)][len u32][name] - the keys BEFORE their name
("rotation.x".."w", "translation.x".."z", "scale.x".."z", "alpha"). Returns {node: {channel: [(time_ms, value), ...]}}."""
import re, struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ae4unpack import unpack

def read(path):
    d = unpack(open(path, "rb").read())
    out, node = {}, None
    for m in re.finditer(rb"([\x01-\x7f])\x00\x00\x00", d):
        n = m.group(1)[0]; s = m.end()
        name = d[s:s + n]
        if len(name) != n or not re.fullmatch(rb"[A-Za-z0-9_@.]+", name): continue
        if b"@" in name:
            node = name.split(b"@", 1)[1].decode(); out.setdefault(node, {}); continue
        if node is None or not re.fullmatch(rb"(rotation|translation|scale)\.[xyzw]|alpha", name): continue
        end = m.start()
        for c in range(1, 4096):
            o = end - 8 * c - 4
            if o < 0: break
            if struct.unpack_from("<I", d, o)[0] == c:
                keys = [struct.unpack_from("<2f", d, o + 4 + 8 * k) for k in range(c)]
                if all(0 <= t < 1e6 for _, t in keys) and all(keys[k][1] <= keys[k + 1][1] for k in range(c - 1)):
                    out[node][name.decode()] = [(t, v) for v, t in keys]; break
    return out

def sample(keys, t):
    """The channel's value at t ms (linear, held past its ends)."""
    if not keys: return None
    if t <= keys[0][0]: return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1: return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 1)
    return keys[-1][1]

if __name__ == "__main__":
    for node, ch in read(sys.argv[1]).items():
        print(node)
        for c, keys in ch.items():
            vals = sorted({round(v, 3) for _, v in keys})
            print(f"   {c:14s} {len(keys):3d} keys  t {keys[0][0]:.0f}..{keys[-1][0]:.0f}  " + (f"const {vals[0]}" if len(vals) == 1 else f"{[(round(t),round(v,3)) for t,v in keys][:12]}"))
