"""Decode GoF3 weapon loadouts from data.pdb (protobuf): which weapon each ship hardpoint carries.

python ae4_pdb_arming.py <data.pdb> [--write data_arming.json] [--show <record name substring>]

data.pdb records: [0a 24 <GUID>] [18 <id>] [22 <len> <name>] then fields, each record length-prefixed by the varint
before its 0a 24. An entity record lists its components as field 1469832 = {1: component record id, 2: component type id}
and its template as field 5181810 = {1: template id}. Components merge field by field: a field the record's own component
has replaces the template's (Ship_Fighter_03_id201_AtaunoRheep_0_T0's Arming lists only weapons, the hardpoint groups come
from Template_Player_Fighter_Base); a component type the record lacks comes whole from the template.

Ship side, component Arming:
  5469906 (repeated varint, int64)  one per hardpoint, in node order <ship>_weapon_000, _001, ...: the weapon group it
                                    fires (0 = primary 1, 1 = primary 2, 2 = secondary, -1 = unused). Templates:
                                    Fighter / Scout [0, 0, 1, 1, -1, -1, 2], Gunship [0, 0, -1, -1, 1, 1, 2]
                                    (checked against the models: each group is a mirrored pair, 006 the centre one)
  9719173 (repeated {1: weapon id}) the default weapon of each group, in group order
  700016  (float)                   unknown (templates: Fighter 1.5, Scout 0.35, Gunship 2; ships override 1 / 3 / 5 / 7)
Weapon side:
  WeaponType 2593239           the gun kind (0 / absent on the HB / UB / GB / event variants; four old records disagree
                               with their model, e.g. PW_CR3_MachineGun_MK3 3 on Auto Laser 006, so "kind" is the model's): 1 Plasma Blast, 2 Mass Driver, 3 Burst Laser, 4 Beam Laser, 5 Plasma Focus,
                               6 Railgun, 7 Scatter Plasma, 8 Auto Laser, 9 Dismantler (secondaries: 1 homing / auto,
                               3 manual rockets); missing on some event / NPC records (their template has it)
  WeaponSpecification 2320945  damage class 1 laser, 2 plasma, 3 ballistic
  GuiAttribute 4644009         the shop type text record (PW_Type_Laser / _Plasma / _Ballistic, SW_Type_Auto / _Manual)
  Shape 7803720                the model: /assets/weapons/generic/<family>/weapon_generic_<family>_mk<N>.ae4scene
                               (the tier picks mk1-3), rockets /assets/weapons/rockets/...
So the gun model on a hardpoint = the Shape of the weapon in that hardpoint's group: a ship with different primaries
shows two different guns (Groza: Auto Laser mk1 on 000 / 001, mk2 on 002 / 003; the rocket's launcher on 006 has no mesh).

--write: {"ships": {record: {...}}, "weapons": {record: {...}}}; each ship has "loadout", an ae4_loadout.py spec of its
default primaries ("000=006:1,001=006:1,002=006:2,003=006:2")."""
import json, re, struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ae4_pdb_skins import Pdb

COMPONENT, TEMPLATE = 1469832, 5181810
F_GROUPS, F_DEFAULTS, F_UNKNOWN = 5469906, 9719173, 700016
F_WTYPE, F_WSPEC, F_GUITYPE, F_SHAPE = 2593239, 2320945, 4644009, 7803720
WEAPON_TYPES = {1: "Plasma Blast", 2: "Mass Driver", 3: "Burst Laser", 4: "Beam Laser", 5: "Plasma Focus", 6: "Railgun",
                7: "Scatter Plasma", 8: "Auto Laser", 9: "Dismantler"}
FAMILIES = {"000": "Burst Laser", "001": "Scatter Plasma", "002": "Plasma Focus", "003": "Dismantler", "004": "Mass Driver",
            "005": "Plasma Blast", "006": "Auto Laser", "007": "Railgun", "008": "Beam Laser"}   # by the records using each
DAMAGE = {1: "laser", 2: "plasma", 3: "ballistic"}
GROUPS = {0: "primary 1", 1: "primary 2", 2: "secondary", -1: "unused"}


class Records:
    def __init__(self, path):
        self.p = Pdb(path); self.d = self.p.d; self.cache = {}

    def name(self, rid):
        return self.p.recs[rid][0] if rid in self.p.recs else None

    def raw(self, rid):
        """The record's bytes, from its length prefix (the varint before 0a 24)."""
        st = self.p.recs[rid][1]; i = st - 1; bs = [self.d[i]]; i -= 1
        while self.d[i] >= 0x80: bs.insert(0, self.d[i]); i -= 1
        n = sum((b & 0x7f) << (7 * k) for k, b in enumerate(bs))
        return self.d[st:st + n]

    @staticmethod
    def parse(b):
        """[(field, wire type, value)] of one message; raises ValueError when b isn't one."""
        def vi(o):
            v = s = 0
            while True:
                x = b[o]; o += 1; v |= (x & 0x7f) << s; s += 7
                if x < 0x80: return v, o
        o = 0; out = []
        while o < len(b):
            k, o = vi(o); f, t = k >> 3, k & 7
            if f == 0: raise ValueError("field 0")
            if t == 0: v, o = vi(o)
            elif t == 1: v = struct.unpack_from("<d", b, o)[0]; o += 8
            elif t == 5: v = struct.unpack_from("<f", b, o)[0]; o += 4
            elif t == 2:
                n, o = vi(o)
                if o + n > len(b): raise ValueError("length")
                v = b[o:o + n]; o += n
            else: raise ValueError("wire type")
            out.append((f, t, v))
        return out

    def fields(self, rid):
        """{field: [values]} of a record (GUID / id / name left out; messages kept as bytes)."""
        out = {}
        for f, t, v in self.parse(self.raw(rid)):
            if f not in (1, 3, 4): out.setdefault(f, []).append(v)
        return out

    def sub(self, b):
        return {f: v for f, _, v in self.parse(b)}

    def resolved(self, rid, depth=0):
        """({component name: merged {field: [values]}}, [record, template, ...])."""
        if rid in self.cache: return self.cache[rid]
        f = self.fields(rid); comps, chain = {}, [self.name(rid)]
        if TEMPLATE in f and depth < 20:
            t = self.sub(f[TEMPLATE][0]).get(1)
            if t in self.p.recs:
                base, ch = self.resolved(t, depth + 1); chain += ch
                comps = {k: dict(v) for k, v in base.items()}
        for c in f.get(COMPONENT, []):
            cid = self.sub(c).get(1)
            if cid not in self.p.recs: continue
            comps.setdefault(self.name(cid), {}).update(self.fields(cid))
        self.cache[rid] = (comps, chain)
        return comps, chain


def s64(v): return v - (1 << 64) if v >= 1 << 63 else v


def model(path):
    m = re.search(r"weapon_generic_(\d{3})_mk(\d)\.ae4scene$", path or "")
    return f"{m.group(1)}:{m.group(2)}" if m else None


def weapon(R, rid):
    c, chain = R.resolved(rid)
    shape = c.get("Shape", {}).get(F_SHAPE, [b""])[0].decode("latin1") or None
    wt = c.get("WeaponType", {}).get(F_WTYPE, [None])[0]
    spec = c.get("WeaponSpecification", {}).get(F_WSPEC, [None])[0]
    gui = c.get("GuiAttribute", {}).get(F_GUITYPE)
    w = {"templates": chain[1:], "secondary": "WeaponSpecification" not in c,
         "weapon_type": wt, "damage": DAMAGE.get(spec), "shop_type": R.name(R.sub(gui[0]).get(1)) if gui else None,
         "model": shape, "family_mk": model(shape)}
    if not w["secondary"]:   # WeaponType 0 is left out (protobuf default): the HB / UB / GB / event variants, any model
        w["kind"] = (FAMILIES.get(w["family_mk"][:3]) if w["family_mk"] else None) or WEAPON_TYPES.get(wt)
    return w


def ship(R, rid, weapons):
    c, chain = R.resolved(rid)
    a = c["Arming"]
    groups = [s64(v) for v in a.get(F_GROUPS, [])]
    defaults = [R.name(R.sub(x).get(1)) for x in a.get(F_DEFAULTS, [])]
    shape = c.get("Shape", {}).get(F_SHAPE, [b""])[0].decode("latin1") or None
    s = {"templates": chain[1:], "scene": shape, "hardpoint_groups": groups, "defaults": defaults,
         "arming_700016": round(a[F_UNKNOWN][0], 4) if F_UNKNOWN in a else None, "hardpoints": {}}
    spec = []
    for i, g in enumerate(groups):
        w = defaults[g] if 0 <= g < len(defaults) else None
        fm = weapons.get(w, {}).get("family_mk") if w else None
        s["hardpoints"][f"{i:03d}"] = {"group": GROUPS.get(g, g), "weapon": w, "family_mk": fm}
        if fm and g in (0, 1): spec.append(f"{i:03d}={fm}")
    s["loadout"] = ",".join(spec)
    return s


def decode(path):
    R = Records(path); weapons, ships = {}, {}
    for rid in R.p.recs:
        try: c, _ = R.resolved(rid)
        except (ValueError, IndexError): continue
        if "WeaponType" in c: weapons[R.name(rid)] = weapon(R, rid)
    for rid in R.p.recs:
        try: c, _ = R.resolved(rid)
        except (ValueError, IndexError): continue
        if "Arming" in c and "WeaponType" not in c and ("Hull" in c or "ShipType" in c):
            ships[R.name(rid)] = ship(R, rid, weapons)
    return {"ships": ships, "weapons": weapons}


if __name__ == "__main__":
    out = decode(sys.argv[1])
    args = sys.argv[2:]
    if "--write" in args:
        json.dump(out, open(args[args.index("--write") + 1], "w", encoding='utf-8'), indent=1, ensure_ascii=False)
        print(f"wrote {len(out['ships'])} ships, {len(out['weapons'])} weapons")
    if "--show" in args:
        q = args[args.index("--show") + 1]
        for k, v in {**out["ships"], **out["weapons"]}.items():
            if q in k: print(k, json.dumps(v, ensure_ascii=False))
