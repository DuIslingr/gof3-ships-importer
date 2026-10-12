"""Every converted ship with its default weapon loadout, as glTF binary: <out>/<ship folder>.glb (+ manifest.json, README.txt).
python build_loadouts.py [converted dir, default ../gof3converted] [out, default ../gof3converted_loadouts] [jobs, default 6]
Needs data_arming.json (ae4_pdb_arming.py) and Blender on PATH; each ship goes through ae4_loadout_gltf.py.

The record per folder: a skin folder its data_skins record (resolve.json), else RECORDS below; a base folder its plain
player record Ship_<class>_NN_id<NNN>_<name>_0_T0, else RECORDS. The guns are that record's default primaries
(data_arming.json "loadout"); a ship with none (the boss / story hulls arm only a rocket launcher, the hulls without a
record) is written as it is, its mounts empty, and listed so in the manifest."""
import glob, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = os.environ.get("GOF3_BLENDER") or "blender"   # import.py sets it (Blender found by itself on any system)
CONV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "gof3converted"))
OUT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "gof3converted_loadouts"))
JOBS = int(sys.argv[3]) if len(sys.argv) > 3 else 6

# folders the rules above don't resolve (from their READMEs; None = no ship record in data.pdb; a list: the first name the
# game version's data.pdb has)
RECORDS = {
    "ship_inouac_600": "Ship_Scout_XX_id600_Nunam",
    "ship_inouac_601": "Ship_Fighter_XX_id601_Kinac",
    "ship_retro_000": ["Ship_Fighter_16_Retro_000", "Ship_Fighter_16_Retro_0_T0"],   # (Switch 1.0.x / Android 2.1.3)
    "ship_vossk_122": "Ship_Gunship_05_id122_Shamash_II_T0",
    "ship_vossk_122_shamash2": "Ship_Gunship_05_id122_Shamash_II_T0",
    "ship_nivelian_201_blackred": "Ship_Fighter_04_id201_AtaunoRheep_2_T0",
    "ship_nivelian_201_grgath": "Ship_Fighter_04_id201_AtaunoRheep_1_T0",
    "ship_nivelian_208_mkktbkkt": "Ship_Scout_01_id208_Sutoe-Shii_0_T0",       # a material skin, no record of its own
    "ship_nivelian_208_sutoeshii": "Ship_Scout_01_id208_Sutoe-Shii_0_T0_Event",
    "ship_nivelian_222_khador_e2017s03": "Ship_Gunship_02_id222_Khador_E2017S03",
    "ship_terran_008_goldgorgon": "Ship_Fighter_14_id008_Gorgon_?_T0",         # the record that isn't a tier or Gold
    "ship_terran_020_dragon": "Ship_Gunship_12_id020_DragonShip_0_T0",
    "ship_terran_021": "Ship_A02_HB08_Snotch",                                # Jaden Thee's record arms no primary
    "ship_nivelian_220": "Ship_A02_BB01_Khador",
    "ship_nivelian_221": "Ship_A01_FM02_Rh'ash",
    "ship_vossk_120": "Ship_A01_BB01_Sh'gaal",
    "ship_vossk_121": "Ship_A01_UB02_Bl'Arek",
    "ship_nivelian_230": None, "ship_terran_007": None, "ship_terran_030": None, "ship_starfox_000": None,
    "ship_vossk_130": None,
}


def pick(folder, ships, skins):
    if folder in skins: return skins[folder]
    if folder in RECORDS:
        r = RECORDS[folder]
        return next((x for x in r if x in ships), r[0]) if isinstance(r, list) else r
    scene = f"/{folder}.ae4scene"
    plain = sorted(k for k, s in ships.items() if s["scene"] and s["scene"].endswith(scene)
                   and re.match(r"^Ship_[A-Za-z]+_\d+_id\d+_.+_0_T0$", k))
    return plain[0] if plain else None


def main():
    # data_arming.json (ae4_pdb_arming.py --write): import.py writes it into its work folder (GOF3_DATA_DIR)
    data = json.load(open(os.path.join(os.environ.get("GOF3_DATA_DIR") or HERE, "data_arming.json"), encoding='utf-8-sig'))
    ships, weapons = data["ships"], data["weapons"]
    skins = {}
    for p in glob.glob(os.path.join(CONV, "ship_*", "resolve.json")):
        r = json.load(open(p, encoding='utf-8-sig'))
        for sk in r.get("data_skins", []):
            if sk.get("record"): skins[f"{r['name']}_{sk['scheme']}"] = sk["record"]
    os.makedirs(OUT, exist_ok=True)
    jobs, manifest = [], {}
    for d in sorted(glob.glob(os.path.join(CONV, "ship_*"))):
        folder = os.path.basename(d); blend = os.path.join(d, folder + ".blend")
        if not os.path.exists(blend): print("no .blend:", folder); continue
        rec = pick(folder, ships, skins)
        s = ships.get(rec) if rec else None
        spec = s["loadout"] if s else ""
        manifest[folder] = {"record": rec, "loadout": spec,
                            "hardpoints": {k: {"group": h["group"], "weapon": h["weapon"],
                                               "kind": weapons.get(h["weapon"] or "", {}).get("kind"),
                                               "model": h["family_mk"]}
                                           for k, h in (s["hardpoints"].items() if s else [])
                                           if h["group"] != "unused"}}
        if not spec:
            manifest[folder]["note"] = "no ship record" if not s else "the record arms no primary weapon: no guns"
        jobs.append((folder, blend, spec))

    def run(job):
        folder, blend, spec = job
        out = os.path.join(OUT, folder + ".glb")
        r = subprocess.run([BLENDER, "-b", "-P", os.path.join(HERE, "ae4_loadout_gltf.py"), "--", blend,
                            os.path.join(CONV, "weapons"), out] + ([spec] if spec else []), capture_output=True, text=True)
        ok = r.returncode == 0 and os.path.exists(out)
        if not ok: open(os.path.join(OUT, folder + ".error.log"), "w", encoding='utf-8').write(r.stdout + r.stderr)
        print(("ok  " if ok else "FAIL"), folder, spec or "(no guns)", flush=True)
        return folder, ok

    with ThreadPoolExecutor(JOBS) as ex:
        for folder, ok in ex.map(run, jobs):
            if not ok: manifest[folder]["error"] = f"{folder}.error.log"
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f"{sum(1 for m in manifest.values() if 'error' not in m)} / {len(manifest)} written to {OUT}")


if __name__ == "__main__":
    main()
