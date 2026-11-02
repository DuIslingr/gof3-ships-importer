"""Galaxy on Fire 3's star systems as a remake mod (gof3_systems): every sector of GoF3's galaxy map a GoF2 system, every
level (hub) of a sector one of its station orbits, with GoF3's own stations, jumpgates, skies and suns. None of the
stations docks, as in GoF3.

python build_gof3_systems.py --pdb <data.pdb> --assets <assets> --out <Mods/gof3_systems> [--only porros_005,trim_000]

<data.pdb>: the Android build's (APK assets/game.jet, tinextract.py), which knows every sector; <assets>: the merged GoF3
assets (assets_best: the iOS tree overlaid with the Android OBB and the Switch romfs, as convert_weapons.py builds it).

What comes from where (gof3_galaxy for the data):
- a system per sector: its name and description, its place on the star map (the galaxy map's star, scaled into a cluster
  below EVERSPACE 2's sectors), its race (the most common race of its stations: Mining is Terran (Starfire Survey), pirate
  stations don't count unless all are), its security (lower with pirate stations, Rigant lowest), its sky (the first
  level's skybox cubemap, sky_strip), its sun (the first level's biggest sun sprite, tinted), its jumpgate (GoF3's gate
  model of the race whose gates its missions use) and gates to its neighbours on GoF3's map (GoF3 travels by its Khador
  drive alone, so the routes are made here: each cluster's nearest neighbours, Trim to Porros to Rigant, and Trim's
  Anchorage to GoF2's Me'enkk);
- a station per level: its name, the largest of the level's GoF3 stations as its model (scene_glb; scaled to at most 5 km:
  GoF3's stations are far bigger next to its ships than GoF2's), not dockable (GoF3 docks at none: its missions start
  from the galaxy map, and "docking" there only ever means the Manticore), a tech level by the sector's place in GoF3's
  progression.
Each station's model shares its race's baked atlases (textures/gof3/<key>_colour.jpg, _emission, _specgloss, _normal:
scene_glb) through its "materials"; looping animations (a gate's rings, a station's moving parts) go into its glb. Last,
gof3_look puts each level's own lights, fog, sky and sun in."""
import argparse, collections, hashlib, json, math, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_ids, ae4_material, ae4_texture, gof3_galaxy, scene_glb, sky_strip
from ae4unpack import unpack

K = 1231.49 / 23.02                      # game units per GoF3 unit (the two Grozas, build_gof3_mod.K)
MAX_STATION = 100000                     # game units: 5 km, GoF2's biggest stations
MIN_STATION = 25000
GATE_SIZE = {"terran": 15000, "nivelian": 15000, "vossk": 22500}   # GoF2's gate spheres 7500 / 11250 across
MOD_ID = "gof3_systems"
MAP_SCALE = 0.12                         # star map units per galaxy map unit: the clusters ~85 x 85 below ES2's sectors
MEENKK = 30                              # GoF2's Me'enkk, the GoF2 system nearest the cluster
RACES = {"Terran": 0, "Mining": 0, "Vossk": 1, "Nivelian": 2, "Pirates": None}
SUBTITLE = {"Terran": "Terran station", "Mining": "Mining station", "Vossk": "Vossk station", "Nivelian": "Nivelian station",
            "Pirates": "Pirate hideout"}
SECURITY_BASE = {"Trim": 3, "Porros": 2, "Rigant": 1}
GOF2_SKY = {"Trim": 3, "Porros": 13, "Rigant": 10}     # the GoF2 sky each cluster's light takes before its own sun colour
PLANETS = [i for i in range(27) if i != 23]


def slug(s): return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def title(s):
    """'COMPLEX "C-03"' -> 'Complex "C-03"', "QHUFU'S THIRST" -> "Qhufu's Thirst" (quoted parts kept)."""
    out = []
    for part in re.split(r'("[^"]*")', s.strip()):
        if part.startswith('"'): out.append(part); continue
        out.append(" ".join(w[:1].upper() + w[1:].lower() for w in part.split(" ")))
    return "".join(out).strip()


def cluster_of(sector): return sector["record"].split("_")[0].capitalize()


def map_pos(star):
    x, z = gof3_galaxy.STAR_NODES[star]
    return [round(125 + x * MAP_SCALE), round(110 + z * MAP_SCALE), 50]


def station_race(e):
    t = e["templates"][0] if e["templates"] else ""
    m = re.match(r"Template Station (\w+)", t)
    return m.group(1) if m else None


def refs(path, assets, kind):
    d = unpack(open(path, "rb").read()); idx = ae4_ids.index(assets); out = []
    for o in range(len(d) - 8):
        p = idx.get(int.from_bytes(d[o:o + 8], "little"))
        if p and p.endswith(kind) and p not in out: out.append(p)
    return out


def sun_png(entity, assets, out):
    """The sun's sprite (its material's texture) tinted by its material's colour, on black."""
    scene = f"{assets}{entity['shape'][len('/assets'):]}"
    mat = scene.replace(".ae4scene", ".ae4material")
    if not os.path.exists(mat):
        mats = [m for m in refs(scene, assets, ".ae4material")]
        if not mats: return None
        mat = mats[0]
    tex = refs(mat, assets, ".ae4texture")
    if not tex: return None
    vals, _ = ae4_material.read(mat)
    tint = next((vals[k][:3] for k in ("Colorize_Color1", "Color", "Tint", "DiffuseColor") if k in vals), (1, 1, 1))
    im = np.asarray(ae4_texture.decode(tex[0]).convert("RGBA")).astype(np.float32) / 255
    rgb = im[..., :3] * im[..., 3:4] * np.array(tint, np.float32)
    Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).resize((512, 512), Image.BICUBIC).save(out)
    return [round(float(v), 3) for v in tint]


def sky_materials(shape, assets):
    """A sky scene's materials, the one named like the scene first: the scene names its models and they their materials
    by resource id (Icicles' skybox_trim_000_B draws skybox_trim_000b; Orpheus' stars mesh skybox_rigant_003_stars)."""
    import engine_meshes
    scene = f"{assets}{shape[len('/assets'):]}"
    named = f"{assets}/skyboxes/materials/{os.path.basename(shape).replace('.ae4scene', '.ae4material')}"
    out = [named] if os.path.exists(named) else []
    if os.path.exists(scene):
        for m in engine_meshes._refs(scene, assets):
            if not m.endswith(".ae4model"): continue
            out += [f for f in engine_meshes._refs(m, assets) if f.endswith(".ae4material") and "/skyboxes/" in f and f not in out]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdb", required=True); ap.add_argument("--assets", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=""); ap.add_argument("--atlas", type=int, default=2048)
    a = ap.parse_args()
    assets, out = a.assets.rstrip("/"), a.out
    only = [o for o in a.only.split(",") if o]
    os.makedirs(f"{out}/models/stations", exist_ok=True); os.makedirs(f"{out}/models/gates", exist_ok=True)
    os.makedirs(f"{out}/textures/gof3", exist_ok=True); os.makedirs(f"{out}/sky", exist_ok=True); os.makedirs(f"{out}/textures/suns", exist_ok=True)
    tmp = f"{out}/.convert"; os.makedirs(tmp, exist_ok=True)
    sectors = [s for s in gof3_galaxy.sectors(a.pdb) if s["star"] in gof3_galaxy.STAR_NODES]
    if only: sectors = [s for s in sectors if any(s["record"].lower().startswith(o) for o in only)]
    print(len(sectors), "sectors")
    groups = {}                       # bake group key -> {kind, light, plating, models}
    converted = {}                    # scene -> convert info (cached)
    def conv(shape, glb):
        if shape in converted: return converted[shape]
        path = f"{assets}{shape[len('/assets'):]}"
        info = scene_glb.convert(path, glb, assets) if os.path.exists(path) else None
        converted[shape] = (info, glb)
        return converted[shape]
    systems, stations = [], []
    sector_ids = {}
    gate_races = {}
    for s in sectors:
        cl = cluster_of(s)
        sid = "gof3_" + slug(s["name"])
        sector_ids[s["record"]] = sid
        st_races, levels = [], []
        for li, lv in enumerate(s["levels"]):
            cands = [e for e in lv["entities"] if station_race(e)]
            if not cands:
                cands = [e for e in lv["entities"] if "/structures/" in e["shape"] and "/stations/" in e["shape"]]
            # the level's most common station race (Mining as Terran's company stations count apart), then its biggest
            rc = collections.Counter(station_race(e) for e in cands if station_race(e))
            if rc:
                top = max(rc, key=lambda r: (rc[r], r != "Pirates"))
                cands = [e for e in cands if station_race(e) == top]
            best = None
            for e in cands:
                h = hashlib.md5(e["shape"].encode()).hexdigest()[:10]
                info, glb = conv(e["shape"], f"{tmp}/{h}.glb")
                if not info: continue
                ext = float(np.max(np.array(info["max"]) - np.array(info["min"])))
                if best is None or ext > best[0]: best = (ext, e, info, glb)
            gates = [e for e in lv["entities"] if e["name"].startswith("JumpGate") and any("JumpGate_Base" in t for t in e["templates"])]
            for g in gates:
                r = next((m.group(1).lower() for t in g["templates"] if (m := re.match(r"Template_(\w+?)_JumpGate_Base", t))), None)
                if r: gate_races.setdefault(sid, collections.Counter())[r] += 1; gate_races.setdefault("_shape_" + r, g["shape"])
            levels.append((lv, best))
            if best: st_races.append(station_race(best[1]) or "Mining")
        counts = collections.Counter(r for r in st_races if RACES.get(r) is not None)
        race_name = max(counts, key=lambda r: (counts[r], -["Terran", "Mining", "Vossk", "Nivelian"].index(r))) if counts else "Terran"
        pirates = sum(1 for r in st_races if r == "Pirates")
        security = max(0, min(3, SECURITY_BASE[cl] - (2 if st_races and pirates * 2 >= len(st_races) else 1 if pirates else 0)))
        order = s["order"] if s["order"] is not None else 2
        tech = max(1, min(10, round(1 + order * 0.45)))
        sys_entry = {"id": sid, "name": title(s["name"]), "race": RACES[race_name], "security": security, "visible": True,
                     "position": map_pos(s["star"]), "sky": GOF2_SKY[cl], "gates": []}
        first_station = None
        for li, (lv, best) in enumerate(levels):
            stid = "gof3_" + slug(lv["record"].replace(" - ", "_"))
            name = title(lv["name"] or lv["record"])
            st = {"id": stid, "system": f"{MOD_ID}:{sid}", "name": name, "techLevel": tech,
                  "planet": PLANETS[int(hashlib.md5(stid.encode()).hexdigest(), 16) % len(PLANETS)]}
            if best:
                ext, e, info, glb = best
                race = station_race(e) or "Mining"
                dst = f"models/stations/{stid}.glb"
                shutil.copyfile(glb, f"{out}/{dst}")
                for key, g in info["groups"].items():
                    gg = groups.setdefault(key, {k: v for k, v in g.items() if k != "models"} | {"models": set()})
                    gg["models"] |= set(g["models"])
                # GoF3 docks at no station: its missions start from the galaxy map and "dock" only ever means the
                # Manticore (the GoF3 Ships mod's mobile station, which roams these systems too), so none docks here
                st.update({"model": dst, "modelSize": int(min(MAX_STATION, max(MIN_STATION, ext * K))), "collision": "box",
                           "orbit": {"station": "nodock"}, "subtitle": SUBTITLE[race],
                           "materials": [{"material": f"gof3[{k}]"} for k in sorted(info["groups"])]})
                if race == "Pirates": st["subtitle"] = "Pirate hideout"
                first_station = first_station or stid
            else:
                st["orbit"] = {"station": False}; st["subtitle"] = "Deep space"
            if li == 0 and s["desc"]: st["description"] = s["desc"]
            stations.append(st)
        if first_station: sys_entry["gateStation"] = f"{MOD_ID}:{first_station}"
        # the sky and sun of the sector's first level with a skybox
        for lv, _ in levels:
            sky = next((e for e in lv["entities"] if "/skyboxes/" in e["shape"]), None)
            if not sky: continue
            png = f"sky/{sid}.png"
            if any(sky_strip.convert(m, f"{out}/{png}", assets) for m in sky_materials(sky["shape"], assets)):
                sys_entry["skybox"] = {"nebula": png, "stars": 1, "nebulaBrightness": 1.0}
            suns = [e for e in lv["entities"] if "/suns/" in e["shape"]]
            if suns:
                sun = max(suns, key=lambda e: max(e.get("scale") or [1]))
                spng = f"textures/suns/{sid}.png"
                tint = sun_png(sun, assets, f"{out}/{spng}")
                if tint: sys_entry["sunTexture"] = spng; sys_entry["sunColor"] = [min(1, max(0.25, v)) for v in tint]
            break
        systems.append((s, sys_entry))
    # the gates: each system's nearest neighbours in its cluster, the clusters to each other, Trim's Anchorage to Me'enkk
    pos = {e["id"]: np.array(gof3_galaxy.STAR_NODES[s["star"]]) for s, e in systems}
    by_cluster = collections.defaultdict(list)
    for s, e in systems: by_cluster[cluster_of(s)].append(e["id"])
    links = set()
    def link(x, y): links.add(tuple(sorted((x, y))))
    for cl, ids in by_cluster.items():
        done = {ids[0]}
        while len(done) < len(ids):   # a minimum spanning tree
            x, y = min(((x, y) for x in done for y in ids if y not in done), key=lambda p: np.linalg.norm(pos[p[0]] - pos[p[1]]))
            link(x, y); done.add(y)
        for x in ids:                 # and each one's second nearest, for a loop or two
            near = sorted((y for y in ids if y != x), key=lambda y: np.linalg.norm(pos[x] - pos[y]))
            if len(near) > 1 and np.linalg.norm(pos[x] - pos[near[1]]) < 120: link(x, near[1])
    def bridge(c1, c2):
        if c1 in by_cluster and c2 in by_cluster:
            x, y = min(((x, y) for x in by_cluster[c1] for y in by_cluster[c2]), key=lambda p: np.linalg.norm(pos[p[0]] - pos[p[1]]))
            link(x, y)
    bridge("Trim", "Porros"); bridge("Porros", "Rigant"); bridge("Trim", "Rigant")
    for s, e in systems:
        e["gates"] = [f"{MOD_ID}:{y if x == e['id'] else x}" for x, y in sorted(links) if e["id"] in (x, y)]
        if s["record"].startswith("Trim_000_A"): e["gates"].append(MEENKK)
    # jumpgates: GoF3's gate model of the race whose gates the sector's missions use
    gate_models = {}
    for r in ("terran", "vossk", "nivelian"):
        shape = gate_races.get("_shape_" + r)
        if not shape: continue
        info, glb = conv(shape, f"{tmp}/gate_{r}.glb")
        if not info: continue
        shutil.copyfile(glb, f"{out}/models/gates/{r}.glb")
        for key, g in info["groups"].items():
            gg = groups.setdefault(key, {k: v for k, v in g.items() if k != "models"} | {"models": set()})
            gg["models"] |= set(g["models"])
        gate_models[r] = {"model": f"models/gates/{r}.glb", "size": GATE_SIZE[r],
                          "materials": [{"material": f"gof3[{k}]"} for k in sorted(info["groups"])]}
    for s, e in systems:
        c = gate_races.get(e["id"])
        r = c.most_common(1)[0][0] if c else {0: "terran", 1: "vossk", 2: "nivelian"}.get(e["race"], "terran")
        if r in gate_models: e["jumpgate"] = dict(gate_models[r])
    # GoF3's hub traffic (gof3_world): its ships' props baked like the stations, as ships.json hulls the npcships fly
    import gof3_world
    world = gof3_world.World(a.pdb)
    hulls = []
    for hid, name, race, folder in gof3_world.traffic_hulls(world, assets):
        scene = gof3_world.scene_of(folder)
        if not scene: continue
        info, glb = conv("/assets" + scene[len(assets):], f"{tmp}/traffic_{hid}.glb")
        if not info: continue
        os.makedirs(f"{out}/models/traffic", exist_ok=True)
        shutil.copyfile(glb, f"{out}/models/traffic/{hid}.glb")
        for key, g in info["groups"].items():
            gg = groups.setdefault(key, {k: v for k, v in g.items() if k != "models"} | {"models": set()})
            gg["models"] |= set(g["models"])
        size = np.array(info["max"]) - np.array(info["min"])
        hulls.append({"id": f"{hid}_hull", "name": name, "race": gof3_world.RACE_ID[race], "armor": 600, "cargo": 200,
                      "handling": 60, "price": 0, "slots": {"primary": 0, "secondary": 0, "turret": 0, "equipment": 0},
                      "model": f"models/traffic/{hid}.glb", "modelLength": int(round(float(size[2]) * K)), "modelYaw": 180,
                      # (the game's own freighter rotation never picks them: only their npcships.json groups fly them)
                      "traffic": {"capital": "freighter", "weight": 0},
                      "materials": [{"material": f"gof3[{k}]"} for k in sorted(info["groups"])]})
    # the baked atlases, then every material entry pointed at its textures
    tex = {}
    for key, g in sorted(groups.items()):
        print("bake", key, len(g["models"]), "parts")
        t = scene_glb.bake_group(key, g, g["models"], f"{out}/textures/gof3", a.atlas)
        tex[key] = t
    def fill(mats):
        for m in mats:
            key = m["material"][5:-1]
            t = tex.get(key, {})
            kind = groups[key]["kind"]
            m["diffuse"] = f"textures/gof3/{t['diffuse']}" if t.get("diffuse") else None
            if t.get("emission"): m["emission"] = f"textures/gof3/{t['emission']}"; m["emissionColor"] = [1, 1, 1]
            if kind == "bake":
                # GoF3's specular colour and gloss (RGB / A) and its normal map, baked like the colour
                m["specularGlossiness"] = f"textures/gof3/{t['specularGlossiness']}"
                m["normal"] = f"textures/gof3/{t['normal']}"
                m["smoothness"] = 1.0
            elif kind == "own":
                v = t["values"]
                m["specularColor"] = v["specular"]; m["smoothness"] = v["smoothness"]
                if v["alpha"] == "MASK": m["alphaClip"] = v["cutoff"]
                else: m["opacity"] = min(v["opacity"], 0.999)   # blended by the texture's alpha (glass, decals)
                if v["doubleSided"]: m["doubleSided"] = True
            else:
                m["smoothness"] = 0.1; m["metallic"] = 0.0
            for k in [k for k, v in m.items() if v is None]: del m[k]
    for st in stations: fill(st.get("materials", []))
    for _, e in systems:
        if "jumpgate" in e: fill(e["jumpgate"]["materials"])
    for h in hulls: fill(h["materials"])
    if hulls: json.dump(hulls, open(f"{out}/ships.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump([e for _, e in systems], open(f"{out}/systems.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(stations, open(f"{out}/stations.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    man = {"id": MOD_ID, "name": "Galaxy on Fire 3 Systems", "version": "1.0.0", "author": "gof3_ships_importer",
           "description": "Galaxy on Fire 3's sectors as star systems: Trim, Porros and Rigant with GoF3's own stations, "
                          "jumpgates, skies and suns; as in GoF3, none of them docks (the Manticore of the GoF3 Ships mod does)."}
    json.dump(man, open(f"{out}/mod.json", "w", encoding="utf-8"), indent=1)
    # GoF3's own lights, fog, skies (their colours, stars and fog) and suns per level (gof3_look)
    import gof3_look
    gof3_look.apply(out, a.pdb, assets)
    # each orbit's asteroid field and planet, the hubs' traffic, the clusters' music (gof3_world)
    gof3_world.apply(out, a.pdb, assets, world=world)
    shutil.rmtree(tmp, ignore_errors=True)
    print(len(systems), "systems,", len(stations), "stations,", len(groups), "atlases")


if __name__ == "__main__":
    main()
