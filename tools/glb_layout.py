"""Read a converted ship .glb's layout without Blender: every node's world matrix, the mesh bounds (accessor min / max of
POSITION through the node transforms) and the named helper points (glTF space: Y up, nose -Z, 1 unit = 1 GoF3 unit).
layout(path) -> {"min": [x, y, z], "max": [...], "points": {node name: [x, y, z]}, "scales": {node name: s}}"""
import json, struct
import numpy as np


def read(path):
    b = open(path, "rb").read()
    n = struct.unpack_from("<I", b, 12)[0]
    return json.loads(b[20:20 + n]), b, n


def trs(nd):
    if "matrix" in nd: return np.array(nd["matrix"], dtype=float).reshape(4, 4).T
    t = nd.get("translation", [0, 0, 0]); r = nd.get("rotation", [0, 0, 0, 1]); s = nd.get("scale", [1, 1, 1])
    x, y, z, w = r
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4); M[:3, :3] = R * np.array(s); M[:3, 3] = t
    return M


def layout(path, skip=lambda name: False):
    j, _, _ = read(path)
    nodes = j["nodes"]; world = {}
    def walk(i, P):
        W = P @ trs(nodes[i]); world[i] = W
        for c in nodes[i].get("children", []): walk(c, W)
    for root in j["scenes"][j.get("scene", 0)]["nodes"]: walk(root, np.eye(4))
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for i, nd in enumerate(nodes):
        if "mesh" not in nd or skip(nd["name"]): continue
        for prim in j["meshes"][nd["mesh"]]["primitives"]:
            acc = j["accessors"][prim["attributes"]["POSITION"]]
            a, z = np.array(acc["min"]), np.array(acc["max"])
            for k in range(8):
                c = np.array([z[0] if k & 1 else a[0], z[1] if k & 2 else a[1], z[2] if k & 4 else a[2], 1.0])
                p = (world[i] @ c)[:3]; lo = np.minimum(lo, p); hi = np.maximum(hi, p)
    pts = {nd["name"]: [float(v) for v in world[i][:3, 3]] for i, nd in enumerate(nodes) if i in world}
    scl = {nd["name"]: float(np.cbrt(abs(np.linalg.det(world[i][:3, :3])))) for i, nd in enumerate(nodes) if i in world}
    return {"min": lo.tolist(), "max": hi.tolist(), "points": pts, "scales": scl}
