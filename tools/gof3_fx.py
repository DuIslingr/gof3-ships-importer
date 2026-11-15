"""GoF3's effect layers of a model (its BlendMode 2 materials: glows, sprites, spotlights, flames, holos, plasma) for the
remake's glow layers (GoF2/ModGlow, a glTF material's "extras" {"additive": true, ...}: ModGlbImages.Glow).

GoF3's effect shaders (their .ae4shader GLSL, ae4_shaders; found 2026-11-12):
  fragment  o = texture (Diffuse_Texture_Channel 1 rgba, 2-5 one channel) [x DiffuseColor with DiffuseColorMultiply; no
            texture: DiffuseColor] x Opacity x the vertex colours (Colorize_VertexColors); Colorize_Custom:
              Colorize_Options 1: o x= mix(C1, C2, o.r) x Colorize_Multiplier
              Colorize_Options 2: o.rgb x= o.rgb + c.rgb (1 - o.rgb) Colorize_Multiplier; o.rgb x= c.a
            o.a x= Alpha_Value (x the angle fade, x the pulse), drawn additively
  vertex    angle fade (AngleBlend_Enabled): |N.E| (AngleBlend_Absolute) ramped from AngleBlend_MinAngle to _MaxAngle
            pulse (Pulsate_Enabled): |sin((t [+ vertex red: Pulsate_UseVertexColorOffsetForPulsate]) x Pulsate_Frequency)|,
              [step(Pulsate_StepThreshold): Pulsate_Step], then smoothstep into Pulsate_Min..Max (Pulsate_SmoothMinMax) or
              clamped to them
            sprites: a section with a_pos2dOffset is a billboard, its vertices at the sprite's centre and a_pos2dOffset the
              corner's offset in view space x the object's scale
            UV scroll (UVAnim_Enabled, not UVAnim_FlowOnly): UVAnim_Speed x UVAnim_SpeedMultiplier a second
The static colour is baked into the texture (bake), normalised to its brightest texel ("intensity" restores it: GoF3's
Opacity reaches 4); the vertex colours, scroll, angle fade, pulse and billboard go in the extras for the remake to do at run
time. Left out: DistanceBlend (off or a no-op in the ships' materials), the flow map's wobble, fog.

layers(scene_path, dirs, assets) -> [(key, Material, [prim])] at the scene nodes' world matrices (structures.convert's space)
write(glb_path, layers, assets): merged into a converted .glb as meshes of their own under its root."""
import io, json, os, re, struct, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ae4_ids, ae4_material, ae4_meshgroup, ae4_scene, structures
import structure_materials as sm


def bake(material, assets):
    """(PNG bytes, extras) of an effect material (see the header)."""
    from PIL import Image
    v, _ = ae4_material.read(material)
    ids = ae4_material.texture_ids(material)
    tex = ae4_ids.resolve(assets, ids["Diffuse"]) if ids.get("Diffuse") else None
    dc = np.array(v.get("DiffuseColor", (1, 1, 1, 1)), np.float32)
    if tex and os.path.exists(tex):
        im = structures.ae4_texture.decode(tex).convert("RGBA")
        if max(im.size) > 512: im = structures.ae4_texture.resized(im, (min(im.width, 512), min(im.height, 512)))
        o = np.asarray(im).astype(np.float32) / 255
        ch = int(v.get("Diffuse_Texture_Channel", 1) or 1)
        if ch > 1: o = np.repeat(o[..., ch - 2:ch - 1], 4, -1)
        if v.get("DiffuseColorMultiply"): o = o * dc
    else:
        o = np.broadcast_to(dc, (4, 4, 4)).copy()
    o = o * float(v.get("Opacity", 1.0))
    if v.get("Colorize_Custom"):
        c1 = np.array(v.get("Colorize_Color1", (1, 1, 1, 1)), np.float32); c2 = np.array(v.get("Colorize_Color2", (1, 1, 1, 1)), np.float32)
        k = float(v.get("Colorize_Multiplier", 1.0))
        c = c1 + (c2 - c1) * o[..., 0:1]
        if int(v.get("Colorize_Options", 0)) == 1: o = o * c * k
        else: o[..., :3] = o[..., :3] * (o[..., :3] + c[..., :3] * (1 - o[..., :3]) * k) * c[..., 3:4]
    o[..., 3] *= float(v.get("Alpha_Value", 1.0))
    peak = max(float(o[..., :3].max()), 1e-6)
    scale = peak if peak > 1 else 1.0
    out = o.copy(); out[..., :3] /= scale; out = np.clip(out, 0, 1)
    b = io.BytesIO(); Image.fromarray((out * 255 + .5).astype(np.uint8), "RGBA").save(b, "PNG")
    ex = {"additive": True, "intensity": round(scale, 3), "vertexColors": bool(v.get("Colorize_VertexColors", True))}
    if v.get("UVAnim_Enabled") and not v.get("UVAnim_FlowOnly"):
        sp, k = v.get("UVAnim_Speed", (0, 0, 0)), float(v.get("UVAnim_SpeedMultiplier", 1.0))
        ex["scroll"] = [round(float(sp[0]) * k, 4), round(float(sp[1]) * k, 4)]
    if v.get("AngleBlend_Enabled"):
        ex["angleFade"] = [round(float(v.get("AngleBlend_MinAngle", 0.0)), 4), round(float(v.get("AngleBlend_MaxAngle", 1.0)), 4)]
        ex["angleAbsolute"] = bool(v.get("AngleBlend_Absolute", True))
    if v.get("Pulsate_Enabled"):
        ex["pulse"] = {"frequency": round(float(v.get("Pulsate_Frequency", 1.0)), 4), "min": round(float(v.get("Pulsate_Min", 0.0)), 4),
                       "max": round(float(v.get("Pulsate_Max", 1.0)), 4), "threshold": round(float(v.get("Pulsate_StepThreshold", 0.5)), 4),
                       "step": bool(v.get("Pulsate_Step")), "smooth": bool(v.get("Pulsate_SmoothMinMax")),
                       "vertexOffset": bool(v.get("Pulsate_UseVertexColorOffsetForPulsate"))}
    return b.getvalue(), ex


def _prim(secs, M):
    """One primitive of an effect material's sections at world matrix M: real normals (the angle fade), the vertex colours, and
    for sprites (a_pos2dOffset) their centres with the corners' offsets in TEXCOORD_1 (its v stored as 1 - v: glTFast flips
    every UV set's v on import, so the remake reads the offset as it is)."""
    R = M[:3, :3]
    P, N, T, C, O, I, base = [], [], [], [], [], [], 0
    for s in secs:
        n = s["count"]
        P.append((np.c_[np.asarray(s["a_position"], np.float32), np.ones(n)] @ M.T)[:, :3])
        if "a_normal" in s:
            nn = np.asarray(s["a_normal"], np.float32) @ R.T
            N.append(nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12))
        else: N.append(np.tile(np.array([[0, 1, 0]], np.float32), (n, 1)))
        T.append(np.asarray(s["a_texCoord0"], np.float32) if "a_texCoord0" in s else np.zeros((n, 2), np.float32))
        C.append(np.asarray(s["a_vtxColor"], np.float32)[:, :4] if "a_vtxColor" in s and np.asarray(s["a_vtxColor"]).ndim == 2
                 else np.ones((n, 4), np.float32))
        if "a_pos2dOffset" in s:
            off = np.asarray(s["a_pos2dOffset"], np.float32)[:, :2].copy(); off[:, 1] = 1.0 - off[:, 1]
            O.append(off)
        else: O.append(None)
        idx = np.asarray(s["indices"], np.int64) + base
        if np.linalg.det(R) < 0: idx = idx.reshape(-1, 3)[:, ::-1].reshape(-1)
        I.append(idx); base += n
    billboard = any(o is not None for o in O)
    prim = {"positions": np.concatenate(P).astype(np.float32), "normals": np.concatenate(N).astype(np.float32),
            "uvs": np.concatenate(T), "colors": np.concatenate(C), "indices": np.concatenate(I)}
    if billboard:
        prim["uvs1"] = np.concatenate([o if o is not None else np.c_[np.zeros(len(t)), np.ones(len(t))] for o, t in zip(O, T)]).astype(np.float32)
    return prim, billboard


def layers(scene_path, dirs, assets, skip=None):
    """[(key, Material, [prim], billboard)] of a scene's effect sections, grouped by material and sprite-ness. 'dirs': the
    folders holding the nodes' meshgroups, or a function node name -> meshgroup path (scene_glb.meshgroup's); 'skip': node
    index -> True to leave a node out (scene_glb: the parts that animate, whose glows would stay behind)."""
    scene = ae4_scene.read(scene_path)
    W = structures.world_matrices(scene)
    groups = {}
    for i, n in scene.items():
        if "collision" in n["name"] or re.search(r"_lod_0*[1-9]\d*_", n["name"]): continue   # (the lower LODs: drawn once)
        if skip and skip(i): continue
        if callable(dirs): mg = dirs(n["name"])
        else: mg = next((f"{d}/{n['name']}.ae4meshgroup" for d in dirs if os.path.exists(f"{d}/{n['name']}.ae4meshgroup")), None)
        if mg is None: continue
        secs = ae4_meshgroup.read_all(mg)
        mats = sm.section_materials(mg, assets)
        by = {}
        for s, m in zip(secs, mats):
            if m is None or not m.effect or "a_position" not in s: continue
            by.setdefault((m.name, "a_pos2dOffset" in s), (m, []))[1].append(s)
        for (name, bb), (m, ss) in by.items():
            prim, billboard = _prim(ss, W[i])
            key = "fx_" + name.replace("structure_", "") + ("_sprite" if billboard and not name.endswith("sprite") and "sprite" not in name else "")
            g = groups.setdefault(key, (m, [], billboard))
            g[1].append(prim)
    return [(k, m, prims, bb) for k, (m, prims, bb) in sorted(groups.items())]


def _read(path):
    b = open(path, "rb").read(); n = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + n]), bytearray(b[28 + n:] if len(b) > 20 + n else b"")


def _write(path, j, bin_):
    while len(bin_) % 4: bin_.append(0)
    j["buffers"] = [{"byteLength": len(bin_)}]
    js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_)
    tmp = path + ".tmp"; open(tmp, "wb").write(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body); os.replace(tmp, path)


def merge(base_path, add_path):
    """add_path's meshes (materials, textures, images) appended into base_path, each mesh a node under its root."""
    a, ab = _read(base_path); f, fb = _read(add_path)
    off = len(ab); pad = (-off) % 4; ab.extend(b"\0" * pad); off += pad; ab.extend(fb)
    nv, na, ni, nt, nm, nme, ns = (len(a.get(k, [])) for k in ("bufferViews", "accessors", "images", "textures", "materials", "meshes", "samplers"))
    for v in f.get("bufferViews", []): v = dict(v); v["byteOffset"] = v.get("byteOffset", 0) + off; v["buffer"] = 0; a.setdefault("bufferViews", []).append(v)
    for x in f.get("accessors", []): x = dict(x); x["bufferView"] += nv; a.setdefault("accessors", []).append(x)
    for x in f.get("images", []): x = dict(x); x["bufferView"] += nv; a.setdefault("images", []).append(x)
    for x in f.get("samplers", []): a.setdefault("samplers", []).append(x)
    for x in f.get("textures", []):
        x = dict(x); x["source"] += ni
        if "sampler" in x: x["sampler"] += ns
        a.setdefault("textures", []).append(x)
    def shift(o):
        if isinstance(o, dict): return {k: (v + nt if k == "index" and isinstance(v, int) else shift(v)) for k, v in o.items()}
        if isinstance(o, list): return [shift(v) for v in o]
        return o
    for x in f.get("materials", []):
        x = dict(x); ex = x.pop("extras", None); x = shift(x)
        if ex is not None: x["extras"] = ex   # (its "intensity" etc. aren't texture indices)
        a.setdefault("materials", []).append(x)
    for me in f.get("meshes", []):
        me = json.loads(json.dumps(me))
        for p in me["primitives"]:
            p["attributes"] = {k: v + na for k, v in p["attributes"].items()}; p["indices"] += na
            if "material" in p: p["material"] += nm
        a.setdefault("meshes", []).append(me)
    root = a["scenes"][a.get("scene", 0)]["nodes"][0]
    for k in range(len(f.get("meshes", []))):
        a["nodes"].append({"name": f["meshes"][k]["name"], "mesh": nme + k})
        a["nodes"][root].setdefault("children", []).append(len(a["nodes"]) - 1)
    _write(base_path, a, ab)


def write(glb_path, fx, assets):
    """The effect layers (layers()) merged into a converted .glb; -> their keys."""
    if not fx: return []
    meshes, materials, images = [], [], []
    for key, m, prims, billboard in fx:
        png, ex = bake(m.path, assets)
        if billboard: ex["billboard"] = True
        images.append((png, "image/png", key, True))
        for p in prims: p["material"] = len(materials)
        materials.append({"name": key, "alphaMode": "BLEND", "doubleSided": True,
                          "pbrMetallicRoughness": {"baseColorFactor": [0.0, 0.0, 0.0, 0.0], "metallicFactor": 0.0, "roughnessFactor": 1.0},
                          "emissiveTexture": {"index": len(images) - 1}, "emissiveFactor": [1.0, 1.0, 1.0], "extras": ex})
        meshes.append({"name": key, "primitives": prims})
    tmp = tempfile.mkdtemp()
    add = os.path.join(tmp, "fx.glb")
    structures.write_glb_parts(add, meshes, materials, images)
    merge(glb_path, add)
    return [k for k, *_ in fx]
