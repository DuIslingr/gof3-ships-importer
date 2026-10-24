"""A nozzle's cross-section from a hull mesh (glTF space: Y up, the engines blowing toward +z): slices across the nozzle at
depths from its engine helper aft, in each slice rays from the helper's axis every 360 / STEPS degrees to the first wall they
meet (skipping a centre plug: hits closer than PLUG x the expected radius); the aftmost slice whose rays nearly all hit (the
nozzle's exit) is its outline. measure(P, I, helpers) -> one outline per helper: [(dx, dy)] around the helper's axis, glTF
units, or None."""
import numpy as np

STEPS = 32
PLUG = 0.3        # hits nearer the axis than this x the expected radius are a centre plug, not the wall
REACH = 3.0       # rays reach this x the expected radius
DEPTHS = 17       # slices from the helper to DEPTH x the expected radius aft
DEPTH = 2.5
MIN_HITS = 28


def _slice(tri, z0, normals):
    """The segments where the triangles cross the plane z = z0: (n, 2, 2) xy, and their triangles' normals' xy (n, 2)."""
    d = tri[:, :, 2] - z0
    s = np.sign(d)
    cross = (s.min(1) < 0) & (s.max(1) > 0)
    t = tri[cross]; dd = d[cross]; nrm = normals[cross][:, :2]
    segs = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        m = dd[:, a] * dd[:, b] < 0
        f = dd[:, a] / np.where(m, dd[:, a] - dd[:, b], 1)
        pts = t[:, a, :2] + (t[:, b, :2] - t[:, a, :2]) * f[:, None]
        segs.append((m, pts))
    out, nout = [], []
    for i in range(len(t)):
        p = [pts[i] for m, pts in segs if m[i]]
        if len(p) == 2: out.append(p); nout.append(nrm[i])
    return np.asarray(out).reshape(-1, 2, 2), np.asarray(nout).reshape(-1, 2)


def _rays(sliced, c, rmin, rmax, facing):
    """The first wall each ray from c meets between rmin and rmax (nan: none): only a wall facing back toward the axis (its
    normal against the ray, x 'facing' for a mesh wound the other way), so a divider's or a plug's far side doesn't count."""
    segs, nrm = sliced
    ang = np.arange(STEPS) * 2 * np.pi / STEPS
    dirs = np.stack([np.cos(ang), np.sin(ang)], 1)
    if len(segs) == 0: return np.full(STEPS, np.nan)
    a = segs[:, 0] - c; e = segs[:, 1] - segs[:, 0]
    out = np.full(STEPS, np.nan)
    for k, dv in enumerate(dirs):
        den = dv[0] * e[:, 1] - dv[1] * e[:, 0]
        ok = np.abs(den) > 1e-12
        t = np.where(ok, (a[:, 0] * e[:, 1] - a[:, 1] * e[:, 0]) / np.where(ok, den, 1), np.nan)   # along the ray
        u = np.where(ok, (a[:, 0] * dv[1] - a[:, 1] * dv[0]) / np.where(ok, den, 1), np.nan)       # along the segment
        hit = ok & (u >= 0) & (u <= 1) & (t >= rmin) & (t <= rmax) & ((facing == 0) | (facing * (nrm @ dv) < 0))
        if hit.any(): out[k] = t[hit].min()
    return out


def _hull(pts):
    """The convex hull of 2D points (counter-clockwise; the outline the remake keeps: a chord across the nozzle drops out)."""
    pts = sorted(set(map(tuple, np.round(pts, 6))))
    if len(pts) < 3: return pts
    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0: h.pop()
            h.append(p)
        return h[:-1]
    return half(pts) + half(pts[::-1])


def measure(P, I, helpers, radius_of):
    """helpers: [(pos, scale)]; radius_of(scale) the expected nozzle radius (glTF units)."""
    tri = P[I]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normals /= np.maximum(1e-12, np.linalg.norm(normals, axis=1))[:, None]
    lo, hi = tri.min(1), tri.max(1)
    out = []
    ang = np.arange(STEPS) * 2 * np.pi / STEPS
    for pos, scale in helpers:
        r = radius_of(scale); c = np.asarray(pos[:2], float)
        near = (hi[:, 0] >= c[0] - 2 * REACH * r) & (lo[:, 0] <= c[0] + 2 * REACH * r) & (hi[:, 1] >= c[1] - 2 * REACH * r) & (lo[:, 1] <= c[1] + 2 * REACH * r) \
               & (hi[:, 2] >= pos[2] - 1.1 * r) & (lo[:, 2] <= pos[2] + DEPTH * r)
        t = tri[near]; tn = normals[near]
        # Three readings (walls facing the axis, the same for a mesh wound the other way, any wall: a facing filter on a
        # mesh wound the other way lets the rays out through the nozzle to the hull beyond, while any wall takes a divider
        # across it, which the hull drops); the one nearest the expected size wins (GoF3 sizes its effect to the nozzle).
        # Each: a closed slice within REACH, else (the Vossk pods: wide and open on a side) within twice that, a few rays missing.
        found = []
        for facing in (1, -1, 0):
            best = None
            for reach, hits in ((REACH, MIN_HITS), (2 * REACH, MIN_HITS - 6)):
                for z0 in np.linspace(pos[2] - r, pos[2] + DEPTH * r, DEPTHS + 7):
                    d = _rays(_slice(t, z0, tn), c, PLUG * r, reach * r, facing)
                    if np.isfinite(d).sum() >= hits: best = d          # (the aftmost closed slice)
                if best is not None: break
            if best is None: continue
            good = np.isfinite(best)
            best = np.interp(ang, ang[good], best[good], period=2 * np.pi)
            hull = _hull([(np.cos(a) * d, np.sin(a) * d) for a, d in zip(ang, best)])
            if len(hull) < 3: continue
            mean = float(np.mean([np.hypot(x, y) for x, y in hull]))
            found.append((abs(np.log(mean / r)), hull))
        if not found: out.append(None); continue
        out.append([(float(x), float(y)) for x, y in min(found, key=lambda f: f[0])[1]])
    return out


def read_glb(path):
    """The first mesh primitive of a .glb (structures.write_glb's): positions (n, 3), triangles (m, 3)."""
    import json, struct
    b = open(path, "rb").read(); jl = struct.unpack_from("<I", b, 12)[0]; j = json.loads(b[20:20 + jl]); o = 20 + jl + 8
    pr = j["meshes"][0]["primitives"][0]
    a = j["accessors"][pr["attributes"]["POSITION"]]; v = j["bufferViews"][a["bufferView"]]
    P = np.frombuffer(b, np.float32, a["count"] * 3, o + v.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(-1, 3)
    ia = j["accessors"][pr["indices"]]; iv = j["bufferViews"][ia["bufferView"]]
    I = np.frombuffer(b, {5125: np.uint32, 5123: np.uint16}[ia["componentType"]], ia["count"],
                      o + iv.get("byteOffset", 0) + ia.get("byteOffset", 0)).reshape(-1, 3)
    return P, I
