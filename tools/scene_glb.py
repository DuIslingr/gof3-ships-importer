"""Convert a GoF3 scene (a station, an assembled station, a jumpgate) to one .glb of instanced parts, for the remake's
stations.json, without Blender.

GoF3 builds its stations from shared parts: a station's .ae4scene places hundreds of instances of its race's station modules
(arms, rings, domes...), docked capital ships, wrecks and asteroids. Every part keeps its own mesh once in the .glb and
each instance is a node with the part's world matrix, so a station of 2000 nodes stays small.

Materials: a race's station modules all map their UV1 into one light map atlas (materials/multi/structure_<race>_stations_
light_ao), a capital ship or a jumpgate into its own (<model>_light_ao); like structures.py (whose bake this reuses) the
tiled detail is the race's plating for every lit section. Each light map is baked once (bake_group) into a colour and an
emission texture in its UV1 space, shared by every station that uses it; the .glb's materials carry only a name
(gof3_bake_<key>) and stations.json's "materials" point them at those texture files. Asteroids keep their family's tiled
diffuse texture on UV0 (gof3_rock_<key>). Effects (glows, sprites, beams, steam, lights), collision and lower LODs are
left out.

scene_glb.convert(scene_path, out_glb, assets) -> {"min", "max", "groups": {key: {...}}, "nodes", "parts", "triangles"}
(glTF space: Y up, 1 unit = 1 GoF3 unit). bake_group(group, out_dir) writes <key>_colour.jpg / <key>_emission.jpg."""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import ae4_meshgroup, ae4_scene, structures

_INDEX = {}
PLATING_GAIN = 2.6           # the baked colour x this (GoF3's platings are dark: its shader brightens them)
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
    """The lod 0 body meshgroup a node instances: its name without the instance number (..._lod_000_body003)."""
    base = re.sub(r"\d{3}$", "", name)
    if not base.endswith("_body") or SKIP.search(base): return None
    idx = index(assets)
    if base in idx: return idx[base]
    for stem, p in idx.items():
        if stem.startswith(base + "___"): return p
    return None


def group(path, assets):
    """(key, info) of the material a part's meshgroup takes, or None to leave it out."""
    p = path.replace("\\", "/")
    stem = os.path.basename(p).split("___")[0][:-len(".ae4meshgroup")] if "___" not in os.path.basename(p) else os.path.basename(p).split("___")[0]
    model = re.sub(r"_lod_000_body$", "", stem)
    if "/structures/" in p:
        race = p.split("/structures/")[1].split("/")[0]
        multi = f"{assets}/structures/{race}/materials/multi"
        cands = [f"{multi}/{model}_light_ao.tga.ae4texture"]
        if "/stations/modules/" in p or "/stations/geosphere/" in p:
            cands.append(f"{multi}/structure_{race}_stations_{'damaged_' if 'damaged' in p else ''}light_ao.tga.ae4texture")
            cands.append(f"{multi}/structure_{race}_stations_light_ao.tga.ae4texture")
        cands.append(f"{multi}/structure_{race}_default_light_ao.tga.ae4texture")
        light = next((c for c in cands if os.path.exists(c)), None)
        tex = f"{assets}/structures/{race}/textures"
        plating = next((f"{tex}/{n}" for n in sorted(os.listdir(tex)) if re.match(rf"structure_{race}_platings_000_diffuse", n)), None) \
            if os.path.isdir(tex) else None
        if light is None or plating is None: return None
        key = os.path.basename(light).replace("_light_ao.tga.ae4texture", "").replace("structure_", "")
        return key, {"kind": "bake", "light": light, "plating": plating}
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


def convert(scene_path, out_glb, assets, skip=None):
    scene = ae4_scene.read(scene_path)
    W = structures.world_matrices(scene)
    parts, groups, inst = {}, {}, []
    for i, n in scene.items():
        if skip and skip(n["name"]): continue
        mg = meshgroup(n["name"], assets)
        if mg is None: continue
        if mg not in parts:
            g = group(mg, assets)
            if g is None: parts[mg] = None; continue
            key, info = g
            secs = _sections(mg)
            uvk = "a_texCoord1" if info["kind"] == "bake" else "a_texCoord0"
            secs = [s for s in secs if uvk in s and (info["kind"] != "bake" or np.abs(np.asarray(s[uvk])).max() > 0)]
            if not secs: parts[mg] = None; continue
            groups.setdefault(key, dict(info, models=set()))["models"].add(mg)
            parts[mg] = (key, secs, uvk)
        if parts[mg] is None: continue
        inst.append((mg, W[i]))
    if not inst: return None
    order = [mg for mg in dict.fromkeys(m for m, _ in inst)]
    blobs, views, accessors, meshes, nodes = [], [], [], [], []
    def add(data, target=None):
        off = sum(len(b) for b in blobs); pad = (-off) % 4
        if pad: blobs.append(b"\0" * pad); off += pad
        blobs.append(data)
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target: v["target"] = target
        views.append(v); return len(views) - 1
    def acc(arr, typ, comp, target, mm=False):
        a = {"bufferView": add(arr.tobytes(), target), "componentType": comp, "count": len(arr), "type": typ}
        if mm: a["min"] = arr.min(0).tolist(); a["max"] = arr.max(0).tolist()
        accessors.append(a); return len(accessors) - 1
    keys = sorted(groups)
    mat_of = {k: i for i, k in enumerate(keys)}
    mesh_of, local_box, tris = {}, {}, 0
    for mg in order:
        key, secs, uvk = parts[mg]
        P = np.concatenate([np.asarray(s["a_position"], np.float32) for s in secs])
        N = np.concatenate([np.asarray(s["a_normal"], np.float32) for s in secs])
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-8)
        T = np.concatenate([np.asarray(s[uvk], np.float32) for s in secs])
        I, base = [], 0
        for s in secs:
            I.append(np.asarray(s["indices"], np.uint32) + base); base += s["count"]
        I = np.concatenate(I)
        tris += len(I) // 3
        prim = {"attributes": {"POSITION": acc(P, "VEC3", 5126, 34962, True), "NORMAL": acc(N, "VEC3", 5126, 34962),
                               "TEXCOORD_0": acc(T, "VEC2", 5126, 34962)}, "indices": acc(I, "SCALAR", 5125, 34963),
                "material": mat_of[key]}
        mesh_of[mg] = len(meshes)
        meshes.append({"name": os.path.basename(mg).split(".")[0].split("___")[0], "primitives": [prim]})
        local_box[mg] = P
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for mg, M in inst:
        nodes.append({"mesh": mesh_of[mg], "matrix": [float(v) for v in M.T.reshape(-1)]})
        P = local_box[mg]
        corners = np.array([[x, y, z] for x in (P[:, 0].min(), P[:, 0].max()) for y in (P[:, 1].min(), P[:, 1].max())
                            for z in (P[:, 2].min(), P[:, 2].max())])
        Q = corners @ M[:3, :3].T + M[:3, 3]
        lo = np.minimum(lo, Q.min(0)); hi = np.maximum(hi, Q.max(0))
    root = {"name": os.path.basename(scene_path).split(".")[0], "children": list(range(1, len(nodes) + 1))}
    materials = [{"name": f"gof3[{k}]",
                  "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.25, "roughnessFactor": 0.6}}
                 for k in keys]
    j = {"asset": {"version": "2.0", "generator": "gof3_ships_importer scene_glb.py"}, "scene": 0,
         "scenes": [{"nodes": [0]}], "nodes": [root] + nodes, "meshes": meshes, "materials": materials,
         "accessors": accessors, "bufferViews": views}
    binc = b"".join(blobs); binc += b"\0" * ((-len(binc)) % 4)
    j["buffers"] = [{"byteLength": len(binc)}]
    js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * ((-len(js)) % 4)
    open(out_glb, "wb").write(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(binc)) + struct.pack("<II", len(js), 0x4E4F534A)
                              + js + struct.pack("<II", len(binc), 0x004E4942) + binc)
    return {"min": lo.tolist(), "max": hi.tolist(), "groups": groups, "nodes": len(nodes), "parts": len(order), "triangles": tris}


def bake_group(key, info, models, out_dir, size=2048):
    """The colour / emission textures of one material group, from every part (meshgroup path) that uses it."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    if info["kind"] == "tex":
        im = structures.ae4_texture.decode(info["diffuse"]).convert("RGB")
        if max(im.size) > 1024: im = im.resize((1024, 1024), Image.BICUBIC)
        im.save(f"{out_dir}/{key}_colour.jpg", quality=88)
        return {"diffuse": f"{key}_colour.jpg"}
    secs = []
    for mg in sorted(models):
        secs += [s for s in _sections(mg) if "a_texCoord1" in s and np.abs(np.asarray(s["a_texCoord1"])).max() > 0]
    col, em, _ = structures.bake(secs, structures._tex(info["light"]), structures._tex(info["plating"]), size)
    # GoF3's platings are dark (a mean of ~0.1): its shader brightens them; the remake's lit hull doesn't
    open(f"{out_dir}/{key}_colour.jpg", "wb").write(structures._jpeg(np.clip(col * PLATING_GAIN, 0, 1)))
    open(f"{out_dir}/{key}_emission.jpg", "wb").write(structures._jpeg(em))
    return {"diffuse": f"{key}_colour.jpg", "emission": f"{key}_emission.jpg"}


if __name__ == "__main__":
    info = convert(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps({k: v for k, v in info.items() if k != "groups"}), {k: len(v["models"]) for k, v in info["groups"].items()})
