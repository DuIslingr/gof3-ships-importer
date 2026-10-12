"""Read the colour presets (Colorize_Color1 / Color2 pairs) from GoF3's data.pdb (protobuf; game.tin / patch_1_0_2.tin).
A preset record: [GUID string][name string] then field 0x... e2 a4 bb 10 (colour 1) and ea a4 bb 10 (colour 2), each a
message of varints 08 r / 10 g / 18 b / 20 a (0..255). Checked: Dragon_Ship = (255, 0, 0) / (35, 36, 40), the same as
materials/ship_terran_020_matid01_body_dragon's Colorize_Color1 / 2 (1, 0, 0) / (0.14, 0.14, 0.16).
Skins that exist only here (no .ae4material), like GoldGorgon (the Golden Gorgon, terran/008), are built from these.

python ae4_pdb_colors.py <data.pdb> [name]   -> every preset (or one) as name: (r, g, b) / (r, g, b) in 0..1"""
import re, sys

C1, C2 = b"\xe2\xa4\xbb\x10", b"\xea\xa4\xbb\x10"
EM = b"\xd2\xd0\xee\x0c"   # an Emissive_* preset: one colour (Emissive_Anila_MkktBkkt = (255, 115, 0))


def varint(d, o):
    v = s = 0
    while True:
        b = d[o]; o += 1
        v |= (b & 0x7f) << s; s += 7
        if b < 0x80: return v, o


def colour(d, o):
    """The message after a colour tag at o: (r, g, b, a) 0..255 (a missing field = 0), and the end offset."""
    n, o = varint(d, o)
    end, c = o + n, {1: 0, 2: 0, 3: 0, 4: 0}
    while o < end:
        k, o = varint(d, o)
        c[k >> 3], o = varint(d, o)
    return (c[1], c[2], c[3], c[4]), end


def presets(path):
    d = open(path, "rb").read()
    out = {}
    for m in re.finditer(rb'"([\x01-\x7f])', d):   # field 4 (name) = 0x22, length, text
        n = m.group(1)[0]
        name = d[m.end():m.end() + n]
        if not re.fullmatch(rb"[A-Za-z0-9_' ]{3,80}", name): continue
        o = m.end() + n
        if d[o:o + 4] == EM:   # single-colour emissive preset: (colour, None)
            try: out.setdefault(name.decode(), (colour(d, o + 4)[0], None))
            except IndexError: pass
            continue
        if d[o:o + 4] != C1: continue
        try:
            c1, o = colour(d, o + 4)
            if d[o:o + 4] != C2: continue
            c2, o = colour(d, o + 4)
        except IndexError:
            continue
        out.setdefault(name.decode(), (c1, c2))
    return out


if __name__ == "__main__":
    p = presets(sys.argv[1])
    for k in sorted(p):
        if len(sys.argv) > 2 and k != sys.argv[2]: continue
        c1, c2 = p[k]
        f = lambda c: tuple(round(x / 255, 3) for x in c[:3])
        print(f"{k:40} {f(c1)}" + (f" / {f(c2)}" if c2 else "  (emissive)"))
