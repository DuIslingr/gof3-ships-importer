"""GoF3's Hades hangar (hangar/geometry/hangar_01, the ShipSelectionB room: the player's ship on the round launch pad) as one
baked .glb for the remake's mod interiors (interiors.json "model"), the Manticore's own hangar.

The room's pieces (ShipSelectionB_*) share one light map on UV1 (textures/ShipSelectionB_light_ao: RGB the baked lighting, A
its occlusion). Each piece's .ae4model lists its sections' materials by an 8-byte id (after the model's id table and the
LOD's meshgroup id: [count u32][id u64]...): GoF3's resource id of the material's path (ae4_ids.resolve), the material's
textures (T1, T2...) by the same ids. (Until 2026-11-02 a table guessed from UV islands stood in, and seven of its ten ids
were wrong: the ground, floors and walls showed the cables texture's coloured balls, the cables the wall's.)

GoF3's hangar shader (the 01..09_hangar materials' .ae4shader, ae4_shaders.text) lights a texel only by its light maps:
  light    = mix(T7 light map, T6 showroom light map, custom_LightMapFade_Value)
  colour   = diffuse x light x (1 - e) + e x diffuse + light x specular x occlusion
with diffuse = T<Diffuse_TextureSlot>.rgb x Diffuse_Color, e (the emissive mask: monitors, lamps) = T<Emissive_TextureSlot>.a
when that slot is set, specular = T<Specular_TextureSlot> (.rgb for channel 0, else .b: the normal map's) x Specular_Color
(its fresnel boost, the rim and the scene's own lights left out: they depend on the view). The fade is 0 in the ship
hangar: VfxController's constructor zeroes it and its target (+0x110 / +0x114), and switchHangarLightMap, the only thing
that sets the target, has no caller in libgofm.so (2026-11-02), so the regular light map (each piece's T7 is the material
file's ShipSelectionA one, replaced by the room's own) lights the room. Baked onto the UV1 unwrap:
  emission = that colour x GLOW         (the room looks as in GoF3 whatever the remake lights; GLOW makes up for its tone map)
  colour   = diffuse x BASE             (a little response to the remake's key light)
The sections without a light map go in as materials of their own on their UV0 (2026-11-02: the room looked bare without
them), by their material's values: unlit ones (Emissive_Unlit: 06_hangar_light_effects, the light strips and lamps of
ShipSelectionB_light, and the pad's orange rim on the floors: GoF3 draws them as their texture x custom_Diffuse_Color,
which nothing in the hangar sets, so the material's Diffuse_Color) as emission-only materials at GLOW, alpha-blended ones
(BlendMode 5: 16_hangar_decals_000, the wall signs of ShipSelectionB_decals_000) as blended lit ones. GoF3's ship ignition
light (hangar_ship_ignition_light_body) and the pulse (17_hangar_pulse_000) stay out: the ignition's idle animation
(hangar_ship_light_idle_anim) holds its alpha at 0, it shows only while a ship launches, as the pulse.

convert(assets, out_glb, size) -> {"min", "max", "triangles"} in glTF space (Y up, 1 unit = 1 GoF3 unit; the pad at the origin)."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_ids, ae4_material, ae4_meshgroup, ae4_texture, structures
from ae4unpack import unpack

PIECES = ["ShipSelectionB_floor", "ShipSelectionB_floor_001", "ShipSelectionB_floor_002", "ShipSelectionB_ground",
          "ShipSelectionB_left_001", "ShipSelectionB_front", "ShipSelectionB_front_001", "ShipSelectionB_engine",
          "ShipSelectionB_mirrored_background", "ShipSelectionB_crates_001", "ShipSelectionB_crates_002",
          "ShipSelectionB_crates_003", "ShipSelectionB_light", "ShipSelectionB_decals_000"]
LIGHT_MAP = "ShipSelectionB_light_ao"
GLOW = 2.2
BASE = 0.15
TEX = 1024                    # each material's textures sampled at this size


def section_materials(model_path):
    """The material ids of a model's first LOD, one per meshgroup section."""
    d = unpack(open(model_path, "rb").read())
    n = struct.unpack_from("<I", d, 8)[0]
    o = 12 + 8 * n + 4 + 8                       # the id table, the LOD count, the LOD's meshgroup id
    k = struct.unpack_from("<I", d, o)[0]; o += 4
    return [d[o + 8 * i:o + 8 * i + 8].hex() for i in range(k)]


def raster(sections, textures, size):
    """Each section's UV0 texture (h, w, c) onto its UV1 unwrap: (size, size, c), mask."""
    col = np.zeros((size, size, textures[0].shape[2]), np.float32); mask = np.zeros((size, size), bool)
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
            col[yy, xx] = px; mask[yy, xx] = True
    return col, mask


def material(assets, mid, cache={}):
    """(name, values, {slot number: texture file}) of a material id (ae4_ids), (None, {}, {}) when it doesn't resolve."""
    if mid not in cache:
        f = ae4_ids.resolve(assets, mid)
        if not f: cache[mid] = (None, {}, {})
        else:
            v, slots = ae4_material.read(f)
            files = {int(k[1:]): ae4_ids.resolve(assets, h) for k, h in slots.items() if k[1:].isdigit()}
            cache[mid] = (os.path.basename(f)[:-len(".ae4material")], v, {k: t for k, t in files.items() if t})
    return cache[mid]


def surface(v, files, load):
    """A lit material's texels for the bake (TEX, TEX, 7): diffuse RGB, the emissive mask, specular RGB (see the header)."""
    diffuse = load(files[int(v.get("Diffuse_TextureSlot", 1))])
    out = np.zeros((TEX, TEX, 7), np.float32)
    out[..., :3] = diffuse[..., :3] * np.asarray(v.get("Diffuse_Color", (1, 1, 1, 1))[:3], np.float32)
    em = int(v.get("Emissive_TextureSlot", 0) or 0)
    if em and em in files: out[..., 3] = load(files[em])[..., 3]
    sp = int(v.get("Specular_TextureSlot", 0) or 0)
    spec = load(files[sp]) if sp in files else np.ones((TEX, TEX, 4), np.float32)
    spec = spec[..., :3] if int(v.get("Specular_Channel", 0) or 0) == 0 else spec[..., 2:3]
    out[..., 4:] = spec * np.asarray(v.get("Specular_Color", (1, 1, 1, 1))[:3], np.float32)
    return out


def convert(assets, out_glb, size=4096, log=print):
    geo = f"{assets}/hangar/geometry/hangar_01"
    cache = {}
    def load(path):
        if path not in cache:
            im = ae4_texture.resized(ae4_texture.decode(path).convert("RGBA"), (TEX, TEX))
            cache[path] = np.asarray(im, np.float32) / 255
        return cache[path]
    sections, textures, unknown, surfaces = [], [], set(), {}
    own = {}   # the sections without a light map by material: {name: (kind, values, texture, [section])}
    for p in PIECES:
        for mid, s in zip(section_materials(f"{geo}/{p}.ae4model"), ae4_meshgroup.read_all(f"{geo}/{p}.ae4meshgroup")):
            name, v, files = material(assets, mid)
            t = files.get(int(v.get("Diffuse_TextureSlot", 1)))
            if name is None or t is None: unknown.add(name or mid); continue
            if "a_texCoord1" in s and np.abs(np.asarray(s["a_texCoord1"])).max():
                if name not in surfaces: surfaces[name] = surface(v, files, load)
                sections.append(s); textures.append(surfaces[name]); continue
            kind = "light" if v.get("Emissive_Unlit") else "decal" if v.get("BlendMode") in (1, 5) else None
            if kind is None: unknown.add(name); continue
            own.setdefault(name, (kind, v, t, []))[3].append(s)
    if unknown: log(f"hangar room: left out: {sorted(unknown)}")
    texel, mask = raster(sections, textures, size)
    light = structures._tex(f"{assets}/hangar/textures/{LIGHT_MAP}.tga.ae4texture", (size, size))
    lm, ao = light[..., :3], light[..., 3:]
    d, e, sp = texel[..., :3], texel[..., 3:4], texel[..., 4:]
    glow = (d * lm * (1 - e) + e * d + lm * sp * ao) * GLOW
    del texel, light, lm, ao, sp, e
    col = structures._dilate(np.concatenate([d * BASE, glow], 2), mask, max(4, size // 256))
    del d, glow
    pos, nrm, uv, idx = [], [], [], []
    for s in sections:
        b = len(pos)
        pos += [list(v) for v in s["a_position"]]; nrm += [list(v) for v in s["a_normal"]]
        uv += [tuple(t) for t in s["a_texCoord1"]]; idx += [k + b for k in s["indices"]]
    meshes = [{"name": "hangar", "primitives": [{"positions": pos, "normals": nrm, "uvs": uv, "indices": idx, "material": 0}]}]
    materials = [{"name": "hangar_hull", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.25,
                                                                 "roughnessFactor": 0.6},
                  "emissiveTexture": {"index": 1}, "emissiveFactor": [1.0, 1.0, 1.0]}]
    images = [(structures._jpeg(col[..., :3]), "image/jpeg", "hangar_colour", False),
              (structures._jpeg(col[..., 3:]), "image/jpeg", "hangar_emission", False)]
    def add_mesh(name, secs, material_index):
        p_, n_, u_, i_ = [], [], [], []
        for sec in secs:
            b = len(p_)
            p_ += [list(x) for x in sec["a_position"]]
            n_ += [list(x) for x in sec["a_normal"]] if "a_normal" in sec else [[0.0, 1.0, 0.0]] * len(sec["a_position"])
            u_ += [tuple(x) for x in sec["a_texCoord0"]]; i_ += [k + b for k in sec["indices"]]
        meshes.append({"name": name, "primitives": [{"positions": p_, "normals": n_, "uvs": u_, "indices": i_,
                                                     "material": material_index}]})
        return len(i_) // 3
    for name, (kind, v, t, secs) in sorted(own.items()):
        img = np.asarray(ae4_texture.decode(t).convert("RGBA"), np.float32) / 255
        img[..., :3] *= np.asarray(v.get("Diffuse_Color", (1, 1, 1, 1))[:3], np.float32)
        k = len(images)
        if kind == "light":   # unlit: its texture as the emission over black, at GLOW as the room (the remake reads the
                              # factor unclamped: no clipping toward white, as GLOW baked into the texture would)
            images.append((structures._jpeg(img[..., :3]), "image/jpeg", name, True))
            materials.append({"name": name, "pbrMetallicRoughness": {"baseColorFactor": [0, 0, 0, 1], "metallicFactor": 0,
                              "roughnessFactor": 1}, "emissiveTexture": {"index": k}, "emissiveFactor": [GLOW] * 3})
        else:                 # alpha-blended, lit
            images.append((structures._png(img, "RGBA"), "image/png", name, True))
            materials.append({"name": name, "alphaMode": "BLEND", "doubleSided": True,
                              "pbrMetallicRoughness": {"baseColorTexture": {"index": k}, "metallicFactor": 0, "roughnessFactor": 0.7}})
        log(f"hangar room: {kind} {name} {add_mesh(name, secs, len(materials) - 1)} triangles")
    structures.write_glb_parts(out_glb, meshes, materials, images, generator="gof3_ships_importer hangar_room.py")
    P = np.asarray(pos)
    return {"min": P.min(0).tolist(), "max": P.max(0).tolist(), "triangles": len(idx) // 3}


if __name__ == "__main__":
    import json
    print(json.dumps(convert(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4096)))
