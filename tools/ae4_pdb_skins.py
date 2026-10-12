"""Decode GoF3 ship skins from data.pdb (protobuf) into tools/data_skins.json entries.

data.pdb records: [0a 24 <GUID text>] [18 <numeric id>] [22 <len> <name>] then fields; records link to each other by the
numeric id (a varint). A ship record (Ship_Fighter_03_id201_AtaunoRheep_1_T0 ...) links its components; the Customization
component holds the skin as slots, each a message [08 <record id>] [10 <type id>]:
  0x12fdc2 colour preset      fields e2a4bb10 colour 1 / eaa4bb10 colour 2 (a missing one is white: Colorize_Boss_Porros
                              has only colour 2 (55, 55, 55); 208's scheme 002 material, the same skin, has colour 1 = 1, 1, 1)
  0x316b81 emissive preset    field  d2d0ee0c colour
  0x674092 specular colour    field  a29bb61e colour            (Gold tiers)
  0x1d4676 / 0x26691a         Specular_Multiplier / Gloss_Multiplier floats (Gold tiers)
  0x7375c5 colour mask        a record with the colormask's /assets/... path
  0x2eb3d0 decal material     a record with ships/decals/materials/ship_matid01_decals_00N.ae4material -> ship_decals_00N.png
  0x4b861d                    the gold version every ship references (the plain ones too): not applied
A colour is a message of varints 08 r / 10 g / 18 b / 20 a (0..255). Records without a Customization inherit the linked
Ship_* template's (Sutoe-Shii _0_T0 -> _0_T0_Event).

python ae4_pdb_skins.py <data.pdb> <assets dir> <spec.json> [--write data_skins.json]
spec.json: {"<race>/<num>": [{"scheme": ..., "record": "<ship record name>", "game_name": ...}, ...]} -> the decoded entries
(printed; with --write merged into data_skins.json, replacing entries of the same ship and scheme)."""
import bisect, json, os, re, struct, sys

TAG_C1, TAG_C2, TAG_EM, TAG_SP = b"\xe2\xa4\xbb\x10", b"\xea\xa4\xbb\x10", b"\xd2\xd0\xee\x0c", b"\xa2\x9b\xb6\x1e"
SLOT = {0x12fdc2: "colour", 0x316b81: "emissive", 0x7375c5: "mask", 0x2eb3d0: "decals", 0x674092: "specular",
        0x1d4676: "spec_mult", 0x26691a: "gloss_mult", 0x4b861d: "goldref"}


class Pdb:
    def __init__(self, path):
        self.d = d = open(path, "rb").read()
        self.recs = {}
        for m in re.finditer(rb"\x0a\x24[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\x18", d):
            rid, o = self.varint(m.end())
            if d[o] != 0x22: continue
            n, o2 = self.varint(o + 1)
            self.recs[rid] = (d[o2:o2 + n].decode("latin1"), m.start(), o2 + n)
        self.starts = sorted(v[1] for v in self.recs.values())
        self.byname = {}
        for k, (n, _, _) in self.recs.items(): self.byname.setdefault(n, []).append(k)

    def varint(self, o):
        v = s = 0
        while True:
            b = self.d[o]; o += 1
            v |= (b & 0x7f) << s; s += 7
            if b < 0x80: return v, o

    def span(self, rid):
        """(start of the fields after the name, end of the record)."""
        start = self.recs[rid][1]
        i = bisect.bisect_right(self.starts, start)
        return self.recs[rid][2], self.starts[i] if i < len(self.starts) else len(self.d)

    def links(self, rid):
        o, e = self.span(rid); out = []
        while o < e - 1:
            v, q = self.varint(o)
            if v in self.recs and v > 1000000 and q - o >= 4: out.append(v); o = q
            else: o += 1
        return out

    def colour(self, rid, tag):
        o, e = self.span(rid)
        i = self.d.find(tag, o, e)
        if i < 0: return None
        n, q = self.varint(i + len(tag)); end = q + n; c = {}
        while q < end:
            k, q = self.varint(q); c[k >> 3], q = self.varint(q)
        return [round(c.get(f, 0) / 255, 4) for f in (1, 2, 3)]

    def path(self, rid):
        o, e = self.span(rid)
        m = re.search(rb"/assets/([\x20-\x7e]+?\.ae4(?:texture|material))", self.d[o:e])
        return m.group(1).decode() if m else None

    def customization(self, rid, depth=0, seen=None):
        seen = seen or {rid}
        for c in self.links(rid):
            if self.recs[c][0] == "Customization": return self.slots(c)
        if depth < 4:
            for c in self.links(rid):
                if c not in seen and self.recs[c][0].startswith("Ship_"):
                    seen.add(c)
                    r = self.customization(c, depth + 1, seen)
                    if r is not None: return r
        return None

    def slots(self, cid):
        o, e = self.span(cid); out = {}
        while o < e:
            tag, q = self.varint(o); wt, f = tag & 7, tag >> 3
            if wt == 2:
                n, q2 = self.varint(q); sub = self.d[q2:q2 + n]; o = q2 + n
                if f in SLOT and sub[:1] == b"\x08":
                    v, _ = self.varint(q2 + 1)
                    out[SLOT[f]] = v
            elif wt == 5:
                if f in SLOT: out[SLOT[f]] = round(struct.unpack_from("<f", self.d, q)[0], 4)
                o = q + 4
            elif wt == 0: _, o = self.varint(q)
            else: break
        out.pop("goldref", None)
        return out


def entry(pdb, rec_name, assets):
    rid = pdb.byname[rec_name][0]
    s = pdb.customization(rid)
    if not s: raise SystemExit(f"{rec_name}: no Customization")
    e = {"record": rec_name}
    if "colour" in s:
        c1, c2 = pdb.colour(s["colour"], TAG_C1), pdb.colour(s["colour"], TAG_C2)
        e["color1"], e["color2"] = c1 or [1.0, 1.0, 1.0], c2 or [1.0, 1.0, 1.0]
        e["preset_record"] = f"{pdb.recs[s['colour']][0]}#{s['colour']}"
    if "emissive" in s:
        e["emissive_color"] = pdb.colour(s["emissive"], TAG_EM)
        e["emissive_record"] = f"{pdb.recs[s['emissive']][0]}#{s['emissive']}"
    spec = {}
    if "specular" in s: spec["Specular_Color"] = pdb.colour(s["specular"], TAG_SP)
    if "spec_mult" in s: spec["Specular_Multiplier"] = s["spec_mult"]
    if "gloss_mult" in s: spec["Gloss_Multiplier"] = s["gloss_mult"]
    if spec: e["specular"] = spec
    if "mask" in s:
        p = pdb.path(s["mask"])
        e["mask"] = p
        if not os.path.exists(os.path.join(assets, p)): e["mask_missing"] = True
    if "decals" in s:
        p = pdb.path(s["decals"]) or ""
        m = re.search(r"ship_matid01_decals_(\d{3})\.ae4material$", p)
        if m and m.group(1) != "000": e["decals"] = f"ship_decals_{m.group(1)}.png"
    return e


if __name__ == "__main__":
    pdb_path, assets, spec_path = sys.argv[1:4]
    pdb = Pdb(pdb_path)
    spec = json.load(open(spec_path, encoding='utf-8-sig'))
    out = {}
    for ship, skins in spec.items():
        for sk in skins:
            e = dict(sk); e.update(entry(pdb, sk["record"], assets))
            out.setdefault(ship, []).append(e)
            print(ship, json.dumps(e))
    if "--write" in sys.argv:
        p = sys.argv[sys.argv.index("--write") + 1]
        j = json.load(open(p, encoding='utf-8-sig'))
        for ship, skins in out.items():
            keep = [x for x in j.get(ship, []) if x["scheme"] not in {s["scheme"] for s in skins}]
            j[ship] = keep + skins
        json.dump(j, open(p, "w", encoding='utf-8'), indent=2)
        print("wrote", p)
