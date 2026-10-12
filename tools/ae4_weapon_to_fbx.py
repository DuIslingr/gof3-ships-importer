"""Blender script: one GoF3 weapon model (a gun tier, a mount, a rocket, a mine) -> FBX + .blend.
blender -b -P ae4_weapon_to_fbx.py -- <config.json>        (written by convert_weapons.py; textures baked first)

Engine space is Y-up with the barrel / nose toward -Z; Blender gets (x, -z, y) and the FBX exporter writes Y-up again.
config: {"name": out name, "out": dir, "texdir": dir,
         "objects": [{"name": object, "meshgroup": path, "materials": [material key per section], "pos": [x, y, z]}],
         "materials": {key: {"kind": "pbr", "prefix": "<textures prefix>"}
                           | {"kind": "glow", "color": [r, g, b], "strength": s, "texture": png, "vcol": bool}},
         "empties": [{"name": ..., "pos": [..], "rot": [x, y, z, w]}]}
Objects named <name>_LODk are the LOD levels (ae4_to_gltf.py puts LOD1.. into <name>_lods.glb). Sprite meshes (sections
with a_pos2dOffset: the game turns each quad to the camera) are built as flat quads in the engine XY plane, facing +Z
(backward, toward a chasing camera)."""
import bpy, sys, os, json, mathutils
sys.path.insert(0, os.path.dirname(__file__))
import ae4_meshgroup

cfg = json.load(open(sys.argv[sys.argv.index("--") + 1:][0], encoding='utf-8-sig'))
name, out, texdir = cfg["name"], cfg["out"], cfg["texdir"]
C = mathutils.Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # engine -> Blender

bpy.ops.wm.read_factory_settings(use_empty=True)
coll = bpy.context.scene.collection
_imgs = {}
def image(fn, data=False):
    p = os.path.join(texdir, fn)
    if p not in _imgs:
        _imgs[p] = bpy.data.images.load(p)
        if data: _imgs[p].colorspace_settings.name = "Non-Color"
    return _imgs[p]

_mats = {}
def material(key):
    if key in _mats: return _mats[key]
    spec = cfg["materials"][key]
    m = bpy.data.materials.new(key); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    def tnode(fn, data=False):
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = image(fn, data); return t
    if spec["kind"] == "pbr":
        T = lambda s: f"{spec['prefix']}_{s}.png"
        nt.links.new(tnode(T("basecolor")).outputs["Color"], b.inputs["Base Color"])
        if os.path.exists(os.path.join(texdir, T("normal"))):
            nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(tnode(T("normal"), True).outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
        nt.links.new(tnode(T("specular")).outputs["Color"], b.inputs["Specular Tint"])
        nt.links.new(tnode(T("roughness"), True).outputs["Color"], b.inputs["Roughness"])
        if os.path.exists(os.path.join(texdir, T("emissive"))):
            nt.links.new(tnode(T("emissive")).outputs["Color"], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 1.0
        b.inputs["Metallic"].default_value = 0.0
    else:   # additive vfx (BlendMode 2): emission = texture x vertex colour x colour; black base, alpha from the texture
        b.inputs["Base Color"].default_value = (0, 0, 0, 1)
        b.inputs["Roughness"].default_value = 1.0
        col = nt.nodes.new("ShaderNodeRGB"); col.outputs[0].default_value = tuple(spec["color"]) + (1.0,)
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1.0
        t = tnode(spec["texture"])
        nt.links.new(t.outputs["Color"], mix.inputs["A"]); nt.links.new(col.outputs[0], mix.inputs["B"])
        emit = mix.outputs["Result"]
        if spec.get("vcol"):
            vc = nt.nodes.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
            mix2 = nt.nodes.new("ShaderNodeMix"); mix2.data_type = "RGBA"; mix2.blend_type = "MULTIPLY"; mix2.inputs["Factor"].default_value = 1.0
            nt.links.new(emit, mix2.inputs["A"]); nt.links.new(vc.outputs["Color"], mix2.inputs["B"]); emit = mix2.outputs["Result"]
        nt.links.new(emit, b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = spec.get("strength", 1.0)
        nt.links.new(t.outputs["Alpha"], b.inputs["Alpha"])
        if hasattr(m, "surface_render_method"): m.surface_render_method = "BLENDED"
        m["gof3_blend"] = "additive"
    _mats[key] = m
    return m

def mesh(spec):
    P, N, UV, VC, F, FM = [], [], [], [], [], []
    keys = spec["materials"]
    has_vcol = False
    for si, sec in enumerate(ae4_meshgroup.read_all(spec["meshgroup"])):
        o = len(P)
        pos = sec["a_position"]
        if "a_pos2dOffset" in sec:   # camera-facing sprite corners: a flat quad in the engine XY plane
            pos = [(x + ox, y + oy, z) for (x, y, z), (ox, oy) in zip(pos, sec["a_pos2dOffset"])]
        P += pos
        N += sec.get("a_normal", [(0.0, 0.0, 1.0)] * sec["count"])
        UV += sec.get("a_texCoord0", [(0.0, 0.0)] * sec["count"])
        VC += sec.get("a_vtxColor", [(1.0, 1.0, 1.0, 1.0)] * sec["count"]); has_vcol |= "a_vtxColor" in sec
        idx = sec["indices"]
        for i in range(0, len(idx), 3):
            F.append((idx[i] + o, idx[i + 1] + o, idx[i + 2] + o)); FM.append(min(si, len(keys) - 1))
    seen = set()   # Blender merges faces over the same three vertices; the game draws them: give repeats own copies
    for fi, f in enumerate(F):
        k = frozenset(f)
        if k in seen:
            nf = []
            for v in f:
                P.append(P[v]); N.append(N[v]); UV.append(UV[v]); VC.append(VC[v]); nf.append(len(P) - 1)
            F[fi] = tuple(nf)
        seen.add(k)
    me = bpy.data.meshes.new(spec["name"])
    me.from_pydata([(x, -z, y) for x, y, z in P], [], F)
    uv = me.uv_layers.new(name="UVMap")
    for l in me.loops:
        u, v = UV[l.vertex_index]; uv.data[l.index].uv = (u, 1.0 - v)
    if has_vcol:   # also all white: a material's vertex colour node reads black from a missing attribute
        ca = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        for i, c in enumerate(VC): ca.data[i].color = c
    for p in me.polygons: p.use_smooth = True; p.material_index = FM[p.index]
    me.normals_split_custom_set_from_vertices([(x, -z, y) for x, y, z in N])
    for k in keys: me.materials.append(material(k))
    ob = bpy.data.objects.new(spec["name"], me); coll.objects.link(ob)
    x, y, z = spec.get("pos", (0, 0, 0)); ob.location = (x, -z, y)
    return ob

root = bpy.data.objects.new(name, None); coll.objects.link(root)
for o in cfg["objects"]: mesh(o).parent = root
for e in cfg.get("empties", []):
    ob = bpy.data.objects.new(e["name"], None); coll.objects.link(ob); ob.empty_display_size = 0.2; ob.parent = root
    q = e.get("rot", (0, 0, 0, 1))
    ob.matrix_basis = C @ mathutils.Matrix.LocRotScale(mathutils.Vector(e["pos"]), mathutils.Quaternion((q[3], q[0], q[1], q[2])),
                                                        mathutils.Vector((1, 1, 1))) @ C.inverted()

os.makedirs(out, exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{name}.blend"))
# GOF3_NO_FBX (import.py): the .blend only; the mod is built from it and its glTF, the FBX is for other uses.
if not os.environ.get("GOF3_NO_FBX"):
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, f"{name}.fbx"), path_mode="COPY", embed_textures=True,
                             mesh_smooth_type="OFF", add_leaf_bones=False, use_tspace=True)
print("wrote", os.path.join(out, f"{name}.fbx"), "objects:", len(bpy.data.objects))
