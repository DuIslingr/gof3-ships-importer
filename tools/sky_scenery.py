"""A GoF3 level's distant scenery painted into its sky (the user, 2026-11-02: no big scenery in the orbits, only in the sky).

GoF3 dresses each level with more than its hub: the other hubs' stations and background stations in the distance
(assets/stations/<sector>/...), billboards, asteroid clusters and rings, junk, comets, background traffic, parked capital
ships. The remake's orbit spans ~10 km (~3700 GoF3 units), so whatever lies farther than NEAR from the level's station (and
what GoF3 hangs on the camera: its background asteroid rings and comets at the origin) is painted into the orbit's sky
strip, as seen from the station: each part's own texture (its material's diffuse, sampled at its UVs), lit by the level's
light, fogged by the level's fog, into the strip's frame at S R^-1 d (d the direction in the level, R the sky entity's turn,
S the x mirror: sky_strip.MIRRORED, gof3_look.sky_rotation), so it turns with the sky. Fog banks, atmospheres, borders, gates
and the station itself are left out.

Rendering: a point splat with a depth buffer, numpy only: each triangle is sampled by a fixed barycentric pattern dense
enough for its size on the face, each sample written to its pixel when nearer; at 2x the strip and filtered down.

paint(level, look, sky_rot, station_shape, nebula_png, stars_png, assets) -> number of entities painted (0: the images are
left as they were)."""
import math, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import ae4_scene, scene_glb, structures
import structure_materials as sm

NEAR = 4000.0            # GoF3 units: nearer than this the orbit itself would hold it (left out)
SKIP = re.compile(r"(?i)fog|atmo|border|jumpgate|skybox|/suns/|/planets/|beam|light|glow|halo|volumetric")
AMBIENT = 0.18
SS = 2                   # supersampling


def _R(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


def euler(rot):
    """GoF3's Transform rotation (degrees) as glm::quat builds it: Rz Ry Rx."""
    x, y, z = (list(rot or [0, 0, 0]) + [0, 0, 0])[:3]
    return _R("z", z) @ _R("y", y) @ _R("x", x)


def _entity_matrix(e):
    M = np.eye(4)
    M[:3, :3] = euler(e.get("rot")) * np.asarray(e.get("scale") or [1, 1, 1], np.float64)
    M[:3, 3] = e.get("pos") or [0, 0, 0]
    return M


def wanted(e, spos):
    """(painted?, camera-attached?) for a level entity."""
    sh = (e.get("shape") or "").replace("/assets/", "")
    if not sh or SKIP.search(sh) or SKIP.search(e.get("name") or ""): return False, False
    if not (sh.startswith("stations/") or sh.startswith("scenery/") or re.search(r"/(props|wrecks|armaments)/", sh)): return False, False
    p = np.asarray(e.get("pos") or [0, 0, 0], np.float64)
    attached = sh.startswith("scenery/") and np.linalg.norm(p) < 10.0   # a backdrop ring / comets on the camera
    if attached: return True, True
    return float(np.linalg.norm(p - spos)) > NEAR, False


_GEOM = {}


def _geometry(scene_path, assets):
    """[(positions (n, 3) in the scene, normals, colour (n, 3) 0..1, indices (m, 3))] of a scene's lod 0 parts."""
    if scene_path in _GEOM: return _GEOM[scene_path]
    out = []
    try: scene = ae4_scene.read(scene_path)
    except Exception: _GEOM[scene_path] = out; return out
    W = structures.world_matrices(scene)
    cache = {}
    for i, n in scene.items():
        mg = scene_glb.meshgroup(n["name"], assets)
        if mg is None: continue
        if mg not in cache:
            parts = []
            try:
                secs = scene_glb._sections(mg)
                mats = sm.section_materials(mg, assets)
            except Exception: secs, mats = [], []
            for s, m in zip(secs, mats):
                if m is not None and (m.effect or m.glass): continue
                P = np.asarray(s["a_position"], np.float32)
                N = np.asarray(s["a_normal"], np.float32) if "a_normal" in s else np.tile(np.array([[0, 1, 0]], np.float32), (len(P), 1))
                if m is not None and m.diffuse and "a_texCoord0" in s:
                    lv = sm.pyramid(m.diffuse)
                    C = sm.sample(lv, np.asarray(s["a_texCoord0"], np.float32) * m.tiling, min(len(lv) - 1, 4))[:, :3] * m.diffuse_color
                else:
                    C = np.tile(((m.diffuse_color * 0.5) if m is not None else np.array([0.35, 0.35, 0.35], np.float32))[None], (len(P), 1))
                parts.append((P, N, np.clip(C, 0, 1).astype(np.float32), np.asarray(s["indices"], np.int64).reshape(-1, 3)))
            cache[mg] = parts
        for P, N, C, I in cache[mg]:
            M = W[i]
            out.append(((P @ M[:3, :3].T + M[:3, 3]).astype(np.float32), (N @ M[:3, :3].T).astype(np.float32), C, I))
    _GEOM[scene_path] = out
    return out


def _face_uv(p):
    """GL / the strip's face (0..5: +X -X +Y -Y +Z -Z) and (u, v) 0..1 (v down) of directions p (n, 3)."""
    ax, ay, az = np.abs(p[:, 0]), np.abs(p[:, 1]), np.abs(p[:, 2])
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    f = np.where((ax >= ay) & (ax >= az), np.where(x > 0, 0, 1), np.where(ay >= az, np.where(y > 0, 2, 3), np.where(z > 0, 4, 5)))
    ma = np.choose(f // 2, [ax, ay, az])
    sc = np.choose(f, [-z, z, x, x, x, -x]); tc = np.choose(f, [-y, -y, z, -z, -y, -y])
    return f, (sc / ma + 1) / 2, (tc / ma + 1) / 2


PATTERNS = {}


def _pattern(k):
    """k x k barycentric samples over a triangle (k(k+1)/2 points)."""
    if k not in PATTERNS:
        pts = [((i + 1 / 3) / k, (j + 1 / 3) / k) for i in range(k) for j in range(k - i)]
        a = np.array(pts, np.float32)
        PATTERNS[k] = np.stack([1 - a[:, 0] - a[:, 1], a[:, 0], a[:, 1]], 1)
    return PATTERNS[k]


def paint(level, look, sky_rot, station_shape, nebula_png, stars_png, assets, face=None, log=print):
    ents = level["entities"]
    st = next((e for e in ents if station_shape and (e.get("shape") or "").endswith(station_shape)), None)
    spos = np.asarray((st or {}).get("pos") or [0, 0, 0], np.float64)
    neb = Image.open(nebula_png).convert("RGB")
    n = face or neb.size[1]
    N = n * SS
    Sx = np.diag([-1.0, 1.0, 1.0])
    to_strip = Sx @ euler(sky_rot).T                         # S R^-1
    light = np.asarray(look["light"]["pos"], np.float64) if look.get("light") else np.array([0, 1, 0], np.float64)
    light /= max(np.linalg.norm(light), 1e-9)
    lrgb = np.clip(np.asarray(look["light"]["rgb"], np.float32) / 2.0, 0, 1.5) if look.get("light") else np.ones(3, np.float32)
    fog = look.get("fog")
    depth = np.full(6 * N * N, np.inf, np.float32)
    color = np.zeros((6 * N * N, 3), np.float32)
    painted = 0
    for e in ents:
        ok, attached = wanted(e, spos)
        if not ok: continue
        path = f"{assets}{e['shape'][len('/assets'):]}"
        geo = _geometry(path, assets)
        if not geo: continue
        E = _entity_matrix(e)
        cam = np.zeros(3) if attached else spos
        painted += 1
        for P, Nn, C, I in geo:
            Pw = P.astype(np.float64) @ E[:3, :3].T + E[:3, 3] - cam      # from the camera, in the level
            Nw = Nn.astype(np.float64) @ E[:3, :3].T
            Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-9)
            dist = np.linalg.norm(Pw, axis=1)
            shade = (AMBIENT + np.maximum(0.0, Nw @ light)[:, None] * lrgb).astype(np.float32)
            col = np.clip(C * shade, 0, 1)
            if fog:
                frgb, dens, off = np.asarray(fog[0], np.float32), fog[1], fog[2]
                fz = np.clip((dist / 6000.0 - off) / (1.0 + off), 0, dens)[:, None].astype(np.float32)
                col = col * (1 - fz) + frgb * fz
            D = Pw @ to_strip.T
            tri = I[(dist[I] > 1e-3).all(1)]
            if not len(tri): continue
            # samples per triangle edge by its size on the face (angular size x pixels per radian)
            A, B, Cc = D[tri[:, 0]], D[tri[:, 1]], D[tri[:, 2]]
            r = np.minimum(np.minimum(dist[tri[:, 0]], dist[tri[:, 1]]), dist[tri[:, 2]])
            edge = np.maximum(np.maximum(np.linalg.norm(A - B, axis=1), np.linalg.norm(B - Cc, axis=1)), np.linalg.norm(Cc - A, axis=1))
            px = edge / np.maximum(r, 1e-6) * (N / 2) * 1.5
            ks = np.clip(np.ceil(px), 1, 64).astype(int)
            for k in np.unique(ks):
                sel = tri[ks == k]
                w = _pattern(int(k))                               # (s, 3)
                Pp = np.einsum("sj,tjc->tsc", w, D[sel]).reshape(-1, 3)
                Cp = np.einsum("sj,tjc->tsc", w, col[sel]).reshape(-1, 3)
                dp = np.linalg.norm(Pp, axis=1).astype(np.float32)
                f, u, v = _face_uv(Pp)
                ix = np.clip((u * N).astype(int), 0, N - 1); iy = np.clip((v * N).astype(int), 0, N - 1)
                idx = f * N * N + iy * N + ix
                order = np.lexsort((dp, idx))                       # per pixel the nearest first
                idx, dp, Cp = idx[order], dp[order], Cp[order]
                first = np.ones(len(idx), bool); first[1:] = idx[1:] != idx[:-1]
                idx, dp, Cp = idx[first], dp[first], Cp[first]
                nearer = dp < depth[idx]
                depth[idx[nearer]] = dp[nearer]; color[idx[nearer]] = Cp[nearer]
    if not painted or not np.isfinite(depth).any():
        return 0
    cov = np.isfinite(depth).astype(np.float32).reshape(6, N, N)
    rgb = color.reshape(6, N, N, 3)
    # down to the strip's size (SS x SS boxes): coverage as alpha, the colour averaged over the covered samples
    def down(a): return a.reshape(6, n, SS, n, SS, *a.shape[3:]).mean((2, 4))
    alpha = down(cov)
    col = down(rgb * cov[..., None]) / np.maximum(alpha[..., None], 1e-6)
    strip_a = np.concatenate(list(alpha), 1)[..., None]
    strip_c = np.concatenate(list(col), 1)
    base = np.asarray(neb.resize((6 * n, n)) if neb.size != (6 * n, n) else neb).astype(np.float32) / 255
    out = base * (1 - strip_a) + strip_c * strip_a
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).resize(neb.size).save(nebula_png)
    if stars_png and os.path.exists(stars_png):
        stars = Image.open(stars_png).convert("RGB")
        a = Image.fromarray((strip_a[..., 0] * 255).astype(np.uint8)).resize(stars.size, Image.BILINEAR)
        s = np.asarray(stars).astype(np.float32) * (1 - np.asarray(a).astype(np.float32)[..., None] / 255)
        Image.fromarray(s.astype(np.uint8)).save(stars_png)   # no stars in front of what is painted
    return painted
