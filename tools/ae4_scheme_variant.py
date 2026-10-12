"""Blender script: a converted ship in one of its paint schemes, as a model of its own (a scheme the game sells as a
separate ship, e.g. the Cronus Dragon = terran/020 + the dragon scheme).
blender -b -P ae4_scheme_variant.py -- <converted ship dir> <scheme> [out dir, default <ship dir>_<scheme>]

Takes <ship>.blend, points the hull at textures/<ship>_basecolor_<scheme> / _emissive_<scheme> (and the glass, specular and
roughness at _glass_ / _specular_ / _roughness_<scheme> when the scheme has its own), renames the root, the LOD / decal objects and the materials to
<ship>_<scheme> (so Unity doesn't merge them with the plain ship's), and writes <out>/<ship>_<scheme>.blend / .fbx with
the textures hard-linked into <out>/textures. Run ae4_to_gltf.py on the .blend for the .glb."""
import bpy, sys, os, shutil, json

argv = sys.argv[sys.argv.index("--") + 1:]
src, scheme = os.path.abspath(argv[0].rstrip("/\\")), argv[1]
name = os.path.basename(src)
var = f"{name}_{scheme}"
out = os.path.abspath(argv[2]) if len(argv) > 2 else f"{src}_{scheme}"
tex_in, tex_out = os.path.join(src, "textures"), os.path.join(out, "textures")
os.makedirs(tex_out, exist_ok=True)
for fn in os.listdir(tex_in):   # hard links: no extra space
    dst = os.path.join(tex_out, fn)
    if os.path.exists(dst): os.remove(dst)
    try: os.link(os.path.join(tex_in, fn), dst)
    except OSError: shutil.copy2(os.path.join(tex_in, fn), dst)

swap = {f"{name}_basecolor.png": f"{name}_basecolor_{scheme}.png", f"{name}_emissive.png": f"{name}_emissive_{scheme}.png"}
rj = os.path.join(src, "resolve.json")
DATA_SKIN = any(sk["scheme"] == scheme for sk in (json.load(open(rj, encoding='utf-8-sig')).get("data_skins", []) if os.path.exists(rj) else []))
for part in (("specular", "roughness") if DATA_SKIN else ("glass", "specular", "roughness")):   # the scheme's own canopy /
    # specular look, when it has one; a data.pdb skin never changes the glass (a material file's gold scheme does)
    if os.path.exists(os.path.join(tex_in, f"{name}_{part}_{scheme}.png")):
        swap[f"{name}_{part}.png"] = f"{name}_{part}_{scheme}.png"
rj = os.path.join(src, "resolve.json")   # a data.pdb skin may use another decal sheet (tools/data_skins.json "decals")
for sk in (json.load(open(rj, encoding='utf-8-sig')).get("data_skins", []) if os.path.exists(rj) else []):
    if sk["scheme"] == scheme and sk.get("decals"):
        swap["ship_decals_000.png"] = sk["decals"]
NO_IRI = any(sk["scheme"] == scheme and sk.get("no_iridescence") for sk in (json.load(open(rj, encoding='utf-8-sig')).get("data_skins", []) if os.path.exists(rj) else []))
for k, v in swap.items():
    if not os.path.exists(os.path.join(tex_in, v)):
        sys.exit(f"missing {v}: bake the scheme first (ae4_ship_textures.py)")

bpy.ops.wm.open_mainfile(filepath=os.path.join(src, f"{name}.blend"))
for img in bpy.data.images:
    fn = os.path.basename(img.filepath)
    if not fn: continue
    new = swap.get(fn, fn)
    img.filepath = os.path.join(tex_out, new)
    img.name = new
    img.reload()
for m in bpy.data.materials:
    if NO_IRI and "gof3_iridescence_mask" in m:   # a _noiri material (Shamash II): no thin film in the glTF
        del m["gof3_iridescence_mask"]
    if m.name.startswith(name + "_"):
        m.name = var + m.name[len(name):]
for o in bpy.data.objects:
    if o.name == name or o.name.startswith(name + "_LOD") or o.name == f"{name}_decals":
        o.name = var + o.name[len(name):]
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{var}.blend"))
# GOF3_NO_FBX (import.py): the .blend only; the mod is built from it and its glTF, the FBX is for other uses.
if not os.environ.get("GOF3_NO_FBX"):
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, f"{var}.fbx"), path_mode="COPY", embed_textures=True,
                             mesh_smooth_type="OFF", add_leaf_bones=False, use_tspace=True)
print("swapped", swap)
print("wrote", os.path.join(out, f"{var}.fbx"))
