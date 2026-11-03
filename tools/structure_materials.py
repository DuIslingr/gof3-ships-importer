"""The materials GoF3 draws a structure's sections with (stations, capital ships, jumpgates, the Hades), for the bakes in
structures.py.

A structure's .ae4model lists, per LOD, its meshgroup and one material per section, by resource id (ae4_ids: the hash of
the asset's path), so every section has its own material: platings, windows, pipes, antennas, solar panels, glass...
Each material file (ae4_material) names its textures by resource id too. GoF3's "Structure" surface (its compiled
shaders, e.g. structure_terran_matid02_platings_000.ae4material_/shader_*.ae4shader) takes:
  diffuse    T1 RGB x Diffuse_Color x vertex colour; T1 A the emissive mask on a *_diffuse_emissive texture
  normal     T2 RG (z = 1, then normalised: Normal_ClearZ), in the mesh's own tangent frame (a_tangent, a_bitangent)
  specular   T2 B x Specular_Color x Specular_Multiplier x vertex colour x the light map's A (its AO)
  gloss      T2 A: Phong exponent exp2(9 g + 1)
  light map  T7 on UV1 (materials/multi/<model>_light_ao): RGB the baked coloured lights, A light and occlusion
No cubemap: only the solar panels and the glass sample one (cubemap_generic_000, Environment_Amount); their specular is
raised by it here so the remake's reflection of the system's sky shows in them. Sections drawn blended (sprites, glows,
holograms, beams, steam: BlendMode 2 / 4) are effects, not hull, and are left out of the bakes.

section_materials(meshgroup, assets) -> [Material | None] per section; Material.sample(uv0, level) -> per-texel values."""
import functools, math, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_ids, ae4_material, ae4_texture
from ae4unpack import unpack

ADDITIVE = {2, 4}            # BlendMode of the effect materials (glows, sprites, holograms, beams, steam)
FLAT_SPEC = 0.04             # a material with no specular map or colour: a plain dielectric


@functools.lru_cache(maxsize=None)
def _model_lods(model_path):
    """{meshgroup id: [material id, ...]} of an .ae4model: [OM4A][version][n ids][ids...][lod count] then per LOD its
    meshgroup id, a count and that many material ids (then a distance)."""
    d = unpack(open(model_path, "rb").read())
    n = struct.unpack_from("<I", d, 8)[0]
    ids = [d[12 + 8 * i:20 + 8 * i] for i in range(n)]
    out = {}
    for mg in ids:
        o = d.find(mg, 12 + 8 * n)
        if o < 0: continue
        k = struct.unpack_from("<I", d, o + 8)[0]
        if 0 < k <= 64 and o + 12 + 8 * k <= len(d):
            out[int.from_bytes(mg, "little")] = [int.from_bytes(d[o + 12 + 8 * j:o + 20 + 8 * j], "little") for j in range(k)]
    return out


def _asset_path(path, assets):
    return "/assets/" + os.path.relpath(path, assets).replace(os.sep, "/")


def section_materials(meshgroup, assets):
    """The Material of each section of a meshgroup (None where it can't be found), from the .ae4model beside it."""
    mid = ae4_ids.resource_id(_asset_path(meshgroup, assets))
    folder = os.path.dirname(meshgroup)
    stem = os.path.basename(meshgroup).split("___")[0]
    stem = stem[:-len(".ae4meshgroup")] if stem.endswith(".ae4meshgroup") else stem
    models = [os.path.join(folder, stem + ".ae4model")]
    models += sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".ae4model"))
    for m in models:
        if not os.path.exists(m): continue
        mats = _model_lods(m).get(mid)
        if mats:
            return [material(ae4_ids.resolve(assets, i), assets) for i in mats]
    return []


def _channels(name):
    """What a texture's channels hold, by its name (the shaders read them by these roles)."""
    n = os.path.basename(name).lower()
    if "_n_s_g" in n: return "nsg"
    if "normal_specular" in n: return "ns"
    if "specular_gloss" in n: return "sg"
    if "normal_emissive" in n: return "ne"
    if "_normal" in n: return "n"
    if "diffuse_emissive" in n: return "de"
    if "diffuse_opacity" in n: return "do"
    if "diffuse" in n: return "d"
    if "_ao" in n: return "ao"
    return None


@functools.lru_cache(maxsize=None)
def pyramid(path):
    """A texture and its mipmaps (box-filtered), float RGBA (h, w, 4) each."""
    a = np.asarray(ae4_texture.decode(path).convert("RGBA")).astype(np.float32) / 255
    out = [a]
    while min(a.shape[:2]) > 4:
        h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
        a = a[:h, :w].reshape(h // 2, 2, w // 2, 2, 4).mean((1, 3))
        out.append(a)
    return out


def sample(levels, uv, level):
    """Bilinear, wrapping (tiled) at one mip level: uv (n, 2) -> (n, 4)."""
    img = levels[min(max(int(level), 0), len(levels) - 1)]
    h, w = img.shape[:2]
    x = (uv[:, 0] % 1.0) * w - 0.5; y = (uv[:, 1] % 1.0) * h - 0.5
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    x0 %= w; y0 %= h; x1 = (x0 + 1) % w; y1 = (y0 + 1) % h
    return img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy


def smoothness(gloss):
    """GoF3's Phong gloss (exponent exp2(9 g + 1)) as URP smoothness (1 - perceptual roughness, through GGX alpha
    = sqrt(2 / (n + 2))), the way ae4_ship_textures maps the ships' gloss."""
    n = 2.0 ** (9.0 * np.asarray(gloss, np.float32) + 1.0)
    return 1.0 - (2.0 / (n + 2.0)) ** 0.25


class Material:
    """One structure material: its textures by role and the values the bakes need."""

    def __init__(self, path, assets):
        self.path = path
        self.name = os.path.basename(path)[:-len(".ae4material")]
        v, slots = ae4_material.read(path)
        self.values = v
        self.blend = int(v.get("BlendMode", 0))
        self.effect = self.blend in ADDITIVE
        self.glass = bool(v.get("Opacity_Glass"))
        tex = {}
        for slot, h in slots.items():
            f = ae4_ids.resolve(assets, h)
            if f: tex[slot] = f
        self.cube = "Cube" in tex
        # an unlit one-colour material (no texture; the effect shader's custom colour: the loot containers' lit strips,
        # collectables_emissive): its colour, else None
        self.unlit_colour = (np.array(v.get("Colorize_Color1", (1, 1, 1, 1))[:3], np.float32) * float(v.get("Colorize_Multiplier", 1.0))
                             if not tex and v.get("Colorize_Custom") else None)
        self.diffuse = self.normal = None
        self.diffuse_role = self.normal_role = None
        for slot in ("T1", "T2", "T3", "T4", "T5", "T6"):
            f = tex.get(slot)
            role = _channels(f) if f else None
            if role in ("de", "do", "d") and self.diffuse is None: self.diffuse, self.diffuse_role = f, role
            elif role in ("nsg", "ns", "sg", "n", "ne") and self.normal is None: self.normal, self.normal_role = f, role
        col = v.get("Diffuse_Color", (1, 1, 1, 1))
        self.diffuse_color = np.array(col[:3], np.float32)
        sc = v.get("Specular_Color", (0, 0, 0, 1))
        self.spec_color = np.array(sc[:3], np.float32) * float(v.get("Specular_Multiplier", 0.0))
        self.overbright = float(v.get("Emissive_Overbright", 1.0) or 1.0)
        self.gloss = float(v.get("Gloss_Amount", 0.5))
        self.environment = float(v.get("Environment_Amount", 0.0)) if self.cube else 0.0
        self.tiling = float(v.get("Diffuse_Tiling", 1.0) or 1.0)
        self.normal_tiling = float(v.get("Normal_Tiling", 1.0) or 1.0)

    def size(self):
        """The diffuse texture's (w, h) (for the mip choice), else 1024."""
        if self.diffuse: return pyramid(self.diffuse)[0].shape[1::-1]
        return (1024, 1024)

    def sample(self, uv0, level, vcol):
        """Per point (uv0 (n, 2), vertex colour (n, 3)): diffuse (n, 3), emissive mask (n,), tangent-space normal (n, 3),
        specular colour (n, 3) before the light map's AO, gloss (n,)."""
        n = len(uv0)
        if self.diffuse:
            d = sample(pyramid(self.diffuse), uv0 * self.tiling, level)
            diffuse = d[:, :3] * self.diffuse_color * vcol
            emissive = np.minimum(1.0, d[:, 3] * self.overbright) if self.diffuse_role == "de" else np.zeros(n, np.float32)
        else:
            diffuse = np.broadcast_to(self.diffuse_color * 0.5, (n, 3)) * vcol
            emissive = np.zeros(n, np.float32)
        nrm = np.zeros((n, 3), np.float32); nrm[:, 2] = 1.0
        spec_mask = np.ones(n, np.float32); gloss = np.full(n, self.gloss, np.float32)
        if self.normal:
            t = sample(pyramid(self.normal), uv0 * self.normal_tiling, level)
            if self.normal_role in ("nsg", "ns", "n", "ne"):
                nrm = np.stack([t[:, 0] * 2 - 1, t[:, 1] * 2 - 1, np.ones(n, np.float32)], 1)
                nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
            if self.normal_role in ("nsg", "ns"): spec_mask = t[:, 2]
            if self.normal_role == "nsg": gloss = t[:, 3]
            if self.normal_role == "sg": spec_mask = t[:, :3].mean(1); gloss = t[:, 3]
        spec = spec_mask[:, None] * self.spec_color * vcol
        if self.environment > 0:   # the cubemap's reflection: at least this much of the sky, sharp
            spec = np.maximum(spec, self.environment * 0.5)
            gloss = np.maximum(gloss, self.gloss)
        if not self.spec_color.any() and not self.environment: spec = np.full((n, 3), FLAT_SPEC, np.float32)
        return diffuse, emissive, nrm, spec, gloss


@functools.lru_cache(maxsize=None)
def material(path, assets):
    if not path or not os.path.exists(path): return None
    try: return Material(path, assets)
    except Exception as e:
        print(f"  material {os.path.basename(path)}: {e}")
        return None


def race_plating(race, assets):
    """The race's main plating material: what a section without a known material is baked with."""
    src = f"{assets}/structures/{race}/materials/source"
    if not os.path.isdir(src): return None
    for f in sorted(os.listdir(src)):
        if re.match(rf"structure_{race}_matid\d+_platings_000\.ae4material$", f): return material(f"{src}/{f}", assets)
    return None


def uv_tangents(P, N, uv, idx):
    """Per-vertex tangents (n, 4) for a tangent-space normal map on 'uv' in glTF's convention: xyz along +u, w the sign
    with bitangent = cross(normal, tangent) x w pointing up the image (toward smaller v, glTF's v running down)."""
    P = np.asarray(P, np.float64); N = np.asarray(N, np.float64); uv = np.asarray(uv, np.float64)
    tri = np.asarray(idx, np.int64).reshape(-1, 3)
    T = np.zeros_like(P); B = np.zeros_like(P)
    p0, p1, p2 = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    t0, t1, t2 = uv[tri[:, 0]], uv[tri[:, 1]], uv[tri[:, 2]]
    e1, e2 = p1 - p0, p2 - p0; d1, d2 = t1 - t0, t2 - t0
    r = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(r) < 1e-20, 0.0, 1.0 / np.where(np.abs(r) < 1e-20, 1.0, r))[:, None]
    tu = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r   # along +u
    tv = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r   # along +v (down the image)
    for k in range(3):
        np.add.at(T, tri[:, k], tu); np.add.at(B, tri[:, k], tv)
    Nn = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    T = T - Nn * (T * Nn).sum(1, keepdims=True)
    bad = np.linalg.norm(T, axis=1) < 1e-12
    if bad.any():   # no UV gradient: any tangent across the normal
        a = np.where(np.abs(Nn[bad, 0:1]) < 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
        T[bad] = a - Nn[bad] * (a * Nn[bad]).sum(1, keepdims=True)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    up = -B   # the normal map's +Y: up the image
    w = np.where((np.cross(Nn, T) * up).sum(1) < 0, -1.0, 1.0)
    return np.c_[T, w].astype(np.float32)
