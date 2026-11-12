"""GoF3's UFOs and bombers for the mod.

UFOs: GoF3's sixth NPC class (Ship_NPC_<race>_UFO_T1-T7 on Template_NPC_UFO_*, in every race's and the pirates' enemy lists
beside the scouts, fighters, gunships and kamikazes: SDL_<race>_T<n>_UFO). Its lore (EnemyShip_UFO_Lore): unmanned defence
drones of a Grey design that guard an area, moving in a quick, erratic way, with a turret that covers a half sphere
(Projectile_Turret_Template_UFO_<race>). Each race's own model (structures/<race>/geometry/props/ufo(s)), its two turret
helpers above and below (the Terran one has none: its hull's top and bottom). In the remake: a ships.json hull per race
(not sold) flown by that race's NPC fighters (ships.json "traffic": "races", "weight" UFO_WEIGHT) with no guns of their own,
its two turret mounts armed (npcTurrets: the Hammerhead D1, the bosses' lightest turret: GoF3's UFO turret is a light one).
GoF3's missions guard places with them: the mod's Hijack (DC03, Vossk) and The Trap (DC04, pirates) spawn them.

Bombers: GoF3's bombers (structures/<race>/geometry/props/bomber/000: Terran, Vossk, Nivelian), its lore
(EnemyShip_Bomber_Lore): they never dogfight, go for frigates and stations with an explosive or EMP payload, heavily
armoured. Its missions fly them at a target (CM06's EMP bombers at the relay, a race picked at random; HT25's convoy
bombers): the mod's Blackout spawns them (gof3_missions.blackout). Not in the traffic: the remake has no role that goes
for capital ships and stations instead of the player. A ships.json hull per race (not sold), BOMBER_ARMOR, GoF3's
capital ship engines at its engine helpers.

Both are capped at the traffic's fighter length (MAX_LENGTH: the pirate UFO is 257 m, the Terran bomber 182 m in GoF3).

build(out, assets) bakes the models into <out>/structures/ and returns the ships.json entries."""
import os

import numpy as np

import capitals
import structures

K = capitals.K                          # game units per GoF3 unit
MAX_LENGTH = 148 / 0.05                 # game units: the remake's traffic flies fighters up to 150 m (gof3_kamikaze.MAX_LENGTH)
RACES = {"terran": 0, "vossk": 1, "nivelian": 2, "pirates": 8}
WORD = {"terran": "Terran", "vossk": "Vossk", "nivelian": "Nivelian", "pirates": "Pirate"}
# race: (its folder under structures/<race>/geometry/props, the model's name, its scene's name when it differs)
UFOS = {"terran": ("ufo", "structure_terran_ufo_000", None),
        "vossk": ("ufo/000", "structure_vossk_ufo_000", None),
        "nivelian": ("ufos/000", "structure_nivelian_ufo_000", "structures_nivelian_ufo_000"),
        "pirates": ("ufo", "structure_pirates_ufo_000", None)}
BOMBERS = ("terran", "vossk", "nivelian")
UFO_WEIGHT = 0.5                        # (as the kamikazes': GoF3's lists weigh each class alike, the mod has many fighters)
UFO_TURRET = 47                         # the Hammerhead D1 (gof3_wanted.TURRET's lightest tier)
UFO_ARMOR, BOMBER_ARMOR = 300, 240      # (the bomber the Groza it stands in for in Blackout had, 160, x1.5: "high armor")
UFO_DESC = "An unmanned defence drone of a Grey design that guards its area, a turret above and below."
BOMBER_DESC = "A heavily armoured bomber that never dogfights: it flies straight for its target with an explosive payload."


def ufo_id(race): return f"gof3_ufo_{race}"
def bomber_id(race): return f"gof3_bomber_{race}"


def _scale(info):
    """The model's length (game units, capped at MAX_LENGTH) and the scale its mounts take with the cap."""
    length = float((np.asarray(info["max"]) - np.asarray(info["min"]))[2] * K)
    capped = min(length, MAX_LENGTH)
    return capped, capped / length if length > 0 else 1.0


def turret_mounts(info, scale):
    """The UFO's turret mounts (slotType 2): its turret helpers, else (the Terran one) the hull's top and bottom middle."""
    hs = [h for n, h in sorted(info["helpers"].items()) if "_turret_" in n]
    if not hs:
        lo, hi = np.asarray(info["min"], float), np.asarray(info["max"], float); c = (lo + hi) / 2
        hs = [([c[0], hi[1], c[2]], 1.0, [0.0, 1.0, 0.0]), ([c[0], lo[1], c[2]], 1.0, [0.0, -1.0, 0.0])]
    out = []
    for h in hs:
        m = {"slotType": 2, "position_engine": capitals.game(h[0], scale)}
        up = h[2] if len(h) > 2 else None
        if up is not None:
            u = [-up[0], up[1], -up[2]]
            if u[1] < -0.7: m["upsideDown"] = True
            elif u[1] < 0.7: m["turretUp"] = [round(v, 3) for v in u]
        out.append(m)
    return out


def build(out, assets, log=print):
    os.makedirs(os.path.join(out, "structures"), exist_ok=True)
    ships = []
    for race, (folder, name, scene) in UFOS.items():
        md = os.path.join(assets, f"structures/{race}/geometry/props/{folder}")
        if not os.path.isdir(md): continue
        glb = f"structures/ufo_{race}.glb"
        info = structures.convert(md, name, race, os.path.join(out, glb), 1024, assets, scene_name=scene, log=log)
        length, scale = _scale(info)
        mounts = turret_mounts(info, scale)
        n = RACES[race]
        ships.append({"id": ufo_id(race), "name": f"{WORD[race]} UFO", "description": UFO_DESC, "race": n,
                      "armor": UFO_ARMOR, "cargo": 0, "handling": 90, "price": 0,
                      "slots": {"primary": 0, "secondary": 0, "turret": len(mounts), "equipment": 0},
                      "model": glb, "modelLength": int(round(length)), "modelYaw": 180, "explosionScale": 1.5,
                      "mounts": mounts, "npcTurrets": [UFO_TURRET] * len(mounts),
                      "traffic": {"weight": UFO_WEIGHT, "races": [n], "ai": "gof3"}})
        log(f"UFO {race}: {round(length * 0.05)} m, {len(mounts)} turrets, {info['triangles']} triangles")
    for race in BOMBERS:
        md = os.path.join(assets, f"structures/{race}/geometry/props/bomber/000")
        if not os.path.isdir(md): continue
        glb = f"structures/bomber_{race}.glb"
        info = structures.convert(md, f"structure_{race}_bomber_000", race, os.path.join(out, glb), 1024, assets, log=log)
        length, scale = _scale(info)
        engines = [(h_n, h) for h_n, h in sorted(info["helpers"].items())
                   if "engine" in h_n and "_engines" not in h_n and capitals.astern(h)]
        n = RACES[race]
        ships.append({"id": bomber_id(race), "name": f"{WORD[race]} bomber", "description": BOMBER_DESC, "race": n,
                      "armor": BOMBER_ARMOR, "cargo": 0, "handling": 40, "price": 0,
                      "slots": {"primary": 0, "secondary": 0, "turret": 0, "equipment": 0},
                      "model": glb, "modelLength": int(round(length)), "modelYaw": 180, "explosionScale": 2.0,
                      "engineGlowColor": capitals.ENGINE_COLOUR[n], "engineFx": capitals.large_engine_fx(out, assets, race),
                      "mounts": capitals.exhausts(os.path.join(out, glb), engines, scale)})
        log(f"bomber {race}: {round(length * 0.05)} m, {len(engines)} engines, {info['triangles']} triangles")
    return ships
