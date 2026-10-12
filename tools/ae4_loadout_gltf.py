"""Blender script: a converted ship with guns on its hardpoints -> one glTF binary (LOD0, like ae4_to_gltf.py's main file).
blender -b -P ae4_loadout_gltf.py -- <ship .blend> <weapons dir> <out .glb> [slot=family:mk,...]
Each gun is the converted weapon (<weapons dir>/weapon_generic_<family>/weapon_generic_<family>_mk<mk>.blend: its root
empty, LOD0 and muzzle empties, with its own material) parented to the ship's *_weapon_<slot> empty at identity, so
the hardpoint's transform (and its 0.75 scale) places it; a slot without a hardpoint is an error; one copy of the mesh per gun model. No spec = the ship as it is.
The .blend is only read: the result goes through ae4_to_gltf.py from a temporary copy next to <out>."""
import bpy, sys, os, re, subprocess, shutil, tempfile

argv = sys.argv[sys.argv.index("--") + 1:]
blend, weapons, out = (os.path.abspath(a) for a in argv[:3])   # a relative .blend path broke the "//.." remap of the guns' textures
spec = argv[3] if len(argv) > 3 else ""
here = os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.open_mainfile(filepath=blend)
name = os.path.splitext(os.path.basename(blend))[0]
lod = re.compile(r"_LOD([1-9]\d*)$")
loaded = {}   # "fam:mk" -> the appended objects (root first)


def load(fam, mk):
    key = f"{fam}:{mk}"
    if key in loaded: return loaded[key]
    w = f"weapon_generic_{fam}_mk{mk}"
    path = os.path.join(weapons, f"weapon_generic_{fam}", w + ".blend")
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n == w or n == w + "_LOD0" or n.startswith(w + "_muzzle_")]
    objs = [o for o in dst.objects if o]
    root = next(o for o in objs if o.name.startswith(w) and o.type == "EMPTY" and "_muzzle_" not in o.name)
    loaded[key] = [(root, root.name)] + [(o, o.name) for o in objs if o is not root]   # with the original names
    return loaded[key]


# the hardpoints: <ship>_weapon_NNN empties; a skin's .blend keeps its hull's names (ship_terran_000_red, ship_retro_000:
# ship_terran_000_weapon_000), so they are found by the suffix
hardpoints = {m.group(1): o for o in bpy.data.objects if o.type == "EMPTY"
              for m in [re.search(r"_weapon_(\d{3})$", o.name)] if m}
for item in filter(None, spec.split(",")):
    slot, wpn = item.split("="); fam, mk = wpn.split(":")
    hp = hardpoints.get(slot)
    if hp is None: raise SystemExit(f"no hardpoint {slot} in {blend}")
    src = load(fam, mk)
    first = src[0][0].users_collection == ()   # not linked to the scene yet: use the appended objects themselves
    copies = {}
    for o, _ in src:
        c = o if first else o.copy()      # copies share the mesh data
        bpy.context.scene.collection.objects.link(c)
        copies[o] = c
    for o, c in copies.items():
        if o.parent in copies: c.parent = copies[o.parent]
    root = copies[src[0][0]]
    root.parent = hp; root.matrix_parent_inverse.identity()
    root.location = (0, 0, 0); root.rotation_euler = (0, 0, 0); root.scale = (1, 1, 1)
    tag = f"{hp.name}_gun_{fam}_mk{mk}"
    for o, orig in src:
        copies[o].name = tag + orig[len(f"weapon_generic_{fam}_mk{mk}"):]
    print("attached", slot, fam, mk)

tmp = tempfile.mkdtemp(prefix="loadout_", dir=os.path.dirname(os.path.abspath(out)))
try:
    tb = os.path.join(tmp, name + "_loadout.blend")
    bpy.ops.file.make_paths_absolute()   # the ship's and the guns' textures stay where they are
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=tb, relative_remap=False)
    r = subprocess.run([bpy.app.binary_path, "-b", "-P", os.path.join(here, "ae4_to_gltf.py"), "--", tb],
                       capture_output=True, text=True)
    glb = os.path.join(tmp, name + "_loadout.glb")
    if r.returncode or not os.path.exists(glb): raise SystemExit("ae4_to_gltf failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    shutil.move(glb, out)
    print("wrote", out)
finally:
    if not os.environ.get("KEEP_TMP"): shutil.rmtree(tmp, ignore_errors=True)
