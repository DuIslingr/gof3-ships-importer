"""Bake a GoF3 ship's textures to PNGs with the game's own shader math (ShipShader GLSL in the .ae4material_ folders).
Usage (venv with texture2ddecoder, Pillow, numpy): ae4_ship_textures.py <ship dir> <ship name> <out textures dir> [resolve.json]

T1 diffuse_emissive: RGB diffuse, A emissive mask (body) / opacity (glass)
T2 specular_gloss:   RGB specular (x Specular_Multiplier), A gloss (x Gloss_Multiplier, Phong exp2(9 g + 1))
T3 normal:           RG normal, Z rebuilt (Normal_ClearZ)
T4 colormask:        diffuse = mix(diffuse, mix(Colorize_Color1, Colorize_Color2, mask.a) * diffuse, mask.r)"""
import sys, os, glob, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_texture, ae4_material
if os.sep == "\\":   # Windows: the code splits and joins paths with "/": glob's results (and the paths given) too
    _glob = glob.glob
    glob.glob = lambda pattern, **kw: [p.replace("\\", "/") for p in _glob(pattern, **kw)]

src, name, out = sys.argv[1:4]
src = os.path.abspath(src).replace("\\", "/")
assets = src.split("/ships/")[0]   # the assets dir, also for ships outside <race>/<num>
os.makedirs(out, exist_ok=True)
def tex(path, size=None):
    """size (w, h): scale to it (assets_best/ mixes 2048 px romfs textures with 1024 px iOS fallbacks)."""
    im = ae4_texture.decode(path)
    if size and im.size != size:
        im = im.resize(size, Image.BICUBIC)
    return np.asarray(im).astype(np.float32) / 255
def save(a, fn, mode=None):
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(os.path.join(out, fn))

# Which files: the naming convention, or (5th argument) the JSON of ae4_resolve.py: the files the ship's GUIDs point at,
# possibly another ship's (variants), and the packed n_s_g layout (terran/031: one texture = normal RG, specular B, gloss A).
R = json.load(open(sys.argv[4], encoding='utf-8-sig')) if len(sys.argv) > 4 else None
if R:
    BODY, GLASS, PACKED = R["body_material"], R["glass_material"], R.get("packed_nsg", False)
    IN = [R.get("Diffuse"), R.get("Specular"), R.get("Normal"), R.get("Colorize")]
    SCHEMES = R.get("schemes", [])
else:
    BODY, GLASS, PACKED = f"{src}/{name}_matid01_body.ae4material", f"{src}/{name}_matid02_glass.ae4material", False
    IN = [f"{src}/{name}_{k}.tga.ae4texture" for k in ("diffuse_emissive", "specular_gloss", "normal", "colormask_000")]
    SCHEMES = sorted(glob.glob(f"{src}/materials/{name}_matid01_body_*.ae4material"))
if PACKED: IN[1] = None
SIZE = max((ae4_texture.decode(p).size for p in IN if p), key=lambda s: s[0] * s[1])   # the largest input's size
def const(*v): return np.broadcast_to(np.array(v, np.float32), (SIZE[1], SIZE[0], 4)).copy()
T1, T2, T3, T4 = (tex(p, SIZE) if p else None for p in IN)
LOADED = [T1 is not None, T2 is not None or PACKED, T3 is not None, T4 is not None]
if PACKED:      # specular = B, gloss = A (the glass-free ShipShader variant of terran/031)
    T2 = np.dstack([T3[..., 2:3]] * 3 + [T3[..., 3:4]])
if T2 is None:  # no specular map (inouac/601): a dull grey, low gloss
    T2 = const(0.25, 0.25, 0.25, 0.3); print("no specular texture: constant 0.25 / gloss 0.3")
if T3 is None:  # no normal map: flat
    T3 = const(0.5, 0.5, 1.0, 1.0); print("no normal texture: flat")
if T4 is None:  # no colormask (Colorize slot 0 or not found): no paint
    T4 = const(0.0, 0.0, 0.0, 0.0); print("no colormask: diffuse unpainted")
body, _ = ae4_material.read(BODY)
body.setdefault("Colorize_Color1", (1, 1, 1, 1)); body.setdefault("Colorize_Color2", (1, 1, 1, 1))

def colorize(mat, mask):
    c1 = np.array(mat["Colorize_Color1"][:3], np.float32); c2 = np.array(mat["Colorize_Color2"][:3], np.float32)
    d = T1[..., :3] * np.array(mat["Diffuse_Color"][:3], np.float32)
    col = c1 + (c2 - c1) * mask[..., 3:4]
    return d + (col * d - d) * mask[..., 0:1]

LUM = np.array([0.22, 0.707, 0.071], np.float32)
def emission(mat, diffuse, e, glass=False):
    """Emissive_EmissiveColorOverwrite: e * (lumin + k * C * (1 - lumin)) * lumin with lumin = the diffuse luminance
    (body shader k = 2; glass shader k = 4 and lumin = clamp(Overbright * lum)); else e * diffuse."""
    if not mat.get("Emissive_EmissiveColorOverwrite"):
        return diffuse * e
    c = np.array(mat["Emissive_Color"][:3], np.float32)
    lum = diffuse @ LUM
    if glass:
        lum = np.clip(mat.get("Emissive_Overbright", 1.0) * lum, 0, 1)
    lum = lum[..., None]
    return e * (lum + (4.0 if glass else 2.0) * c * (1.0 - lum)) * lum

base = colorize(body, T4)
save(base, f"{name}_basecolor.png")
save(emission(body, base, T1[..., 3:4]), f"{name}_emissive.png")
if body.get("Emissive_EmissiveColorOverwrite"):
    print("emissive colour override", np.round(body["Emissive_Color"][:3], 2))
# texture roles by slot (the slot order differs per ship: terran/vossk T2 spec / T3 normal, nivelian T2 normal / T3 spec)
by_slot = {body.get(k + "_TextureSlot", d): t for k, d, t, real in
           (("Diffuse", 1, T1, LOADED[0]), ("Specular", 2, T2, LOADED[1]), ("Normal", 3, T3, LOADED[2]), ("Colorize", 4, T4, LOADED[3]))
           if real}   # never the constant stand-ins
ao_src = by_slot.get(body.get("AmbientOcclusion_TextureSlot", 0))
if ao_src is None and (R or {}).get("AmbientOcclusion"):   # AO in a texture of its own (drone: T7 lightmap_ao)
    ao_src = tex(R["AmbientOcclusion"], SIZE)
AO = None
if ao_src is not None:   # AO = a channel of one of the textures (light and specular x AO)
    AO = ao_src[..., body.get("AmbientOcclusion_Channel", 2)]
    if AO.min() < 0.99:
        save(AO, f"{name}_ao.png", "L"); print("ambient occlusion baked")
    else:
        AO = None
SPEC_KEYS = ("Specular_Color", "Specular_Multiplier", "Gloss_Multiplier", "Colorize_Specular")
def specular_map(mat, mask):
    spec = T2[..., :3] * np.array(mat["Specular_Color"][:3], np.float32)
    if mat.get("Colorize_Specular"):   # specularTexel *= min(1, colorizeColor + 1 - colorizeMask)
        c1 = np.array(mat["Colorize_Color1"][:3], np.float32); c2 = np.array(mat["Colorize_Color2"][:3], np.float32)
        spec = spec * np.minimum(1.0, c1 + (c2 - c1) * mask[..., 3:4] + 1.0 - mask[..., 0:1])
    if AO is not None: spec = spec * AO[..., None]
    return spec * mat["Specular_Multiplier"]
def roughness_map(mat):
    n = 2.0 ** (9.0 * T2[..., 3] * mat["Gloss_Multiplier"] + 1.0)   # Phong exponent
    return (2.0 / (n + 2.0)) ** 0.25                                 # -> GGX alpha -> perceptual roughness
def scheme_specular(mat, mask, var):
    """A scheme with its own specular look (the gold schemes: tint (1, 0.82, 0.29) x 5, gloss x 4) gets its own maps."""
    if any(mat.get(k) != body.get(k) for k in SPEC_KEYS) or (mat.get("Colorize_Specular") and mask is not T4):
        save(specular_map(mat, mask), f"{name}_specular_{var}.png")
        save(roughness_map(mat), f"{name}_roughness_{var}.png", "L")
        return True
    return False
save(specular_map(body, T4), f"{name}_specular.png")
if body.get("Iridescence_TextureSlot", 0) > 0:   # T5: RGB spectrum looked up by N.V, A = mask on the mesh UVs
    I = tex((R or {}).get("Iridescence") or f"{src}/{name}_iridescence_mask.tga.ae4texture", SIZE)
    save(I[..., 3] * body.get("Iridescence_Strength", 1.0), f"{name}_iridescence_mask.png", "L")
    save(I[..., :3], f"{name}_iridescence_gradient.png")
    print("iridescence textures")
save(roughness_map(body), f"{name}_roughness.png", "L")
xy = T3[..., :2] * 2 - 1
z = np.sqrt(np.clip(1 - (xy ** 2).sum(-1), 0, 1))
save(np.dstack([T3[..., 0], T3[..., 1], z * 0.5 + 0.5]), f"{name}_normal.png")
def glass_texture(path, quiet=False):
    """The canopy: (lit) diffuse x Diffuse_Color, with the override emission over it where the glass shader has one;
    opacity = the diffuse alpha (or the glass's own textures, terran/031)."""
    gmat, gslots = ae4_material.read(path)
    a = T1[..., 3:4]
    rgb = T1[..., :3]
    if (R or {}).get("GlassDiffuse"):   # the glass's own textures (terran/031): diffuse T1, opacity = T2.a x Opacity_Amount
        g1 = tex(R["GlassDiffuse"]); rgb = g1[..., :3]
        g2 = tex(R["GlassOpacity"], (g1.shape[1], g1.shape[0])) if R.get("GlassOpacity") else np.ones_like(g1)
        a = g2[..., 3:4] * gmat.get("Opacity_Amount", 0.5)
        if not quiet: print("glass textures", os.path.basename(R["GlassDiffuse"]), "opacity x", gmat.get("Opacity_Amount", 0.5))
    rgb = rgb * np.array(gmat.get("Diffuse_Color", (1, 1, 1, 1))[:3], np.float32)   # diffuseTexel = T1.rgb * custom_Diffuse_Color
    if gmat.get("Emissive_EmissiveColorOverwrite"):   # glass: (lit) diffuse * (1 - e) + override emission, opacity = A
        rgb = rgb * (1 - a) + emission(gmat, rgb, a, glass=True)
        if not quiet: print("glass emissive override", np.round(gmat["Emissive_Color"][:3], 2))
    return np.dstack([rgb, a])
if GLASS and os.path.exists(GLASS):
    save(glass_texture(GLASS), f"{name}_glass.png")
save(T1[..., :3], f"{name}_diffuse_raw.png"); save(T1[..., 3], f"{name}_emissive_mask.png", "L")
save(T4, f"{name}_colormask_000.png")

# paint schemes (materials/<name>_matid01_body_<variant>.ae4material, colormasks/<name>_cm_<variant>)
for mp in SCHEMES:
    owner = os.path.basename(mp).split("_matid01_body_")[0]          # the ship the scheme belongs to (a variant borrows them)
    var = os.path.basename(mp)[len(f"{owner}_matid01_body_"):-len(".ae4material")]
    if var.endswith(("_cloak", "_dissolve", "_cloak_npc")):
        continue
    cm = f"{os.path.dirname(os.path.dirname(mp))}/colormasks/{owner}_cm_{var}.tga.ae4texture"
    if not os.path.exists(cm): cm = (R or {}).get("scheme_masks", {}).get(mp, cm)   # resolved elsewhere (008's 000 -> cm_001)
    mask = tex(cm, SIZE) if os.path.exists(cm) else T4
    vmat = {**body, **ae4_material.read(mp)[0]}   # what a scheme leaves out is the body's (201 scheme 002: no Gloss_Multiplier)
    vbase = colorize(vmat, mask)
    save(vbase, f"{name}_basecolor_{var}.png")
    save(emission(vmat, vbase, T1[..., 3:4]), f"{name}_emissive_{var}.png")   # a scheme may recolour the glow
    own_spec = scheme_specular(vmat, mask, var)
    gv = f"{os.path.dirname(mp)}/{owner}_matid02_glass_{var}.ae4material"   # the scheme's own canopy (dragon: orange)
    if not os.path.exists(gv) and owner == name:   # a ship's own scheme with an unsuffixed glass (008: materials/..._glass)
        gv = f"{os.path.dirname(mp)}/{owner}_matid02_glass.ae4material"
    if GLASS and os.path.exists(GLASS) and os.path.exists(gv):
        save(glass_texture(gv, quiet=True), f"{name}_glass_{var}.png")
    print("paint scheme", var, "mask", os.path.basename(cm) if os.path.exists(cm) else "colormask_000",
          "+ glass" if GLASS and os.path.exists(gv) else "", "+ specular" if own_spec else "")

# skins that exist only as colour presets in data.pdb (ae4_resolve.py / data_skins.json): the body material with the
# preset's two colours through its mask; the canopy stays the ship's (presets only recolour the hull)
for sk in (R or {}).get("data_skins", []):
    vmat = dict(body, Colorize_Color1=tuple(sk["color1"]) + (1.0,), Colorize_Color2=tuple(sk["color2"]) + (1.0,))
    if sk.get("emissive_color"):   # an Emissive_* preset: the override glow colour
        vmat.update(Emissive_EmissiveColorOverwrite=True, Emissive_Color=tuple(sk["emissive_color"]) + (1.0,))
    if sk.get("specular_from"):    # a material pack's specular look (the Gold pack = the gold scheme's specular / gloss)
        smat = ae4_material.read(sk["specular_from"])[0]
        vmat.update({k: smat[k] for k in SPEC_KEYS + ("Gloss_Amount", "Environment_Enabled") if k in smat})
    if sk.get("specular"):         # a material pack's specular values given directly
        vmat.update({k: (tuple(v) + (1.0,) if isinstance(v, list) else v) for k, v in sk["specular"].items()})
    mask = tex(sk["mask"], SIZE) if sk.get("mask") else T4   # no mask slot (the Gold tiers): the ship's own
    vbase = colorize(vmat, mask)
    save(vbase, f"{name}_basecolor_{sk['scheme']}.png")
    save(emission(vmat, vbase, T1[..., 3:4]), f"{name}_emissive_{sk['scheme']}.png")
    own_spec = scheme_specular(vmat, mask, sk["scheme"])
    print("data.pdb skin", sk["scheme"], "preset", sk.get("preset") or sk.get("preset_record"), np.round(sk["color1"], 3), "/", np.round(sk["color2"], 3),
          "mask", os.path.basename(sk.get("mask") or "colormask_000"), "+ emissive" if sk.get("emissive_color") else "", "+ specular" if own_spec else "")

if os.path.exists(f"{src}/{name}_decals.tga.ae4texture"):   # the ship's own decal sheet (starfox)
    save(tex(f"{src}/{name}_decals.tga.ae4texture"), f"{name}_decals.png")
    print("own decal sheet")

# weapon mount: T1 normal_diffuse = RG normal, B diffuse / specular
M = tex(f"{assets}/weapons/generic/mounts/000/weapon_generic_mount_000_normal_diffuse.tga.ae4texture")
save(np.repeat(M[..., 2:3], 3, -1), "weapon_generic_mount_000_basecolor.png")
mxy = M[..., :2] * 2 - 1
save(np.dstack([M[..., 0], M[..., 1], np.sqrt(np.clip(1 - (mxy ** 2).sum(-1), 0, 1)) * 0.5 + 0.5]), "weapon_generic_mount_000_normal.png")
# mount contact shadow: black, alpha = tex.a * luminance (texture referenced by GUID only: vfx_generic_glow_000 stands in)
G = tex(f"{assets}/vfx/generic/vfx_generic_glow_000.tga.ae4texture")
a = G[..., 3] * (G[..., :3] @ np.array([0.3, 0.59, 0.11], np.float32))
save(np.dstack([np.zeros_like(a)] * 3 + [a]), "ship_mount_shadow.png", "RGBA")
for k in range(4):
    p = f"{assets}/ships/decals/textures/ship_decals_00{k}.tga.ae4texture"
    save(tex(p), f"ship_decals_00{k}.png")
print("textures ->", out)
