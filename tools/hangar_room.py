"""GoF3's Hades hangar (hangar/geometry/hangar_01, the ShipSelectionB room: the player's ship on the round launch pad) as one
baked .glb for the remake's mod interiors (interiors.json "model"), the Manticore's own hangar.

The room's pieces (ShipSelectionB_*) share one light map on UV1 (textures/ShipSelectionB_light_ao: RGB the baked lighting, its
occlusion included). Each piece's .ae4model lists its sections' materials by an 8-byte id (after the model's id table and the
LOD's meshgroup id: [count u32][id u64]...), which no file maps back to a material; MATERIALS below was found by matching each
id's UV0 island borders against the edges of the hangar's numbered textures over every section that uses it (the cables
material 04 shares 05's texture), then checked on renders. Baked onto the UV1 unwrap:
  emission = diffuse(UV0) x light map RGB x GLOW     (GoF3's own lighting: the room looks as in GoF3 whatever the remake lights)
  colour   = diffuse(UV0) x BASE                     (a little response to the remake's key light)
The sections without a light map go in as materials of their own on their UV0 (2026-11-02: the room looked bare without
them): LIGHTS, GoF3's 06_hangar_light_effects (unlit: Emissive_Unlit, its texture drawn as it is: the light strips and lamps
of ShipSelectionB_light and the floors) as an emission-only material, and DECALS, 16_hangar_decals_000 (alpha-blended, lit:
the wall signs of ShipSelectionB_decals_000). The pulse (17_hangar_pulse_000, additive, vertex-coloured: GoF3's launch
effect) stays out.

convert(assets, out_glb, size) -> {"min", "max", "triangles"} in glTF space (Y up, 1 unit = 1 GoF3 unit; the pad at the origin)."""
import glob, os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_meshgroup, ae4_texture, structures
from ae4unpack import unpack

PIECES = ["ShipSelectionB_floor", "ShipSelectionB_floor_001", "ShipSelectionB_floor_002", "ShipSelectionB_ground",
          "ShipSelectionB_left_001", "ShipSelectionB_front", "ShipSelectionB_front_001", "ShipSelectionB_engine",
          "ShipSelectionB_mirrored_background", "ShipSelectionB_crates_001", "ShipSelectionB_crates_002",
          "ShipSelectionB_crates_003"]
MATERIALS = {
    "e62a4a8693f8f5f5": "01_hangar_floor_001", "822d8c767feda3e7": "02_hangar_001", "37133fed148bd2d6": "05_hangar_Cables_001",
    "0727efc12bd2c57f": "05_hangar_Cables_001", "7855531f67f68aad": "07_hangar_crates_001", "a1fc0925f4b21782": "12_hangar_wall_001",
    "8552b6380f006334": "16_hangar_decals_000", "c95e90c7ab2e445a": "11_hangar_monitors_001", "1223e8de51f26d8a": "08_hangar_002",
    "514395008b487772": "10_hangar_floor_004",
}
LIGHTS = ("6c2439f06a422239", "06_hangar_light_effects", ["ShipSelectionB_light"])   # (id, texture, pieces beside PIECES)
DECALS = ("373a342518cc4cc1", "16_hangar_decals_000", ["ShipSelectionB_decals_000"])
LIGHT_MAP = "ShipSelectionB_light_ao"
GLOW = 2.2
BASE = 0.15


def section_materials(model_path):
    """The material ids of a model's first LOD, one per meshgroup section."""
    d = unpack(open(model_path, "rb").read())
    n = struct.unpack_from("<I", d, 8)[0]
    o = 12 + 8 * n + 4 + 8                       # the id table, the LOD count, the LOD's meshgroup id
    k = struct.unpack_from("<I", d, o)[0]; o += 4
    return [d[o + 8 * i:o + 8 * i + 8].hex() for i in range(k)]


def raster(sections, textures, size):
    """Each section's UV0 texture onto its UV1 unwrap: colour (size, size, 3), mask."""
    col = np.zeros((size, size, 3), np.float32); mask = np.zeros((size, size), bool)
    for s, tex in zip(sections, textures):
        uv1 = np.asarray(s["a_texCoord1"], np.float64) * size
        uv0 = np.asarray(s["a_texCoord0"], np.float64)
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
            e = -0.5 / max(abs(d), 1.0)
            inside = (l0 >= e) & (l1 >= e) & (l2 >= e)
            if not inside.any(): continue
            w = np.stack([l0[inside], l1[inside], l2[inside]], 1)
            px = structures._sample(tex, w @ uv0[[a, b, c]])
            yy, xx = gy[inside].astype(int), gx[inside].astype(int)
            col[yy, xx] = px[:, :3]; mask[yy, xx] = True
    return col, mask


def convert(assets, out_glb, size=4096, log=print):
    geo = f"{assets}/hangar/geometry/hangar_01"
    cache = {}
    def tex(name):
        if name not in cache:
            f = glob.glob(f"{assets}/hangar/textures/{name}_D*.ae4texture")[0]
            cache[name] = np.asarray(ae4_texture.decode(f).convert("RGBA").resize((1024, 1024), Image.BICUBIC), np.float32) / 255
        return cache[name]
    sections, textures, unknown = [], [], set()
    own = {LIGHTS[0]: [], DECALS[0]: []}   # the unlit lights and the decals: sections without a light map
    for p in PIECES + LIGHTS[2] + DECALS[2]:
        for mid, s in zip(section_materials(f"{geo}/{p}.ae4model"), ae4_meshgroup.read_all(f"{geo}/{p}.ae4meshgroup")):
            if mid in own: own[mid].append(s); continue
            if "a_texCoord1" not in s or not np.abs(np.asarray(s["a_texCoord1"])).max(): continue
            if mid not in MATERIALS: unknown.add(mid); continue
            sections.append(s); textures.append(tex(MATERIALS[mid]))
    if unknown: log(f"hangar room: sections of unknown materials left out: {sorted(unknown)}")
    col, mask = raster(sections, textures, size)
    col = structures._dilate(col, mask, max(4, size // 256))
    light = structures._tex(f"{assets}/hangar/textures/{LIGHT_MAP}.tga.ae4texture")
    lm = np.asarray(Image.fromarray((light * 255).astype(np.uint8)).resize((size, size), Image.BILINEAR)).astype(np.float32) / 255
    pos, nrm, uv, idx = [], [], [], []
    for s in sections:
        b = len(pos)
        pos += [list(v) for v in s["a_position"]]; nrm += [list(v) for v in s["a_normal"]]
        uv += [tuple(t) for t in s["a_texCoord1"]]; idx += [k + b for k in s["indices"]]
    meshes = [{"name": "hangar", "primitives": [{"positions": pos, "normals": nrm, "uvs": uv, "indices": idx, "material": 0}]}]
    materials = [{"name": "hangar_hull", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.25,
                                                                 "roughnessFactor": 0.6},
                  "emissiveTexture": {"index": 1}, "emissiveFactor": [1.0, 1.0, 1.0]}]
    images = [(structures._jpeg(col * BASE), "image/jpeg", "hangar_colour", False),
              (structures._jpeg(col * lm[..., :3] * GLOW), "image/jpeg", "hangar_emission", False)]
    for (mid, name, _), kind in ((LIGHTS, "lights"), (DECALS, "decals")):
        secs = own[mid]
        if not secs: log(f"hangar room: no {kind} sections"); continue
        f = glob.glob(f"{assets}/hangar/textures/{name}_D*.ae4texture")
        if not f: log(f"hangar room: no {name} texture"); continue
        t = np.asarray(ae4_texture.decode(f[0]).convert("RGBA"), np.float32) / 255
        p_, n_, u_, i_ = [], [], [], []
        for s in secs:
            b = len(p_)
            p_ += [list(v) for v in s["a_position"]]; n_ += [list(v) for v in s["a_normal"]]
            u_ += [tuple(x) for x in s["a_texCoord0"]]; i_ += [k + b for k in s["indices"]]
        k = len(images)
        if kind == "lights":   # unlit: its texture as the emission over black
            images.append((structures._jpeg(t[..., :3]), "image/jpeg", f"hangar_{kind}", True))
            materials.append({"name": f"hangar_{kind}", "pbrMetallicRoughness": {"baseColorFactor": [0, 0, 0, 1], "metallicFactor": 0,
                              "roughnessFactor": 1}, "emissiveTexture": {"index": k}, "emissiveFactor": [1.0, 1.0, 1.0]})
        else:                  # alpha-blended, lit
            images.append((structures._png(t, "RGBA"), "image/png", f"hangar_{kind}", True))
            materials.append({"name": f"hangar_{kind}", "alphaMode": "BLEND", "doubleSided": True,
                              "pbrMetallicRoughness": {"baseColorTexture": {"index": k}, "metallicFactor": 0, "roughnessFactor": 0.7}})
        meshes.append({"name": f"hangar_{kind}", "primitives": [{"positions": p_, "normals": n_, "uvs": u_, "indices": i_,
                                                                "material": len(materials) - 1}]})
        log(f"hangar room: {kind} {len(i_) // 3} triangles")
    structures.write_glb_parts(out_glb, meshes, materials, images, generator="gof3_ships_importer hangar_room.py")
    P = np.asarray(pos)
    return {"min": P.min(0).tolist(), "max": P.max(0).tolist(), "triangles": len(idx) // 3}


if __name__ == "__main__":
    import json
    print(json.dumps(convert(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4096)))
