"""Convert a GoF3 structure (a capital ship, the Hades / Manticore) to one baked .glb, without Blender.

GoF3 draws its structures with a few tiled materials (structure_<race>_matidNN_*: platings, windows, pipes...) on UV0 and a
per-model light map on UV1 (materials/multi/<model>_light_ao: RGB the baked coloured lights, A the baked light and
occlusion). The model's .ae4model names each section's material by resource id (structure_materials), so each section is
baked with its own material's textures and values. Each model is baked onto its own UV1 unwrap, which is unique:
  base colour   = diffuse(UV0) x Diffuse_Color x vertex colour x (0.45 + 0.55 light map A)
  emission      = light map RGB (the coloured lights) x (1.4 + specular) + the diffuse's emissive mask (its tiny lit
                  windows), dimmed
  specular      = the n_s_g map's B x Specular_Color x Specular_Multiplier x vertex colour x light map A (GoF3's
                  specular colour, its values as they are: GoF3 lights in gamma space, so the texture is read as sRGB)
  glossiness    = the n_s_g map's A as smoothness (structure_materials.smoothness)
  normal        = the n_s_g map's RG in the mesh's tangent frame, turned into the UV1 unwrap's (the glb's TANGENT)
Sections of an unlit one-colour material (no texture, Colorize_Custom: the loot containers' collectables_emissive strips)
go in as emission-only materials of that colour (UNLIT_GLOW).
The colour, specular-glossiness and normal maps go in as glTF's KHR_materials_pbrSpecularGlossiness (the remake's mod
loader reads it into URP's specular setup). Sections GoF3 draws alpha-tested or blended (antennas, glass, decals) get a
material of their own on their own tiled texture (UV0); effect sections (sprites, glows, holograms, beams) and sections
without a light map (UV1 all 0) are left out.

structures.convert(model_dir, name, race, out_glb, size) -> {"min", "max", "helpers": {name: (pos, scale, up)}} in glTF space
(Y up, the nose -Z, 1 unit = 1 GoF3 unit), the helpers from the model's scene (turrets, engines, the hangar, damage)."""
import io, json, math, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_meshgroup, ae4_scene, ae4_texture
import structure_materials as sm

LIGHT_FLOOR = 0.45            # the light map's A scales the colour from this to 1 (full: too dark under the remake's own light)
LIGHT_GLOW = 1.4              # the light map's RGB as emission
WINDOW_GLOW = 0.6             # the plating's emissive mask (alpha) as emission
OWN_SIZE = 1024               # an own material's tiled texture at most this size
UNLIT_GLOW = 2.2              # an unlit one-colour section's emission (hangar_room.GLOW: the remake tone maps it down)


def _tex(path, size=None):
    im = ae4_texture.decode(path)
    if size and im.size != size: im = ae4_texture.resized(im, size)
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


def classify(sections, mats, fallback):
    """Each section's part in the conversion: ("bake", material) for the light-mapped hull, ("own", material) for one
    GoF3 draws alpha-tested or blended (its own tiled texture), None to leave out (effects, no light map). 'mats' is
    structure_materials.section_materials' list (may be short or hold None: the race's plating then)."""
    out = []
    for i, s in enumerate(sections):
        m = mats[i] if i < len(mats) else None
        if m is not None and m.effect: out.append(None); continue
        if m is not None and m.unlit_colour is not None: out.append(("glow", m)); continue
        if m is not None and (m.blend == 1 or m.values.get("Opacity_Threshold", 0) > 0) and m.diffuse_role == "do":
            out.append(("own", m)); continue
        if "a_texCoord1" not in s or np.abs(np.asarray(s["a_texCoord1"])).max() <= 0: out.append(None); continue
        out.append(("bake", m or fallback))
    return out


def bake(items, light, size):
    """The UV1 unwrap's maps from [(section, Material, uv1 tangents (n, 4))]: a dict of float arrays (size, size, ...):
    colour, emission, specular (RGB), smoothness, normal (tangent space, xyz) and the mask of baked texels."""
    col = np.zeros((size, size, 3), np.float32); em = np.zeros((size, size, 3), np.float32)
    spec = np.zeros((size, size, 3), np.float32); gloss = np.zeros((size, size), np.float32)
    nrm = np.zeros((size, size, 3), np.float32); nrm[..., 2] = 1.0
    mask = np.zeros((size, size), bool)
    for s, mat, tan in items:
        uv1 = np.asarray(s["a_texCoord1"], np.float64) * size
        uv0 = np.asarray(s["a_texCoord0"], np.float64)
        vc = np.asarray(s.get("a_vtxColor", [(1, 1, 1, 1)] * s["count"]), np.float32)
        if len(vc) != s["count"]: vc = np.ones((s["count"], 4), np.float32)
        frame = mat.normal is not None and "a_tangent" in s and "a_bitangent" in s
        if frame:
            Tg = np.asarray(s["a_tangent"], np.float64); Bg = np.asarray(s["a_bitangent"], np.float64)
        Ng = np.asarray(s["a_normal"], np.float64)
        tw, th = mat.size()
        texels = tw * th * mat.tiling * mat.tiling
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
            U = uv0[[a, b, c]]
            # the mip level whose texels match the unwrap's: tiled detail far finer than a texel of the bake averages out
            area0 = abs((U[1, 0] - U[0, 0]) * (U[2, 1] - U[0, 1]) - (U[2, 0] - U[0, 0]) * (U[1, 1] - U[0, 1])) * texels
            level = 0.5 * math.log2(max(area0 / abs(d), 1.0))
            dif, emi, n_t, sp, g = mat.sample(w @ U, level, (w @ vc[[a, b, c]])[:, :3])
            yy, xx = gy[inside].astype(int), gx[inside].astype(int)
            col[yy, xx] = dif
            em[yy, xx] = dif * emi[:, None] * WINDOW_GLOW
            spec[yy, xx] = sp
            gloss[yy, xx] = g
            nn = w @ Ng[[a, b, c]]
            nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
            if frame:
                # GoF3's normal (its tangent frame: v_tangentToLocal = (tangent, bitangent, normal)) in object space ...
                n_o = (w @ Tg[[a, b, c]]) * n_t[:, 0:1] + (w @ Bg[[a, b, c]]) * n_t[:, 1:2] + nn * n_t[:, 2:3]
                # ... then in the unwrap's tangent frame, as the glb's TANGENT gives it
                t = w @ tan[[a, b, c], :3].astype(np.float64)
                t -= nn * (t * nn).sum(1, keepdims=True)
                t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
                bt = np.cross(nn, t) * float(tan[a, 3])
                o = np.stack([(n_o * t).sum(1), (n_o * bt).sum(1), (n_o * nn).sum(1)], 1)
                nrm[yy, xx] = o / np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-12)
            mask[yy, xx] = True
    # its RGB scaled apart from its A (the occlusion): Pillow scales RGBA premultiplied, which darkened the light by the
    # occlusion a second time wherever the light map wasn't the bake's size (ae4_texture.resized, 2026-11-02)
    lm = np.asarray(ae4_texture.resized(Image.fromarray((light * 255).astype(np.uint8)), (size, size), Image.BILINEAR)).astype(np.float32) / 255
    col = col * (LIGHT_FLOOR + (1 - LIGHT_FLOOR) * lm[..., 3:4])
    spec = spec * lm[..., 3:4]   # GoF3: specularTexel *= ambientocclusionTexel
    # GoF3's "lightmap specular": the baked coloured lights caught in the specular parts too
    em = em * lm[..., 3:4] + lm[..., :3] * (LIGHT_GLOW + spec)
    steps = max(4, size // 128)
    nrm = _dilate(nrm, mask, steps)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=2, keepdims=True), 1e-12)
    return {"colour": _dilate(col, mask, steps), "emission": _dilate(em, mask, steps), "specular": _dilate(spec, mask, steps),
            "smoothness": _dilate(sm.smoothness(gloss)[..., None], mask, steps)[..., 0], "normal": nrm, "mask": mask}


def _png(a, mode):
    b = io.BytesIO()
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(b, "PNG", optimize=True)
    return b.getvalue()


SHINE_SCALE = 2              # the specular-glossiness and normal maps at this fraction of the bake (PNGs: 4x the JPG's size)


def _half(a):
    h, w = a.shape[0] // SHINE_SCALE, a.shape[1] // SHINE_SCALE
    if SHINE_SCALE <= 1 or min(h, w) < 256: return a
    return a[:h * SHINE_SCALE, :w * SHINE_SCALE].reshape(h, SHINE_SCALE, w, SHINE_SCALE, -1).mean((1, 3))


def map_images(maps, gain=1.0):
    """The bake's maps as image files: colour / emission JPG, specular-glossiness (RGB specular, A smoothness) and the
    normal map (xyz -> RGB) PNG, those two at 1 / SHINE_SCALE of the bake."""
    sg = _half(np.concatenate([maps["specular"], maps["smoothness"][..., None]], 2))
    n = _half(maps["normal"]); n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-12)
    return {"colour": _jpeg(maps["colour"] * gain), "emission": _jpeg(maps["emission"]), "specgloss": _png(sg, "RGBA"),
            "normal": _png(n * 0.5 + 0.5, "RGB")}


def own_images(mat):
    """An own material's (antennas, glass, decals) tiled texture, its alpha the opacity, as a PNG at most OWN_SIZE."""
    im = ae4_texture.decode(mat.diffuse).convert("RGBA")
    if max(im.size) > OWN_SIZE: im = ae4_texture.resized(im, (OWN_SIZE, OWN_SIZE * im.size[1] // im.size[0]))
    a = np.asarray(im).astype(np.float32) / 255
    a[..., :3] *= mat.diffuse_color
    return {"colour": _png(a, "RGBA")}


def own_values(mat):
    """An own material's constant specular colour, smoothness, alpha mode and cut-off."""
    spec = np.clip(mat.spec_color if mat.spec_color.any() else np.full(3, sm.FLAT_SPEC), 0, 1)
    if mat.environment > 0: spec = np.maximum(spec, mat.environment * 0.5)
    clip = float(mat.values.get("Opacity_Threshold", 0) or 0)
    return {"specular": [round(float(v), 3) for v in spec], "smoothness": round(float(sm.smoothness(mat.gloss)), 3),
            "alpha": "MASK" if mat.blend == 0 and clip > 0 else "BLEND", "cutoff": round(clip, 3),
            "opacity": float(mat.values.get("Opacity_Amount", 1.0) or 1.0), "doubleSided": int(mat.values.get("CullMode", 2)) == 0}


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


SPEC_GLOSS = "KHR_materials_pbrSpecularGlossiness"


def hull_material(name, tex, emissive=True):
    """The baked hull's glTF material: 'tex' the texture index of each map (colour, emission, specgloss, normal)."""
    m = {"name": name, "pbrMetallicRoughness": {"baseColorTexture": {"index": tex["colour"]}, "metallicFactor": 0.0,
                                                "roughnessFactor": 0.5},
         "normalTexture": {"index": tex["normal"]},
         "extensions": {SPEC_GLOSS: {"diffuseTexture": {"index": tex["colour"]}, "specularGlossinessTexture": {"index": tex["specgloss"]},
                                     "specularFactor": [1.0, 1.0, 1.0], "glossinessFactor": 1.0}}}
    if emissive and "emission" in tex: m["emissiveTexture"] = {"index": tex["emission"]}; m["emissiveFactor"] = [1.0, 1.0, 1.0]
    return m


def own_material(name, tex, v):
    """An own material's glTF material (own_values' v)."""
    m = {"name": name, "alphaMode": v["alpha"],
         "pbrMetallicRoughness": {"baseColorTexture": {"index": tex}, "baseColorFactor": [1.0, 1.0, 1.0, v["opacity"]],
                                  "metallicFactor": 0.0, "roughnessFactor": round(1.0 - v["smoothness"], 3)},
         "extensions": {SPEC_GLOSS: {"diffuseTexture": {"index": tex}, "diffuseFactor": [1.0, 1.0, 1.0, v["opacity"]],
                                     # (glTF's factor is linear; own_values gives GoF3's values, sRGB like the maps)
                                     "specularFactor": [round(c ** 2.2, 4) for c in v["specular"]], "glossinessFactor": v["smoothness"]}}}
    if v["alpha"] == "MASK": m["alphaCutoff"] = v["cutoff"]
    if v["doubleSided"]: m["doubleSided"] = True
    return m


def write_glb_parts(path, meshes, materials, images, generator="gof3_ships_importer structures.py", nodes=None, animations=None):
    """A .glb of several meshes. meshes: [{"name", "primitives": [{"positions", "normals", "uvs", "tangents" (optional),
    "colors" (optional, rgba), "indices", "material"}]}]; materials: glTF materials whose texture indices are image indices; images: [(bytes, mime,
    name, repeat)]. nodes: glTF nodes (default one per mesh under a root). animations: one glTF animation of
    [{"node", "times" (s), "translation", "rotation", "scale"}] (linear keys)."""
    blobs, views, accessors = [], [], []
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
    out_meshes = []
    for mesh in meshes:
        prims = []
        for p in mesh["primitives"]:
            nrm = np.asarray(p["normals"], np.float32)
            nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-8)
            attrs = {"POSITION": acc(np.asarray(p["positions"], np.float32), "VEC3", 5126, 34962, True),
                     "NORMAL": acc(nrm, "VEC3", 5126, 34962), "TEXCOORD_0": acc(np.asarray(p["uvs"], np.float32), "VEC2", 5126, 34962)}
            if p.get("tangents") is not None: attrs["TANGENT"] = acc(np.asarray(p["tangents"], np.float32), "VEC4", 5126, 34962)
            if p.get("colors") is not None: attrs["COLOR_0"] = acc(np.asarray(p["colors"], np.float32), "VEC4", 5126, 34962)
            prims.append({"attributes": attrs, "indices": acc(np.asarray(p["indices"], np.uint32), "SCALAR", 5125, 34963),
                          "material": p["material"]})
        out_meshes.append({"name": mesh["name"], "primitives": prims})
    gl_anim = None
    if animations:
        chans, samps = [], []
        for a in animations:
            t = np.asarray(a["times"], np.float32)
            inp = acc(t.reshape(-1, 1), "SCALAR", 5126, None, True)
            for path_, typ in (("translation", "VEC3"), ("rotation", "VEC4"), ("scale", "VEC3")):
                samps.append({"input": inp, "output": acc(np.asarray(a[path_], np.float32), typ, 5126, None), "interpolation": "LINEAR"})
                chans.append({"sampler": len(samps) - 1, "target": {"node": a["node"], "path": path_}})
        gl_anim = {"name": "loop", "channels": chans, "samplers": samps}
    img_views = [add(b) for b, _, _, _ in images]
    samplers = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071},
                {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
    if nodes is None:
        nodes = [{"name": os.path.splitext(os.path.basename(path))[0], "children": list(range(1, len(out_meshes) + 1))}] + \
                [{"name": m["name"], "mesh": i} for i, m in enumerate(out_meshes)]
    j = {"asset": {"version": "2.0", "generator": generator}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes,
         "meshes": out_meshes, "materials": materials,
         "textures": [{"source": i, "sampler": 1 if rep else 0} for i, (_, _, _, rep) in enumerate(images)],
         "samplers": samplers,
         "images": [{"bufferView": v, "mimeType": mime, "name": n} for v, (_, mime, n, _) in zip(img_views, images)],
         "accessors": accessors, "bufferViews": views}
    if gl_anim: j["animations"] = [gl_anim]
    if any(SPEC_GLOSS in m.get("extensions", {}) for m in materials): j["extensionsUsed"] = [SPEC_GLOSS]
    binc = b"".join(blobs); binc += b"\0" * ((-len(binc)) % 4)
    j["buffers"] = [{"byteLength": len(binc)}]
    js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * ((-len(js)) % 4)
    open(path, "wb").write(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(binc)) + struct.pack("<II", len(js), 0x4E4F534A)
                           + js + struct.pack("<II", len(binc), 0x004E4942) + binc)


def convert(model_dir, name, race, out_glb, size=2048, assets=None, body=None):
    """body: the hull meshgroup's name when it isn't <name>_lod_000_body (the loot containers' collectables_002_<race>_body,
    lit by their race's default light map)."""
    body_name = body or f"{name}_lod_000_body"
    assets = assets or model_dir.replace("\\", "/").split("/structures/")[0]
    sdir = f"{assets}/structures/{race}"
    scene = ae4_scene.read(f"{model_dir}/{name}.ae4scene")
    W = world_matrices(scene)
    body = next((i for i, n in scene.items() if n["name"] == body_name), None)
    M = W[body] if body is not None else np.eye(4)
    # The Hades' body is a root of its own at +(0, 86, -9.3) beside its geometry / helpers roots at -(0, 86, -9.3): it belongs
    # under the geometry root (the two cancel). Taken alone it put the hull 86 units above its own engine helpers (the
    # Manticore's exhausts hung under its nozzles).
    geo = next((i for i, n in scene.items() if n["name"] == f"{name}_geometry" and n["parent"] == -1), None)
    if body is not None and geo is not None and scene[body]["parent"] == -1: M = W[geo] @ W[body]
    mg_path = f"{model_dir}/{body_name}.ae4meshgroup"
    sections = ae4_meshgroup.read_all(mg_path)
    parts = classify(sections, sm.section_materials(mg_path, assets), sm.race_plating(race, assets))
    lm_path = f"{sdir}/materials/multi/{name}_light_ao.tga.ae4texture"
    if not os.path.exists(lm_path): lm_path = f"{sdir}/materials/multi/structure_{race}_default_light_ao.tga.ae4texture"
    light = _tex(lm_path)
    items, own, glows = [], {}, {}
    for s, part in zip(sections, parts):
        if part is None: continue
        if part[0] == "own": own.setdefault(part[1].name, (part[1], []))[1].append(s); continue
        if part[0] == "glow": glows.setdefault(part[1].name, (part[1], []))[1].append(s); continue
        items.append((s, part[1], sm.uv_tangents(s["a_position"], s["a_normal"], s["a_texCoord1"], s["indices"])))
    maps = bake(items, light, size)
    mask = maps["mask"]
    R = M[:3, :3]; flip = -1.0 if np.linalg.det(R) < 0 else 1.0
    def placed(s, uvk, tan=None):
        P = (np.c_[np.asarray(s["a_position"]), np.ones(s["count"])] @ M.T)[:, :3]
        N = np.asarray(s["a_normal"]) @ R.T
        T = None
        if tan is not None:
            T = np.c_[tan[:, :3] @ R.T, tan[:, 3] * flip]
            T[:, :3] /= np.maximum(np.linalg.norm(T[:, :3], axis=1, keepdims=True), 1e-12)
        return P, N, np.asarray(s[uvk]), T
    def merged(group, uvk, tangents):
        pos, nrm, uv, tan, idx, base = [], [], [], [], [], 0
        for k, s in enumerate(group):
            P, N, U, T = placed(s, uvk, tangents[k] if tangents else None)
            pos.append(P); nrm.append(N); uv.append(U)
            if T is not None: tan.append(T)
            idx.append(np.asarray(s["indices"], np.int64) + base); base += s["count"]
        return {"positions": np.concatenate(pos), "normals": np.concatenate(nrm), "uvs": np.concatenate(uv),
                "tangents": np.concatenate(tan) if tan else None, "indices": np.concatenate(idx)}
    img = map_images(maps)
    images = [(img["colour"], "image/jpeg", f"{name}_colour", False), (img["emission"], "image/jpeg", f"{name}_emission", False),
              (img["specgloss"], "image/png", f"{name}_specgloss", False), (img["normal"], "image/png", f"{name}_normal", False)]
    materials = [hull_material(f"{name}_hull", {"colour": 0, "emission": 1, "specgloss": 2, "normal": 3})]
    hull = merged([s for s, _, _ in items], "a_texCoord1", [t for _, _, t in items])
    hull["material"] = 0
    prims = [hull]
    for key in sorted(own):
        mat, group = own[key]
        if not mat.diffuse: continue
        images.append((own_images(mat)["colour"], "image/png", f"{name}_{key}", True))
        materials.append(own_material(f"{name}_{key}", len(images) - 1, own_values(mat)))
        p = merged(group, "a_texCoord0", None); p["material"] = len(materials) - 1
        prims.append(p)
    for key in sorted(glows):   # unlit in one colour: emission only, at UNLIT_GLOW against the remake's tone map
        mat, group = glows[key]
        materials.append({"name": f"{name}_{key}", "pbrMetallicRoughness": {"baseColorFactor": [0, 0, 0, 1], "metallicFactor": 0,
                          "roughnessFactor": 1}, "emissiveFactor": [round(float(c) * UNLIT_GLOW, 4) for c in mat.unlit_colour]})
        p = merged(group, "a_texCoord0", None); p["material"] = len(materials) - 1
        prims.append(p)
    write_glb_parts(out_glb, [{"name": name, "primitives": prims}], materials, images,
                    nodes=[{"name": name, "mesh": 0}])
    pos = hull["positions"]; idx = np.concatenate([p["indices"] for p in prims])
    if len(prims) > 1: pos = np.concatenate([p["positions"] for p in prims])
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
