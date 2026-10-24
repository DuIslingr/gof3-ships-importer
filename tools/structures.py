"""Convert a GoF3 structure (a capital ship, the Hades / Manticore) to one baked .glb, without Blender.

GoF3 draws its structures with a few tiled materials (structure_<race>_matidNN_*: platings, windows, pipes...) on UV0 and a
per-model light map on UV1 (materials/multi/<model>_light_ao: RGB the baked coloured lights, A the baked light and
occlusion). The model's sections name their materials by GUID only and nothing in the game files maps those GUIDs back to the
material files (no name hash, no table: tried), so the tiled detail is taken from the race's plating texture for every lit
section. Each model is baked onto its own UV1 unwrap, which is unique:
  base colour = plating(UV0, its own tiling) x vertex colour x (0.45 + 0.55 light map A)
  emission    = light map RGB (the coloured lights) + the plating's emissive mask (its tiny lit windows), dimmed
Sections without a light map (UV1 all 0: the sprites and glows drawn as billboards) are left out.

structures.convert(model_dir, name, race, out_glb, size) -> {"min", "max", "helpers": {name: (pos, scale, up)}} in glTF space
(Y up, the nose -Z, 1 unit = 1 GoF3 unit), the helpers from the model's scene (turrets, engines, the hangar, damage)."""
import io, json, math, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_meshgroup, ae4_scene, ae4_texture

LIGHT_FLOOR = 0.45            # the light map's A scales the colour from this to 1 (full: too dark under the remake's own light)
LIGHT_GLOW = 1.4              # the light map's RGB as emission
WINDOW_GLOW = 0.6             # the plating's emissive mask (alpha) as emission


def _tex(path, size=None):
    im = ae4_texture.decode(path)
    if size and im.size != size: im = im.resize(size, Image.BICUBIC)
    return np.asarray(im.convert("RGBA")).astype(np.float32) / 255


def _quat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def world_matrices(nodes):
    """Each scene node's world matrix (engine space = glTF space: Y up)."""
    W = {}
    def get(i):
        if i in W: return W[i]
        n = nodes[i]
        M = np.eye(4); M[:3, :3] = _quat(n["rot"]) * np.array(n["scale"]); M[:3, 3] = n["pos"]
        p = n["parent"]
        W[i] = (get(p) @ M) if p in nodes and p != i else M
        return W[i]
    for i in nodes: get(i)
    return W


def _sample(img, uv):
    """Bilinear, wrapping (tiled): img (h, w, c), uv (n, 2) -> (n, c)."""
    h, w = img.shape[:2]
    x = (uv[:, 0] % 1.0) * w - 0.5; y = (uv[:, 1] % 1.0) * h - 0.5
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    x0 %= w; y0 %= h; x1 = (x0 + 1) % w; y1 = (y0 + 1) % h
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def _dilate(col, mask, steps):
    """Spread the baked texels into the empty ones around the UV islands (no dark seams once mipmapped)."""
    col = col.copy(); m = mask.copy()
    for _ in range(steps):
        acc = np.zeros_like(col); cnt = np.zeros(m.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sm = np.roll(np.roll(m, dy, 0), dx, 1); sc = np.roll(np.roll(col, dy, 0), dx, 1)
            acc += sc * sm[..., None]; cnt += sm
        grow = (~m) & (cnt > 0)
        col[grow] = acc[grow] / cnt[grow][:, None]
        m = m | grow
        if m.all(): break
    return col


def bake(sections, light, plating, size):
    """The model's UV1 texture: (colour, emission) float arrays (size, size, 3)."""
    col = np.zeros((size, size, 3), np.float32); em = np.zeros((size, size, 3), np.float32)
    mask = np.zeros((size, size), bool)
    for s in sections:
        uv1 = np.asarray(s["a_texCoord1"], np.float64) * size
        uv0 = np.asarray(s["a_texCoord0"], np.float64)
        vc = np.asarray(s.get("a_vtxColor", [(1, 1, 1, 1)] * s["count"]), np.float32)
        if len(vc) != s["count"]: vc = np.ones((s["count"], 4), np.float32)
        idx = np.asarray(s["indices"], np.int64).reshape(-1, 3)
        for a, b, c in idx:
            P = uv1[[a, b, c]]
            x0, y0 = np.floor(P.min(0)).astype(int); x1, y1 = np.ceil(P.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, size), min(y1, size)
            if x1 <= x0 or y1 <= y0: continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            d = (P[1, 1] - P[2, 1]) * (P[0, 0] - P[2, 0]) + (P[2, 0] - P[1, 0]) * (P[0, 1] - P[2, 1])
            if abs(d) < 1e-12: continue
            l0 = ((P[1, 1] - P[2, 1]) * (gx - P[2, 0]) + (P[2, 0] - P[1, 0]) * (gy - P[2, 1])) / d
            l1 = ((P[2, 1] - P[0, 1]) * (gx - P[2, 0]) + (P[0, 0] - P[2, 0]) * (gy - P[2, 1])) / d
            l2 = 1 - l0 - l1
            e = -0.5 / max(abs(d), 1.0)   # include the texels the edges pass through
            inside = (l0 >= e) & (l1 >= e) & (l2 >= e)
            if not inside.any(): continue
            w = np.stack([l0[inside], l1[inside], l2[inside]], 1)
            t0 = w @ uv0[[a, b, c]]
            v = w @ vc[[a, b, c]]
            px = _sample(plating, t0)
            yy, xx = gy[inside].astype(int), gx[inside].astype(int)
            col[yy, xx] = px[:, :3] * v[:, :3]
            em[yy, xx] = px[:, :3] * px[:, 3:4] * WINDOW_GLOW
            mask[yy, xx] = True
    lm = np.asarray(Image.fromarray((light * 255).astype(np.uint8)).resize((size, size), Image.BILINEAR)).astype(np.float32) / 255
    col = col * (LIGHT_FLOOR + (1 - LIGHT_FLOOR) * lm[..., 3:4])
    em = em * lm[..., 3:4] + lm[..., :3] * LIGHT_GLOW
    steps = max(4, size // 128)
    return _dilate(col, mask, steps), _dilate(em, mask, steps), mask


def _jpeg(a):
    b = io.BytesIO()
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)).save(b, "JPEG", quality=88)
    return b.getvalue()


def write_glb(path, positions, normals, uvs, indices, colour_jpg, emission_jpg, name):
    """One mesh, one material: the baked colour and emission (glTF: Y up; UV top-left origin like the decoded textures)."""
    pos = np.asarray(positions, np.float32); nrm = np.asarray(normals, np.float32); uv = np.asarray(uvs, np.float32)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-8)
    idx = np.asarray(indices, np.uint32)
    blobs, views, accessors = [], [], []
    def add(data, target=None):
        off = sum(len(b) for b in blobs)
        pad = (-off) % 4
        if pad: blobs.append(b"\0" * pad); off += pad
        blobs.append(data)
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target: v["target"] = target
        views.append(v); return len(views) - 1
    def acc(arr, typ, comp, target, mm=False):
        a = {"bufferView": add(arr.tobytes(), target), "componentType": comp, "count": len(arr), "type": typ}
        if mm: a["min"] = arr.min(0).tolist(); a["max"] = arr.max(0).tolist()
        accessors.append(a); return len(accessors) - 1
    p_acc = acc(pos, "VEC3", 5126, 34962, True); n_acc = acc(nrm, "VEC3", 5126, 34962); t_acc = acc(uv, "VEC2", 5126, 34962)
    i_acc = acc(idx, "SCALAR", 5125, 34963)
    c_view = add(colour_jpg); e_view = add(emission_jpg)
    j = {"asset": {"version": "2.0", "generator": "gof3_ships_importer structures.py"},
         "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": name, "mesh": 0}],
         "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": p_acc, "NORMAL": n_acc, "TEXCOORD_0": t_acc},
                                                    "indices": i_acc, "material": 0}]}],
         "materials": [{"name": f"{name}_hull", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.25,
                                                                      "roughnessFactor": 0.6},
                        "emissiveTexture": {"index": 1}, "emissiveFactor": [1.0, 1.0, 1.0]}],
         "textures": [{"source": 0, "sampler": 0}, {"source": 1, "sampler": 0}],
         "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
         "images": [{"bufferView": c_view, "mimeType": "image/jpeg", "name": f"{name}_colour"},
                    {"bufferView": e_view, "mimeType": "image/jpeg", "name": f"{name}_emission"}],
         "accessors": accessors, "bufferViews": views}
    binc = b"".join(blobs); binc += b"\0" * ((-len(binc)) % 4)
    j["buffers"] = [{"byteLength": len(binc)}]
    js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * ((-len(js)) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binc)) + struct.pack("<II", len(js), 0x4E4F534A) + js \
        + struct.pack("<II", len(binc), 0x004E4942) + binc
    open(path, "wb").write(out)


def convert(model_dir, name, race, out_glb, size=2048, assets=None):
    assets = assets or model_dir.replace("\\", "/").split("/structures/")[0]
    sdir = f"{assets}/structures/{race}"
    scene = ae4_scene.read(f"{model_dir}/{name}.ae4scene")
    W = world_matrices(scene)
    body = next((i for i, n in scene.items() if n["name"] == f"{name}_lod_000_body"), None)
    M = W[body] if body is not None else np.eye(4)
    # The Hades' body is a root of its own at +(0, 86, -9.3) beside its geometry / helpers roots at -(0, 86, -9.3): it belongs
    # under the geometry root (the two cancel). Taken alone it put the hull 86 units above its own engine helpers (the
    # Manticore's exhausts hung under its nozzles).
    geo = next((i for i, n in scene.items() if n["name"] == f"{name}_geometry" and n["parent"] == -1), None)
    if body is not None and geo is not None and scene[body]["parent"] == -1: M = W[geo] @ W[body]
    sections = [s for s in ae4_meshgroup.read_all(f"{model_dir}/{name}_lod_000_body.ae4meshgroup")
                if "a_texCoord1" in s and np.abs(np.asarray(s["a_texCoord1"])).max() > 0]
    lm_path = f"{sdir}/materials/multi/{name}_light_ao.tga.ae4texture"
    if not os.path.exists(lm_path): lm_path = f"{sdir}/materials/multi/structure_{race}_default_light_ao.tga.ae4texture"
    light = _tex(lm_path)
    plating = _tex(f"{sdir}/textures/structure_{race}_platings_000_diffuse_emissive.tga.ae4texture")
    col, em, mask = bake(sections, light, plating, size)
    pos, nrm, uv, idx = [], [], [], []
    for s in sections:
        base = len(pos)
        P = np.c_[np.asarray(s["a_position"]), np.ones(s["count"])] @ M.T
        N = np.asarray(s["a_normal"]) @ M[:3, :3].T
        pos += P[:, :3].tolist(); nrm += N.tolist(); uv += [tuple(t) for t in s["a_texCoord1"]]
        idx += [i + base for i in s["indices"]]
    write_glb(out_glb, pos, nrm, uv, idx, _jpeg(col), _jpeg(em), name)
    helpers = {}
    for i, n in scene.items():
        if i == body: continue
        if re.search(r"_(turret|engine|damaged|hangar|bow|stern|generator)", n["name"]):
            Wm = W[i]
            up = Wm[:3, 1] / max(1e-9, float(np.linalg.norm(Wm[:3, 1])))
            back = Wm[:3, 2] / max(1e-9, float(np.linalg.norm(Wm[:3, 2])))   # an engine's way out (glTF +z = astern)
            helpers[n["name"]] = ([float(v) for v in Wm[:3, 3]], float(np.cbrt(abs(np.linalg.det(Wm[:3, :3])))), [float(v) for v in up],
                                  [float(v) for v in back])
    P = np.asarray(pos)
    return {"min": P.min(0).tolist(), "max": P.max(0).tolist(), "helpers": helpers, "triangles": len(idx) // 3,
            "coverage": float(mask.mean())}


if __name__ == "__main__":
    d, n, r, o = sys.argv[1:5]
    info = convert(d, n, r, o, int(sys.argv[5]) if len(sys.argv) > 5 else 2048)
    print(json.dumps({k: v for k, v in info.items() if k != "helpers"}), len(info["helpers"]), "helpers")
