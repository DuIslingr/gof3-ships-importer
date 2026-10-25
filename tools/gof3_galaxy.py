"""Galaxy on Fire 3's galaxy from data.pdb: its sectors (the galaxy map's stars) and each sector's levels (its hubs), with
the entities that make each level's look: its stations, sky, suns, planets and the mission jumpgates.

data.pdb (protobuf, see ae4_pdb_arming): a sector record has field 1635146 = its galaxy map node ("GM_star_Porros_005"),
4067579 = {1: its name text}, 9934023 = {1: its description text}, 5269619 = its order, 9334089 = {1: level id} per level.
A level record is GUID-less (... 18 <id> 22 <name> <fields>): 5132369 = {1: its name text}, 2643183 = its music event,
5231566 = {1: entity id, 3: the editor folder} per entity. An entity is an ordinary record with components (Shape: its
scene, Transform: 6503637 position, 3457660 rotation in degrees, 7443144 scale) and a template chain ("Template Station
Vossk", "Template_Vossk_JumpGate_Base"). Text records hold their string in 3906420.

The galaxy map's layout is the hangar's galaxymap_000 scene: one node per star (its sector's place in x / z), found here by
the planet meshes next to it (Porros, Rigant) or by its levels' count and pairs (Trim; STAR_NODES).

gof3_galaxy.sectors(pdb_path) -> [ {record, star, name, desc, order, levels: [ {record, id, name, music, entities} ]} ]."""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
from ae4_pdb_arming import Records

F_STAR, F_NAME, F_DESC, F_ORDER, F_LEVELS = 1635146, 4067579, 9934023, 5269619, 9334089
L_NAME, L_MUSIC, L_ENT = 5132369, 2643183, 5231566
T_TEXT = 3906420
SHAPE, POS, ROT, SCALE = 7803720, 6503637, 3457660, 7443144

# The galaxy map nodes (galaxymap_000.ae4scene, x / z in its units) of the stars. Porros' and Rigant's by the planet meshes
# beside them; Trim's by their levels (Thorn the one with one, Phoenix Station with two) and their A / B pairs lying close
# (000 A / B, 001 A / B, 003 A / B); Neo Vegas, Porros Port and Lazuline are a guess among the last three (the scene names
# none of them), Porros Port the one nearest Porros.
STAR_NODES = {
    "GM_star_Porros_000": (229.5, 251.4), "GM_star_Porros_001": (259.3, 212.3), "GM_star_Porros_002": (73.9, 309.6),
    "GM_star_Porros_003": (315.8, 47.2), "GM_star_Porros_004": (338.6, 285.0), "GM_star_Porros_005": (308.6, 358.9),
    "GM_star_Porros_006": (151.8, 82.8), "GM_star_Porros_007": (353.6, 196.8), "GM_star_Porros_008": (183.5, 173.1),
    "GM_star_Rigant_000": (25.2, -184.4), "GM_star_Rigant_001": (110.4, -117.2), "GM_star_Rigant_002": (171.2, -355.8),
    "GM_star_Rigant_003": (-75.6, -341.9), "GM_star_Rigant_004": (191.4, -169.3),
    "GM_star_Trim_000": (-288.3, 241.5), "GM_star_Trim_000_B": (-312.0, 271.8), "GM_star_Trim_001": (-138.1, 139.1),
    "GM_star_Trim_001_B": (-75.3, 123.5), "GM_star_Trim_003": (-109.7, 275.4), "GM_star_Trim_003_B": (-147.4, 311.3),
    "GM_star_Trim_006": (-315.1, 147.4), "GM_star_Trim_004": (-42.4, 189.8), "GM_star_Trim_002": (-289.7, 345.3),
    "GM_star_Trim_005": (-163.0, 206.5),
}


def _enc(v):
    o = b""
    while True:
        b = v & 0x7f; v >>= 7
        if v: o += bytes([b | 0x80])
        else: return o + bytes([b])


class Galaxy:
    def __init__(self, pdb):
        self.R = Records(pdb); self.d = self.R.d

    def _vi(self, o):
        v = s = 0; d = self.d
        while True:
            x = d[o]; o += 1; v |= (x & 0x7f) << s; s += 7
            if x < 0x80: return v, o

    def level_fields(self, rid):
        m = re.search(re.escape(b"\x18" + _enc(rid) + b'"'), self.d)
        if not m: return None, {}
        n, o = self._vi(m.end()); name = self.d[o:o + n].decode("utf8", "replace"); o += n
        out = {}
        for _ in range(4000):
            try:
                k, o2 = self._vi(o); f, t = k >> 3, k & 7
                if f == 0 or t not in (0, 1, 2, 5): break
                if t == 0: v, o2 = self._vi(o2)
                elif t == 1: v = struct.unpack_from("<d", self.d, o2)[0]; o2 += 8
                elif t == 5: v = struct.unpack_from("<f", self.d, o2)[0]; o2 += 4
                else: n2, o2 = self._vi(o2); v = self.d[o2:o2 + n2]; o2 += n2
                if f == 1 and t == 2 and len(v) == 36: break
                out.setdefault(f, []).append(v); o = o2
            except Exception: break
        return name, out

    def text(self, rid):
        R = self.R
        return R.fields(rid).get(T_TEXT, [b""])[0].decode("utf8", "replace") if rid in R.p.recs else None

    def vec(self, b):
        s = self.R.sub(b); return [round(float(s.get(k, 0.0)), 4) for k in (1, 2, 3)]

    def entity(self, rid):
        R = self.R
        comps, chain = R.resolved(rid)
        shape = comps.get("Shape", {}).get(SHAPE, [b""])[0].decode("latin1") or None
        tr = comps.get("Transform", {})
        e = {"name": R.name(rid).strip(), "templates": chain[1:], "shape": shape}
        if POS in tr: e["pos"] = self.vec(tr[POS][0])
        if ROT in tr: e["rot"] = self.vec(tr[ROT][0])
        if SCALE in tr: e["scale"] = self.vec(tr[SCALE][0])
        return e

    def sectors(self):
        R = self.R; out = []
        for rid in R.p.recs:
            try: f = R.fields(rid)
            except Exception: continue
            if F_STAR not in f: continue
            s = {"record": R.name(rid), "star": f[F_STAR][0].decode(),
                 "name": self.text(R.sub(f[F_NAME][0]).get(1)) if F_NAME in f else None,
                 "desc": self.text(R.sub(f[F_DESC][0]).get(1)) if F_DESC in f else None,
                 "order": f.get(F_ORDER, [None])[0], "levels": []}
            for x in f.get(F_LEVELS, []):
                lid = R.sub(x).get(1)
                lname, lf = self.level_fields(lid)
                if lname is None: continue
                lv = {"record": lname, "id": lid, "music": lf.get(L_MUSIC, [b""])[0].decode() or None,
                      "name": self.text(R.sub(lf[L_NAME][0]).get(1)) if L_NAME in lf else None, "entities": []}
                for e in lf.get(L_ENT, []):
                    sub = R.sub(e); eid = sub.get(1)
                    folder = sub.get(3).decode() if isinstance(sub.get(3), (bytes, bytearray)) else ""
                    if eid not in R.p.recs: continue
                    try: en = self.entity(eid)
                    except Exception: continue
                    if not en["shape"]: continue
                    en["folder"] = folder
                    lv["entities"].append(en)
                lv["levels_sorted_key"] = lname
                s["levels"].append(lv)
            s["levels"].sort(key=lambda l: l["record"])
            out.append(s)
        out.sort(key=lambda s: s["record"])
        return out


def sectors(pdb):
    return Galaxy(pdb).sectors()
