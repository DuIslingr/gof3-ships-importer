"""Convert a GoF3 scene (a station, an assembled station, a jumpgate) to one .glb of instanced parts, for the remake's
stations.json, without Blender.

GoF3 builds its stations from shared parts: a station's .ae4scene places hundreds of instances of its race's station modules
(arms, rings, domes...), docked capital ships, wrecks and asteroids. Every part keeps its own mesh once in the .glb and
each instance is a node with the part's world matrix, so a station of 2000 nodes stays small.

Materials: a race's station modules all map their UV1 into one light map atlas (materials/multi/structure_<race>_stations_
light_ao), a capital ship or a jumpgate into its own (<model>_light_ao). Like structures.py (whose bake this reuses) every
section is baked with its own material (structure_materials: the part's .ae4model names it), into colour, emission,
specular-glossiness and normal maps in its UV1 space, shared by every station that uses the atlas; sections GoF3 draws
alpha-tested or blended (antennas, glass, decals) keep a material of their own on their tiled texture (own_<material>).
The .glb's materials carry only a name (gof3[<key>]) and stations.json's "materials" point them at the texture files.
Asteroids keep their family's tiled diffuse texture on UV0 (gof3_rock_<key>). Effects (glows, sprites, beams, steam,
lights), collision and lower LODs are left out; with effects=True (the jumpgates) the gate's own effect layers come in
(_add, _glow, _glows, _electricity: GoF3's BlendMode 2 materials), each a gof3[fx_<material>] material that stations.json
draws additive (its texture x DiffuseColor x Opacity x the vertex colours, scrolling by UVAnim). The sky window (a fixed
cubemap seen through the gate) is still left out.

scene_glb.convert(scene_path, out_glb, assets) -> {"min", "max", "groups": {key: {...}}, "nodes", "parts", "triangles"}
(glTF space: Y up, 1 unit = 1 GoF3 unit). bake_group(key, info, models, out_dir) writes the group's textures."""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import ae4_animation, ae4_meshgroup, ae4_scene, structures
import structure_materials as sm

_INDEX = {}
PLATING_GAIN = 2.6           # the baked colour x this (GoF3's platings are dark: its shader brightens them)
FX = re.compile(r"_(add|glows?(_\d+)?|electricity)$")   # a gate's effect layers (convert's effects=True)
SKIP = re.compile(r"(?i)collision|_lod_0*[1-9]\d*_|glow|sprite|beam|streak|steam|_fx|lights?_|flare|holo|spotlight|_shadow|decal")


def index(assets):
    """{meshgroup stem: path} of every lod 0 body under assets (cached per folder)."""
    if assets in _INDEX: return _INDEX[assets]
    out = {}
    for root, _, files in os.walk(assets):
        for f in files:
            if f.endswith(".ae4meshgroup"): out.setdefault(f[:-len(".ae4meshgroup")], os.path.join(root, f))
    _INDEX[assets] = out
    return out


def meshgroup(name, assets):
    """The lod 0 body meshgroup a node instances: its name without the instance number (..._lod_000_body003), or a
    turning part of its own (the Vossk gate's ..._lod_000_ring_01 / _02, the Terran gate's ..._lod_000_antenna)."""
    ring = re.search(r"_lod_000_(ring_\d+|antenna)$", name)
    base = name if ring else re.sub(r"\d{3}$", "", name)
    if not (ring or base.endswith("_body")) or SKIP.search(base): return None
    idx = index(assets)
    if base in idx: return idx[base]
    for stem, p in idx.items():
        if stem.startswith(base + "___"): return p
    return None


def fx_meshgroup(name, assets):
    """The effect layer meshgroup a node instances (a gate's ..._add / _glow / _glow_000 / _glows_000 / _electricity), or None."""
    idx = index(assets)
    for base in (name, re.sub(r"\d{3}$", "", name)):
        if FX.search(base) and base in idx: return idx[base]
    return None


def fx_split(mg, assets):
    """An effect meshgroup's sections by their additive material: {key: (Material, [section])}."""
    out = {}
    for s, m in zip(_sections(mg), sm.section_materials(mg, assets)):
        if m is None or not m.effect or "a_texCoord0" not in s: continue
        out.setdefault("fx_" + m.name.replace("structure_", ""), (m, []))[1].append(s)
    return out


def _fx_prim(secs, material):
    P = np.concatenate([np.asarray(s["a_position"], np.float32) for s in secs])
    T = np.concatenate([np.asarray(s["a_texCoord0"], np.float32) for s in secs])
    C = np.concatenate([np.asarray(s["a_vtxColor"], np.float32)[:, :4] if "a_vtxColor" in s and np.asarray(s["a_vtxColor"]).ndim == 2
                        else np.ones((s["count"], 4), np.float32) for s in secs])
    I, base = [], 0
    for s in secs:
        I.append(np.asarray(s["indices"], np.int64) + base); base += s["count"]
    N = np.tile(np.array([[0, 1, 0]], np.float32), (len(P), 1))   # (unlit: the layer has none)
    return {"positions": P, "normals": N, "uvs": T, "colors": C, "indices": np.concatenate(I), "material": material}


def group(path, assets):
    """(key, info) of the material a part's meshgroup takes, or None to leave it out."""
    p = path.replace("\\", "/")
    stem = os.path.basename(p).split("___")[0][:-len(".ae4meshgroup")] if "___" not in os.path.basename(p) else os.path.basename(p).split("___")[0]
    model = re.sub(r"_lod_000_(body|ring_\d+|antenna)$", "", stem)
    if "/structures/" in p:
        race = p.split("/structures/")[1].split("/")[0]
        multi = f"{assets}/structures/{race}/materials/multi"
        cands = [f"{multi}/{model}_light_ao.tga.ae4texture"]
        if "/stations/modules/" in p or "/stations/geosphere/" in p:
            cands.append(f"{multi}/structure_{race}_stations_{'damaged_' if 'damaged' in p else ''}light_ao.tga.ae4texture")
            cands.append(f"{multi}/structure_{race}_stations_light_ao.tga.ae4texture")
        cands.append(f"{multi}/structure_{race}_default_light_ao.tga.ae4texture")
        light = next((c for c in cands if os.path.exists(c)), None)
        if light is None: return None
        key = os.path.basename(light).replace("_light_ao.tga.ae4texture", "").replace("structure_", "")
        return key, {"kind": "bake", "light": light, "race": race}
    if "/asteroids/" in p:
        m = re.match(r"asteroid_([a-z]+)_([a-z]+)", model)
        if not m: return None
        tex = f"{assets}/asteroids/textures"
        fam = f"asteroid_{m.group(1)}_{m.group(2)}"
        diff = sorted(n for n in os.listdir(tex) if n.startswith(fam) and "diffuse" in n)
        if not diff:
            diff = sorted(n for n in os.listdir(tex) if n.startswith(f"asteroid_{m.group(1)}") and "diffuse" in n)
        if not diff: return None
        return f"rock_{m.group(1)}_{m.group(2)}", {"kind": "tex", "diffuse": f"{tex}/{diff[0]}"}
    return None


def _sections(path):
    return [s for s in ae4_meshgroup.read_all(path) if s.get("count") and s.get("indices")]


def own_key(mat):
    return "own_" + mat.name.replace("structure_", "")


def split(mg, info, assets):
    """A part's sections by what they become: (baked [(section, Material, uv1 tangents)], own {key: (Material, [section])}).
    The same for convert's meshes and bake_group's maps, so the glb's tangents are the ones the normal map was baked for."""
    secs = _sections(mg)
    if info["kind"] != "bake":
        return [(s, None, None) for s in secs if "a_texCoord0" in s], {}
    parts = structures.classify(secs, sm.section_materials(mg, assets), sm.race_plating(info["race"], assets))
    baked, own = [], {}
    for s, part in zip(secs, parts):
        if part is None: continue
        if part[0] == "own":
            if part[1].diffuse: own.setdefault(own_key(part[1]), (part[1], []))[1].append(s)
            continue
        baked.append((s, part[1], sm.uv_tangents(s["a_position"], s["a_normal"], s["a_texCoord1"], s["indices"])))
    return baked, own


def _prim(secs, uvk, tangents, material):
    P = np.concatenate([np.asarray(s["a_position"], np.float32) for s in secs])
    N = np.concatenate([np.asarray(s["a_normal"], np.float32) for s in secs])
    T = np.concatenate([np.asarray(s[uvk], np.float32) for s in secs])
    I, base = [], 0
    for s in secs:
        I.append(np.asarray(s["indices"], np.int64) + base); base += s["count"]
    return {"positions": P, "normals": N, "uvs": T, "indices": np.concatenate(I), "material": material,
            "tangents": np.concatenate(tangents) if tangents else None}


# The scene's clips that play for good (a gate's rotator and rings, a station's turning or sliding parts); not the
# cutscenes, damage states, destruction, a station's docking clips (in / out / off) or the leftovers (test, bomb, event).
ONE_SHOT = re.compile(r"(?i)cutscene|damage|destroy|_in\b|_in\.|_out|_off|idle|test|bomb|event|cam_")
MAX_KEYS = 720               # an animated node's keys at most (resampled evenly past this)


def scene_animations(scene_path, assets):
    """{node name: {channel: [(ms, value)]}} of the looping clips the scene refers to (the first clip naming a node wins)."""
    out = {}
    # by id, else beside the scene under its own name (the Terran gates' structure_terran_jumpgate_000.ae4animation)
    folder, stem = os.path.dirname(scene_path), os.path.basename(scene_path).split(".")[0]
    near = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".ae4animation") and f.startswith(stem)]
    for f in structures_refs(scene_path, assets) + near:
        if not f.endswith(".ae4animation") or ONE_SHOT.search(os.path.basename(f)): continue
        for node, ch in ae4_animation.read(f).items(): out.setdefault(node, ch)
    return out


def structures_refs(path, assets):
    import engine_meshes
    return engine_meshes._refs(path, assets)


def _local(n, ch=None, t=0.0):
    """A scene node's local matrix (as structures.world_matrices builds it), its channels sampled at t ms when given."""
    pos, rot, scl = list(n["pos"]), list(n["rot"]), list(n["scale"])
    if ch:
        for c, keys in ch.items():
            kind, axis = c.split(".") if "." in c else (c, "")
            v = ae4_animation.sample(keys, t)
            if kind == "rotation": rot["xyzw".index(axis)] = v
            elif kind == "translation": pos["xyz".index(axis)] = v
            elif kind == "scale": scl["xyz".index(axis)] = v
    q = np.asarray(rot, np.float64); q /= max(np.linalg.norm(q), 1e-12)
    M = np.eye(4); M[:3, :3] = structures._quat(q) * np.asarray(scl); M[:3, 3] = pos
    return M


def _trs(M):
    """(translation, rotation quaternion x y z w, scale) of an affine matrix."""
    S = np.linalg.norm(M[:3, :3], axis=0)
    R = M[:3, :3] / np.where(S > 1e-12, S, 1.0)
    if np.linalg.det(R) < 0: S[0] = -S[0]; R[:, 0] = -R[:, 0]
    w = np.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = np.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2
    y = np.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2
    z = np.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2
    x = np.copysign(x, R[2, 1] - R[1, 2]); y = np.copysign(y, R[0, 2] - R[2, 0]); z = np.copysign(z, R[1, 0] - R[0, 1])
    q = np.array([x, y, z, w]); q /= max(np.linalg.norm(q), 1e-12)
    return M[:3, 3].copy(), q, S


def convert(scene_path, out_glb, assets, skip=None, effects=False):
    scene = ae4_scene.read(scene_path)
    W = structures.world_matrices(scene)
    parts, groups, inst = {}, {}, []
    for i, n in scene.items():
        if skip and skip(n["name"]): continue
        mg = meshgroup(n["name"], assets)
        if mg is None and effects and (mg := fx_meshgroup(n["name"], assets)) is not None and mg not in parts:
            fx = fx_split(mg, assets)
            for k, (mat, _) in fx.items():
                groups.setdefault(k, {"kind": "fx", "material": mat.path, "models": set()})["models"].add(mg)
            parts[mg] = (None, {"kind": "fx"}, [], fx) if fx else None
        if mg is None: continue
        if mg not in parts:
            g = group(mg, assets)
            if g is None: parts[mg] = None; continue
            key, info = g
            baked, own = split(mg, info, assets)
            if not baked and not own: parts[mg] = None; continue
            if baked: groups.setdefault(key, dict(info, models=set()))["models"].add(mg)
            for k, (mat, _) in own.items():
                groups.setdefault(k, {"kind": "own", "material": mat.path, "models": set()})["models"].add(mg)
            parts[mg] = (key, info, baked, own)
        if parts[mg] is None: continue
        inst.append((mg, W[i], i))
    if not inst: return None
    order = [mg for mg in dict.fromkeys(m for m, _, _ in inst)]
    keys = sorted(groups)
    mat_of = {k: i for i, k in enumerate(keys)}
    meshes, mesh_of, local_box, tris = [], {}, {}, 0
    for mg in order:
        key, info, baked, own = parts[mg]
        prims = []
        if info["kind"] == "fx":
            prims += [_fx_prim(own[k][1], mat_of[k]) for k in sorted(own)]
        elif baked:
            uvk = "a_texCoord1" if info["kind"] == "bake" else "a_texCoord0"
            tangents = [t for _, _, t in baked] if info["kind"] == "bake" else None
            prims.append(_prim([s for s, _, _ in baked], uvk, tangents, mat_of[key]))
        for k in (sorted(own) if info["kind"] != "fx" else []):
            prims.append(_prim(own[k][1], "a_texCoord0", None, mat_of[k]))
        tris += sum(len(p["indices"]) // 3 for p in prims)
        mesh_of[mg] = len(meshes)
        meshes.append({"name": os.path.basename(mg).split(".")[0].split("___")[0], "primitives": prims})
        local_box[mg] = np.concatenate([p["positions"] for p in prims])
    # GoF3's looping animations: each animated scene node a glTF node of its own carrying the parts under it, its keys in
    # one glTF animation (the remake plays a model's first clip on a loop: ModGltf.LoopAnimations)
    by_name = {}
    for i, n in scene.items(): by_name.setdefault(n["name"], i)
    moving = {}
    for name, ch in scene_animations(scene_path, assets).items():
        i = by_name.get(name)
        if i is not None and any(len({round(v, 5) for _, v in k}) > 1 for k in ch.values()): moving[i] = ch
    def animated_above(i):
        seen = set()
        while i in scene and i not in seen:
            if i in moving: return i
            seen.add(i); i = scene[i]["parent"]
        return None
    carried = {animated_above(i) for _, _, i in inst} - {None}
    for a in list(carried):   # an animated node's animated ancestors carry it
        p = animated_above(scene[a]["parent"]) if scene[a]["parent"] in scene else None
        while p is not None: carried.add(p); p = animated_above(scene[p]["parent"]) if scene[p]["parent"] in scene else None
    nodes, children, gl_of = [], {None: []}, {}
    def gl_parent(a):
        p = scene[a]["parent"]
        return animated_above(p) if p in scene else None
    order_a, placed = [], set()
    while len(placed) < len(carried):
        for a in sorted(carried - placed):
            if gl_parent(a) is None or gl_parent(a) in placed: order_a.append(a); placed.add(a)
    animation, length = [], max([max(k[-1][0] for k in moving[a].values()) for a in carried] or [0])
    for a in order_a:
        pa = gl_parent(a)
        rel = np.linalg.inv(W[pa]) @ W[scene[a]["parent"]] if pa is not None else \
            (W[scene[a]["parent"]] if scene[a]["parent"] in scene else np.eye(4))
        t, q, sc = _trs(rel @ _local(scene[a]))
        gl_of[a] = len(nodes) + 1
        nodes.append({"name": scene[a]["name"], "translation": t.tolist(), "rotation": q.tolist(), "scale": sc.tolist()})
        children.setdefault(pa, []).append(gl_of[a]); children[a] = []
        ch = moving[a]
        own = max(k[-1][0] for k in ch.values())
        times = sorted({tt for k in ch.values() for tt, _ in k})
        if len(times) > MAX_KEYS: times = list(np.linspace(0.0, own, MAX_KEYS))
        reps = max(1, int(round(length / own))) if own > 0 else 1   # a shorter clip runs again until the longest ends
        T, R, S, ts, prev = [], [], [], [], None
        for r in range(reps):
            for tt in times:
                if r and tt == 0.0: continue
                tr, qq, ss = _trs(rel @ _local(scene[a], ch, tt))
                if prev is not None and np.dot(prev, qq) < 0: qq = -qq
                prev = qq
                T.append(tr); R.append(qq); S.append(ss); ts.append((r * own + tt) / 1000.0)
        animation.append({"node": gl_of[a], "times": np.asarray(ts, np.float32),
                          "translation": np.asarray(T, np.float32), "rotation": np.asarray(R, np.float32), "scale": np.asarray(S, np.float32)})
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for mg, M, i in inst:
        a = animated_above(i)
        local = np.linalg.inv(W[a]) @ M if a is not None else M
        children.setdefault(a, []).append(len(nodes) + 1)
        nodes.append({"mesh": mesh_of[mg], "matrix": [float(v) for v in local.T.reshape(-1)]})
        P = local_box[mg]
        corners = np.array([[x, y, z] for x in (P[:, 0].min(), P[:, 0].max()) for y in (P[:, 1].min(), P[:, 1].max())
                            for z in (P[:, 2].min(), P[:, 2].max())])
        Q = corners @ M[:3, :3].T + M[:3, 3]
        lo = np.minimum(lo, Q.min(0)); hi = np.maximum(hi, Q.max(0))
    root = {"name": os.path.basename(scene_path).split(".")[0], "children": children[None]}
    for a, g in gl_of.items():
        if children.get(a): nodes[g - 1]["children"] = children[a]
    materials = [{"name": f"gof3[{k}]",
                  "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.6}}
                 for k in keys]
    structures.write_glb_parts(out_glb, meshes, materials, [], "gof3_ships_importer scene_glb.py", nodes=[root] + nodes,
                               animations=animation)
    return {"min": lo.tolist(), "max": hi.tolist(), "groups": groups, "nodes": len(nodes), "parts": len(order), "triangles": tris,
            "animated": len(animation)}


def bake_group(key, info, models, out_dir, size=2048):
    """The textures of one material group, from every part (meshgroup path) that uses it: {"diffuse", "emission",
    "specularGlossiness", "normal"} file names, or an own material's {"diffuse", values}."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    if info["kind"] == "tex":
        im = structures.ae4_texture.decode(info["diffuse"]).convert("RGB")
        if max(im.size) > 1024: im = im.resize((1024, 1024), Image.BICUBIC)
        im.save(f"{out_dir}/{key}_colour.jpg", quality=88)
        return {"diffuse": f"{key}_colour.jpg"}
    if info["kind"] == "fx":
        return fx_values(key, info["material"], out_dir)
    if info["kind"] == "own":
        mat = sm.material(info["material"], os.path.dirname(info["material"]).split("/structures/")[0])
        open(f"{out_dir}/{key}_colour.png", "wb").write(structures.own_images(mat)["colour"])
        return {"diffuse": f"{key}_colour.png", "values": structures.own_values(mat)}
    items = []
    assets = info["light"].split("/structures/")[0]
    for mg in sorted(models):
        items += split(mg, info, assets)[0]
    maps = structures.bake(items, structures._tex(info["light"]), size)
    # GoF3's platings are dark (a mean of ~0.1): its shader brightens them; the remake's lit hull doesn't
    img = structures.map_images(maps, PLATING_GAIN)
    names = {"colour": f"{key}_colour.jpg", "emission": f"{key}_emission.jpg", "specgloss": f"{key}_specgloss.png",
             "normal": f"{key}_normal.png"}
    for k, n in names.items(): open(f"{out_dir}/{n}", "wb").write(img[k])
    return {"diffuse": names["colour"], "emission": names["emission"], "specularGlossiness": names["specgloss"],
            "normal": names["normal"]}


def fx_values(key, material, out_dir):
    """An effect layer's texture (its Diffuse slot, decoded to PNG) and stations.json values: GoF3's additive colour is the
    texture x DiffuseColor x Opacity (x the vertex colours with Colorize_VertexColors); UVAnim scrolls it (speed x multiplier
    a second) unless it only drives the flow map's distortion (UVAnim_FlowOnly), which the remake doesn't draw."""
    import ae4_material, ae4_ids
    v, _ = ae4_material.read(material)
    assets = material.split("/structures/")[0]
    slots = {k: ae4_ids.resolve(assets, h) for k, h in ae4_material.texture_ids(material).items()}
    out = {"values": {"color": [round(float(c), 4) for c in v.get("DiffuseColor", (1, 1, 1, 1))[:3]],
                      "intensity": round(float(v.get("Opacity", 1.0)) * float(v.get("Colorize_Multiplier", 1.0)), 3),
                      "vertexColors": bool(v.get("Colorize_VertexColors", True))}}
    if v.get("UVAnim_Enabled") and not v.get("UVAnim_FlowOnly"):
        sp, k = v.get("UVAnim_Speed", (0, 0, 0)), float(v.get("UVAnim_SpeedMultiplier", 1.0))
        out["values"]["scroll"] = [round(float(sp[0]) * k, 4), round(float(sp[1]) * k, 4)]
    tex = slots.get("Diffuse") or slots.get("T1")
    if tex and os.path.exists(tex):
        im = structures.ae4_texture.decode(tex).convert("RGBA")
        if max(im.size) > 512: im = im.resize((min(im.width, 512), min(im.height, 512)))
        im.save(f"{out_dir}/{key}.png")
        out["diffuse"] = f"{key}.png"
    return out


if __name__ == "__main__":
    info = convert(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps({k: v for k, v in info.items() if k != "groups"}), {k: len(v["models"]) for k, v in info["groups"].items()})
    if len(sys.argv) > 4:
        for k, g in sorted(info["groups"].items()): print(k, bake_group(k, g, g["models"], sys.argv[4], 1024))
