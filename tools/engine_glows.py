"""Measure each engine of a converted ship .glb from what the model shows there: the hull's emissive texture around every
_engine_NNN helper. engines(path) -> [{"node", "pos" (glTF: the nozzle's exit, see below), "node_pos", "color" [r, g, b] (max channel 1) or None, "size" [w, h]
(half extents across the thrust axis, GoF3 units) or None, "lit" (how much of the nozzle glows)}].

For each helper the hull's triangles within a search radius (by the ship's length) are sampled (centroid + 3 points each);
the emissive texel at each sample, weighted by its brightness, gives the colour; the samples brighter than 35 % of the
brightest give the nozzle's extent (x / y, the engines point along -Z: the plume goes +Z in glTF space). A helper with
no lit samples (a nozzle the texture doesn't light) gets None: the caller falls back to the GoF3 engine effect's colour."""
import io, re
import numpy as np
from PIL import Image
from glb_layout import read, trs


def _accessor(j, b, n, idx):
    acc = j["accessors"][idx]; bv = j["bufferViews"][acc["bufferView"]]
    comp = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[acc["componentType"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    start = 28 + n + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", 0) or np.dtype(comp).itemsize * ncomp
    raw = np.frombuffer(b, dtype=np.uint8, count=stride * (acc["count"] - 1) + np.dtype(comp).itemsize * ncomp, offset=start)
    out = np.lib.stride_tricks.as_strided(raw.view(np.uint8), shape=(acc["count"], np.dtype(comp).itemsize * ncomp),
                                          strides=(stride, 1)).copy().view(comp)
    return out.reshape(acc["count"], ncomp) if ncomp > 1 else out.reshape(-1)


def _image(j, b, n, tex_index, cache):
    src = j["textures"][tex_index]["source"]
    if src not in cache:
        bv = j["bufferViews"][j["images"][src]["bufferView"]]; o = 28 + n + bv.get("byteOffset", 0)
        cache[src] = np.asarray(Image.open(io.BytesIO(b[o:o + bv["byteLength"]])).convert("RGB"), dtype=np.float32) / 255.0
    return cache[src]


def rim_colour(C, L):
    """The nozzle's colour: hue from the coloured texels (weighted by brightness x saturation, so the white-hot core
    doesn't wash it out), saturation the 75th percentile of the bright texels', value 1."""
    import colorsys
    hsv = np.array([colorsys.rgb_to_hsv(*np.clip(c, 0, 1)) for c in C])
    w = L * hsv[:, 1] + 1e-6
    ang = hsv[:, 0] * 2 * np.pi
    h = (np.arctan2((np.sin(ang) * w).sum(), (np.cos(ang) * w).sum()) / (2 * np.pi)) % 1.0
    sat = float(np.percentile(hsv[:, 1], 75))
    return [round(float(v), 3) for v in colorsys.hsv_to_rgb(float(h), sat, 1.0)]


def convex_hull(pts):
    """Andrew's monotone chain (2D), counter-clockwise."""
    p = sorted(set(map(tuple, np.round(np.asarray(pts, dtype=float), 4))))
    if len(p) < 3: return p
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for q in p:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0: lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], q) <= 0: hi.pop()
        hi.append(q)
    return lo[:-1] + hi[:-1]


def engines(path, radius_frac=0.09, emissive=None):
    """emissive: a PNG path standing in for the body material's emissive texture (a paint scheme's)."""
    j, b, n = read(path)
    nodes = j["nodes"]; world = {}
    def walk(i, P):
        W = P @ trs(nodes[i]); world[i] = W
        for c in nodes[i].get("children", []): walk(c, W)
    for root in j["scenes"][j.get("scene", 0)]["nodes"]: walk(root, np.eye(4))
    cache = {}
    pts, cols, lums, hull_pts = [], [], [], []
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for i, nd in enumerate(nodes):
        if "mesh" not in nd or i not in world: continue
        name = nd["name"]
        hull = name.endswith("_LOD0") and "_gun_" not in name
        for prim in j["meshes"][nd["mesh"]]["primitives"]:
            P = _accessor(j, b, n, prim["attributes"]["POSITION"]).astype(np.float64)
            P = (np.c_[P, np.ones(len(P))] @ world[i].T)[:, :3]
            lo = np.minimum(lo, P.min(0)); hi = np.maximum(hi, P.max(0))
            if hull: hull_pts.append(P)
            if not hull or "TEXCOORD_0" not in prim["attributes"]: continue
            mat = j["materials"][prim.get("material", 0)]
            if "emissiveTexture" not in mat: continue
            if emissive and mat.get("name", "").endswith("_body"):
                if emissive not in cache:
                    cache[emissive] = np.asarray(Image.open(emissive).convert("RGB"), dtype=np.float32) / 255.0
                img = cache[emissive]
            else:
                img = _image(j, b, n, mat["emissiveTexture"]["index"], cache)
            ef = np.array(mat.get("emissiveFactor", [1, 1, 1]), dtype=np.float32)
            UV = _accessor(j, b, n, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
            I = _accessor(j, b, n, prim["indices"]).reshape(-1, 3) if "indices" in prim else np.arange(len(P)).reshape(-1, 3)
            for wts in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6)):
                w = np.array(wts)
                sp = P[I[:, 0]] * w[0] + P[I[:, 1]] * w[1] + P[I[:, 2]] * w[2]
                su = UV[I[:, 0]] * w[0] + UV[I[:, 1]] * w[1] + UV[I[:, 2]] * w[2]
                h, wd = img.shape[:2]
                x = np.clip((su[:, 0] % 1.0) * (wd - 1), 0, wd - 1).astype(int); y = np.clip((su[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(int)
                c = img[y, x] * ef
                pts.append(sp); cols.append(c); lums.append(c.max(1))
    pts = np.concatenate(pts) if pts else np.zeros((0, 3)); cols = np.concatenate(cols) if cols else np.zeros((0, 3))
    lums = np.concatenate(lums) if lums else np.zeros(0)
    hull_pts = np.concatenate(hull_pts) if hull_pts else np.zeros((0, 3))
    length = hi[2] - lo[2]; R = max(0.6, radius_frac * length)
    out = []
    for i, nd in enumerate(nodes):
        if i not in world or not re.search(r"_engine_\d{3}$", nd["name"]): continue
        node = world[i][:3, 3]
        # the nozzle's exit: GoF3 starts its plume at the helper, often inside the hull (Khador's 5 units deep); the glow
        # goes where the hull ends behind it (+z = backwards), within 0.8 units of the thrust axis
        p = node.copy()
        if len(hull_pts):
            axis = np.linalg.norm(hull_pts[:, :2] - node[:2], axis=1) < 0.8
            behind = hull_pts[axis & (hull_pts[:, 2] > node[2])]
            if len(behind): p[2] = behind[:, 2].max() + 0.05
        # measured at the helper (whose nozzle the texture lights around it), at the exit when the helper is buried
        c = p if p[2] - node[2] > 0.5 else node
        d = np.linalg.norm(pts - c, axis=1)
        near = d < R
        e = {"node": nd["name"], "pos": p.tolist(), "node_pos": node.tolist(), "color": None, "size": None, "lit": 0.0,
             "scale": float(np.cbrt(abs(np.linalg.det(world[i][:3, :3]))))}
        if near.sum() >= 4 and lums[near].max() > 0.15:
            L = lums[near]; C = cols[near]; Q = pts[near]
            bright = L > 0.35 * L.max()
            e["color"] = rim_colour(C[bright], L[bright])
            # the nozzle: the hottest samples (60 % of the brightest) nearest the helper, their 80th-percentile spread
            # across the thrust axis (the extreme extent took in the lit trim around the nozzles)
            hot = L > 0.6 * L.max()
            q = Q[hot]; dq = np.linalg.norm(q - c, axis=1)
            core = q[dq <= max(np.percentile(dq, 50), 0.15)]
            half = np.maximum(np.percentile(np.abs(core[:, :2] - c[:2]), 80, axis=0), 0.1)
            e["size"] = half.round(3).tolist()
            # its outline across the thrust axis: the convex hull of those samples (the outer tenth dropped as trim),
            # around the measuring point (glTF units); the remake's exhaust styles take its shape
            off = core[:, :2] - c[:2]
            if len(off) >= 8: off = off[np.linalg.norm(off, axis=1) <= np.percentile(np.linalg.norm(off, axis=1), 90)]
            hull = convex_hull(off)
            if len(hull) >= 3: e["outline"] = [[round(float(x), 3), round(float(y), 3)] for x, y in hull]
            e["lit"] = round(float(bright.sum()) / float(near.sum()), 3)
        out.append(e)
    # mirrored engines (x -> -x, the same y / z) share one size: the texture's sampling differs between the two sides
    for a in out:
        for b in out:
            if a is b or not a["size"] or not b["size"]: continue
            pa, pb = a["pos"], b["pos"]
            if abs(pa[0] + pb[0]) < 0.15 and abs(pa[1] - pb[1]) < 0.15 and abs(pa[2] - pb[2]) < 0.15 and abs(pa[0]) > 0.15:
                m = [round((u + v) / 2, 3) for u, v in zip(a["size"], b["size"])]
                a["size"] = m; b["size"] = list(m)
    for e in out:   # at most 2.5 : 1 (a lit strip beside a round nozzle flattened it)
        if e["size"]:
            w, h = e["size"]
            if w > 2.5 * h: h = round(w / 2.5, 3)
            if h > 2.5 * w: w = round(h / 2.5, 3)
            e["size"] = [w, h]
    return out


if __name__ == "__main__":
    import sys, json
    for e in engines(sys.argv[1]): print(json.dumps(e))
