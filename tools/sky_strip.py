"""A GoF3 sky (skyboxes/materials/skybox_<name>.ae4material) as the remake's 6:1 cube-face strip.

The material names its cubemap by resource id (ae4_ids); the cubemap .ae4texture holds six faces of one mip back to back
after the 0x4000 header (format 16 ETC2 RGB / 17 ETC2 RGBA8 / 1 RGBA8): the top, then the four sides round the horizon left
to right (the second of them in front), then the bottom, each upright as seen from inside (found by matching the faces'
edges: 0's bottom edge meets 2's top, 1-2-3-4 meet side by side, 5's top meets 2's bottom). STRIP puts them in the remake's
order +X, -X, +Y, -Y, +Z, -Z. The material's
Colorize tints the sky by Colorize_Color1 (a grey on most), applied here.

sky_strip.convert(material_path, out_png, assets) -> the cubemap's path (None when the material names none)."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_ids, ae4_material
from ae4unpack import unpack
import texture2ddecoder as t


STRIP = [3, 1, 0, 5, 2, 4]
# The file's faces are GL's targets (libgofm's ae::render::opengl::loadTexture uploads face i to +Y, -X, +Z, +X, -Z, -Y), and
# GoF3's sky shader samples them with the sky mesh's own position (textureCube(EnvironmentMap, normalize(a_position))) in
# its level frame, which is the remake's with x mirrored (glTFast's way, the sun's, the station models'). So the remake's
# strip at Unity direction u must hold the cube at (-u.x, u.y, u.z): the X faces swapped and every face mirrored left to
# right (convert_gof3); then a level's sky turn is a rotation (gof3_look.sky_rotation). STRIP alone showed GoF3's skies
# mirrored.
MIRRORED = [1, 3, 0, 5, 2, 4]


def cubemap_of(material_path, assets):
    d = unpack(open(material_path, "rb").read())
    idx = ae4_ids.index(assets)
    for o in range(len(d) - 8):
        p = idx.get(int.from_bytes(d[o:o + 8], "little"))
        if p and "/cubemap_" in p.replace("\\", "/"): return p
    return None


def faces(path):
    d = unpack(open(path, "rb").read())
    fmt = struct.unpack_from("<I", d, 0x0c)[0]
    w = struct.unpack_from("<H", d, 0x1a)[0]; h = struct.unpack_from("<H", d, 0x1e)[0]
    per = {16: w * h // 2, 17: w * h, 1: w * h * 4}[fmt]
    out = []
    for f in range(6):
        raw = d[0x4000 + f * per:0x4000 + (f + 1) * per]
        if fmt == 1: out.append(Image.frombytes("RGBA", (w, h), raw, "raw", "RGBA"))
        else:
            px = t.decode_etc2(raw, w, h) if fmt == 16 else t.decode_etc2a8(raw, w, h)
            out.append(Image.frombytes("RGBA", (w, h), px, "raw", "BGRA"))
    return out


def convert(material_path, out_png, assets, flips=None):
    cube = cubemap_of(material_path, assets)
    if cube is None: return None
    vals, _ = ae4_material.read(material_path)
    tint = np.array(vals.get("Colorize_Color1", (1, 1, 1, 1))[:3], np.float32) if vals.get("Colorize_Enabled") else np.ones(3, np.float32)
    fs = faces(cube)
    w = fs[0].size[0]
    strip = Image.new("RGB", (w * 6, w))
    for i, src in enumerate(STRIP):
        f = fs[src].convert("RGB")
        op = (flips or {}).get(i)
        if op: f = f.transpose(op)
        strip.paste(f, (i * w, 0))
    a = np.asarray(strip).astype(np.float32) * tint
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(out_png)
    return cube


if __name__ == "__main__":
    print(convert(sys.argv[1], sys.argv[2], sys.argv[3]))


# The remake's strip faces (+X, -X, +Y, -Y, +Z, -Z, each upright as seen from inside; the up face with the front at its bottom
# edge, the down face with it at its top): the cube's surface point (Unity's axes, -0.5..0.5) at a face's (u, v), v down.
def _face_points(i, n):
    u, v = np.meshgrid((np.arange(n) + 0.5) / n - 0.5, (np.arange(n) + 0.5) / n - 0.5)
    h = np.full_like(u, 0.5)
    return [np.stack([h, -v, -u], -1), np.stack([-h, -v, u], -1), np.stack([u, h, v], -1),
            np.stack([u, -h, -v], -1), np.stack([u, -v, h], -1), np.stack([-u, -v, -h], -1)][i]


LUMA = np.array([0.22, 0.707, 0.071], np.float32)


def convert_gof3(material_path, out_png, assets, colors=None, fog=None, stars_png=None, stars_face=1024):
    """The sky as GoF3's skybox shader draws it (skybox_*.ae4material_ GLSL): the cube tinted by its Colorize, the stars layer
    under it, the level's fog over both:
      Colorize_Gradient: tint = mix(C1, C2, length(vec3(p) + 0.5)) x Colorize_Multiplier, p the cube's surface (+-0.5) on
        its axis (Colorize_x / y / z_axis, negated by the invert flags; GoF3's x is Unity's mirrored, glTFast's way);
      Colorize_Options 3: rgb x C2 + C1;  else: rgb x mix(C1, C2, r^2) x Colorize_Multiplier;
      stars = Stars(face uv) x (1 - cube) faded out where the tinted sky's luminance passes Star_BlendTreshold x 0.1;
      fog (Fog_Enabled): mix(rgb, fogColor, the level's fog density).
    'colors' (C1, C2): the sky entity's Colorize (else the material's); 'fog' (rgb 0..1, density). The nebula strip holds the
    tinted, fogged cube, 'stars_png' the stars (the remake adds the two layers, as GoF3 does). Returns the cubemap's path."""
    import ae4_material as am
    cube = cubemap_of(material_path, assets)
    if cube is None: return None
    v, _ = am.read(material_path)
    fs = faces(cube)
    n = fs[0].size[0]
    on = v.get("Colorize_Enabled", False)
    c1 = np.array((colors[0] if colors else v.get("Colorize_Color1", (1, 1, 1, 1)))[:3], np.float32)
    c2 = np.array((colors[1] if colors else v.get("Colorize_Color2", (1, 1, 1, 1)))[:3], np.float32)
    mult = float(v.get("Colorize_Multiplier", 1.0))
    axis = next((k for k, a in enumerate("xyz") if v.get(f"Colorize_{a}_axis")), 1)
    invert = any(v.get(f"Colorize_invert_{a}_axis") for a in "xyz")
    thr = float(v.get("Star_BlendTreshold", 0.5)) * 0.1
    f = float(fog[1]) if fog and v.get("Fog_Enabled", True) else 0.0
    fc = np.array(fog[0][:3], np.float32) if fog else np.zeros(3, np.float32)
    stex = None
    if stars_png:
        st = am.texture_ids(material_path).get("Stars")
        sp = ae4_ids.resolve(assets, st) if st else None
        if sp:
            import ae4_texture
            stex = ae4_texture.decode(sp).convert("RGB").resize((stars_face, stars_face), Image.LANCZOS)
    neb = Image.new("RGB", (n * 6, n)); stars = Image.new("RGB", (stars_face * 6, stars_face)) if stex else None
    for i, src in enumerate(MIRRORED):
        rgb = np.asarray(fs[src].convert("RGB")).astype(np.float32)[:, ::-1] / 255   # (STRIP's note: the cube at x mirrored)
        raw = rgb
        if on:
            if v.get("Colorize_Gradient"):
                p = _face_points(i, n) * np.array([-1.0, 1.0, 1.0])   # GoF3's x: Unity's mirrored
                s = p[..., axis] * (-1.0 if invert else 1.0)
                t = (np.sqrt(3.0) * np.abs(s + 0.5))[..., None]
                rgb = rgb * (c1 + (c2 - c1) * t) * mult
            elif v.get("Colorize_Options") == 3:
                rgb = rgb * c2 + c1
            else:
                rgb = rgb * (c1 + (c2 - c1) * (raw[..., :1] ** 2)) * mult
        rgb = np.clip(rgb, 0, 1)
        neb.paste(Image.fromarray((np.clip(rgb * (1 - f) + fc * f, 0, 1) * 255 + 0.5).astype(np.uint8)), (i * n, 0))
        if stex is not None:
            big = lambda a: np.asarray(Image.fromarray((a * 255 + 0.5).astype(np.uint8)).resize((stars_face, stars_face), Image.BILINEAR)).astype(np.float32) / 255
            sr = np.asarray(stex).astype(np.float32) / 255 * (1 - big(raw))
            lum = big(rgb) @ LUMA
            fade = np.ones_like(lum) if thr <= 0 else np.clip((lum - thr) / thr, 0, 1)
            sr = np.clip(sr * (1 - fade[..., None]), 0, 1) * (1 - f)
            stars.paste(Image.fromarray((sr * 255 + 0.5).astype(np.uint8)), (i * stars_face, 0))
    neb.save(out_png)
    if stars is not None: stars.save(stars_png)
    return cube
