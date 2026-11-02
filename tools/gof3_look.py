"""Galaxy on Fire 3's look of its levels for the gof3_systems mod: each level's lights, fog, sky and sun from data.pdb, put
into a built mod's systems.json / stations.json and sky images (build_gof3_systems runs it last; on its own it redoes them
for a mod already built, without baking the stations again).

python gof3_look.py --pdb <data.pdb> --assets <assets> --out <Mods/gof3_systems>

From each level (field ids from the protobuf schema in libgofm.so: Location, Light, Colorize):
- its main light: the brightest of the Default group's (layerMask 1; the Special groups light planets and background
  props). A directional light shines from its entity's position (Rhea's sits on its sun sprites; "light - default 2"
  on the far planet), so the orbit's "sun" is that direction: yaw atan2(x, z), pitch asin(y) (GoF3's level axes, Y up,
  as the stations' glTF; glTFast mirrors x and the orbit frame mirrors z, which cancel for the yaw);
- the system's "sunColor": that light's diffuse / 255 x intensity, over the remake's LIGHT0 of 1.5, of the sector's first
  level with a sky;
- the orbit's "fog": GoF3's fog is linear from 4000 x offset to its density, which caps it (v_fog = clamp((z / 4000 -
  offset) / (1 + offset), 0, density)); the remake's runs from 0 to 1 at "end", so "end" is set where it reaches the cap at
  the same distance; no fog for density 0;
- the sky (sky_strip.convert_gof3): the sky entity's Colorize, the material's stars layer as the skybox's own "stars"
  image, the level's fog over both;
- the sun's sprite: the level's sun sprite nearest the main light, tinted by its entity's Colorize the way GoF3's sun
  shader does (t (t + c (1 - t)), c = mix(C1, C2, t)).
- the sky's turn: each station's orbit "skyRotation" from its level's sky entity (sky_rotation; the system's sky image is
  its first level's, so a level of another sky turns that one);
Left as they were: the second light, ambient and planets (the remake has no fields for them)."""
import argparse, json, math, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_ids, ae4_material, ae4_texture, gof3_galaxy, sky_strip

K = 1231.49 / 23.02                       # game units per GoF3 unit (build_gof3_systems.K)
FOG_COLOR, FOG_DENSITY, FOG_OFFSET = 9793531, 943302, 8366443
L_AMBIENT, L_DIFFUSE, L_INTENSITY, L_MASK = 1183415, 8835811, 7830468, 5964216
COLOR1, COLOR2 = 4315724, 4315725
LIGHT0 = 1.5                              # the remake's sunColor 1 = GoF2's LIGHT0 of 1.5


def slug(s): return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def level_look(G, lid):
    """{"fog": (rgb, density, offset) | None, "light": {rgb, pos} | None, "colorize": {entity name: (C1, C2)}}."""
    R = G.R
    _, lf = G.level_fields(lid)
    def one(f, k, default=None): return f[k][0] if k in f else default
    def col(b): s = R.sub(b); return [s.get(k, 255) / 255.0 for k in (1, 2, 3, 4)]
    fog = None
    if FOG_COLOR in lf and one(lf, FOG_DENSITY, 0.0) > 0:
        fog = (col(lf[FOG_COLOR][0])[:3], float(one(lf, FOG_DENSITY, 0.0)), float(one(lf, FOG_OFFSET, 0.0)))
    lights, colorize = [], {}
    for e in lf.get(gof3_galaxy.L_ENT, []):
        eid = R.sub(e).get(1)
        if eid not in R.p.recs: continue
        try: comps, _ = R.resolved(eid)
        except Exception: continue
        name = R.name(eid).strip()
        if "Colorize" in comps:
            c = comps["Colorize"]
            if COLOR1 in c or COLOR2 in c:
                colorize[name] = (col(c[COLOR1][0]) if COLOR1 in c else [1, 1, 1, 1], col(c[COLOR2][0]) if COLOR2 in c else [1, 1, 1, 1])
        if "Light" in comps:
            f = comps["Light"]
            if not (int(one(f, L_MASK, 1)) & 1): continue
            tr = comps.get("Transform", {})
            pos = G.vec(tr[gof3_galaxy.POS][0]) if gof3_galaxy.POS in tr else [0, 0, 1]
            d = col(one(f, L_DIFFUSE)) if L_DIFFUSE in f else [1, 1, 1, 1]
            i = float(one(f, L_INTENSITY, 1.0))
            lights.append({"rgb": [c * i for c in d[:3]], "pos": pos, "name": name})
    lights.sort(key=lambda l: -sum(l["rgb"]))
    return {"fog": fog, "light": lights[0] if lights else None, "colorize": colorize}


def direction(pos):
    x, y, z = pos; n = math.sqrt(x * x + y * y + z * z) or 1.0
    return [round(math.degrees(math.atan2(x, z)), 1), round(math.degrees(math.asin(max(-1.0, min(1.0, y / n)))), 1)]


def sky_rotation(rot):
    """stations.json orbit "skyRotation" (Unity Euler degrees) for a GoF3 sky entity's Transform rotation (degrees): GoF3
    turns the sky by R = Rz Ry Rx (glm::quat of the radians, x first) in its level frame, which is Unity's with x mirrored
    (S); with sky_strip's mirrored strip the remake's turn is Q = S R S, given as Unity's Quaternion.Euler (Ry Rx Rz)."""
    def R(axis, deg):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
                "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]
    x, y, z = (list(rot) + [0, 0, 0])[:3]
    S = np.diag([-1.0, 1.0, 1.0])
    Q = S @ (R("z", z) @ R("y", y) @ R("x", x)) @ S
    a = math.degrees(math.asin(max(-1.0, min(1.0, -Q[1, 2]))))
    if abs(Q[1, 2]) < 0.9999:
        b = math.degrees(math.atan2(Q[0, 2], Q[2, 2])); c = math.degrees(math.atan2(Q[1, 0], Q[1, 1]))
    else:   # x at +-90: only y - z (or y + z) is fixed
        b = math.degrees(math.atan2(-Q[2, 0], Q[0, 0])); c = 0.0
    return [round(a, 3), round(b, 3), round(c, 3)]


def fog_entry(fog):
    """The remake's orbit "fog" for GoF3's (rgb, density, offset): 1 at "end", so GoF3's cap at the same distance."""
    rgb, density, offset = fog
    cap = 4000.0 * (offset + density * (1.0 + offset))   # GoF3 units: where its fog reaches its density
    return {"color": [round(c, 3) for c in rgb], "end": int(round(max(cap, 1000.0) * K / max(density, 1e-3), -3))}


def sun_sprite(entity, colors, assets, out, light_pos=None):
    """The sun sprite's texture tinted as GoF3's sun shader does with its entity's Colorize: rgb = t (t + c (1 - t)) x
    Colorize_Multiplier, c = mix(C1, C2, t.r), on black. Returns the tint's mean colour, or None."""
    path = f"{assets}{entity['shape'][len('/assets'):]}"
    import build_gof3_systems as b
    mats = b.refs(path, assets, ".ae4material")
    if not mats:
        models = b.refs(path, assets, ".ae4model")
        mats = b.refs(models[0], assets, ".ae4material") if models else []
    if not mats: return None
    tex = b.refs(mats[0], assets, ".ae4texture")
    if not tex: return None
    v, _ = ae4_material.read(mats[0])
    c1 = np.array((colors[0] if colors else v.get("Colorize_Color1", (1, 1, 1, 1)))[:3], np.float32)
    c2 = np.array((colors[1] if colors else v.get("Colorize_Color2", (1, 1, 1, 1)))[:3], np.float32)
    mult = float(v.get("Colorize_Multiplier", 1.0))
    im = np.asarray(ae4_texture.decode(tex[0]).convert("RGBA")).astype(np.float32) / 255
    t = im[..., :3] * im[..., 3:4] * float(v.get("Opacity", 1.0) or 1.0)
    c = c1 + (c2 - c1) * t[..., :1]
    rgb = np.clip(t * (t + c * (1 - t) * mult), 0, 1)
    Image.fromarray((rgb * 255 + 0.5).astype(np.uint8)).resize((512, 512), Image.BICUBIC).save(out)
    return [round(float(x), 3) for x in (c1 + c2) / 2]


def apply(out, pdb, assets, log=print):
    systems = json.load(open(f"{out}/systems.json", encoding="utf-8"))
    stations = json.load(open(f"{out}/stations.json", encoding="utf-8"))
    by_sys = {e["id"]: e for e in systems}
    by_st = {s["id"]: s for s in stations}
    G = gof3_galaxy.Galaxy(pdb)
    import build_gof3_systems as b
    for s in G.sectors():
        sid = "gof3_" + slug(s["name"]) if s["name"] else None
        e = by_sys.get(sid)
        if e is None: continue
        sky_done = False
        for lv in s["levels"]:
            look = level_look(G, lv["id"])
            st = by_st.get("gof3_" + slug(lv["record"].replace(" - ", "_")))
            if st is not None:
                orbit = st.setdefault("orbit", {})
                if look["light"]: orbit["sun"] = direction(look["light"]["pos"])
                lsky = next((x for x in lv["entities"] if "/skyboxes/" in x["shape"]), None)
                if lsky is not None: orbit["skyRotation"] = sky_rotation(lsky.get("rot") or [0, 0, 0])
                else: orbit.pop("skyRotation", None)
                if look["fog"]: orbit["fog"] = fog_entry(look["fog"])
                else: orbit.pop("fog", None)
            sky = next((x for x in lv["entities"] if "/skyboxes/" in x["shape"]), None)
            if sky_done or not sky: continue
            png, spng = f"sky/{sid}.png", f"sky/{sid}_stars.png"
            colors = look["colorize"].get(sky["name"])
            fog = (look["fog"][0], look["fog"][1]) if look["fog"] else None
            if any(sky_strip.convert_gof3(m, f"{out}/{png}", assets, colors, fog, f"{out}/{spng}") for m in b.sky_materials(sky["shape"], assets)):
                e["skybox"] = {"nebula": png, "nebulaBrightness": 1.0}
                if os.path.exists(f"{out}/{spng}"): e["skybox"].update({"stars": spng, "starsBrightness": 1.0})
                else: e["skybox"]["stars"] = 1
            if look["light"]:
                e["sunColor"] = [round(min(1.0, max(0.05, c / LIGHT0)), 3) for c in look["light"]["rgb"]]
            suns = [x for x in lv["entities"] if "/suns/" in x["shape"] and x.get("pos")]
            if suns:
                lp = np.array(look["light"]["pos"], np.float64) if look["light"] else None
                def score(x):
                    p = np.array(x["pos"], np.float64)
                    return -float(np.dot(p, lp) / (np.linalg.norm(p) * np.linalg.norm(lp) + 1e-9)) if lp is not None else -max(x.get("scale") or [1])
                sun = min(suns, key=score)
                spath = f"textures/suns/{sid}.png"
                if sun_sprite(sun, look["colorize"].get(sun["name"]), assets, f"{out}/{spath}"): e["sunTexture"] = spath
            sky_done = True
        log(f"look {sid}: sun {e.get('sunColor')}, sky {e.get('skybox', {}).get('nebula')}")
    json.dump(systems, open(f"{out}/systems.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(stations, open(f"{out}/stations.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdb", required=True); ap.add_argument("--assets", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    apply(a.out, a.pdb, a.assets.rstrip("/"))
