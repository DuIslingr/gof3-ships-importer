"""GoF3's loot containers as the GoF3 ships' own crates (the remake's ships.json "crate", Modding.ModCrates).

What a destroyed GoF3 enemy leaves is a LootPickup (data.pdb: ConfigGame's lootDrops, AmmoDrop / HullDrop, all with the
LootPickup prefab; RewardExtension::spawnLootEntity), drawn with collectables/geometry/002/mining/collectables_002_mining:
a 27-unit container of the mining race's platings, its lit strips the unlit orange collectables_emissive. The same box
comes in the Terran, Vossk and Nivelian races' platings (collectables_002_<race>; data.pdb uses the Vossk one for two
event collectables), so a GoF3 ship's crate is its race's (GoF2's: Terran, Vossk, Nivelian), the pirates' and the rest's
the mining one GoF3 drops for every enemy. (CrateTerran / CrateNivelian / CrateMining, collectables/crates/*, are the
gacha screen's opening animation, GUI::GachaMediator::startCrateAnimation, not loot.) Each is baked like a structure
(structures.convert: its race's default light map, UV1) into crates/<name>.glb; the remake fits it to its race's GoF2
container (no crateSize: GoF3's box is bigger than a fighter).

build(out_dir, assets) -> {GoF2 race: "crates/<name>.glb"}; crate_for(race) -> the path for a ships.json entry."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import structures

LOOKS = ("terran", "vossk", "nivelian", "mining")
BY_RACE = {0: "terran", 1: "vossk", 2: "nivelian"}   # GoF2 race -> GoF3 look; others "mining" (GoF3's LootPickup)


def crate_for(race):
    return f"crates/{BY_RACE.get(race, 'mining')}.glb"


def build(out_dir, assets, log=print):
    os.makedirs(os.path.join(out_dir, "crates"), exist_ok=True)
    for look in LOOKS:
        d = f"{assets}/collectables/geometry/002/{look}"
        info = structures.convert(d, f"collectables_002_{look}", look, os.path.join(out_dir, f"crates/{look}.glb"), 512, assets,
                                  body=f"collectables_002_{look}_body")
        log(f"crate {look}: {info['triangles']} triangles, {round(max(b - a for a, b in zip(info['min'], info['max'])), 1)} units")
    return {r: crate_for(r) for r in (0, 1, 2, 3, 8)}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    build(os.path.abspath(sys.argv[1]), os.environ.get("GOF3_ASSETS") or os.path.join(here, "..", "work", "merged", "assets"))
