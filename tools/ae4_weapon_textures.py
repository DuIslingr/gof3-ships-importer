"""Bake GoF3 weapon textures to PNGs with the game's weapon shader math (the GLSL in weapon_generic_NNN.ae4material_):
  T1 diffuse            RGB x Diffuse_Color
  T4 colormask          colorizeColor = mix(Colorize_Color1, Colorize_Color2, cm.a); diffuse = mix(d, colorizeColor * d, cm.r)
                        emissive = cm.a: lit colour x (1 - e) + e x diffuse
  T2 normal_ao          normal = normalize(rg * 2 - 1, 1) (Normal_ClearZ: Z is 1, not rebuilt); B = an AO bake the shader
                        never reads (AmbientOcclusion_TextureSlot 0), kept as _ao_raw
  specular              diffuse^2 (the colorized diffuse, before the tint) x min(1, colorizeColor + 1 - cm.r) x Specular_Multiplier
  gloss                 Gloss_Amount x Gloss_Multiplier, constant (Phong exp2(9 g + 1) -> GGX perceptual roughness)
  T3 specular_gloss     listed in the material but never sampled by the shader: kept as _specular_gloss_raw only

Usage: ae4_weapon_textures.py <weapons/generic/NNN dir> <out textures dir> [material] [out name]
  material: another .ae4material over the same textures (the gold variants: generic/000_gold has no textures of its own,
  its material points at 000's with the gold colours); out name defaults to the material's name."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_texture, ae4_material

src, out = sys.argv[1:3]
tname = "weapon_generic_" + os.path.basename(os.path.normpath(src))
mpath = sys.argv[3] if len(sys.argv) > 3 else f"{src}/{tname}.ae4material"
name = sys.argv[4] if len(sys.argv) > 4 else os.path.splitext(os.path.basename(mpath))[0]
os.makedirs(out, exist_ok=True)


def tex(p, size=None):
    im = ae4_texture.decode(p)
    if size and im.size != size: im = im.resize(size, Image.BICUBIC)
    return np.asarray(im).astype(np.float32) / 255


def save(a, fn, mode=None):
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(os.path.join(out, fn))


def roughness(gloss):
    n = 2.0 ** (9.0 * gloss + 1.0)            # Phong exponent
    return (2.0 / (n + 2.0)) ** 0.25          # -> GGX alpha -> perceptual roughness (as ae4_ship_textures.py)


D0 = ae4_texture.decode(f"{src}/{tname}_diffuse.tga.ae4texture")
size = D0.size
D = np.asarray(D0).astype(np.float32) / 255
CM = tex(f"{src}/{tname}_colormask_000.tga.ae4texture", size)
N = tex(f"{src}/{tname}_normal_ao.tga.ae4texture", size)
mat, _ = ae4_material.read(mpath)
c1 = np.array(mat["Colorize_Color1"][:3], np.float32); c2 = np.array(mat["Colorize_Color2"][:3], np.float32)
d = D[..., :3] * np.array(mat.get("Diffuse_Color", (1, 1, 1, 1))[:3], np.float32)
col = c1 + (c2 - c1) * CM[..., 3:4]
mask = CM[..., 0:1]
base = d + (col * d - d) * mask
save(base, f"{name}_basecolor.png")
save(base * CM[..., 3:4], f"{name}_emissive.png")
xy = N[..., :2] * 2 - 1
n = np.dstack([xy, np.ones(xy.shape[:2], np.float32)])
n /= np.linalg.norm(n, axis=-1, keepdims=True)
save(n * 0.5 + 0.5, f"{name}_normal.png")
spec = d * d
if mat.get("Colorize_Specular", True): spec = spec * np.minimum(1.0, col + 1.0 - mask)
save(spec * mat.get("Specular_Multiplier", 1.0), f"{name}_specular.png")
g = mat.get("Gloss_Amount", 0.5) * mat.get("Gloss_Multiplier", 1.0)
save(np.full(base.shape[:2], roughness(g), np.float32), f"{name}_roughness.png", "L")
# the unprocessed inputs, for repainting (once per texture set)
if name == tname:
    save(D, f"{tname}_diffuse_raw.png", "RGBA")
    save(CM, f"{tname}_colormask_000.png", "RGBA")
    save(N[..., 2], f"{tname}_ao_raw.png", "L")
    sg = f"{src}/{tname}_specular_gloss.tga.ae4texture"
    if os.path.exists(sg): save(tex(sg, size), f"{tname}_specular_gloss_raw.png", "RGBA")
print(name, size, "C1", np.round(c1, 2), "C2", np.round(c2, 2), "gloss", round(g, 2), "-> roughness", round(roughness(g), 2))
