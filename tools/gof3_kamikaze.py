"""GoF3's kamikazes for the mod: its fifth NPC class (ShipType 4, Template_NPC_Kamikaze_T*, on Template_Boss_TankGunship),
in every race's and the pirates' enemy lists (data.pdb's SDL_<race>_T<n>_Kamikaze, beside the scouts, fighters, gunships
and UFOs). Each is a drone of its race's own (structures/<race>/geometry/props/kamikaze/000) that rams its target
(Device_KamikazeRam: a 5 s charge at the player 800-1500 off) behind a front shield (Device_KamikazeFrontShield: 67 %
stopped, the player within 30 degrees ahead), laying mines behind it (SW_NPC_Kamikaze_Minelayer: one every 4 s with the
player 300-2500 off, each chasing the player for 4.5 s) and throwing them at a player close in front
(SW_NPC_Kamikaze_Minethrower: 50-300 off, within 30 degrees, every 5 s, 3 s of flight); a single hit destroys a mine.

In the remake: a ships.json hull per race (not sold) flown by that race's NPC fighters (ships.json "traffic": "races",
"weight" WEIGHT), the ram as the traffic role "detonator" (it holds its guns, flies into its target and blows up close by),
the mine layer, the mine thrower and the front shield as its "devices" (gof3_wanted's exporters, the tier-4 records';
the remake's "mineLayer" with a negative "layBehind" for the thrower). Its NPCs fight GoF3's way ("ai": "gof3") like
the mod's other hulls.

build(D, out, assets) bakes the models into <out>/structures/ and returns the ships.json entries."""
import os

import gof3_wanted

RACES = {"terran": 0, "vossk": 1, "nivelian": 2, "pirates": 8}
NAMES = {"terran": "Terran kamikaze", "vossk": "Vossk kamikaze", "nivelian": "Nivelian kamikaze", "pirates": "Pirate kamikaze"}
RECORD = "Ship_NPC_Kamikaze_{}_T4"   # (the tiers differ only in their hull and damage, which the remake's traffic sets)
WEIGHT = 0.5                         # (GoF3's lists weigh each class alike; the mod has many fighter hulls of each race)
K = 1231.49 / 23.02                  # game units per GoF3 unit (build_gof3_mod.K)
MAX_LENGTH = 148 / 0.05              # game units: the remake's traffic flies fighters up to 150 m (the Nivelian one is 150)


def hull_id(race): return f"gof3_kamikaze_{race}"


def build(D, out, assets, log=print):
    import structures, numpy as np
    R = D.R
    by_name = {}
    for r in R.p.recs: by_name.setdefault(R.name(r), r)
    os.makedirs(os.path.join(out, "structures"), exist_ok=True)
    ships = []
    for race, number in RACES.items():
        md = os.path.join(assets, f"structures/{race}/geometry/props/kamikaze/000")
        name = f"structure_{race}_kamikaze_000"
        rec = by_name.get(RECORD.format(race.capitalize() if race != "pirates" else "Pirate"))
        if not os.path.isdir(md) or rec is None: continue
        glb = f"structures/kamikaze_{race}.glb"
        info = structures.convert(md, name, race, os.path.join(out, glb), 1024, assets)
        size = (np.asarray(info["max"]) - np.asarray(info["min"])) * K
        comps = R.resolved(rec)[0]
        devices = gof3_wanted.mine_layers(D, comps) + [d for d in gof3_wanted.devices(D, comps) if d["type"] != "teleport"]
        ships.append({"id": hull_id(race), "name": NAMES[race], "description": "A drone that rams its target and lays mines.",
                      "race": number, "armor": 400, "cargo": 0, "handling": 60, "price": 0,
                      "slots": {"primary": 0, "secondary": 0, "turret": 0, "equipment": 0},
                      "model": glb, "modelLength": int(round(min(float(size[2]), MAX_LENGTH))), "modelYaw": 180, "explosionScale": 1.5,
                      "traffic": {"weight": WEIGHT, "races": [number], "role": "detonator", "ai": "gof3", "devices": devices}})
        log(f"kamikaze {race}: {round(min(size[2], MAX_LENGTH) * 0.05)} m long, {info['triangles']} triangles, {len(devices)} devices "
            f"({', '.join(d['type'] for d in devices)})")
    return ships
