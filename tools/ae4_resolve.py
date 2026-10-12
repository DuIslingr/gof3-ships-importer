"""Resolve which material and texture files a GoF3 ship really uses.

Files never store their own GUID: models list their materials and materials their textures by 8-byte GUIDs only (no
lookup table in the romfs either). The GUID -> file maps are inferred from the ships whose files follow the naming
convention (<ship>_matid01_body.ae4material, <ship>_diffuse_emissive / _specular_gloss / _normal / _colormask_000), then
used for the ships that borrow another ship's files (variants such as terran/021, which has no material or texture of its own).

python ae4_resolve.py <assets dir> [ship, e.g. terran/021] [out.json] -> prints the resolution (JSON for one ship)."""
import glob, json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import ae4_material
from ae4unpack import unpack
if os.sep == "\\":   # Windows: the code splits and joins paths with "/": glob's results (and the paths given) too
    _glob = glob.glob
    glob.glob = lambda pattern, **kw: [p.replace("\\", "/") for p in _glob(pattern, **kw)]

ROLE_KEYS = {  # filename hints per material role (checked against texture names in the material's ship folder)
    "Diffuse": ("diffuse_emissive", "diffuse"),
    "Specular": ("specular_gloss", "spec_gloss", "specular"),
    "Normal": ("_normal", "_n_s_g", "_n_s"),
    "Colorize": ("colormask_000",),
    "Iridescence": ("iridescence_mask",),
}


def model_lods(path):
    d = unpack(open(path, "rb").read())
    n = struct.unpack_from("<I", d, 8)[0]
    o = 12 + 8 * n
    lods = []
    count = struct.unpack_from("<I", d, o)[0]; o += 4
    for _ in range(count):   # [LOD id 8][count][count x material id 8][pad u32][distance f32][pad u32]
        c = struct.unpack_from("<I", d, o + 8)[0]
        lods.append([d[o + 12 + 8 * i:o + 20 + 8 * i].hex() for i in range(c)])
        o += 12 + 8 * c + 12
    return lods


def body_glass_ids(model):
    lods = model_lods(model)
    ids = [i for lod in lods for i in lod]
    body = max(lods[0], key=lambda i: (ids.count(i), -lods[0].index(i)))   # most used, a tie = the first section (vossk/109)
    glass = [i for i in lods[0] if i != body]
    return body, glass[0] if glass else None


class Resolver:
    def __init__(self, assets):
        self.assets = assets.replace("\\", "/")
        self.ships = {}
        for d in sorted(glob.glob(f"{assets}/ships/*/*/")):
            race, num = d.rstrip("/").split("/")[-2:]
            name = f"ship_{race}_{num}"
            if os.path.exists(f"{d}{name}_lod_000_body.ae4model"):
                self.ships[f"{race}/{num}"] = (d.rstrip("/"), name)
        for d in sorted(glob.glob(f"{assets}/ships/*/")):   # ships outside <race>/<num> (ships/starfox)
            m = glob.glob(f"{d}*_lod_000_body.ae4model")
            if m and d.rstrip("/").split("/")[-1] not in self.ships:
                self.ships[d.rstrip("/").split("/")[-1]] = (d.rstrip("/"), os.path.basename(m[0])[:-len("_lod_000_body.ae4model")])
        self.mat_by_guid, self.tex_by_guid, self.conflicts = {}, {}, []
        self._learn()

    def _vote(self, table, guid, path):
        """Several files under one GUID = copies of one asset (nivelian/230 = 210's textures): keep them all."""
        c = table.setdefault(guid, [])
        if path not in c:
            if c: self.conflicts.append((guid, c[0], path))
            c.append(path)

    @staticmethod
    def _best(cands, own_dir):
        """The largest copy (the 2048 px romfs one over a 1024 px iOS one), then the ship's own."""
        def area(p):
            if not p.endswith(".ae4texture"): return 0
            d = unpack(open(p, "rb").read())   # old iOS files are whole zstd frames
            return struct.unpack_from("<H", d, 0x1a)[0] * struct.unpack_from("<H", d, 0x1e)[0]
        return max(cands, key=lambda p: (area(p), os.path.dirname(p) == own_dir)) if cands else None

    def _learn(self):
        for key, (d, name) in self.ships.items():
            body, glass = body_glass_ids(f"{d}/{name}_lod_000_body.ae4model")
            bp, gp = f"{d}/{name}_matid01_body.ae4material", f"{d}/{name}_matid02_glass.ae4material"
            if os.path.exists(bp): self._vote(self.mat_by_guid, body, bp)
            if glass and os.path.exists(gp): self._vote(self.mat_by_guid, glass, gp)
            texs = [os.path.basename(p) for p in glob.glob(f"{d}/*.ae4texture")]
            for mp in [bp] + sorted(glob.glob(f"{d}/materials/{name}_matid01_body_*.ae4material")):
                if not os.path.exists(mp): continue
                vals, slots = ae4_material.read(mp)
                var = os.path.basename(mp)[len(f"{name}_matid01_body_"):-len(".ae4material")] if "/materials/" in mp else None
                for role, keys in ROLE_KEYS.items():
                    slot = vals.get(f"{role}_TextureSlot", 0)
                    guid = slots.get(f"T{slot}") if slot else None
                    if not guid: continue
                    if role == "Colorize" and var:
                        cm = f"{d}/colormasks/{name}_cm_{var}.tga.ae4texture"
                        if os.path.exists(cm): self._vote(self.tex_by_guid, guid, cm)
                        continue
                    if role == "Specular" and slot == vals.get("Normal_TextureSlot"): continue   # packed n_s_g
                    hits = [t for t in texs if any(k in t for k in keys) and "glass" not in t]
                    hits = [t for t in hits if keys[0] in t] or hits
                    if len(hits) == 1: self._vote(self.tex_by_guid, guid, f"{d}/{hits[0]}")

    def material(self, key, which):
        """which = 'body' / 'glass': the ship's own file, else the one its model's GUID points at."""
        d, name = self.ships[key]
        own = f"{d}/{name}_matid0{1 if which == 'body' else 2}_{which}.ae4material"
        if os.path.exists(own): return own
        body, glass = body_glass_ids(f"{d}/{name}_lod_000_body.ae4model")
        g = body if which == "body" else glass
        if g and g in self.mat_by_guid: return self._best(self.mat_by_guid[g], d)
        if which == "glass" and not g: return None
        # the ship's own stand-ins with the same textures: the plain material (inouac/601), the dissolve variant (same
        # slots and colours, only the unused emissive colour differs), the NPC version
        n = 1 if which == "body" else 2
        for c in ([f"{d}/{name}.ae4material"] if which == "body" else []) + [
                f"{d}/{name}_matid0{n}_{which}_dissolve.ae4material", f"{d}/npc_{name}_matid0{n}_{which}.ae4material",
                f"{d}/npc_{name[5:]}_matid0{n}_{which}.ae4material"]:
            if os.path.exists(c): return c
        return None

    def resolve(self, key):
        d, name = self.ships[key]
        out = {"ship": key, "dir": d, "name": name, "missing": []}
        body = self.material(key, "body")
        out["body_material"] = body
        out["glass_material"] = self.material(key, "glass")
        ov = json.load(open(os.path.join(os.path.dirname(__file__), "ship_overrides.json"), encoding='utf-8-sig')).get(key, {})
        for k in ("body_material", "glass_material"):   # corrections from the game data (tools/ship_overrides.json)
            if ov.get(k):
                out[k] = os.path.join(self.assets, ov[k]); out.setdefault("notes", []).append(f"{k} from ship_overrides.json")
        body = out["body_material"]
        if not out["glass_material"] and body and body_glass_ids(f"{d}/{name}_lod_000_body.ae4model")[1]:
            # an unknown glass GUID on a variant: the glass of the ship its body material comes from (terran/022 -> 020)
            b = os.path.basename(body).split("_matid01")[0]
            g = f"{os.path.dirname(body)}/{b}_matid02_glass.ae4material"
            if os.path.dirname(body) != d and os.path.exists(g):
                out["glass_material"] = g
                out.setdefault("notes", []).append(f"glass material taken from {b}")
        if not body:
            out["missing"].append("body material")
            return out
        vals, slots = ae4_material.read(body)
        out["packed_nsg"] = bool(vals.get("Normal_TextureSlot")) and vals.get("Normal_TextureSlot") == vals.get("Specular_TextureSlot")
        for role in ROLE_KEYS:
            slot = vals.get(f"{role}_TextureSlot", 0)
            if not slot:
                out[role] = None
                continue
            guid = slots.get(f"T{slot}")
            p = self._best(self.tex_by_guid.get(guid, []), d)
            mdir = os.path.dirname(body)
            for base in ([] if p else [d, mdir]):   # this ship's (or the material's ship's) own conventional file
                for k in ROLE_KEYS[role]:
                    c = [x for x in glob.glob(f"{base}/*{k}*.tga.ae4texture") + glob.glob(f"{base}/colormasks/*{k}*.tga.ae4texture")
                         if "glass" not in x]
                    if len(c) == 1: p = c[0]; break
                if not p and role == "Colorize":   # a lone paint mask (vossk/120's cm_001, nivelian/220's cm_002)
                    c = sorted(set(glob.glob(f"{base}/*_cm_*.tga.ae4texture")) | set(glob.glob(f"{base}/colormasks/*_cm_*.tga.ae4texture")))
                    names = {os.path.basename(x) for x in c}
                    if len(names) == 1:
                        p = c[-1]; out.setdefault("notes", []).append(f"colormask guessed: {os.path.basename(p)}")
                        self._vote(self.tex_by_guid, guid, p)   # nivelian/222 shares 220's mask GUID
                if p: break
            out[role] = p
            if not p and not (role == "Specular" and out["packed_nsg"]):
                out["missing"].append(f"{role} texture (T{slot} {guid})")
        # the glass's own textures (terran/031), when its diffuse isn't the hull's
        gm = out["glass_material"]
        if gm:
            gv, gs = ae4_material.read(gm)
            gd = gs.get(f"T{gv.get('Diffuse_TextureSlot', 1)}")
            if gd and gd != slots.get(f"T{vals.get('Diffuse_TextureSlot', 1)}"):
                gdir = os.path.dirname(gm)
                g1 = glob.glob(f"{gdir}/*glass_diffuse*.ae4texture"); g2 = glob.glob(f"{gdir}/*glass*opacity*.ae4texture")
                out["GlassDiffuse"] = g1[0] if len(g1) == 1 else None
                out["GlassOpacity"] = g2[0] if len(g2) == 1 else None
        # paint schemes: those of the ship the body material came from, plus the ship's own (terran/008 borrows 006's
        # material and schemes but has its own scheme 000 too)
        src_dir = os.path.dirname(body)
        src_name = os.path.basename(body).split("_matid01")[0]
        schemes = glob.glob(f"{src_dir}/materials/{src_name}_matid01_body_*.ae4material")
        schemes += glob.glob(f"{d}/materials/{name}_matid01_body_*.ae4material")
        out["schemes"] = sorted(set(schemes))
        # each scheme's mask: colormasks/<owner>_cm_<scheme>, else the body's own mask when the GUID is the same, else
        # the GUID map, else the owner's only colormask (008's scheme 000 -> cm_001, Gorgon_ColorMask in data.pdb)
        body_t4 = slots.get(f"T{vals.get('Colorize_TextureSlot', 0)}")
        out["scheme_masks"] = {}
        for mp in out["schemes"]:
            owner = os.path.basename(mp).split("_matid01_body_")[0]
            var = os.path.basename(mp)[len(f"{owner}_matid01_body_"):-len(".ae4material")]
            odir = os.path.dirname(os.path.dirname(mp))
            cm = f"{odir}/colormasks/{owner}_cm_{var}.tga.ae4texture"
            if os.path.exists(cm): continue
            sv, ss = ae4_material.read(mp)
            g = ss.get(f"T{sv.get('Colorize_TextureSlot', 0)}")
            if not g or g == body_t4: continue
            p = self._best(self.tex_by_guid.get(g, []), odir)
            if not p:
                c = glob.glob(f"{odir}/colormasks/*_cm_*.tga.ae4texture")
                p = c[0] if len(c) == 1 else None
            if p: out["scheme_masks"][mp] = p
        # skins that exist only as colour presets in data.pdb (tools/data_skins.json): the body material with the
        # preset's two colours through the given mask
        skins = json.load(open(os.path.join(os.path.dirname(__file__), "data_skins.json"), encoding='utf-8-sig')).get(key, [])
        if skins:
            import ae4_pdb_colors
            root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
            pdb = next(p for p in (os.environ.get("GOF3_PDB") or "",   # import.py: the merged data.pdb
                                   f"{root}/romfs_extracted/patch_1_0_2/data.pdb", f"{root}/romfs_extracted/game/data.pdb") if p and os.path.exists(p))
            presets = ae4_pdb_colors.presets(pdb)
            out["data_skins"] = []
            for sk in skins:
                e = dict(sk)
                if "color1" not in sk:   # by preset name; entries from ae4_pdb_skins.py carry their decoded colours
                    c1, c2 = presets[sk["preset"]]
                    e.update(color1=[x / 255 for x in c1[:3]], color2=[x / 255 for x in c2[:3]])
                if sk.get("mask"): e["mask"] = os.path.join(self.assets, sk["mask"])
                if sk.get("emissive_preset"):   # Emissive_* preset (one colour)
                    e["emissive_color"] = [x / 255 for x in presets[sk["emissive_preset"]][0][:3]]
                if sk.get("specular_from"):     # the material whose specular look a pack copies
                    e["specular_from"] = os.path.join(self.assets, sk["specular_from"])
                out["data_skins"].append(e)
        return out


if __name__ == "__main__":
    r = Resolver(sys.argv[1])
    for k in r.ships: r.resolve(k)   # a first pass records the guessed masks for the ships sharing them
    if len(sys.argv) > 2:
        js = json.dumps(r.resolve(sys.argv[2]), indent=1)
        if len(sys.argv) > 3: open(sys.argv[3], "w", encoding='utf-8').write(js)
        print(js)
        sys.exit()
    print(f"{len(r.ships)} ships, {len(r.mat_by_guid)} material GUIDs, {len(r.tex_by_guid)} texture GUIDs, "
          f"{len(r.conflicts)} GUIDs with several copies")
    for k in r.ships:
        x = r.resolve(k)
        short = lambda p: p and p.replace(r.assets + "/ships/", "")
        print(f"{k:13} {'OK ' if not x['missing'] else 'MISSING ' + ', '.join(x['missing'])}"
              f"  body={short(x['body_material'])}  D={short(x.get('Diffuse'))}  CM={short(x.get('Colorize'))}"
              + (f"  [{'; '.join(x['notes'])}]" if x.get("notes") else ""))
