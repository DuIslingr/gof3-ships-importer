"""Blender script: export a converted ship .blend to glTF binary.
blender -b -P ae4_to_gltf.py -- <file.blend>
Writes <name>.glb (LOD0, decals, glass, mounts, shadows, hardpoint/helper empties as nodes) and, if the .blend has them,
<name>_lods.glb with LOD1..LODn (glTF has no standard LOD mechanism, so they are kept out of the main file)."""
import bpy, sys, os, re, json, struct
blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=blend)
base = os.path.splitext(blend)[0]
lod = re.compile(r"_LOD[1-9]\d*$")
# alpha-blended materials (glass, decals, mount shadows) -> glTF alphaMode BLEND
for m in bpy.data.materials:
    if m.use_nodes and m.node_tree.nodes.get("Principled BSDF") and m.node_tree.nodes["Principled BSDF"].inputs["Alpha"].is_linked:
        if hasattr(m, "surface_render_method"): m.surface_render_method = "BLENDED"
def export(path, keep):
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        o.select_set(keep(o))
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
                              export_tangents=True, export_image_format="AUTO", export_extras=False)
    print("wrote", path, sum(1 for o in bpy.data.objects if keep(o)), "objects")
    add_iridescence(path)
def add_iridescence(path):
    """Blender's exporter ignores thin film: add KHR_materials_iridescence to materials tagged gof3_iridescence_mask
    (the game's view-angle spectrum, masked by the texture; glTF reads the factor from the texture's R channel)."""
    tagged = {m.name: m["gof3_iridescence_mask"] for m in bpy.data.materials if "gof3_iridescence_mask" in m}
    if not tagged: return
    d = open(path, "rb").read()
    jlen = struct.unpack_from("<I", d, 12)[0]; j = json.loads(d[20:20 + jlen])
    blen = struct.unpack_from("<I", d, 20 + jlen)[0]; binc = bytearray(d[28 + jlen:28 + jlen + blen])
    done = 0
    for mat in j.get("materials", []):
        if mat.get("name") not in tagged: continue
        png = open(tagged[mat["name"]], "rb").read()
        while len(binc) % 4: binc.append(0)
        j["bufferViews"].append({"buffer": 0, "byteOffset": len(binc), "byteLength": len(png)}); binc += png
        j.setdefault("images", []).append({"name": os.path.basename(tagged[mat["name"]])[:-4], "mimeType": "image/png",
                                           "bufferView": len(j["bufferViews"]) - 1})
        j.setdefault("textures", []).append({"source": len(j["images"]) - 1})
        mat.setdefault("extensions", {})["KHR_materials_iridescence"] = {
            "iridescenceFactor": 1.0, "iridescenceTexture": {"index": len(j["textures"]) - 1},
            "iridescenceIor": 1.3, "iridescenceThicknessMinimum": 100.0, "iridescenceThicknessMaximum": 400.0}
        done += 1
    if not done: return
    j.setdefault("extensionsUsed", []).append("KHR_materials_iridescence")
    while len(binc) % 4: binc.append(0)
    j["buffers"][0]["byteLength"] = len(binc)
    js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binc)) + struct.pack("<II", len(js), 0x4E4F534A) + js \
        + struct.pack("<II", len(binc), 0x004E4942) + bytes(binc)
    open(path, "wb").write(out)
    print("added KHR_materials_iridescence to", done, "material(s) in", os.path.basename(path))

def ancestors_ok(o):
    while o:
        if lod.search(o.name): return False
        o = o.parent
    return True
export(base + ".glb", ancestors_ok)
lods = [o for o in bpy.data.objects if lod.search(o.name)]
if lods and not os.path.basename(base).endswith("_loadout"):
    export(base + "_lods.glb", lambda o: lod.search(o.name) is not None)
