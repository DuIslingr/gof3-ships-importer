"""Galaxy on Fire 3's engine effects as they are: every part of an engine scene (vfx/engines/<race>/vfx_engine_<race>_000,
the capital ships' vfx/engines/large/vfx_enigne_large_<race>) with its own mesh, transform, textures and the shader the
game draws it with, for the remake's EngineFx ("engineFx": {"meshes": "fx/engines/<name>.json"}).

What the game does (libgofm.so and its shaders):
- a scene names its models, a model its meshgroup and material, a material its textures, all by resource id:
  ae::resource::getResourceId (0x15fdad8) = MurmurHash3_x86_128 of "/assets/<path>" with seed 1, the two 64-bit halves
  xor-ed (ae4_ids);
- a material is drawn by one of the shader variants in its "<material>.ae4material_" folder, compiled for exactly the
  options it uses (the ones the material's flags name but the variant leaves out don't count: the Vossk exhaust's
  DiffuseColor, the Terran exhaust's Colorize); the GLSL (GLES2) variant in romfs shaders/ is read here for what it does:
  sprite (a_pos2dOffset: camera-facing, sized by the object's scale), the diffuse texture or the DiffuseColor alone,
  luminance alpha, DiffuseColor as the colour / times it, the flow map, UV scrolling (on the texture or the flow), the
  colourise formulas (option 1: x mix(C1, C2, r) x M; option 2: rgb *= rgb + C (1 - rgb) M, x C.a), the angle blend
  (|N.E|, -N.E or N.E remapped Min..Max into alpha), pulsating (|sin(t f)| clamped Min..Max, rgb and alpha), the vertex
  animation (pos += strength N sin((t + y) freq) a, the vertex alpha then 1), BlendMode 2 additive / 1 alpha;
- the scene's animations: a looping one (the Nivelian spiral's turn), "ignite" (the Terran engine's burst) and
  "engines_off" (the capital engines' flicker out).
Everything in GoF3 units in the engine's own frame (+z backward along the exhaust); the remake maps it onto each exhaust."""
import json, os, re, struct, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ae4_ids, ae4_material, ae4_meshgroup, ae4_scene, ae4_animation
from ae4unpack import unpack


def _refs(path, assets):
    """The files a GoF3 resource refers to by id, in order."""
    d = unpack(open(path, "rb").read())
    idx = ae4_ids.index(assets)
    out = []
    for o in range(len(d) - 7):
        f = idx.get(struct.unpack_from("<Q", d, o)[0])
        if f and f not in out: out.append(f)
    return out


def _variant(material, merged):
    """The material's GLSL (GLES2) shader variant's text, None when the game has none."""
    folder = material + "_"
    if not os.path.isdir(folder): return None
    for f in sorted(os.listdir(folder)):
        src = os.path.join(merged, "shaders", f)
        if not os.path.exists(src): continue
        t = open(src, "rb").read().decode("latin-1")
        if "attribute vec3 a_position" in t and "#ifdef FRAGMENT" in t: return t
    return None


def _features(glsl, v):
    """What the variant does, with the material's values for it."""
    vert, frag = glsl.split("#ifdef FRAGMENT", 1) if "#ifdef FRAGMENT" in glsl else (glsl, "")
    vert = vert[vert.find("void main()"):]
    def has(s, where): return s in where
    f = {}
    f["sprite"] = has("a_pos2dOffset", vert)
    f["useTex"] = has("texture2D(Diffuse", frag)
    f["lumAlpha"] = has("diffuseTexel.a *= dot(", frag)
    f["rgbFromDc"] = has("diffuseTexel.rgb = (custom_DiffuseColor).rgb", frag)
    f["mulDc"] = has("diffuseTexel * custom_DiffuseColor", frag)
    f["flow"] = has("texture2D(FlowMap", frag)
    f["scrollDirect"] = has("v_texCoord0 = a_texCoord0 + fract(uvSpeed", vert)
    f["scrollFlow"] = has("v_texCoordFlow = v_texCoordFlow + fract(uvSpeed", vert)
    if has("colorizeColor * Colorize_Multiplier", frag): f["colorize"] = 1
    elif has("colorizeColor.rgb * (1.0 - out_FragColor.rgb)", frag): f["colorize"] = 2
    else: f["colorize"] = 0
    f["colorizeVtx"] = has("mix((v_colVtx)", frag)
    if has("v_angleBlend = abs(v_angleBlend)", vert): f["angle"] = 1
    elif has("v_angleBlend * -1.0", vert): f["angle"] = 2
    elif has("v_angleBlend = clamp((v_angleBlend - AngleBlend_MinAngle)", vert): f["angle"] = 3
    else: f["angle"] = 0
    f["pulsate"] = has("v_pulsate = abs(sin(", vert)
    f["vertexAnim"] = has("VertexAnimation_Strength * a_normal", vert)
    f["opaqueVtxAlpha"] = has("vec4(a_vtxColor.rgb,1.0)", vert)
    f["blend"] = int(v.get("BlendMode", 2))
    f["cullBack"] = int(v.get("CullMode", 0)) != 0
    f["opacity"] = round(float(v.get("Opacity", 1.0)), 4)
    f["diffuse"] = [round(float(x), 4) for x in v.get("DiffuseColor", (1, 1, 1, 1))]
    f["c1"] = [round(float(x), 4) for x in v.get("Colorize_Color1", (1, 1, 1, 1))]
    f["c2"] = [round(float(x), 4) for x in v.get("Colorize_Color2", (1, 1, 1, 1))]
    f["colorizeMul"] = round(float(v.get("Colorize_Multiplier", 1.0)), 4)
    f["angleMin"] = round(float(v.get("AngleBlend_MinAngle", 0.0)), 4)
    f["angleMax"] = round(float(v.get("AngleBlend_MaxAngle", 1.0)), 4)
    f["pulseMin"] = round(float(v.get("Pulsate_Min", 0.0)), 4)
    f["pulseMax"] = round(float(v.get("Pulsate_Max", 1.0)), 4)
    f["pulseFreq"] = round(float(v.get("Pulsate_Frequency", 1.0)), 4)
    sp = v.get("UVAnim_Speed", (0.0, 0.0, 0.0)); mul = float(v.get("UVAnim_SpeedMultiplier", 1.0))
    f["uvSpeed"] = [round(float(sp[0]) * mul, 4), round(float(sp[1]) * mul, 4)]
    f["flowTiling"] = round(float(v.get("UVAnim_FlowTiling", 1.0)), 4)
    f["flowStrength"] = round(float(v.get("UVAnim_FlowStrength", 0.0)), 4)
    f["vaFreq"] = round(float(v.get("VertexAnimation_Frequenz", 0.0)), 4)
    f["vaStrength"] = round(float(v.get("VertexAnimation_Strength", 0.0)), 4)
    f["alpha"] = round(float(v.get("Alpha_Value", 1.0)), 4)
    return f


def _texture(src, out_dir, cache):
    """The texture decoded to fx/engines/tex/<name>.png (once), its path in the mod."""
    if src in cache: return cache[src]
    name = os.path.basename(src).split(".")[0]
    rel = f"fx/engines/tex/{name}.png"
    dst = os.path.join(out_dir, rel)
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        subprocess.run([sys.executable, os.path.join(HERE, "ae4_texture.py"), src, dst], check=True, capture_output=True)
    cache[src] = rel
    return rel


def _matrix(n):
    x, y, z, w = n["rot"]
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4); M[:3, :3] = R * np.asarray(n["scale"]); M[:3, 3] = n["pos"]
    return M


def _decompose(M):
    s = np.linalg.norm(M[:3, :3], axis=0)
    R = M[:3, :3] / s
    tr = R.trace()
    if tr > 0:
        q = 0.5 / np.sqrt(tr + 1.0); w = 0.25 / q
        x, y, z = (R[2, 1] - R[1, 2]) * q, (R[0, 2] - R[2, 0]) * q, (R[1, 0] - R[0, 1]) * q
    else:
        i = int(np.argmax(np.diag(R)))
        if i == 0:
            q = 2 * np.sqrt(1 + R[0, 0] - R[1, 1] - R[2, 2]); w = (R[2, 1] - R[1, 2]) / q; x = 0.25 * q; y = (R[0, 1] + R[1, 0]) / q; z = (R[0, 2] + R[2, 0]) / q
        elif i == 1:
            q = 2 * np.sqrt(1 + R[1, 1] - R[0, 0] - R[2, 2]); w = (R[0, 2] - R[2, 0]) / q; x = (R[0, 1] + R[1, 0]) / q; y = 0.25 * q; z = (R[1, 2] + R[2, 1]) / q
        else:
            q = 2 * np.sqrt(1 + R[2, 2] - R[0, 0] - R[1, 1]); w = (R[1, 0] - R[0, 1]) / q; x = (R[0, 2] + R[2, 0]) / q; y = (R[1, 2] + R[2, 1]) / q; z = 0.25 * q
    r = lambda a: [round(float(t), 5) for t in a]
    return r(M[:3, 3]), r([x, y, z, w]), r(s)


def _anims(scene_path, assets):
    """The scene's animations by node: {node: [{"kind", "length", "channels": [{"name", "keys": [t, v, t, v...]}]}]}."""
    out = {}
    for f in _refs(scene_path, assets):
        if not f.endswith(".ae4animation"): continue
        name = os.path.basename(f)
        kind = "ignite" if "ignite" in name else "off" if "_off" in name else "idle" if "idle" in name else "loop"
        if kind == "idle": continue   # (the Terran idle: every channel at rest)
        for node, ch in ae4_animation.read(f).items():
            moving = {c: k for c, k in ch.items() if len({round(v, 4) for _, v in k}) > 1}
            if not moving: continue
            length = max(k[-1][0] for k in ch.values())
            out.setdefault(node, []).append({"kind": kind, "length": round(length, 1),
                                             "channels": [{"name": c, "keys": [round(x, 5) for t, v in k for x in (t, v)]} for c, k in moving.items()]})
    return out


# How much brighter than its formula GoF3's ship viewer shows each part (the remake's _Intensity: the fragment's addition x
# this before the 8-bit clamp; GoF3's frame looks bloomed, which none of its effect shaders holds), matched by eye against
# clips of the Argus (Terran), Moornta (Nivelian) and Shamash (Vossk) rotating in GoF3's ship viewer: the Terran engine's
# parts and the capital engines 4; the Nivelian (and the Inouac, on its textures) flare 1.5, plume 2 and helix 5 (at 4 its
# flare and plume blew out to white); the Vossk flare 1.5 and its thin tendril plumes 5.
# By the engine's name and the part's last word (its node "vfx_engine_nivelian_000_spiral").
INTENSITY = {("engine_nivelian", "mesh"): 1.5, ("engine_nivelian", "exhaust"): 2.0, ("engine_nivelian", "spiral"): 5.0,
             ("engine_inouac", "mesh"): 1.5, ("engine_inouac", "exhaust"): 2.0,
             ("engine_vossk", "mesh"): 1.5, ("engine_vossk", "exhaust"): 5.0}
DEFAULT_INTENSITY = 4.0


def build(out_dir, assets, merged, scene_rel, name, tex_cache=None, root_filter=None):
    """fx/engines/<name>.json in out_dir from the engine scene 'scene_rel' (under assets), the mod's path to it; None when
    the scene has no drawable part. 'root_filter': only the parts under the scene's root node of that name (the large
    engines' scene holds every race)."""
    scene_path = os.path.join(assets, scene_rel)
    tex_cache = {} if tex_cache is None else tex_cache
    nodes = ae4_scene.read(scene_path)
    by_name = {n["name"]: (k, n) for k, n in nodes.items()}
    models = {os.path.basename(f).rsplit(".", 1)[0]: f for f in _refs(scene_path, assets) if f.endswith(".ae4model")}
    anims = _anims(scene_path, assets)
    def world(k):
        n = nodes[k]; M = _matrix(n)
        return world(n["parent"]) @ M if n["parent"] in nodes else M
    def root(k):
        while nodes[k]["parent"] in nodes: k = nodes[k]["parent"]
        return nodes[k]["name"]
    parts = []
    for k, n in sorted(nodes.items()):
        model = models.get(n["name"])
        if model is None: continue
        if root_filter and root(k) != root_filter: continue
        refs = _refs(model, assets)
        mesh = next((f for f in refs if f.endswith(".ae4meshgroup")), None)
        mat = next((f for f in refs if f.endswith(".ae4material")), None)
        if mesh is None or mat is None: continue
        v, _ = ae4_material.read(mat)
        glsl = _variant(mat, merged)
        if glsl is None: continue
        feat = _features(glsl, v)
        tex = {s: ae4_ids.resolve(assets, i) for s, i in ae4_material.texture_ids(mat).items()}
        part = {"name": n["name"]}
        part["pos"], part["rot"], part["scale"] = _decompose(world(k))
        g = ae4_meshgroup.read_all(mesh)[0]
        P = np.asarray(g["a_position"], dtype=float)
        part["v"] = [round(float(x), 5) for x in P.ravel()]
        if "a_normal" in g: part["n"] = [round(float(x), 4) for x in np.asarray(g["a_normal"], dtype=float).ravel()]
        if "a_texCoord0" in g: part["uv"] = [round(float(x), 5) for x in np.asarray(g["a_texCoord0"], dtype=float).ravel()]
        C = np.asarray(g.get("a_vtxColor", np.full((len(P), 4), 255)), dtype=float)
        if C.max() > 1.0: C = C / 255.0
        part["c"] = [round(float(x), 4) for x in C.ravel()]
        if feat["sprite"] and "a_pos2dOffset" in g:
            part["o"] = [round(float(x), 5) for x in np.asarray(g["a_pos2dOffset"], dtype=float).ravel()]
        part["i"] = [int(x) for x in np.asarray(g["indices"]).ravel()]
        if feat["useTex"] and tex.get("Diffuse"): part["texture"] = _texture(tex["Diffuse"], out_dir, tex_cache)
        elif feat["useTex"]: continue   # (a texture the game names but doesn't ship)
        if feat["flow"] and tex.get("FlowMap"): part["flowMap"] = _texture(tex["FlowMap"], out_dir, tex_cache)
        elif feat["flow"]: feat["flow"] = False
        part.update(feat)
        part["intensity"] = INTENSITY.get((name, n["name"].rsplit("_", 1)[-1]), DEFAULT_INTENSITY)
        if n["name"] in anims: part["anims"] = anims[n["name"]]
        parts.append(part)
    if not parts: return None
    rel = f"fx/engines/{name}.json"
    os.makedirs(os.path.join(out_dir, "fx", "engines"), exist_ok=True)
    with open(os.path.join(out_dir, rel), "w") as fh:
        json.dump({"source": "/assets/" + scene_rel.replace(os.sep, "/"), "parts": parts}, fh, separators=(",", ":"))
    return rel


if __name__ == "__main__":
    out, assets, merged, scene = sys.argv[1:5]
    print(build(out, assets, merged, scene, os.path.basename(scene).split(".")[0], root_filter=sys.argv[5] if len(sys.argv) > 5 else None))
