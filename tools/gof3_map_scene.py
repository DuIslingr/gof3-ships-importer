"""Galaxy on Fire 3's star map in a system's view, for the remake's systems.json "mapScene" (the GoF3 Systems mod).

GoF3 shows a system as one part of ONE scene, the hangar's galaxymap_000.ae4scene: every planet, moon, ring, orbit line,
rock field and nebula of the 24 systems lies in it, and the camera flies to the system's star. Its areas are tags in the
same scene ("Trim_000_A_H4 - AnchorageStation"), where GoF3 draws each area's ring. So the whole scene goes into one
.glb (models/gof3_galaxymap.glb), with:
  - every mesh the system views show (planets, their orbit lines, atmospheres, rocks, the Kaamo Club, the nebulae and
    the star sheets), each section in its material's look as GoF3's map shaders draw it (below);
  - per star three nodes, "map_camera:<star>", "map_target:<star>" and "map_up:<star>" (a point one unit above the
    camera along its up): GoF3's own camera for that system (positions only, so no axis convention can turn it);
  - per area tag a node "map_area:<tag>" at the tag's place;
  - the group node "map_galaxy" holding GoF3's nebula sheets, which the remake's galaxy view also draws behind the
    systems, fitted to their suns (StarMap; the "map_target:<star>" nodes are the stars).
systems.json gets "mapScene": {"model", "camera": "<star>", "fov": 22} and GoF3's orange "mapMarkers" (tools/map_markers),
stations.json "mapArea": "<tag>".

The camera (decompiled, libgofm.so): GalaxyMap3DMediator::handleStar takes getCameraState(star): the solar system's
galaxyMapCamRotation (proto Rotation yaw / pitch / roll, data.pdb field 9305891 of the sector record; each in [0, 1] "the
rotation of the GalaxyMap camera when zoomed in ... Interpolates between the min/max values set in ConfigGalaxyMap"),
distance 100, fov 22. GalaxyMapCameraController::setStarFocus: target = the star tag's position (LocationProxy::
getEntityByTag); orientation = the galaxy view's (0, 1.9198622 rad, 0) + (0, rad(minYaw + yaw x (maxYaw - minYaw)),
rad(sign x minRoll + (2 roll - 1)(maxRoll - minRoll))), sign that of 2 roll - 1 (ConfigGalaxyMap: minYaw / minRoll 10,
maxYaw / maxRoll 40). CameraProxy::setCameraTransform: M = rotate(I, o.y, X) . rotate(o.x, Y) . rotate(o.z, -Z); the
camera at target + M[2] x distance, looking at the target, up M[1]. Checked against two recordings of GoF3's map: the
areas' rings land within 0.04 screen half-heights (RMS over 33 rings) of where the recordings show them.

The materials (each section's .ae4material, its compiled GLSL read for what the fragment does; the blend modes are the
engine's BlendStateDescriptor table): 0 solid, 1 alpha, 2 add by alpha, 6 add, 7 screen (one, 1 - src colour). The
planets: texture x Opacity x vertex colour, unlit (their light is painted into the atlas). The atmospheres: DiffuseColor x
Opacity + the rim (clamp(N.E + 1), remapped by RimEffect_Min / MaxAngle, x RimEffect_Color). The nebulae and star sheets:
the VFX colorize (c = mix(vertex colour, Colorize_Color2, t.r); rgb *= rgb + c (1 - rgb) Colorize_Multiplier; rgb *= c.a),
the texture channel the material reads (Diffuse_Texture_Channel) baked into the image; Colorize_Options 1 multiplies by c
instead (the black hole's swirl). A blended layer below RenderLayer 0 writes no depth (the nebula haze hid the Porros
planets drawn after it). Each glTF material's "extras"
carry the look as "unlit" (the remake's GoF2/ModUnlit, ModMaterials.UnlitFromGltf).

python gof3_map_scene.py --assets <assets> --pdb <data.pdb> --mod <Mods/gof3_systems>   (writes the .glb, adds the fields)"""
import argparse, io, json, math, os, re, shutil, struct, sys, zlib
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_material, ae4_meshgroup, ae4_shaders, ae4_texture, structures
import structure_materials as sm
from ae4unpack import unpack

SCENE = "hangar/geometry/galaxymap/galaxymap_000.ae4scene"
MODEL = "models/gof3_galaxymap.glb"
MARKERS = {"ring": "textures/gof3_map_ring.png", "selected": "textures/gof3_map_ring_selected.png", "pulse": "textures/gof3_map_pulse.png"}
DISTANCE, FOV = 100.0, 22.0                     # getCameraState: 0x42c80000, 0x41b00000
GALAXY_ORIENTATION = (0.0, 1.9198622, 0.0)      # setStarFocus's galaxy view state (110 degrees)
MIN_YAW, MAX_YAW, MIN_ROLL, MAX_ROLL = 10.0, 40.0, 10.0, 40.0   # ConfigGalaxyMap (data.pdb, the proto's defaults too)
F_CAM_ROTATION = 9305891                        # SolarSystem.galaxyMapCamRotation (proto Rotation: 1 yaw, 2 pitch, 3 roll)
F_TAG = 1635146                                 # galaxyMapTag (a sector's star, a level's area)
BLENDS = {0: "opaque", 1: "alpha", 2: "addAlpha", 3: "subtract", 4: "multiply", 5: "multiplyAlpha", 6: "add", 7: "screen",
          8: "premultiplied"}                   # BlendStateDescriptor kSolid .. kForkAddAlpha
CULL = {0: "none", 1: "front", 2: "back"}
# what the system views show: the planets, their orbit lines and atmospheres, the rocks, the Kaamo Club, the nebulae and
# the star sheets; not the galaxy view's grids, borders, holograms and unlock effects
SKIP = re.compile(r"hologrid|innerboarder|outerboarder|ui_holo|ui_unlock|^GM_|^Camera|_cam$")
MAX_TEXTURE = {"nebulae": 1024}                 # the soft nebula sheets halved; the rest as GoF3 has them (2048)
# GoF3's nebulae: also drawn behind its systems in the remake's galaxy view (the group node "map_galaxy", fitted to the
# systems' suns by StarMap)
GALAXY = re.compile(r"^galaxymap_000_nebulae_")


def _dump(obj, path, **kw):
    """json to path through a new file (os.replace): a hardlinked copy of a build keeps its original's file."""
    with open(path + ".new", "w", encoding="utf-8") as f: json.dump(obj, f, **kw)
    os.replace(path + ".new", path)


def read_nodes(path):
    """{id: {name, parent, pos, rot, scale}} of every node record (ae4_scene keeps only the longest run of records; this
    scene has two). A record: [id u64][id u32][pos 3f][scale 3f][quat xyzw 4f][parent i64]; names [id][crc32][len][name]."""
    d = unpack(open(path, "rb").read())
    names = {}
    for m in re.finditer(rb"[A-Za-z_][A-Za-z0-9_ .\-'+]{2,}", d):
        for s in range(m.start(), m.end() - 2):
            o = s - 12
            if o < 0: continue
            nid, crc, ln = struct.unpack_from("<III", d, o)
            if 0 < ln < 256 and s + ln <= len(d) and zlib.crc32(d[s:s + ln]) == crc: names[nid] = d[s:s + ln].decode("latin1")
    nodes = {}
    for o in range(len(d) - 60):
        nid, nid2 = struct.unpack_from("<QI", d, o)
        if nid != nid2 or nid >= 4096 or nid not in names: continue
        f = struct.unpack_from("<10f", d, o + 12)
        if abs(sum(c * c for c in f[6:10]) - 1) > 1e-3: continue
        par = struct.unpack_from("<q", d, o + 52)[0]
        pos, scale = f[:3], f[3:6]
        if not all(1e-6 < abs(v) < 100 for v in scale) or not all(abs(v) < 1e5 for v in pos):
            pos, scale = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)   # the first record overlaps the header (GM_UI_Base: scale 1000 on y): a plain group; Porros Port's model
            # is authored in large units (scale 0.00094)
        nodes[nid] = {"name": names[nid], "pos": pos, "scale": scale, "rot": f[6:10],
                      "parent": par if 0 <= par < 4096 and par != nid else -1}
    for n in nodes.values():
        if n["parent"] not in nodes: n["parent"] = -1
    return nodes


def _rot(axis, a):
    c, s = math.cos(a), math.sin(a); x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def camera(target, yaw, roll):
    """GoF3's camera of a star: (position, up) for its galaxyMapCamRotation yaw / roll in [0, 1] (see the docstring)."""
    o = list(GALAXY_ORIENTATION)
    o[1] += math.radians(MIN_YAW + yaw * (MAX_YAW - MIN_YAW))
    v = 2 * roll - 1
    o[2] += math.radians((MIN_ROLL if v >= 0 else -MIN_ROLL) + v * (MAX_ROLL - MIN_ROLL))
    M = _rot((1, 0, 0), o[1]) @ _rot((0, 1, 0), o[0]) @ _rot((0, 0, -1), o[2])
    return np.asarray(target, float) + M[:, 2] * DISTANCE, M[:, 1]


def _glsl(material, assets, vertex_colours):
    """The fragment and vertex code of the material's GLSL variant (the one taking a_vtxColor when the mesh has it)."""
    best = None
    for p in ae4_shaders.variants(material, assets):
        t = re.sub(r"[^\x09\x0a\x20-\x7e]+", "\n", ae4_shaders.text(p))
        if "#ifdef FRAGMENT" not in t or "metal_stdlib" in t: continue
        has = "a_vtxColor" in t
        if best is None or has == vertex_colours: best = t
        if has == vertex_colours: break
    if best is None: return "", ""
    v0 = best.find("#ifdef VERTEX\n\n\tuniform"); f0 = best.find("#ifdef FRAGMENT\n\t//FOG")
    if f0 < 0: f0 = best.rfind("#ifdef FRAGMENT")
    return best[f0:], best[v0:f0] if v0 >= 0 else ""


def look(material, assets, vertex_colours):
    """(extras "unlit" dict, texture (path, channel) or None) of one material as its GLSL draws it."""
    v, _ = ae4_material.read(material)
    frag, vert = _glsl(material, assets, vertex_colours)
    def col(k, dflt=(1, 1, 1, 1)): return [round(float(c), 4) for c in (v.get(k) or dflt)]
    u = {"blend": BLENDS.get(int(v.get("BlendMode", 0)), "opaque"), "cull": CULL.get(int(v.get("CullMode", 2)), "back"),
         "depthWrite": bool(v.get("DepthWrite", True)), "layer": int(v.get("RenderLayer", 0))}
    colour = [1.0, 1.0, 1.0, 1.0]
    tex = None
    m = re.search(r"diffuseTexel = vec4\(texture2D\(Diffuse, texCoord, 0\.0\)(\.\w+)?\)", frag)
    if m:
        ch = (m.group(1) or ".rgba")[1:]
        if "diffuseTexel.a = 1.0" in frag and ch == "rgba": ch = "rgb"
        tex = (ae4_material.texture_ids(material).get("Diffuse"), ch)
    elif "custom_DiffuseColor" in frag.split("out_FragColor = diffuseTexel")[0]:
        colour = col("DiffuseColor")
    if re.search(r"out_FragColor \*= Opacity", frag):
        colour = [c * float(v.get("Opacity", 1.0)) for c in colour]
    u["color"] = [round(c, 4) for c in colour]
    # a blended background layer (RenderLayer < 0: the nebula haze nebulae_solid) writes no depth here: drawn before the
    # blended planets of the Porros atlas, its depth hid them where it passes in front (GoF3's draw order of its layers
    # isn't known; its map shows those planets)
    if u["blend"] != "opaque" and u["layer"] < 0: u["depthWrite"] = False
    if re.search(r"out_FragColor \*= v_colVtx", frag): u["vertexColors"] = True
    if "colorizeColor" in frag:
        u["colorize"] = {"color2": col("Colorize_Color2"), "multiplier": round(float(v.get("Colorize_Multiplier", 1.0)), 4),
                         "color1": None if "mix((v_colVtx)" in frag else col("Colorize_Color1"),
                         # Colorize_Options 1: the colour times the colorize colour (the black hole's swirl), else the tint
                         "mode": "multiply" if "out_FragColor *= colorizeColor" in frag else "tint"}
    if "custom_Alpha_Value" in frag and float(v.get("Alpha_Value", 1.0)) != 1.0: u["alpha"] = round(float(v["Alpha_Value"]), 4)
    if "v_rimEffect" in frag:
        u["rim"] = {"color": col("RimEffect_Color")[:3], "min": round(float(v.get("RimEffect_MinAngle", 0.0)), 4),
                    "max": round(float(v.get("RimEffect_MaxAngle", 1.0)), 4)}
    if "UVAnim_Speed" in vert.split("void main()")[-1] and v.get("UVAnim_Enabled"):
        sp = v.get("UVAnim_Speed") or (0, 0, 0); k = float(v.get("UVAnim_SpeedMultiplier", 1.0))
        if any(sp[:2]): u["scroll"] = [round(sp[0] * k, 4), round(sp[1] * k, 4)]
    return u, tex


def _image(path, channel, assets_kind):
    """The texture with the channel the material reads baked in, as (bytes, mime)."""
    im = ae4_texture.decode(path).convert("RGBA")
    cap = next((s for k, s in MAX_TEXTURE.items() if k in os.path.basename(path)), None)
    if cap and max(im.size) > cap: im = ae4_texture.resized(im, (cap, cap))
    a = np.asarray(im)
    if channel in ("r", "g", "b", "a"):
        c = a[:, :, "rgba".index(channel)]
        im = Image.fromarray(c, "L")
    elif channel == "rgb" or a[:, :, 3].min() == 255:
        im = Image.fromarray(a[:, :, :3], "RGB")
    buf = io.BytesIO()
    if im.mode in ("RGB", "L") and "_ui" not in os.path.basename(path):
        im.save(buf, "JPEG", quality=92); return buf.getvalue(), "image/jpeg"
    im.save(buf, "PNG", optimize=True); return buf.getvalue(), "image/png"


def convert(assets, out_glb, cam_rotations, log=print):
    """Writes the .glb; cam_rotations {star tag: (yaw, roll)}. -> {"stars": [...], "areas": [...]}."""
    import ae4_ids
    scene_path = os.path.join(assets, SCENE)
    nodes = read_nodes(scene_path)
    W = structures.world_matrices(nodes)
    folder = os.path.dirname(scene_path)
    looks, mats, images, img_of = {}, [], [], {}
    meshes, gl_nodes, mesh_of = [], [], {}
    def material_index(path, vertex_colours):
        key = (path, vertex_colours)
        if key in looks: return looks[key]
        u, tex = look(path, assets, vertex_colours)
        name = os.path.basename(path)[:-len(".ae4material")] + ("" if vertex_colours else "_novc")
        m = {"name": f"gof3map[{name}]", "extras": {"unlit": u},
             "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 1.0}}
        if tex and tex[0]:
            f = ae4_ids.resolve(assets, tex[0])
            if f:
                ik = (f, tex[1])
                if ik not in img_of:
                    b, mime = _image(f, tex[1], assets)
                    img_of[ik] = len(images); images.append((b, mime, os.path.basename(f).split(".")[0] + "_" + tex[1], True))
                m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": img_of[ik]}
        if u["blend"] != "opaque": m["alphaMode"] = "BLEND"
        if u["cull"] == "none": m["doubleSided"] = True
        looks[key] = len(mats); mats.append(m)
        return looks[key]
    tris = 0
    for i, n in sorted(nodes.items()):
        if SKIP.search(n["name"]): continue
        mg = os.path.join(folder, n["name"] + ".ae4meshgroup")
        if not os.path.exists(mg): continue
        if mg not in mesh_of:
            secs = ae4_meshgroup.read_all(mg)
            mpaths = [m.path if m else None for m in sm.section_materials(mg, assets)]
            prims = []
            for k, s in enumerate(secs):
                if k >= len(mpaths) or not mpaths[k] or "a_texCoord0" not in s: continue
                vc = "a_vtxColor" in s
                P = np.asarray(s["a_position"], np.float32)
                N = np.asarray(s["a_normal"], np.float32) if "a_normal" in s else \
                    P / np.maximum(np.linalg.norm(P, axis=1, keepdims=True), 1e-6)
                C = np.asarray(s["a_vtxColor"], np.float32)[:, :4] if vc else None
                prims.append({"positions": P, "normals": N, "uvs": np.asarray(s["a_texCoord0"], np.float32), "colors": C,
                              "indices": np.asarray(s["indices"], np.int64), "material": material_index(mpaths[k], vc)})
                tris += len(s["indices"]) // 3
            mesh_of[mg] = len(meshes) if prims else None
            if prims: meshes.append({"name": n["name"], "primitives": prims})
        if mesh_of[mg] is None: continue
        gl_nodes.append({"name": n["name"], "mesh": mesh_of[mg], "matrix": [float(x) for x in W[i].T.reshape(-1)],
                         "_galaxy": bool(GALAXY.search(n["name"]))})
    stars, areas = [], []
    by_name = {n["name"]: i for i, n in nodes.items()}
    for i, n in sorted(nodes.items()):
        nm = n["name"]
        if nm.startswith("GM_star_"):
            if nm not in cam_rotations: continue
            t = W[i][:3, 3]
            pos, up = camera(t, *cam_rotations[nm])
            for kind, p in (("camera", pos), ("target", t), ("up", pos + up)):
                gl_nodes.append({"name": f"map_{kind}:{nm}", "translation": [float(x) for x in p]})
            stars.append(nm)
        elif nodes.get(n["parent"], {}).get("name", "").startswith("GM_star_"):
            gl_nodes.append({"name": f"map_area:{nm}", "translation": [float(x) for x in W[i][:3, 3]]})
            areas.append(nm)
    # glTF node indices: the root, the nodes, then the galaxy group (its children the nebulae)
    galaxy = [k + 1 for k, g in enumerate(gl_nodes) if g.pop("_galaxy", False)]
    for g in gl_nodes: g.pop("_galaxy", None)
    group = {"name": "map_galaxy", "children": galaxy}
    root = {"name": "gof3_galaxymap", "children": [k + 1 for k in range(len(gl_nodes)) if k + 1 not in galaxy] + [len(gl_nodes) + 1]}
    gl_nodes.append(group)
    os.makedirs(os.path.dirname(out_glb), exist_ok=True)
    if os.path.exists(out_glb): os.remove(out_glb)   # (a hardlinked copy keeps its original's)
    structures.write_glb_parts(out_glb, meshes, mats, images, "gof3_ships_importer gof3_map_scene.py", nodes=[root] + gl_nodes)
    log(f"  {os.path.basename(out_glb)}: {len(meshes)} meshes, {tris} triangles, {len(mats)} materials, {len(images)} images, "
        f"{len(stars)} cameras, {len(areas)} areas, {os.path.getsize(out_glb) / 1e6:.1f} MB")
    return {"stars": stars, "areas": areas}


def apply(out, pdb, assets, log=print):
    """Writes the mod's models/gof3_galaxymap.glb and gives its systems "mapScene" and its stations "mapArea"."""
    import gof3_galaxy
    import build_gof3_systems as b
    G = gof3_galaxy.Galaxy(pdb); R = G.R
    rot = {}
    for rid in R.p.recs:
        try: f = R.fields(rid)
        except Exception: continue
        if F_TAG not in f or F_CAM_ROTATION not in f: continue
        r = R.sub(f[F_CAM_ROTATION][0])
        rot[f[F_TAG][0].decode()] = (float(r.get(1, 0.0)), float(r.get(3, 0.0)))
    info = convert(assets, os.path.join(out, MODEL), rot, log)
    sysj = json.load(open(f"{out}/systems.json", encoding="utf-8"))
    stj = json.load(open(f"{out}/stations.json", encoding="utf-8"))
    star_of, area_of = {}, {}
    for s in G.sectors():
        if not s["name"]: continue
        star_of["gof3_" + b.slug(s["name"])] = s["star"]
        for lv in s["levels"]:
            _, lf = G.level_fields(lv["id"])
            tag = lf.get(F_TAG, [b""])[0]
            if tag: area_of["gof3_" + b.slug(lv["record"].replace(" - ", "_"))] = tag.decode()
    n_sys = n_st = 0
    # GoF3's orange markers (tools/map_markers, see its README)
    os.makedirs(f"{out}/textures", exist_ok=True)
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_markers")
    for f in MARKERS.values():
        dst = os.path.join(out, f)
        if os.path.exists(dst): os.remove(dst)   # (a hardlinked copy keeps its original's)
        shutil.copyfile(os.path.join(here, os.path.basename(f)), dst)
    for e in sysj:
        star = star_of.get(e["id"])
        if star in info["stars"]:
            e["mapScene"] = {"model": MODEL, "camera": star, "fov": FOV}; n_sys += 1
            e["mapMarkers"] = dict(MARKERS)
    for st in stj:
        tag = area_of.get(st["id"])
        if tag in info["areas"]: st["mapArea"] = tag; n_st += 1
        elif tag: log(f"  {st['id']}: area tag {tag!r} not in the scene")
    _dump(sysj, f"{out}/systems.json", indent=1, ensure_ascii=False)
    _dump(stj, f"{out}/stations.json", indent=1, ensure_ascii=False)
    log(f"  map scenes: {n_sys} systems, {n_st} of {len(stj)} stations placed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True); ap.add_argument("--pdb", required=True); ap.add_argument("--mod", required=True)
    a = ap.parse_args()
    apply(a.mod.rstrip("/"), a.pdb, a.assets.rstrip("/"))
