"""Bring a built GoF3 Systems mod up to the builder's 2026-11-22 changes without building it all again:
GoF3's map the right way up (build_gof3_systems.map_pos), Mkkt Bkkt's club (its sector built alone with --only and
merged in), GoF3's own routes for the gates (build_gof3_systems.make_gates) and GoF3's star map scenes (gof3_map_scene).

python patch_gof3_systems.py --pdb <data.pdb> --assets <assets> --mod <Mods/gof3_systems> [--version 1.1.0]"""
import argparse, json, os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import build_gof3_systems as b
import gof3_galaxy, gof3_map_scene

CLUB = "MKKT_BKKT_000"


def _dump(obj, path, **kw):
    """json to path through a new file (os.replace): a hardlinked copy of a build keeps its original's file."""
    with open(path + ".new", "w", encoding="utf-8") as f: json.dump(obj, f, **kw)
    os.replace(path + ".new", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdb", required=True); ap.add_argument("--assets", required=True); ap.add_argument("--mod", required=True)
    ap.add_argument("--version", default=None)
    a = ap.parse_args()
    out = a.mod.rstrip("/")
    sysj = json.load(open(f"{out}/systems.json", encoding="utf-8"))
    stj = json.load(open(f"{out}/stations.json", encoding="utf-8"))
    sectors = [s for s in gof3_galaxy.sectors(a.pdb) if s["star"] in gof3_galaxy.STAR_NODES and s["name"]]
    star_of = {"gof3_" + b.slug(s["name"]): s["star"] for s in sectors}
    club = next(s for s in sectors if s["record"] == CLUB)
    club_id = "gof3_" + b.slug(club["name"])
    # Mkkt Bkkt's club, built alone and merged in
    if not any(e["id"] == club_id for e in sysj):
        tmp = tempfile.mkdtemp(prefix="gof3_club_", dir=os.path.dirname(out))
        try:
            subprocess.run([sys.executable, "-u", os.path.join(os.path.dirname(__file__), "build_gof3_systems.py"), "--pdb", a.pdb,
                            "--assets", a.assets, "--out", tmp, "--only", "mkkt_bkkt"], check=True)
            new_sys = json.load(open(f"{tmp}/systems.json", encoding="utf-8"))
            new_st = json.load(open(f"{tmp}/stations.json", encoding="utf-8"))
            for e in new_sys:
                e.pop("mapScene", None)
                e["gates"] = []
                sysj.append(e)
            for st in new_st:
                st.pop("mapArea", None)
                stj.append(st)
            for root, _, files in os.walk(tmp):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), tmp)
                    if rel.endswith(".json") or rel.startswith(".") or os.path.exists(os.path.join(out, rel)): continue
                    if rel.startswith("music" + os.sep): continue   # (the cluster music gof3_world writes; a build without it keeps none)
                    os.makedirs(os.path.dirname(os.path.join(out, rel)), exist_ok=True)
                    shutil.copyfile(os.path.join(root, f), os.path.join(out, rel))
                    print("  +", rel)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    # GoF3's map the right way up
    for e in sysj:
        if e["id"] in star_of: e["position"] = b.map_pos(star_of[e["id"]])
    # the gates: GoF3's own routes, bridged (build_gof3_systems.make_gates); a gate to a system of another mod is kept
    rec_of = {"gof3_" + b.slug(s["name"]): s for s in sectors}
    others = {e["id"]: [g for g in e.get("gates", []) if not str(g).startswith(b.MOD_ID + ":") and g != b.MEENKK] for e in sysj}
    b.make_gates([(rec_of[e["id"]], e) for e in sysj if e["id"] in rec_of], gof3_galaxy.map_lines(a.pdb))
    for e in sysj: e["gates"] = e.get("gates", []) + [g for g in others.get(e["id"], []) if g not in e.get("gates", [])]
    _dump(sysj, f"{out}/systems.json", indent=1, ensure_ascii=False)
    _dump(stj, f"{out}/stations.json", indent=1, ensure_ascii=False)
    # GoF3's star map scenes
    gof3_map_scene.apply(out, a.pdb, a.assets)
    if a.version:
        man = json.load(open(f"{out}/mod.json", encoding="utf-8")); man["version"] = a.version
        _dump(man, f"{out}/mod.json", indent=1)
    print(f"patched {out}: {len(sysj)} systems, {len(stj)} stations")


if __name__ == "__main__":
    main()
