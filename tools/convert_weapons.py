"""GoF3 weapons -> FBX / .blend / glTF, one folder per weapon under <out>/weapons (default ../gof3converted/weapons).
python convert_weapons.py [assets dir, default ../assets_best] [out root] [only: a substring of the weapon names]
Needs this venv (texture2ddecoder, Pillow, numpy) and Blender on PATH.

  weapon_generic_NNN[_gold]   the guns: mk1 / mk2 / mk3 each with its LODs and muzzle empties (gold = 000 / 004 / 005's
                              models and textures with the gold material's colours and gloss)
  weapon_<race>_mount_000     the hardpoint mounts (generic 000 and the Terran / Nivelian / Vossk ones), "mount" empty
  weapon_rocket_<type>        the rockets: body, exhaust (crossed planes) and glow sprite at the scene's offsets
  weapon_mine_000             the mine: body (two shells) and its glow sprites
  weapon_flak_mines_<race>_000  the flak mines
Not converted: the menu (hangar showroom) copies and their shadow planes, the secondary launcher (a muzzle node only, no mesh).

Materials are linked by GUID only (models list material GUIDs, materials texture GUIDs; no file stores its own): the
weapon's own material by its name, the rest from MATERIALS / VFX_TEXTURES below (see each README)."""
import contextlib, glob, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = os.environ.get("GOF3_BLENDER") or "blender"   # import.py sets it (Blender found by itself on any system)
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image
import ae4_material, ae4_scene, ae4_texture
from ae4_resolve import model_lods
if os.sep == "\\":   # Windows: the code splits and joins paths with "/": glob's results (and the paths given) too
    _glob = glob.glob
    glob.glob = lambda pattern, **kw: [p.replace("\\", "/") for p in _glob(pattern, **kw)]

A = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "assets_best")).replace("\\", "/")
OUT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "gof3converted", "weapons"))
ONLY = sys.argv[3] if len(sys.argv) > 3 else ""
W = os.path.join(A, "weapons")
PY = sys.executable

# vfx textures the glow / exhaust materials name by GUID only (their "Diffuse" sampler: ea14a6b1a5a1b34b for the rocket
# glows, da5a9b35bdda51b4 for the exhausts and the mine sprites; each shared by dozens of vfx materials, all of them round
# flares / lights / beacon sprites, and no file says which texture it is): vfx_generic_glow_000 stands in for both, as in
# ae4_ship_textures.py (on the exhaust's crossed planes, U along, V across, it gives a tapering flame)
VFX_TEXTURES = {"glow": "vfx/generic/vfx_generic_glow_000", "exhaust": "vfx/generic/vfx_generic_glow_000"}


def save(a, path, mode=None):
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(path)


def tex(p):
    return np.asarray(ae4_texture.decode(p)).astype(np.float32) / 255


def roughness(g):
    return (2.0 / (2.0 ** (9.0 * g + 1.0) + 2.0)) ** 0.25


FAILED = []


@contextlib.contextmanager
def skipped(d):
    """One weapon: a failure (a texture or material the game files lack, e.g. a gold variant missing from a Switch-only
    romfs) skips it and the rest go on; listed at the end."""
    try:
        yield
    except (SystemExit, Exception) as e:
        name = os.path.basename(d.rstrip("/\\"))
        FAILED.append(name)
        print(f"  skipped {name}: {e}", flush=True)


def run(cmd, log):
    r = subprocess.run(cmd, capture_output=True, text=True)
    open(log, "a", encoding='utf-8').write(" ".join(cmd) + "\n" + r.stdout + r.stderr + "\n")
    if r.returncode: raise SystemExit(f"failed: {' '.join(cmd)} (see {log})")
    return r.stdout


def blender(cfg, folder):
    os.makedirs(folder, exist_ok=True)
    cp = os.path.join(folder, cfg["name"] + ".json")
    json.dump(cfg, open(cp, "w", encoding='utf-8'), indent=1)
    log = os.path.join(folder, "convert.log")
    o = run([BLENDER, "-b", "-P", os.path.join(HERE, "ae4_weapon_to_fbx.py"), "--", cp], log)
    run([BLENDER, "-b", "-P", os.path.join(HERE, "ae4_to_gltf.py"), "--", os.path.join(folder, cfg["name"] + ".blend")], log)
    os.remove(cp)
    print(" ", next((re.split(r"[\\/]", l)[-1] for l in o.splitlines() if l.startswith("wrote")), cfg["name"]))


def scene_nodes(path):
    return ae4_scene.read(path) if os.path.exists(path) else {}


def vfx_texture(texdir, kind):
    """The game blends these additively (rgb added, alpha 1); glTF / FBX have no additive mode: alpha = the brightest
    channel, so the black surround is transparent under ordinary alpha blending."""
    fn = os.path.basename(VFX_TEXTURES[kind]) + "_additive.png"
    p = os.path.join(texdir, fn)
    if not os.path.exists(p):
        os.makedirs(texdir, exist_ok=True)
        t = tex(os.path.join(A, VFX_TEXTURES[kind] + ".tga.ae4texture"))
        save(np.dstack([t[..., :3], t[..., :3].max(-1) * t[..., 3]]), p, "RGBA")
    return fn


def glow_material(mpath, texdir, kind):
    """VFX shader (BlendMode 2): rgb = t x vcol; c = mix(C1, C2, rgb); rgb *= rgb + c (1 - rgb) x Colorize_Multiplier.
    For a white texel that is the texel itself; the glTF / FBX stand-in: emission = texture x vertex colour x C1 x M."""
    v = ae4_material.read(mpath)[0]
    return {"kind": "glow", "color": list(v.get("Colorize_Color1", (1, 1, 1, 1))[:3]), "strength": v.get("Colorize_Multiplier", 1.0),
            "texture": vfx_texture(texdir, kind), "vcol": bool(v.get("Colorize_VertexColors")), "source": os.path.relpath(mpath, A)}


def readme(folder, title, lines):
    open(os.path.join(folder, "README.txt"), "w", encoding='utf-8').write(
        f"{title} (Galaxy on Fire 3), converted from {os.path.relpath(A, os.path.dirname(HERE))}/ with ../../../tools/convert_weapons.py\n"
        "(assets_best = the iOS assets/ tree, overlaid with the Android OBB, overlaid with the Switch romfs: each file from the\n"
        " best source that has it)\n\n"
        "Y-up, barrel / nose toward -Z, 1 unit = 1 game unit. Each model: .fbx (textures embedded), .blend, .glb (LOD0 and\n"
        "the other parts) and _lods.glb (LOD1..n, when there are any); regenerate the .glb: blender -b -P\n"
        "../../../tools/ae4_to_gltf.py -- <file.blend>\n\n" + "\n".join(lines) + "\n")


# ---- guns -------------------------------------------------------------------------------------------------------------
def guns():
    for d in sorted(glob.glob(f"{W}/generic/[0-9][0-9][0-9]*")):
        with skipped(d):
            fam = os.path.basename(d)                        # 001, 000_gold
            base = fam.split("_")[0]
            name = f"weapon_generic_{fam}"
            if ONLY not in name: continue
            print(name)
            folder = os.path.join(OUT, name); texdir = os.path.join(folder, "textures")
            mat = f"{d}/{name}.ae4material"
            run([PY, os.path.join(HERE, "ae4_weapon_textures.py"), f"{W}/generic/{base}", texdir, mat, name], os.path.join(folder, "convert.log"))
            lines = [f"Material  weapons/generic/{fam}/{name}.ae4material",
                     f"Textures  weapons/generic/{base}/weapon_generic_{base}_{{diffuse, colormask_000, normal_ao}}.tga.ae4texture"
                     + (" (the gold material points at the base gun's textures)" if fam != base else ""), "",
                     "Models (one file per tier):"]
            for mk in (1, 2, 3):
                models = glob.glob(f"{d}/*_mk{mk}_lod_000_body.ae4model")
                if not models: continue
                stem = os.path.basename(models[0])[:-len("_lod_000_body.ae4model")]   # 005_gold's models are named weapon_generic_005_mkN
                lods = model_lods(models[0])
                objs = []
                for k in range(0, 21):
                    mg = f"{d}/{stem}_lod_{k:03d}_body.ae4meshgroup"
                    if os.path.exists(mg): objs.append({"name": f"{name}_mk{mk}_LOD{k}", "meshgroup": mg, "materials": [name] * len(lods[min(k, len(lods) - 1)])})
                nodes = scene_nodes(f"{d}/{name}_mk{mk}.ae4scene") or scene_nodes(f"{d}/{stem}.ae4scene")
                empties = [{"name": n["name"].replace(stem, f"{name}_mk{mk}"), "pos": n["pos"], "rot": n["rot"]}
                           for n in nodes.values() if "_muzzle_" in n["name"]]
                blender({"name": f"{name}_mk{mk}", "out": folder, "texdir": texdir, "objects": objs, "empties": empties,
                         "materials": {name: {"kind": "pbr", "prefix": name}}}, folder)
                lines.append(f"  {name}_mk{mk}: {len(objs)} LODs, muzzles " + ", ".join(
                    f"{e['name'].split('_')[-1]} at ({', '.join(f'{v:.3f}' for v in e['pos'])})" for e in sorted(empties, key=lambda e: e["name"])))
            lines += ["", "textures/ (the weapon shader's math, ../../../tools/ae4_weapon_textures.py):",
                      "  _basecolor (colorized diffuse), _emissive (colormask alpha x diffuse), _normal (OpenGL / +Y green),",
                      "  _specular (diffuse^2 x the tint, Blender's Specular Tint), _roughness (constant: Gloss_Amount x Gloss_Multiplier)",
                      "  and the raw inputs for repainting: _diffuse_raw, _colormask_000 (R tint mask, A emissive / tint blend),",
                      "  _ao_raw (normal_ao.b, not used by the game shader), _specular_gloss_raw (in the material, never sampled)",
                      "", "Not included: the game shader's fresnel, rim light and environment; the cloak / dissolve materials."]
            readme(folder, name, lines)


# ---- mounts -----------------------------------------------------------------------------------------------------------
MOUNT_MAT = "weapons/generic/mounts/000/generic_mount_000.ae4material"
def mount_textures(texdir):
    """generic_mount_000: T1 normal_diffuse = RG normal, B diffuse (Diffuse_Channel 2), A specular (Specular_Channel 3);
    T2 colormask with white / white colours (no tint)."""
    p = "weapon_generic_mount_000"
    if os.path.exists(os.path.join(texdir, p + "_basecolor.png")): return p
    os.makedirs(texdir, exist_ok=True)
    v = ae4_material.read(os.path.join(A, MOUNT_MAT))[0]
    M = tex(f"{W}/generic/mounts/000/weapon_generic_mount_000_normal_diffuse.tga.ae4texture")
    d = np.repeat(M[..., 2:3], 3, -1) * np.array(v.get("Diffuse_Color", (1, 1, 1, 1))[:3], np.float32)
    save(d, os.path.join(texdir, p + "_basecolor.png"))
    xy = M[..., :2] * 2 - 1
    n = np.dstack([xy, np.ones(xy.shape[:2], np.float32)]); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    save(n * 0.5 + 0.5, os.path.join(texdir, p + "_normal.png"))
    save(np.repeat(M[..., 3:4], 3, -1) * v.get("Specular_Multiplier", 1.0), os.path.join(texdir, p + "_specular.png"))
    save(np.full(M.shape[:2], roughness(v.get("Gloss_Amount", 0.5) * v.get("Gloss_Multiplier", 1.0)), np.float32),
         os.path.join(texdir, p + "_roughness.png"), "L")
    return p


def mounts():
    for d in sorted(glob.glob(f"{W}/generic/mounts/*/")):
        with skipped(d):
            model = glob.glob(f"{d}*_lod_000_body.ae4model")[0]
            name = os.path.basename(model)[:-len("_lod_000_body.ae4model")]
            if ONLY not in name: continue
            print(name)
            folder = os.path.join(OUT, name); texdir = os.path.join(folder, "textures")
            guid = model_lods(model)[0][0]
            src = MATERIALS.get(guid, MOUNT_MAT)
            p = mount_textures(texdir) if src == MOUNT_MAT else material_textures(src, texdir)
            nodes = scene_nodes(f"{d}{name}.ae4scene")
            empties = [{"name": n["name"], "pos": n["pos"], "rot": n["rot"]} for n in nodes.values() if n["name"].endswith("_mount")]
            blender({"name": name, "out": folder, "texdir": texdir, "empties": empties,
                     "objects": [{"name": f"{name}_LOD0", "meshgroup": f"{d}{name}_lod_000_body.ae4meshgroup", "materials": ["mount"]}],
                     "materials": {"mount": {"kind": "pbr", "prefix": p}}}, folder)
            note = MATERIAL_NOTES.get(guid, "")
            readme(folder, name, [f"Material  {src}" + (f"  ({note})" if note else "")
                                  + ("" if guid in MATERIALS or src == MOUNT_MAT else f"  (model GUID {guid}: not found, the generic mount's stands in)"),
                                  "", f"{name}: the mount mesh, " + (f"the '{empties[0]['name']}' empty (where the gun sits) at ({', '.join(f'{v:.3f}' for v in empties[0]['pos'])})" if empties else "no gun node"),
                                  "", "textures/: _basecolor, _normal (OpenGL / +Y green), _specular, _roughness (constant)"])


# ---- materials found only by GUID ---------------------------------------------------------------------------------------
MATERIALS = {}        # model material GUID -> material path (relative to the assets dir), filled by find_materials()
MATERIAL_NOTES = {}


def material_textures(mrel, texdir):
    """A plain lit material (diffuse / normal / specular slots by name): bake basecolor, normal, specular, roughness."""
    raise NotImplementedError(mrel)


# ---- rockets ----------------------------------------------------------------------------------------------------------
def rocket_textures(mpath, texdir):
    """weapon_rocket_all / _redtrail: T1 diffuse RGB, A emissive (Emissive_Channel 3), specular = T1 rgb (slot 1) x
    Specular_Color x Specular_Multiplier, gloss = Gloss_Amount (0: rough), no normal map (vertex normals)."""
    p = os.path.splitext(os.path.basename(mpath))[0]
    if os.path.exists(os.path.join(texdir, p + "_basecolor.png")): return p
    os.makedirs(texdir, exist_ok=True)
    v = ae4_material.read(mpath)[0]
    T = tex(f"{W}/rockets/textures/weapon_rockets_diffuse.tga.ae4texture")
    d = T[..., :3] * np.array(v.get("Diffuse_Color", (1, 1, 1, 1))[:3], np.float32)
    save(d, os.path.join(texdir, p + "_basecolor.png"))
    save(d * T[..., 3:4] if v.get("Emissive_TextureSlot") else np.zeros_like(d), os.path.join(texdir, p + "_emissive.png"))
    save(T[..., :3] * np.array(v.get("Specular_Color", (1, 1, 1, 1))[:3], np.float32) * v.get("Specular_Multiplier", 1.0),
         os.path.join(texdir, p + "_specular.png"))
    save(np.full(T.shape[:2], roughness(v.get("Gloss_Amount", 0.0)), np.float32), os.path.join(texdir, p + "_roughness.png"), "L")
    return p


def rockets():
    for d in sorted(glob.glob(f"{W}/rockets/geometry/*/")):
        with skipped(d):
            key = os.path.basename(d.rstrip("/"))
            bodies = glob.glob(f"{d}*_body.ae4model")
            if not bodies: continue
            stem = os.path.basename(bodies[0])[:-len("_body.ae4model")]   # weapon_rocket_npc_ingame
            name = f"weapon_rocket_{key}"
            if ONLY not in name: continue
            print(name)
            folder = os.path.join(OUT, name); texdir = os.path.join(folder, "textures")
            mats = sorted(os.path.basename(m) for m in glob.glob(f"{W}/rockets/materials/*.ae4material"))
            # the body: weapon_rocket_all, except the redtail's own (GUID ccbd... = weapon_rocket_redtrail: the files say "redtrail")
            body_guid = model_lods(bodies[0])[0][0]
            body_mat = "weapon_rocket_redtrail.ae4material" if key == "redtail" else "weapon_rocket_all.ae4material"
            mk = lambda part: next((m for m in mats if m == f"weapon_rocket_{'redtrail' if key == 'redtail' else key}_{part}.ae4material"), None)
            materials = {"body": {"kind": "pbr", "prefix": rocket_textures(f"{W}/rockets/materials/{body_mat}", texdir)}}
            objs = [{"name": f"{name}_body", "meshgroup": f"{d}{stem}_body.ae4meshgroup", "materials": ["body"]}]
            nodes = {n["name"]: n for n in (scene_nodes(f"{d}{stem}.ae4scene") or scene_nodes(f"{d}{name}.ae4scene")).values()}
            lines = [f"Body material  weapons/rockets/materials/{body_mat}  (model GUID {body_guid}; texture weapons/rockets/textures/weapon_rockets_diffuse)"]
            for part, kind in (("exhaust", "exhaust"), ("glow", "glow")):
                mg = f"{d}{stem}_{part}.ae4meshgroup"
                if not os.path.exists(mg): continue
                m = mk(part)
                if m: materials[part] = glow_material(f"{W}/rockets/materials/{m}", texdir, kind)
                else: materials[part] = {"kind": "glow", "color": [1, 0.5, 0.2], "strength": 2.0, "texture": vfx_texture(texdir, kind), "vcol": True}
                pos = nodes.get(f"{stem}_{part}", {}).get("pos", (0, 0, 0))
                objs.append({"name": f"{name}_{part}", "meshgroup": mg, "materials": [part], "pos": list(pos)})
                lines.append(f"{part.capitalize():7s} material  " + (f"weapons/rockets/materials/{m}" if m else "none found: orange stand-in")
                             + f"  (additive; colour {np.round(materials[part]['color'], 2).tolist()} x {materials[part]['strength']}, at z {pos[2]:.3f})")
            blender({"name": name, "out": folder, "texdir": texdir, "objects": objs, "materials": materials, "empties": []}, folder)
            readme(folder, name, lines + ["",
                   f"{name}.fbx: {name}_body, _exhaust (crossed planes along +Z behind the nozzle, faded by vertex colours 'Col'),",
                   "  _glow (the game's camera-facing sprite, built as a flat quad facing backward)",
                   "The exhaust / glow textures are named by GUID only (da5a9b35bdda51b4 / ea14a6b1a5a1b34b: shared round vfx glows,",
                   f"no file says which): {os.path.basename(VFX_TEXTURES['glow'])} stands in for both.",
                   "Not included: the exhaust's flow-map animation, the glow's angle fade, the cloak / dissolve materials."])


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    guns(); mounts(); rockets()
    print("done ->", OUT + (f" ({len(FAILED)} skipped: {', '.join(FAILED)})" if FAILED else ""))
