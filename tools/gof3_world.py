"""Galaxy on Fire 3's hubs as the gof3_systems mod's orbits: their traffic, asteroid fields, planets and music, from
data.pdb (field ids from the protobuf schema in libgofm.so) and the game's sound banks. build_gof3_systems runs it; on its
own it redoes a built mod's orbits (not the traffic hulls' models, which are baked with the stations).

- Traffic (traffic(), hull_entries(), npcships()): GoF3's hub traffic is no level entity but the level's event scripts
  (Location.eventScript 2769012 / eventScriptObjects 673082, "SmallShipsNNN_Route_script"): SpawnEntities (3812436 the ship,
  1079566 the count) at a zone, then FollowRoute REPEATING round a route of waypoints (Location.route 8905672). Eight of the
  68 levels have some: mining ships, the Vossk traders and miners, the Terran transports, the Morpheus freighters. As
  npcships.json freighters (the remake's flies straight on; GoF3's loops are lost), their hulls GoF3's props, baked like
  the stations (scene_glb).
- Asteroid fields (fields(), orbit_patch()): Field entities (form, dimension, items) and the asteroids GoF3 really places, in
  merged/cache.field/<level id>.pb (cache.field.FieldsCache, one leaf per asteroid). One field per orbit: the count, the
  fields' centre and reach (scaled into the remake's ~10 km orbit), the type by the asteroid family, the ores: GoF3's
  OreType names are GoF2's items (Iron 156, Doxtrite 160, Cesogen 161, Pyresium 158, Novanium 217); only Anchorage H4 has
  an OreDistribution (Iron 1400, Doxtrite 900, Cesogen), the families' ores elsewhere are this importer's pick.
- Planets (planets(), render_planet()): camera-attached hemispheres (CameraAttachmentSystem::update_: camera +
  distanceFactor x position): the main one's direction and angular size as the orbit's "planet" (size ~ 1.503 tan(angle),
  the remake's planet quad; past 60 degrees, a horizon, it can't show), its picture (lit disc) as the station's
  planetTexture.
- Music (music()): each level's Location audioMusicEvent is its cluster's (event:/music/music_porros / _rigant / _trim);
  the cluster's calm layer, music_stream_<cluster>.bank's area_arrival1-5, joined with crossfades as the systems'
  spaceMusic."""
import collections, glob, json, math, os, re, shutil, struct, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import gof3_galaxy, gof3_look

RACE_NAME = {2: "LocationNative", 3: "Terran", 4: "Vossk", 5: "Inouac", 6: "Nivelian", 7: "Pirates"}
FORM = {1: "Sphere", 2: "Box", 3: "Cylinder", 4: "Line", 5: "Plane"}
ORE_NAME = {1: "Iron", 2: "Doxtrite", 3: "Cesogen", 4: "Pyresium", 5: "Novanium"}
ORE_ITEM = {"Iron": 156, "Doxtrite": 160, "Cesogen": 161, "Pyresium": 158, "Novanium": 217}
# GoF3's asteroid families: the remake's field type, and the ores (a pick: GoF3 shipped without mining but Anchorage H4's)
FIELD_TYPE = {"marleen/rust": "rock", "marleen/rock": "rock", "slate/rock": "rock", "megalith/rock": "rock",
              "obsidian/rock": "rock", "moon/rock": "rock", "megalith/snow": "ice", "magma/molten": "magma",
              "magma/crust": "magma", "marleen/lavacrack": "magma", "obsidian/plasma": "magma"}
FIELD_ORES = {"marleen/rust": [156, {"item": 160, "chance": 2}], "marleen/rock": [156, 160], "slate/rock": [160, 161],
              "megalith/rock": [156, 161], "obsidian/rock": [161, {"item": 217, "chance": 0.2}], "moon/rock": [156, 160],
              "megalith/snow": [161, {"item": 160, "chance": 0.5}], "magma/molten": [158], "magma/crust": [158, 156],
              "marleen/lavacrack": [158, {"item": 156, "chance": 0.5}], "obsidian/plasma": [158, {"item": 217, "chance": 0.3}]}
ORBIT_REACH = 150000.0      # game units: the farthest field or route at most this far out (the remake's orbit, ~10 km)
# GoF3's traffic ships: (hull id, name, race, prop scene under structures/, length in game units)
TRAFFIC = {"Ship_NPC_Mining_Mining_000": ("gof3_mining_ship", "Mining Ship", "terran", "mining/geometry/props/miningships/000"),
           "Ship_NPC_Vossk_Mining_000": ("gof3_vossk_mining_ship", "Vossk Mining Ship", "vossk", "vossk/geometry/props/miningships/000"),
           "Ship_NPC_Vossk_Trading_000": ("gof3_vossk_trader", "Vossk Trader", "vossk", "vossk/geometry/props/tradingships/000"),
           "Ship_NPC_Terran_Traffic_000": ("gof3_terran_shuttle", "Terran Transport", "terran", "terran/geometry/props/trafficships/000")}
MORPHEUS = "Ship_NPC_Terran_000_Freighter_Morpheus_Location_Traffic"   # GoF3 Ships' capital_terran_000
RACE_ID = {"terran": 0, "vossk": 1, "nivelian": 2}
K = gof3_look.K
MUSIC_CLUSTERS = ("porros", "rigant", "trim")


def slug(s): return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def station_id(level_record): return "gof3_" + slug(level_record.replace(" - ", "_"))


class World:
    """One read of data.pdb for all of it."""

    def __init__(self, pdb):
        self.G = gof3_galaxy.Galaxy(pdb)
        self.R = self.G.R
        self.pdb = pdb
        self.levels = {}
        for s in self.G.sectors():
            for lv in s["levels"]: self.levels[lv["record"]] = dict(lv, sector=s)

    def nm(self, r): return (self.R.name(r) or "?").strip()

    def ref(self, v):
        try: s = self.R.sub(v)
        except Exception: return None
        t = s.get(1)
        return t if isinstance(t, int) and t in self.R.p.recs else None

    # ------------------------------------------------------------ traffic

    def ship_info(self, rid):
        comps, chain = self.R.resolved(rid)
        sh = comps.get("Shape", {}).get(7803720, [b""])[0].decode("latin1")
        return {"record": self.nm(rid), "shape": sh, "race": RACE_NAME.get(comps.get("Identity", {}).get(9536365, [None])[0])}

    def traffic(self, lid):
        """{"spawns": [{record, count}], "routes": [{name, waypoints}]} of a level's event scripts."""
        R = self.R
        _, lf = self.G.level_fields(lid)
        out = {"spawns": [], "gets": set(), "routes": []}
        seen = set()
        def walk(root):
            if root in seen or root not in R.p.recs: return
            seen.add(root)
            f = R.fields(root)
            if 3812436 in f and (1079566 in f or 2002065 in f):
                what = self.ref(f[3812436][0])
                if what: out["spawns"].append({"record": self.nm(what), "count": f.get(1079566, [1])[0], **self.ship_info(what)})
                return
            if 9873224 in f: out["gets"].add(f[9873224][0].decode("utf8", "replace"))
            for k, vs in f.items():
                if k in (1469832, 5181810): continue
                for v in vs:
                    if isinstance(v, (bytes, bytearray)) and len(v) < 40:
                        t = self.ref(v)
                        if t: walk(t)
        for x in lf.get(2769012, []) + lf.get(673082, []):
            r = self.ref(x)
            if r: walk(r)
        for x in lf.get(8905672, []):
            r = self.ref(x)
            if not r or self.nm(r) not in out["gets"]: continue
            comps, _ = R.resolved(r)
            pts = []
            for w in comps.get("Path", {}).get(924776, []):
                wid = self.ref(w)
                if not wid: continue
                wc, _ = R.resolved(wid)
                if 6503637 in wc.get("Transform", {}): pts.append(self.G.vec(wc["Transform"][6503637][0]))
            out["routes"].append({"name": self.nm(r), "waypoints": pts})
        out["gets"] = sorted(out["gets"])
        return out

    # ------------------------------------------------------------ fields

    def fields(self, lid, merged):
        """The level's Field entities (name, pos, dimension) and its cache's placed asteroids per field (count, kinds)."""
        R = self.R
        _, lf = self.G.level_fields(lid)
        fl = []
        for e in lf.get(gof3_galaxy.L_ENT, []):
            eid = self.ref(e)
            if not eid: continue
            try: comps, _ = R.resolved(eid)
            except Exception: continue
            if "Field" not in comps: continue
            tr = comps.get("Transform", {}); f = comps["Field"]
            fl.append({"name": self.nm(eid), "pos": self.G.vec(tr[6503637][0]) if 6503637 in tr else [0, 0, 0],
                       "form": FORM.get(f.get(6271188, [None])[0]), "dimension": self.G.vec(f[5180477][0]) if 5180477 in f else None})
        return {"fields": fl, "cache": self._cache(lid, merged)}

    def _cache(self, lid, merged):
        R = self.R
        p = os.path.join(merged, "cache.field", f"{lid}.pb")
        if not os.path.exists(p): return []
        def walk_node(b, off, leaves):
            t = np.array(off, float); kids = []; leaf = None
            for f, w, v in R.parse(b):
                if f == 1:
                    for f2, w2, v2 in R.parse(v):
                        if f2 == 2: t = t + np.array([R.sub(v2).get(k, 0.0) for k in (1, 2, 3)])
                elif f == 2: kids.append(v)
                elif f == 3: leaf = R.sub(v).get(1)
            if leaf is not None: leaves.append((leaf, t.tolist()))
            for k in kids: walk_node(k, t.tolist(), leaves)
        out = []
        for f, w, v in R.parse(open(p, "rb").read()):
            if f != 2: continue
            fd = R.parse(v); fuid = next((x for k, _, x in fd if k == 1), None)
            leaves = []
            for k, _, x in fd:
                if k == 3: walk_node(x, [0, 0, 0], leaves)
            if not leaves: continue
            pts = np.array([q for _, q in leaves])
            kinds = collections.Counter()
            for u, _ in leaves:
                sh = None
                if u in R.p.recs:
                    try: sh = self.R.resolved(u)[0].get("Shape", {}).get(7803720, [b""])[0].decode("latin1").replace("/assets/", "")
                    except Exception: sh = None
                kinds[(sh or self.nm(u)).replace("asteroids/geometry/", "").rsplit("/", 1)[0]] += 1
            out.append({"field": self.nm(fuid) if fuid in R.p.recs else fuid, "count": len(leaves),
                        "centre": ((pts.min(0) + pts.max(0)) / 2).tolist(), "extent": (pts.max(0) - pts.min(0)).tolist(),
                        "kinds": dict(kinds)})
        return out

    def ores(self):
        """{level id: [(GoF2 item, mass)]} of the OreDistribution records (Anchorage H4's alone)."""
        R = self.R; out = collections.defaultdict(list)
        for rid in R.p.recs:
            try: f = R.fields(rid)
            except Exception: continue
            if 2166687 not in f: continue
            loc = R.sub(f[2166687][0]).get(1)
            for t, m in ((3457417, 4301087), (4149517, 4993219), (3918817, 4762519)):
                if t in f:
                    ore = ORE_NAME.get(f[t][0])
                    if ore: out[loc].append((ORE_ITEM[ore], f.get(m, [None])[0]))
        return out

    # ------------------------------------------------------------ planets

    def planets(self, lid):
        """The level's planets: name, shape, pos, scale, distanceFactor, colorize; the main one first (the biggest that
        isn't a moon)."""
        R = self.R
        _, lf = self.G.level_fields(lid)
        out = []
        for e in lf.get(gof3_galaxy.L_ENT, []):
            eid = self.ref(e)
            if not eid: continue
            try: comps, _ = R.resolved(eid)
            except Exception: continue
            shape = comps.get("Shape", {}).get(7803720, [b""])[0].decode("latin1")
            if "/planets/" not in shape: continue
            tr = comps.get("Transform", {})
            c = comps.get("Colorize", {})
            def col(k): return [x / 255.0 for x in (R.sub(c[k][0]).get(i, 255) for i in (1, 2, 3))] if k in c else None
            out.append({"name": self.nm(eid), "shape": shape,
                        "pos": self.G.vec(tr[6503637][0]) if 6503637 in tr else [0, 0, 0],
                        "scale": self.G.vec(tr[7443144][0]) if 7443144 in tr else [1, 1, 1],
                        "distanceFactor": float(tr[3236628][0]) if 3236628 in tr else 1.0,
                        "attached": bool(tr.get(2251614, [0])[0]), "colors": (col(4315724), col(4315725)),
                        "moon": "/moon/" in shape or "moon" in self.nm(eid).lower()})
        return out


# ---------------------------------------------------------------- traffic into the mod

def traffic_hulls(world, assets):
    """The traffic ships the hubs spawn: [(hull id, name, race, prop scene path)] (one per kind, any level)."""
    kinds = {}
    for lv in world.levels.values():
        for sp in world.traffic(lv["id"])["spawns"]:
            t = TRAFFIC.get(sp["record"])
            if t: kinds[t[0]] = (t[0], t[1], t[2], f"{assets}/structures/{t[3]}")
    return sorted(kinds.values())


def scene_of(folder):
    """A prop folder's scene (.ae4scene)."""
    s = sorted(glob.glob(os.path.join(folder, "*.ae4scene")))
    return s[0] if s else None


def npcships(world, station_ids, hulls):
    """npcships.json: per traffic kind and station, freighters as many as GoF3 spawns there."""
    have = {h for h, *_ in hulls}
    out = []
    for rec, lv in world.levels.items():
        sid = station_id(rec)
        if sid not in station_ids: continue
        counts = collections.Counter()
        for sp in world.traffic(lv["id"])["spawns"]: counts[sp["record"]] += sp["count"]
        for record, n in sorted(counts.items()):
            if record in TRAFFIC and TRAFFIC[record][0] in have:
                hid, name, race, _ = TRAFFIC[record]
                ship = f"gof3_systems:{hid}_hull"
            elif record == MORPHEUS:
                hid, name, race, ship = "gof3_morpheus", "Morpheus", "terran", "gof3_ships:capital_terran_000"
            else: continue
            out.append({"id": f"{hid}_{sid[5:]}", "kind": "freighter", "ship": ship, "name": name, "race": race, "speed": 2,
                        "escorts": {"count": 0},
                        "loot": {"items": [{"item": 156 if "ining" in record else 116, "amount": [3, 8]}]},
                        "spawn": {"chance": 100, "stations": [f"gof3_systems:{sid}"], "count": int(n)}})
    return out


# ---------------------------------------------------------------- orbits: asteroids, planets

def _glb_extent(path):
    d = open(path, "rb").read(); n = struct.unpack_from("<I", d, 12)[0]; j = json.loads(d[20:20 + n])
    mn, mx = np.full(3, 1e30), np.full(3, -1e30)
    root = j["nodes"][0]
    for node in j["nodes"][1:]:
        if "mesh" not in node: continue
        M = np.array(node.get("matrix", [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])).reshape(4, 4).T
        for pr in j["meshes"][node["mesh"]]["primitives"]:
            a = j["accessors"][pr["attributes"]["POSITION"]]
            if "min" not in a: continue
            c = np.array([[x, y, z, 1] for x in (a["min"][0], a["max"][0]) for y in (a["min"][1], a["max"][1]) for z in (a["min"][2], a["max"][2])]) @ M.T
            mn = np.minimum(mn, c[:, :3].min(0)); mx = np.maximum(mx, c[:, :3].max(0))
    return root.get("name"), float((mx - mn).max()) if mx[0] > mn[0] else 1.0


def orbit_patch(world, lv, st, out, merged, ores_by_level):
    """The station's orbit "asteroids" and "planet" from GoF3's level, and its planet's picture (None: none)."""
    spos, W = np.zeros(3), 40.0
    if "model" in st:
        name, ext = _glb_extent(f"{out}/{st['model']}")
        W = st["modelSize"] / max(ext, 1e-6)
        e = next((x for x in lv["entities"] if (x.get("shape") or "").endswith("/" + (name or "") + ".ae4scene")), None)
        if e and e.get("pos"): spos = np.array(e["pos"])   # the station entity the model was baked from
    fd = world.fields(lv["id"], merged); tr = world.traffic(lv["id"])
    cache = [c for c in fd["cache"] if not any(k.startswith(("structures", "?")) for k in c["kinds"])]
    fl = [f for f in fd["fields"] if not any(k in f["name"].lower() for k in ("wreck", "junk", "hulk", "debris"))]
    if not fl and cache: fl = [{"name": str(c["field"]), "pos": c["centre"], "dimension": c["extent"]} for c in cache]
    pts = [np.array(f["pos"]) for f in fl] + [np.array(w) for r in tr["routes"] for w in r["waypoints"]]
    F = min(W, ORBIT_REACH / max([np.linalg.norm(p - spos) for p in pts] + [1.0]))   # game units per GoF3 unit
    patch = {}
    n = sum(c["count"] for c in cache)
    if n and fl:
        fam = collections.Counter()
        for c in cache:
            for k, v in c["kinds"].items(): fam["/".join(k.split("/")[:2])] += v
        top = fam.most_common(1)[0][0]
        P = np.array([f["pos"] for f in fl]); D = np.array([f["dimension"] or [0, 0, 0] for f in fl])
        centre = P.mean(0) - spos
        spread = float(max(np.linalg.norm(p - spos - centre) + d.max() / 2 for p, d in zip(P, D))) * 2 * F
        c = centre * F   # GoF3 (x, y, z) -> the orbit's game axes (-x, y, -z), as the stations' glb and the sun
        ores = ores_by_level.get(lv["id"])
        patch["asteroids"] = {"count": int(min(300, max(20, n))), "centre": [int(round(-c[0], -2)), int(round(c[1], -2)), int(round(-c[2], -2))],
                              "spread": int(round(min(200000, max(30000, spread)), -3)), "type": FIELD_TYPE.get(top, "rock"),
                              "ores": [{"item": i, "chance": m or 300} for i, m in ores] if ores else FIELD_ORES.get(top, [156])}
    pl = [p for p in world.planets(lv["id"]) if np.linalg.norm(p["pos"]) > 0]
    # the biggest planet first, the moons after (the first that renders as a hemisphere is the orbit's: render())
    return patch, sorted(pl, key=lambda p: (p["moon"], -_angular(p)))


def _sky_turn(orbit):
    """R, the level's sky turn, back from the orbit's "skyRotation" (Q = S R S as Unity's Euler: Ry Rx Rz)."""
    a, b, c = [math.radians(v) for v in (orbit.get("skyRotation") or [0, 0, 0])]
    def R(axis, t):
        cs, sn = math.cos(t), math.sin(t)
        return {"x": np.array([[1, 0, 0], [0, cs, -sn], [0, sn, cs]]), "y": np.array([[cs, 0, sn], [0, 1, 0], [-sn, 0, cs]]),
                "z": np.array([[cs, -sn, 0], [sn, cs, 0], [0, 0, 1]])}[axis]
    S = np.diag([-1.0, 1.0, 1.0])
    return S @ (R("y", b) @ R("x", a) @ R("z", c)) @ S


def paint_planets(out, st, planets, assets, world, lv, log=print):
    """Each planet rendered with GoF3's shader (gof3_planets.render, its view: forward f the planet's direction, right
    r = up x f, up u = f x r) and pasted into the orbit's sky strip: a strip pixel p looks along d = R S p in the level, its
    place on the disc (d.r / d.f, d.u / d.f) / tan(angular radius). The orbit gets its own sky and stars copies (no stars in
    front of a planet)."""
    import gof3_planets, tempfile
    from PIL import Image
    orbit = st["orbit"]; sky = orbit["skybox"]
    neb_rel = f"sky/{st['id']}.png"
    if sky["nebula"] != neb_rel: shutil.copyfile(f"{out}/{sky['nebula']}", f"{out}/{neb_rel}")
    neb = np.asarray(Image.open(f"{out}/{neb_rel}").convert("RGB")).astype(np.float32) / 255
    n = neb.shape[0]
    g = (np.arange(n) + 0.5) / n
    U, V = np.meshgrid(g, g)
    Rt = _sky_turn(orbit); S = np.diag([-1.0, 1.0, 1.0])
    cover = np.zeros(neb.shape[:2], np.float32)
    painted = 0
    for p in planets:
        tmp = tempfile.mktemp(suffix=".png")
        try:
            if not gof3_planets.render(p, assets, tmp, world, lv): continue
            disc = np.asarray(Image.open(tmp).convert("RGBA")).astype(np.float32) / 255
        finally:
            if os.path.exists(tmp): os.remove(tmp)
        f = np.array(p["pos"], float); f /= np.linalg.norm(f)
        up = np.array([0.0, 1.0, 0.0]) if abs(f[1]) < 0.99 else np.array([0.0, 0.0, 1.0])
        r = np.cross(up, f); r /= np.linalg.norm(r); u = np.cross(f, r)
        t = math.tan(math.radians(_angular(p)))
        size = disc.shape[0]; half = size * gof3_planets.FILL / 2
        for face in range(6):
            pts = sky_strip_points(face, U, V)                       # strip-frame directions (n, n, 3)
            d = pts.reshape(-1, 3) @ (Rt @ S).T
            fd = d @ f
            ok = fd > 1e-6
            x = np.where(ok, (d @ r) / np.where(ok, fd, 1), 9e9) / t
            y = np.where(ok, (d @ u) / np.where(ok, fd, 1), 9e9) / t
            inside = (x * x + y * y) <= 1.05
            if not inside.any(): continue
            ix = np.clip((size / 2 + x * half).astype(int), 0, size - 1); iy = np.clip((size / 2 - y * half).astype(int), 0, size - 1)
            px = disc[iy, ix]; a = np.where(inside, px[:, 3], 0.0).reshape(n, n)
            sl = neb[:, face * n:(face + 1) * n]
            sl[:] = sl * (1 - a[..., None]) + px[:, :3].reshape(n, n, 3) * a[..., None]
            cover[:, face * n:(face + 1) * n] = np.maximum(cover[:, face * n:(face + 1) * n], a)
        painted += 1
    if not painted:
        if sky["nebula"] != neb_rel: os.remove(f"{out}/{neb_rel}")
        return 0
    Image.fromarray((np.clip(neb, 0, 1) * 255 + 0.5).astype(np.uint8)).save(f"{out}/{neb_rel}")
    sky["nebula"] = neb_rel
    if isinstance(sky.get("stars"), str):
        stars_rel = f"sky/{st['id']}_stars.png"
        s_im = Image.open(f"{out}/{sky['stars']}").convert("RGB")
        m = Image.fromarray((cover * 255).astype(np.uint8)).resize(s_im.size, Image.BILINEAR)
        s = np.asarray(s_im).astype(np.float32) * (1 - np.asarray(m).astype(np.float32)[..., None] / 255)
        Image.fromarray(s.astype(np.uint8)).save(f"{out}/{stars_rel}")
        sky["stars"] = stars_rel
    log(f"  {st['id']}: {painted} planets / moons in its sky")
    return painted


def sky_strip_points(face, U, V):
    """The strip face's directions (Unity's axes, the strip's frame) at (u, v) 0..1, v down (sky_strip._face_points)."""
    a, b = U - 0.5, V - 0.5
    h = np.full_like(a, 0.5)
    return [np.stack([h, -b, -a], -1), np.stack([-h, -b, a], -1), np.stack([a, h, b], -1),
            np.stack([a, -h, -b], -1), np.stack([a, -b, h], -1), np.stack([-a, -b, -h], -1)][face]


def planet_entry(p):
    """The orbit's "planet" for a GoF3 planet: its direction, and its size against the remake's planet quad (up to 60
    degrees of angular radius; a bigger one is a horizon the remake can't show)."""
    yaw, pitch = gof3_look.direction(p["pos"])
    return {"size": round(1.503 * math.tan(math.radians(min(60.0, _angular(p)))), 2), "yaw": yaw, "pitch": pitch}


_radius = {}


def _mesh_radius(shape, assets):
    if shape in _radius: return _radius[shape]
    import ae4_meshgroup
    path = assets + shape[len("/assets"):]
    r = None
    for mg in sorted(glob.glob(os.path.dirname(path) + "/*.ae4meshgroup")):
        if any(k in os.path.basename(mg) for k in ("corona", "atmo", "cloud", "fog", "flash", "ring", "swirl", "collision", "shadow", "fx", "glow")): continue
        try:
            pts = np.concatenate([np.asarray(s["a_position"]).reshape(-1, 3) for s in ae4_meshgroup.read_all(mg)])
            r = max(r or 0, float(np.max(np.linalg.norm(pts - (pts.max(0) + pts.min(0)) / 2, axis=1))))
        except Exception: pass
    _radius[shape] = r or 1.0
    return _radius[shape]


_ASSETS = [None]


def _angular(p):
    """A planet's angular radius in degrees from the camera (camera + distanceFactor x position)."""
    d = float(np.linalg.norm(p["pos"])) * (p["distanceFactor"] if p["attached"] else 1.0)
    return math.degrees(math.atan2(_mesh_radius(p["shape"], _ASSETS[0]) * max(p["scale"]), max(d, 1.0)))


# ---------------------------------------------------------------- music

def music(merged, out, log=print):
    """music/gof3_<cluster>_space.ogg: the cluster's area_arrival1-5 (music_stream_<cluster>.bank) joined with 4 s
    crossfades; returns {cluster: track name}."""
    import gof3_sounds
    vg, ff = shutil.which("vgmstream-cli"), shutil.which("ffmpeg")
    if not vg or not ff:
        log("  music: vgmstream-cli and ffmpeg are needed (the systems keep the game's music)"); return {}
    os.makedirs(f"{out}/music", exist_ok=True)
    tracks = {}
    for cl in MUSIC_CLUSTERS:
        bank = os.path.join(merged, "sound", f"music_stream_{cl}.bank")
        if not os.path.exists(bank): continue
        folder = gof3_sounds.decode_bank(bank)
        if not folder: continue
        waves = {os.path.splitext(f)[0].lower(): os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".wav")}
        # (Porros and Rigant name theirs with a version: MC_mus_porros_area_arrival1_v2)
        parts = [w for i in range(1, 6) for w in [next((p for n, p in sorted(waves.items()) if re.search(rf"area_arrival{i}(_v\d+)?$", n)), None)] if w]
        if not parts: continue
        name = f"gof3_{cl}_space"
        cmd = [ff, "-y", "-v", "error"]
        for p in parts: cmd += ["-i", p]
        if len(parts) > 1:
            chain, prev = [], "[0:a]"
            for i in range(1, len(parts)):
                lab = f"[a{i}]" if i < len(parts) - 1 else "[out]"
                chain.append(f"{prev}[{i}:a]acrossfade=d=4:c1=tri:c2=tri{lab}"); prev = lab
            cmd += ["-filter_complex", ";".join(chain), "-map", "[out]"]
        cmd += ["-c:a", "libvorbis", "-q:a", "5", f"{out}/music/{name}.ogg"]
        if subprocess.run(cmd).returncode == 0: tracks[cl] = name; log(f"  music {name}: {len(parts)} parts")
    return tracks


def cluster_of(level_record): return level_record.split("_")[0].lower()


# ---------------------------------------------------------------- all of it on a built mod

def apply(out, pdb, assets, log=print, world=None, music_too=True):
    """The orbits' asteroids, planets (and their pictures) and the systems' music on a built gof3_systems; npcships.json
    for the traffic whose hulls the mod has (ships.json)."""
    merged = os.path.dirname(assets.rstrip("/"))
    world = world or World(pdb)
    _ASSETS[0] = assets
    stations = json.load(open(f"{out}/stations.json", encoding="utf-8"))
    systems = json.load(open(f"{out}/systems.json", encoding="utf-8"))
    by_id = {s["id"]: s for s in stations}
    ores = world.ores()
    import gof3_planets
    for rec, lv in world.levels.items():
        st = by_id.get(station_id(rec))
        if st is None: continue
        patch, candidates = orbit_patch(world, lv, st, out, merged, ores)
        orbit = st.setdefault("orbit", {})
        if "asteroids" in patch: orbit["asteroids"] = patch["asteroids"]
        else: orbit.pop("asteroids", None)
        orbit.pop("planet", None); st.pop("planetTexture", None)
        rel = f"textures/planets/{st['id']}.png"
        main = None
        for p in candidates[:6]:
            if gof3_planets.render(p, assets, f"{out}/{rel}", world, lv):
                orbit["planet"] = planet_entry(p); st["planetTexture"] = rel; main = p; break
        # the level's other planets and moons, painted into the orbit's own sky (the remake shows one planet)
        others = [p for p in candidates if p is not main and 0.2 < _angular(p) <= 60.0]
        if others and orbit.get("skybox"): paint_planets(out, st, others, assets, world, lv, log)
    hulls_file = f"{out}/ships.json"
    hulls = [(s["id"][:-len("_hull")],) for s in json.load(open(hulls_file, encoding="utf-8"))] if os.path.exists(hulls_file) else []
    ships = npcships(world, set(by_id), hulls)
    if ships: json.dump(ships, open(f"{out}/npcships.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if music_too and os.path.isdir(os.path.join(merged, "sound")):
        tracks = music(merged, out, log)
        sector_cluster = {}
        for rec, lv in world.levels.items():
            sid = "gof3_" + slug(lv["sector"]["name"]) if lv["sector"]["name"] else None
            if sid: sector_cluster.setdefault(sid, cluster_of(rec))
        for e in systems:
            t = tracks.get(sector_cluster.get(e["id"], ""))
            if t: e["spaceMusic"] = t
    json.dump(stations, open(f"{out}/stations.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(systems, open(f"{out}/systems.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    n_ast = sum(1 for s in stations if s.get("orbit", {}).get("asteroids"))
    n_pl = sum(1 for s in stations if s.get("planetTexture"))
    log(f"world: {n_ast} asteroid fields, {n_pl} planets, {len(ships)} traffic groups")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdb", required=True); ap.add_argument("--assets", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--no-music", action="store_true")
    a = ap.parse_args()
    apply(a.out, a.pdb, a.assets.rstrip("/"), music_too=not a.no_music)
