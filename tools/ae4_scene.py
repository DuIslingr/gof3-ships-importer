"""Read a GoF3 .ae4scene (CS4A): node records [parent i64][id u64][id u32][pos 3f][scale 3f][quat xyzw 4f]
and the name table [id u32][hash u32][len u32][name]. Returns {id: dict(name, parent, pos, scale, rot)}."""
import struct, sys, os, re, zlib
sys.path.insert(0, os.path.dirname(__file__))
from ae4unpack import unpack

def read(path):
    d = unpack(open(path, "rb").read()) if not path.endswith(".bin") else open(path, "rb").read()
    names = {}
    # name table: [id u32][crc32(name) u32][len u32][name]; take every entry whose crc matches
    for m in re.finditer(rb"[a-z][a-z0-9_]{2,}", d):
        o = m.start() - 12
        if o < 0:
            continue
        nid, crc, ln = struct.unpack_from("<III", d, o)
        n = d[m.start():m.start() + ln]
        if 0 < ln < 256 and zlib.crc32(n) == crc:
            names[nid] = n.decode()
    # node records: 60 bytes each, back to back, not aligned (vossk/130 starts at 0xb2). Collect every offset that
    # decodes as a plausible record, then keep the longest run spaced exactly 60 bytes apart (drops false matches).
    def rec(o):
        parent, nid, nid2 = struct.unpack_from("<qQI", d, o)
        if not (nid == nid2 and nid < 4096 and parent != nid):
            return None
        if not -1 <= parent < 4096:
            parent = -1                       # the first record's parent field overlaps the header: a root
        f = struct.unpack_from("<10f", d, o + 20)
        sc, q = f[3:6], f[6:10]
        if all(0.001 < abs(v) < 1000 for v in sc) and abs(sum(c * c for c in q) - 1) < 1e-3 and all(abs(v) < 1e6 for v in f[:3]):
            return dict(id=nid, name=names.get(nid, f"node_{nid}"), parent=parent, pos=f[0:3], scale=sc, rot=q)
        return None
    cands = {o: r for o in range(0, len(d) - 59) if (r := rec(o))}
    best, start = [], 0
    for o in cands:
        if o - 60 in cands: continue          # not the start of a run
        run, o0 = [], o
        while o in cands: run.append(cands[o]); o += 60
        if len(run) > len(best): best, start = run, o0
    # A node's parent is the i64 at the start of the NEXT record (the record is [id u64][id u32][10f][parent i64] read
    # from its second field on): taken from the record's own leading field, every parent was the node before's, the
    # first one lost (a root) and the Hades' hull 86 units off its own engine helpers.
    ids = {r["id"] for r in best}
    for k, r in enumerate(best):
        o = start + 60 * (k + 1)
        p = struct.unpack_from("<q", d, o)[0] if o + 8 <= len(d) else -1
        r["parent"] = p if p in ids and p != r["id"] else -1
    nodes = {r.pop("id"): r for r in best}
    return nodes

if __name__ == "__main__":
    nodes = read(sys.argv[1])
    def show(pid, depth):
        for i, n in sorted(nodes.items()):
            if n["parent"] == pid:
                print("  " * depth + f"{i:3d} {n['name']}  pos={tuple(round(v,3) for v in n['pos'])} rot={tuple(round(v,3) for v in n['rot'])} scale={tuple(round(v,3) for v in n['scale'])}")
                show(i, depth + 1)
    show(-1, 0)
    for i, n in sorted(nodes.items()):   # parent not in the file
        if n["parent"] != -1 and n["parent"] not in nodes: print(f"{i:3d} {n['name']} (parent {n['parent']} missing)"); show(i, 1)
    print(len(nodes), "nodes")
