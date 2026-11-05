"""GoF3's NPC fighters' mine drops for the mod (the remake's ships.json "traffic": { "devices" }).

GoF3 hands its NPCs a secondary weapon by race, class and danger level (data.pdb's SW_DL_<race>_0N_*: ShipType 531157,
race 3704837, levelFrom 3920418, the weapon 8694459): gunships homing missiles from level 3 and cluster missiles from 9,
fighters sphere mines from 4 and biter mines from 8. The gunships' missiles become the mod's GoF3 missiles as their
hulls' "traffic": { "secondaries" } (homing: SW_CR_Homing's gof3_crhoming, cluster: SW_MR_Cluster's gof3_mrcluster; an
NPC's second weapon does its gun's damage, GoF2's); the fighters' mines become devices of the mod's GoF3 fighter hulls:

  sphere mine   SW_NPC_SphereMineDrop<race>: one every 5 s behind it, the player 1140 units off or more; the mine is an
                EffectZone (75 units, 15 s), each race's its own: the Terran one drains 70 % of the shield a second
                (BuffShieldDamageOverTime 2.31 % every 0.033 s), the Vossk one slows by 66 % and drains 19 %, the
                Nivelian and pirate ones eat the whole ship (TotalDOT: 5 and 26 % a second, HULL_PERCENT at most; the
                Nivelian's energy drain left out, GoF2 has no energy): the remake's "cloud"
  biter mine    SW_NPC_BiterMineDrop<race>: one every 7 s, a MovingBomb chasing the player within 300 for 6 s at 200, with
                no blast; the drop's AbilitySlowdown (speed x 0 for 10 s) on whoever it reaches: the remake's "mineLayer"
                with no damage and SLOW_PERCENT, its 96 hull shootable

GoF3's levels as the remake's ranks x RANK_PER_LEVEL (sphere mines from rank 8, biter mines from 16, which take over);
SHARE of the hull's NPCs carry them (GoF3 gives each NPC one loadout; its sphere entry's "chance" 1 is unclear, and
GoF2's fighters carry none: a share keeps them from every ship). The race of each hull's own (pirate hulls the pirates').

apply(D, ships, classes, mod_id) adds them to the hulls' traffic; returns how many fighter hulls got mines."""
import gof3_wanted

RACES = {0: "Terran", 1: "Vossk", 2: "Nivelian", 8: "Pirate"}
WEAPON = {"sphere": {"Terran": "SW_NPC_SphereMineDropTerran", "Vossk": "SW_NPC_Vossk_SphereMineDrop",
                     "Nivelian": "SW_NPC_SphereMineDropNivelian", "Pirate": "SW_NPC_Pirate_SphereMineDrop"},
          "biter": {"Terran": "SW_NPC_BiterMineDropTerran", "Vossk": "SW_NPC_Vossk_BiterMineDrop",
                    "Nivelian": "SW_NPC_BiterMineDropNivelian", "Pirate": "SW_NPC_Pirate_BiterMineDrop"}}
LEVEL = {"sphere": 4, "biter": 8, "homing": 3, "cluster": 9}   # SW_DL_*_0N_* levelFrom
MISSILES = (("homing", "gof3_crhoming"), ("cluster", "gof3_mrcluster"))   # (the gunships': build_gof3_mod.SECONDARIES)
RANK_PER_LEVEL = 2
SHARE = 25                           # % of a hull's NPCs with each
SLOW_PERCENT = 80                    # (GoF3's x 0 for 10 s stops the ship dead; the remake leaves it a fifth)
HULL_PERCENT = 5                     # a cloud's hull loss a second at most (GoF3's TotalDOT counts against hull + shield
                                     # together: the pirates' 26 % a second of the remake's hull alone killed in 4 s)


def _devices(D, race):
    R = D.R
    by = {}
    for r in R.p.recs: by.setdefault(R.name(r), r)
    out = []
    for kind, names in WEAPON.items():
        rid = by.get(names[race])
        if rid is None: continue
        found = gof3_wanted.mine_layers(D, {"Arming": {9719173: [_ref(rid)]}})
        for d in found:
            d["minRank"] = LEVEL[kind] * RANK_PER_LEVEL
            if kind == "sphere": d["maxRank"] = LEVEL["biter"] * RANK_PER_LEVEL - 1
            d["share"] = SHARE
            if d["type"] == "mineLayer" and d.get("slowPercent", 0) > SLOW_PERCENT: d["slowPercent"] = SLOW_PERCENT
            if d.get("hullPercent", 0) > HULL_PERCENT: d["hullPercent"] = HULL_PERCENT
            out.append(d)
    return out


def _ref(rid):
    """An ObjectRef message to record 'rid' (field 1), as the records carry them."""
    def varint(n):
        b = bytearray()
        while True:
            x = n & 0x7f; n >>= 7
            b.append(x | 0x80 if n else x)
            if not n: return bytes(b)
    return b"\x08" + varint(rid)


def secondaries(mod_id):
    """A gunship hull's "secondaries": homing missiles from GoF3's level 3, cluster missiles from 9 (taking over)."""
    out = []
    for i, (kind, item) in enumerate(MISSILES):
        e = {"item": f"{mod_id}:{item}", "minRank": LEVEL[kind] * RANK_PER_LEVEL, "share": SHARE}
        if i + 1 < len(MISSILES): e["maxRank"] = LEVEL[MISSILES[i + 1][0]] * RANK_PER_LEVEL - 1
        out.append(e)
    return out


def apply(D, ships, classes, mod_id, log=print):
    cache, n = {}, 0
    gunships = 0
    for s in ships:
        if classes.get(s["id"]) == "gunship" and not (s.get("traffic") or {}).get("boss"):
            s.setdefault("traffic", {})["secondaries"] = secondaries(mod_id)
            gunships += 1
    for s in ships:
        if classes.get(s["id"]) != "fighter" or (s.get("traffic") or {}).get("boss"): continue
        race = RACES.get(s.get("race"))
        if race is None: continue
        if race not in cache: cache[race] = _devices(D, race)
        if not cache[race]: continue
        s.setdefault("traffic", {}).setdefault("devices", []).extend(dict(d) for d in cache[race])
        n += 1
    sample = next(iter(cache.values()), [])
    log(f"loadouts: {n} fighter hulls with GoF3's mine drops ({', '.join(d['type'] for d in sample)}), {gunships} gunship "
        "hulls with its missiles")
    return n
