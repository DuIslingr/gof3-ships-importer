"""A GoF3 planet as the remake's planet picture: the planet's hemisphere seen from the camera, lit as GoF3's planet shader
lights it, on a transparent square (the disc filling 89 % of it, like the game's own planet_NNN_big).

GoF3's planet shader (planets/**/planet_*.ae4material_ GLSL), per vertex: lambert = clamp(N.L x Light_Transition);
rim = 1 - max(0, N.-E); planet rim = clamp((N.E + 1 - RimEffect_MinAngle) / (RimEffect_MaxAngle - RimEffect_MinAngle)) x
RimEffect_Color; atmosphere: lambert' = clamp((L.N + Atmosphere_Density) x Light_Transition), alpha = clamp(rim ^ (0.5 /
Atmosphere_Density), Atmosphere_Density, 1), colour = light x lambert' + ambient; per pixel: diffuse(UV x Surface_Tiling)
x (light x lambert + ambient), mixed toward Atmosphere_Color x the atmosphere's colour by its alpha, plus the planet rim.
The light is the level's light of the planet's LightDistribution group (GoF3 lights planets with its "Special" lights),
from that light entity's position; the picture is upright in the planet's view (the world's up kept up).

render(planet, assets, out_png, world, level) -> True when written."""
import glob, math, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_material, ae4_meshgroup, ae4_texture, gof3_galaxy

SIZE = 1024
FILL = 0.89
SKIP = ("corona", "atmo", "cloud", "fog", "flash", "ring", "swirl", "collision", "shadow", "fx", "glow")


def _refs(path, assets, ext):
    import build_gof3_systems as b
    return b.refs(path, assets, ext)


def _lights(world, lid):
    """[(mask, position, diffuse rgb 0..1 x intensity, ambient rgb)] of the level."""
    R = world.R
    _, lf = world.G.level_fields(lid)
    out = []
    for e in lf.get(gof3_galaxy.L_ENT, []):
        eid = world.ref(e)
        if not eid: continue
        try: comps, _ = R.resolved(eid)
        except Exception: continue
        if "Light" not in comps: continue
        f = comps["Light"]; tr = comps.get("Transform", {})
        def col(k): return np.array([R.sub(f[k][0]).get(i, 255) / 255.0 for i in (1, 2, 3)]) if k in f else np.ones(3)
        i = float(f.get(7830468, [1.0])[0])
        out.append((int(f.get(5964216, [1])[0]), np.array(world.G.vec(tr[6503637][0]) if 6503637 in tr else [0, 0, 1], float),
                    col(8835811) * i, col(1183415)))
    return out


def _planet_mask(world, lid, name):
    R = world.R
    _, lf = world.G.level_fields(lid)
    for e in lf.get(gof3_galaxy.L_ENT, []):
        eid = world.ref(e)
        if eid and world.nm(eid) == name:
            try: comps, _ = R.resolved(eid)
            except Exception: return 1
            return int(comps.get("LightDistribution", {}).get(5964216, [1])[0])
    return 1


def render(planet, assets, out_png, world, level):
    scene = assets + planet["shape"][len("/assets"):]
    if not os.path.exists(scene): return False
    folder = os.path.dirname(scene)
    body = None
    for mg in sorted(glob.glob(folder + "/*_lod_000*.ae4meshgroup")) + sorted(glob.glob(folder + "/*.ae4meshgroup")):
        if not any(k in os.path.basename(mg) for k in SKIP): body = mg; break
    if body is None: return False
    mats = [m for mod in _refs(scene, assets, ".ae4model") for m in _refs(mod, assets, ".ae4material")]
    mat = next((m for m in mats if not any(k in os.path.basename(m) for k in SKIP)), None)
    if mat is None: return False
    v, _ = ae4_material.read(mat)
    tex = _refs(mat, assets, ".ae4texture")
    diffuse = next((t for t in tex if "diffuse" in os.path.basename(t)), tex[0] if tex else None)
    if diffuse is None: return False
    D = np.asarray(ae4_texture.decode(diffuse).convert("RGB")).astype(np.float32) / 255
    c1, c2 = planet.get("colors") or (None, None)
    # light: the planet's group's, else the level's brightest Default one
    lights = _lights(world, level["id"])
    mask = _planet_mask(world, level["id"], planet["name"])
    cand = [l for l in lights if l[0] & mask] or [l for l in lights if l[0] & 1] or lights
    if cand: _, lpos, ldiff, lamb = max(cand, key=lambda l: l[2].sum())
    else: lpos, ldiff, lamb = np.array([1.0, 0.5, 1.0]), np.ones(3), np.full(3, 0.1)
    # the view: from the camera toward the planet, the world's up kept up; z toward the camera
    f = np.array(planet["pos"], float); f /= max(np.linalg.norm(f), 1e-9)
    up = np.array([0.0, 1.0, 0.0]) if abs(f[1]) < 0.99 else np.array([0.0, 0.0, 1.0])
    r = np.cross(up, f); r /= np.linalg.norm(r); u = np.cross(f, r)
    Lw = lpos / max(np.linalg.norm(lpos), 1e-9)
    L = np.array([Lw @ r, Lw @ u, -(Lw @ f)])          # in the view: x right, y up, z toward the camera
    # the hemisphere: its dome (mean normal) toward the camera
    secs = ae4_meshgroup.read_all(body)
    secs = [s for s in secs if "a_texCoord0" in s and s.get("count")]
    if not secs: return False
    P = np.concatenate([np.asarray(s["a_position"], float).reshape(-1, 3) for s in secs])
    UV = np.concatenate([np.asarray(s["a_texCoord0"], float).reshape(-1, 2) for s in secs])
    I, base = [], 0
    for s in secs: I.append(np.asarray(s["indices"], np.int64).reshape(-1, 3) + base); base += s["count"]
    I = np.concatenate(I)
    P -= (P.max(0) + P.min(0)) / 2
    if all("a_normal" in s for s in secs):
        N = np.concatenate([np.asarray(s["a_normal"], float).reshape(-1, 3) for s in secs])
    else:   # (planet meshes without normals: the faces' own, outward from the mesh's middle)
        N = np.zeros_like(P)
        fn = np.cross(P[I[:, 1]] - P[I[:, 0]], P[I[:, 2]] - P[I[:, 0]])
        for k in range(3): np.add.at(N, I[:, k], fn)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
        if (N * (P - P.mean(0))).sum() < 0: N = -N
    dome = N.mean(0)
    dome = dome / np.linalg.norm(dome) if np.linalg.norm(dome) > 1e-3 else np.array([0.0, 0.0, 1.0])   # (a whole sphere)
    a = np.array([1.0, 0, 0]) if abs(dome[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(a, dome); x /= np.linalg.norm(x); y = np.cross(dome, x)
    B = np.stack([x, y, dome])                           # mesh -> view (dome = +z)
    P = P @ B.T; N = N @ B.T
    # only hemispheres (a ring, a flat glow quad or a strip isn't a planet's body)
    ext = P.max(0) - P.min(0)
    if ext[2] < 0.3 * max(ext[0], ext[1]) or not 0.7 < ext[0] / max(ext[1], 1e-9) < 1.4: return False
    R = np.abs(P[:, :2]).max()
    S = SIZE * FILL / 2 / R
    xy = np.c_[P[:, 0] * S + SIZE / 2, SIZE / 2 - P[:, 1] * S]
    tiling = float(v.get("Surface_Tiling", 1.0) or 1.0)
    lt = float(v.get("Light_Transition", 1.0) or 1.0)
    dens = float(v.get("Atmosphere_Density", 0.0) or 0.0) if v.get("Atmosphere_Enabled") else 0.0
    atm_col = np.array(v.get("Atmosphere_Color", (0, 0, 0, 1))[:3], np.float32)
    rim_on = v.get("RimEffect_Enabled", False)
    rim_col = np.array(v.get("RimEffect_Color", (0, 0, 0, 1))[:3], np.float32)
    rmin, rmax = float(v.get("RimEffect_MinAngle", 0.0)), float(v.get("RimEffect_MaxAngle", 1.0))
    # the mesh gives the texture coordinates (rasterised, then spread to the whole disc: GoF3's hemispheres are low-poly,
    # their outline a polygon); the normals are the sphere's own
    uvb = np.zeros((SIZE, SIZE, 2), np.float32); have = np.zeros((SIZE, SIZE), bool)
    for t in I:
        Q = xy[t]
        if (P[t, 2] < -1e-6 * R).all(): continue       # the hemisphere's back
        x0, y0 = np.floor(Q.min(0)).astype(int); x1, y1 = np.ceil(Q.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, SIZE), min(y1, SIZE)
        if x1 <= x0 or y1 <= y0: continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        d = (Q[1, 1] - Q[2, 1]) * (Q[0, 0] - Q[2, 0]) + (Q[2, 0] - Q[1, 0]) * (Q[0, 1] - Q[2, 1])
        if abs(d) < 1e-12: continue
        l0 = ((Q[1, 1] - Q[2, 1]) * (gx - Q[2, 0]) + (Q[2, 0] - Q[1, 0]) * (gy - Q[2, 1])) / d
        l1 = ((Q[2, 1] - Q[0, 1]) * (gx - Q[2, 0]) + (Q[0, 0] - Q[2, 0]) * (gy - Q[2, 1])) / d
        l2 = 1 - l0 - l1
        ins = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not ins.any(): continue
        Wb = np.stack([l0[ins], l1[ins], l2[ins]], 1)
        yy, xx = gy[ins].astype(int), gx[ins].astype(int)
        uvb[yy, xx] = Wb @ UV[t]; have[yy, xx] = True
    if not have.any(): return False
    # the disc: the biggest circle the mesh covers whole (inside the low-poly outline, no smearing); a mesh with holes in
    # it (a horizon planet's partial cap) is no disc
    g = np.arange(SIZE) + 0.5 - SIZE / 2
    GX, GY = np.meshgrid(g, g)
    dist = np.sqrt(GX * GX + GY * GY)
    r_out = SIZE * FILL / 2
    holes = (~have) & (dist <= r_out)
    r_in = float(dist[holes].min()) if holes.any() else r_out
    if r_in < 0.85 * r_out: return False
    c = (np.arange(SIZE) + 0.5 - SIZE / 2) / r_in
    X, Y = np.meshgrid(c, -c)
    r2 = X * X + Y * Y
    disc = r2 <= 1.0
    n = np.stack([X, Y, np.sqrt(np.clip(1 - r2, 0, 1))], -1)[disc]
    uv = uvb[disc] * tiling
    h, w = D.shape[:2]
    tx = ((uv[:, 0] % 1) * (w - 1)).astype(int); ty = ((uv[:, 1] % 1) * (h - 1)).astype(int)
    dif = D[ty, tx]
    if c1 is not None and c2 is not None and v.get("Colorize_Enabled"):
        dif = dif * (np.array(c1) + (np.array(c2) - np.array(c1)) * dif[:, :1])
    lam = np.clip(n @ L * lt, 0, 1)[:, None]
    out = dif * (ldiff * lam + lamb)
    rim = 1 - np.maximum(0, n[:, 2])
    if dens > 0:
        al = np.clip((n @ L + dens) * lt, 0, 1)[:, None]
        aa = np.clip(rim ** (0.5 / dens), dens, 1)[:, None]
        out = out * (1 - aa) + atm_col * (ldiff * al + lamb) * aa
    if rim_on:
        pr = np.clip((np.clip(-n[:, 2] + 1, 0, 1) - rmin) / max(rmax - rmin, 1e-6), 0, 1)[:, None]
        out = out + pr * rim_col
    col = np.zeros((SIZE, SIZE, 3), np.float32); col[disc] = out
    # a soft edge (a pixel's worth)
    alpha = np.clip((1.0 - np.sqrt(r2)) * r_in + 0.5, 0, 1).astype(np.float32)
    # the disc back to filling FILL of the picture
    k = r_in / r_out
    if k < 0.999:
        lo, hi = int(round(SIZE / 2 - SIZE / 2 * k)), int(round(SIZE / 2 + SIZE / 2 * k))
        col = np.asarray(Image.fromarray((np.clip(col[lo:hi, lo:hi], 0, 1) * 255).astype(np.uint8)).resize((SIZE, SIZE), Image.LANCZOS)).astype(np.float32) / 255
        alpha = np.asarray(Image.fromarray((alpha[lo:hi, lo:hi] * 255).astype(np.uint8)).resize((SIZE, SIZE), Image.LANCZOS)).astype(np.float32) / 255
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    rgba = np.dstack([np.clip(col, 0, 1), alpha])
    Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").save(out_png, optimize=True)
    return True
