"""GoF3's Most Wanted bosses' paint as skins of their hulls (data_skins.json entries with "boss": true).

Every campaign boss (gof3_wanted.bosses) flies a hull in its gang's paint, its ship record's Customization (ae4_pdb_skins):
act 1's Gr'Gath (Colorize_Boss_Trim + Emissive_Boss_Trim, decal sheet 001), act 2's Grey Shadow (Colorize_Boss_Porros +
Emissive_Boss_Porros, sheet 002), act 3's Vortex (Colorize_Boss_Rigant_Vortex_Yellow / _Orange, sheet 003), each through
a colour mask, mostly its own hull's (a few bosses borrow another hull's mask: GoF3's data as it is, the hulls derived from
one being alike). A boss record without a Customization takes its second record's (Sh'gaal's is on ..._2); Ti-Nung has
none (no skin). One skin per hull and paint: bosses in the same paint on the same hull share it (Th'Rrshr and Ica'Brn).

The player ships' gang skins (data_skins.json "grgath" / "greyshadow", from GoF3's player ship records) are the same
colours with the player version's glow (BrownEmissive / none): the bosses' are skins of their own ("Gr'Gath Boss").

python gof3_boss_skins.py --write    regenerates the "boss" entries of data_skins.json from the work folder's data.pdb
(GOF3_MERGED etc. as build_gof3_mod.py reads them). gof3_wanted.build gives each boss its skin (wanted.json "skin")."""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_SKINS = os.path.join(HERE, "data_skins.json")

GANG = {   # colour preset -> (scheme id, the skin's name)
    "Colorize_Boss_Trim": ("boss_grgath", "Gr'Gath Boss"),
    "Colorize_Boss_Porros": ("boss_greyshadow", "Grey Shadow Boss"),
    "Colorize_Boss_Rigant_Vortex_Yellow": ("boss_vortexyellow", "Vortex Yellow"),
    "Colorize_Boss_Rigant_Vortex_Orange": ("boss_vortexorange", "Vortex Orange"),
    "Colorize_Boss_Rigant_Vortex_Green": ("boss_vortexgreen", "Vortex Green"),
}


def slug(s): return re.sub(r"[^a-z0-9]+", "", s.lower())


def paint_of(pdb, record, assets):
    """The record's paint (ae4_pdb_skins.entry), else its second record's (<record>_2); None without one."""
    import ae4_pdb_skins as S
    for name in (record, record + "_2"):
        if name not in pdb.byname: continue
        try: return S.entry(pdb, name, assets)
        except SystemExit: continue
    return None


def compute(D, pdb_path, assets):
    """{ "race/num": [entry, ...] } of the bosses' skins and { record: ("race_num", scheme) }."""
    import ae4_pdb_skins as S, gof3_wanted
    pdb = S.Pdb(pdb_path)
    by_hull, of_record = {}, {}
    for b in gof3_wanted.bosses(D):
        m = re.search(r"ships/([a-z]+)/(\d+)", b["shape"])
        e = paint_of(pdb, b["record"], assets) if m else None
        preset = (e or {}).get("preset_record", "").split("#")[0]
        if not e or preset not in GANG: continue
        hull = f"{m.group(1)}/{m.group(2)}"
        paint = {k: e.get(k) for k in ("color1", "color2", "emissive_color", "decals")}
        mask = e.get("mask")   # (data.pdb's own path, assets-relative; an absolute one made relative)
        paint["mask"] = (os.path.relpath(mask, assets) if os.path.isabs(mask) else mask).replace(os.sep, "/") if mask else None
        skins = by_hull.setdefault(hull, [])
        same = next((s for s in skins if all(s.get(k) == v for k, v in paint.items())), None)
        if same is None:
            scheme, name = GANG[preset]
            if any(s["scheme"] == scheme for s in skins):   # (the same gang in another paint on this hull: its boss's name)
                scheme, name = f"{scheme}_{slug(b['title'])}", f"{name} ({b['title'].title()})"
            same = dict(scheme=scheme, name=name, boss=True, records=[], **{k: v for k, v in paint.items() if v is not None})
            same["record"] = e["record"]
            skins.append(same)
        same["records"].append(b["record"])
        of_record[b["record"]] = (hull.replace("/", "_"), same["scheme"])
    for skins in by_hull.values():
        for s in skins:
            s["game_name"] = (f"{s['name']}: the Most Wanted bosses' paint ({', '.join(s['records'])}): "
                              f"{s['record']}'s Customization")
    return by_hull, of_record


def write(by_hull, path=DATA_SKINS):
    """data_skins.json with its "boss" entries replaced by these."""
    d = json.load(open(path, encoding="utf-8-sig"))
    for k, v in list(d.items()):
        if isinstance(v, list): d[k] = [e for e in v if not e.get("boss")]
    for hull, skins in by_hull.items():
        d.setdefault(hull, []).extend(skins)
    d = {k: v for k, v in d.items() if not isinstance(v, list) or v}
    open(path, "w", encoding="utf-8").write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def skin_of(record, mod_id=None, path=DATA_SKINS):
    """A boss record's skin id in the kit ("<race>_<num>_<scheme>", skins_of's), from data_skins.json; None without one."""
    d = json.load(open(path, encoding="utf-8-sig"))
    for hull, skins in d.items():
        if not isinstance(skins, list): continue
        for s in skins:
            if s.get("boss") and record in s.get("records", []):
                return f"{hull.replace('/', '_')}_{s['scheme']}"
    return None


if __name__ == "__main__":
    import build_gof3_mod as B
    D = B.Data()
    by_hull, of_record = compute(D, B.PDB, B.ASSETS)
    for hull, skins in sorted(by_hull.items()):
        for s in skins: print(f"{hull:13s} {s['scheme']:28s} {s['name']:32s} {', '.join(s['records'])}")
    if "--write" in sys.argv:
        write(by_hull); print("data_skins.json: boss skins written")
