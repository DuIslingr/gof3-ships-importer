"""Blender script: GoF3 ship -> FBX (+ .blend).
blender -b -P ae4_ship_to_fbx.py -- <ship dir> <ship name> <out dir>     (textures baked first by ae4_ship_textures.py into <out dir>/textures)

Engine space is Y-up; Blender gets (x, -z, y), the FBX exporter writes Y-up again (-Z forward... the ship's nose is engine -Z).
Contents: <name>_LOD0..5 (LOD0: body + glass, the glass = the trailing index block whose vertices no earlier triangle uses),
decals, the 7 weapon mounts with their contact shadows at the scene's weapon_mount_helper nodes, and every other scene node
(weapon hardpoints, engines, contrails, camera, damage points, collision volumes, npc trails) as empties."""
import bpy, sys, os, re, struct, mathutils
sys.path.insert(0, os.path.dirname(__file__))
import ae4_meshgroup, ae4_scene

argv = sys.argv[sys.argv.index("--") + 1:]
src, name, out = argv[:3]
texdir = os.path.join(out, "textures")
assets = os.path.abspath(src).replace("\\", "/").split("/ships/")[0]   # the assets dir, also for ships outside <race>/<num>
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

def material(mname, base, normal=None, spec=None, rough=None, emissive=None, alpha=False, unlit=False, roughness=0.5, black=False):
    m = bpy.data.materials.new(mname); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    def tnode(fn, data=False):
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = image(fn, data); return t
    t = tnode(base)
    if black: b.inputs["Base Color"].default_value = (0, 0, 0, 1)
    else: nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    if alpha:
        nt.links.new(t.outputs["Alpha"], b.inputs["Alpha"])
        if hasattr(m, "surface_render_method"): m.surface_render_method = "BLENDED"
    if unlit:
        nt.links.new(t.outputs["Color"], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 1.0
    if normal:
        nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(tnode(normal, True).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    if spec: nt.links.new(tnode(spec).outputs["Color"], b.inputs["Specular Tint"])
    if rough: nt.links.new(tnode(rough, True).outputs["Color"], b.inputs["Roughness"])
    else: b.inputs["Roughness"].default_value = roughness
    if emissive:
        nt.links.new(tnode(emissive).outputs["Color"], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 1.0
    b.inputs["Metallic"].default_value = 0.0
    return m

def mesh(path, oname, mats, section_mat=None):
    """One object from every section of a meshgroup; section i gets material slot section_mat[i] (default 0)."""
    g = {"indices": []}
    for si, sec in enumerate(ae4_meshgroup.read_all(path)):
        base = len(g.get("a_position", []))
        for a in ("a_position", "a_normal", "a_texCoord0"):
            g.setdefault(a, [])
            g[a] += sec[a] if a in sec else [(0.0, 0.0) if a == "a_texCoord0" else (0.0, 1.0, 0.0)] * sec["count"]
        g.setdefault("mat", []).extend([(section_mat or {}).get(si, 0)] * (len(sec["indices"]) // 3))
        g["indices"] += [i + base for i in sec["indices"]]
    idx = g["indices"]
    # Blender merges faces over the same three vertices; the game draws them (overlaps, back faces): give repeats own copies
    seen = set()
    for i in range(0, len(idx), 3):
        k = frozenset(idx[i:i + 3])
        if k in seen:
            for j in range(i, i + 3):
                for a in ("a_position", "a_normal", "a_texCoord0"):
                    g[a].append(g[a][idx[j]])
                idx[j] = len(g["a_position"]) - 1
        seen.add(k)
    me = bpy.data.meshes.new(oname)
    me.from_pydata([(x, -z, y) for x, y, z in g["a_position"]], [], [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx), 3)])
    for p in me.polygons: p.material_index = g["mat"][p.index]
    uv = me.uv_layers.new(name="UVMap"); tc = g["a_texCoord0"]
    for l in me.loops:
        u, v = tc[l.vertex_index]; uv.data[l.index].uv = (u, 1.0 - v)
    for p in me.polygons: p.use_smooth = True
    me.normals_split_custom_set_from_vertices([(x, -z, y) for x, y, z in g["a_normal"]])
    for m in mats: me.materials.append(m)
    ob = bpy.data.objects.new(oname, me); coll.objects.link(ob)
    return ob

def lod_materials(model):
    """Per LOD, the material ids of its meshgroup sections, from the .ae4model:
    [OM4A][ver][N][N x 8-byte ids][LOD count] then per LOD [id 8][count][count x material id 8][pad u32][distance f32][pad u32]."""
    d = ae4_meshgroup.unpack(open(model, "rb").read())
    n = struct.unpack_from("<I", d, 8)[0]
    o = 12 + 8 * n
    lods = []
    count = struct.unpack_from("<I", d, o)[0]; o += 4
    for _ in range(count):
        o += 8                                     # the LOD's own id
        c = struct.unpack_from("<I", d, o)[0]; o += 4
        lods.append([d[o + 8 * i:o + 8 * i + 8].hex() for i in range(c)])
        o += 8 * c + 12   # [pad u32][distance f32][pad u32]
    return lods

def local(n):
    q = n["rot"]
    m = mathutils.Matrix.LocRotScale(mathutils.Vector(n["pos"]), mathutils.Quaternion((q[3], q[0], q[1], q[2])), mathutils.Vector(n["scale"]))
    return C @ m @ C.inverted()

T = lambda s: f"{name}_{s}.png"
body = material(f"{name}_body", T("basecolor"), T("normal"), T("specular"), T("roughness"), T("emissive"))
glass = material(f"{name}_glass", T("glass"), alpha=True, unlit=True) if os.path.exists(os.path.join(texdir, T("glass"))) else None
if os.path.exists(os.path.join(texdir, T("iridescence_mask"))):   # for ae4_to_gltf.py (KHR_materials_iridescence)
    body["gof3_iridescence_mask"] = os.path.join(texdir, T("iridescence_mask"))
own_decals = os.path.exists(os.path.join(texdir, T("decals")))   # a ship's own decal sheet (starfox) instead of the shared ones
decal = material(f"{name}_decals", T("decals") if own_decals else "ship_decals_000.png", alpha=True, roughness=0.6)
mountm = material("weapon_generic_mount_000", "weapon_generic_mount_000_basecolor.png", "weapon_generic_mount_000_normal.png", roughness=0.55)
shadowm = material("ship_mount_shadow", "ship_mount_shadow.png", alpha=True, black=True, roughness=1.0)

root = bpy.data.objects.new(name, None); coll.objects.link(root)
lods = lod_materials(os.path.join(src, f"{name}_lod_000_body.ae4model"))
ids = [i for lod in lods for i in lod]
body_id = max(lods[0], key=lambda i: (ids.count(i), -lods[0].index(i)))   # the most used material is the hull (a tie: the
                                                                       # first section, vossk/109); any other one is the glass
glass_sections = 0
for k in range(0, 21):   # most ships 6 LODs, some (nivelian/221) 13
    p = os.path.join(src, f"{name}_lod_{k:03d}_body.ae4meshgroup")
    if not os.path.exists(p): continue
    mats = lods[k] if k < len(lods) else [body_id]
    slot = {i: (1 if m != body_id and glass else 0) for i, m in enumerate(mats)}
    glass_sections += sum(slot.values()) if k == 0 else 0
    mesh(p, f"{name}_LOD{k}", [body, glass] if any(slot.values()) else [body], slot).parent = root
dp = os.path.join(src, f"{name}_lod_000_decals.ae4meshgroup")
if os.path.exists(dp): mesh(dp, f"{name}_decals", [decal]).parent = root

# scene nodes
scene = next((os.path.join(src, f) for f in os.listdir(src) if f.lower() == f"{name}.ae4scene".lower()), None)   # ship_StarFox_000
nodes = ae4_scene.read(scene)
objs = {}
skip = re.compile(r"^(node_\d+|weapon_generic_mount_000.*|.*_lod_\d+_(body|decals)|.*_geometry|.*_weapon_shadow_\d+)$")
def build(nid, parent):
    n = nodes[nid]
    if skip.match(n["name"]):                 # mesh / container node: no empty, but keep its children
        for cid, c in sorted(nodes.items()):
            if c["parent"] == nid: build(cid, parent)
        return
    e = bpy.data.objects.new(n["name"], None); coll.objects.link(e)
    e.empty_display_size = 0.5; e.parent = parent; e.matrix_basis = local(n)
    objs[nid] = e
    if "weapon_mount_helper" in n["name"]:
        mount = mesh(os.path.join(assets, "weapons/generic/mounts/000/weapon_generic_mount_000_lod_000_body.ae4meshgroup"),
                     n["name"].replace("_helper", "") + "_mesh", [mountm])
        mount.parent = e
        for cid, c in nodes.items():
            if c["parent"] == nid and "_weapon_shadow_" in c["name"]:
                sp = os.path.join(src, c["name"] + ".ae4meshgroup")
                if os.path.exists(sp):
                    s = mesh(sp, c["name"], [shadowm]); s.parent = e; s.matrix_basis = local(c)
    for cid, c in sorted(nodes.items()):
        if c["parent"] == nid: build(cid, e)
for nid, n in sorted(nodes.items()):
    if n["parent"] == -1 or n["parent"] not in nodes: build(nid, root)

os.makedirs(out, exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{name}.blend"))
# GOF3_NO_FBX (import.py): the .blend only; the mod is built from it and its glTF, the FBX is for other uses.
if not os.environ.get("GOF3_NO_FBX"):
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, f"{name}.fbx"), path_mode="COPY", embed_textures=True,
                             mesh_smooth_type="OFF", add_leaf_bones=False, use_tspace=True)
print("LOD materials", [len(l) for l in lods], "- LOD0 glass sections:", glass_sections)
print("wrote", os.path.join(out, f"{name}.fbx"), "objects:", len(bpy.data.objects))
