"""GoF3's capital ships and the Hades (as the Manticore, a mobile station) for the GoF3 Ships mod.

The nine capital ships (structures/<race>/geometry/props/largeships/000-002: per race a battleship, a freighter and a frigate)
are baked by structures.convert into structures/<race>_<n>.glb and written as ships.json ships the remake flies in its traffic
("traffic": { "capital": ... }, Modding.ModCapitalShips): the battleships and frigates parked in the orbits' capital ship
special with their turret helpers armed (npcTurrets, at most MAX_TURRETS: the multiplayer copies carry 8), the freighters
cruising among the orbits' freighters. Never sold. At GoF3's own scale (K), so the Nemesis is 4.4 km long.

The Hades (structures/terran/geometry/props/hades) becomes the Manticore, stations.json's mobile station (Modding.
MobileStations): no planet, it tours the Terran systems (MANTICORE_ROUTE, a Terran ship wherever it is) and is docked at where
it is, its system the one of the orbit it is in, into
its own hangar and bar (interiors.json): the hangar GoF3's own Hades hangar (hangar_room: the ShipSelectionB room, GoF3's
lighting baked in, at GoF3's scale like the ships), the bar the game's Terran bar lit cooler (its markers the game's own, read
from StationLevel.GameRoomMarkers). At HADES_SCALE of GoF3's (12.6 km would reach past the flight level's 15 km far plane).

build(out_dir, assets) -> (ships, stations, interiors): the ships.json, stations.json and interiors.json entries."""
import math, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import structures, hangar_room

K = 1231.49 / 23.02                       # game units per GoF3 unit (build_gof3_mod.K)
MAX_TURRETS = 8
MAX_ENGINES = 8
ENGINE_GLOW = 2.0                         # an engine helper's scale x this = its glow's radius (GoF3 units)
TURRET = {0: 48, 1: 49, 2: 48}            # the Hammerhead D2A2, the Vossk L'ksaar
ENGINE_COLOUR = {0: [1.0, 0.55, 0.22], 1: [0.55, 1.0, 0.2], 2: [0.22, 0.6, 1.0]}
RACE = {"terran": 0, "vossk": 1, "nivelian": 2}
CAPITALS = [   # race, model number, role, name, description
    ("terran", "000", "freighter", "Morpheus", "A Terran heavy freighter: the convoys' workhorse between the Terran systems."),
    ("terran", "001", "battleship", "Nemesis", "The Terran fleet's battleship, four kilometres of armour and gun turrets."),
    ("terran", "002", "frigate", "Proteus", "A Terran frigate, the battleships' escort and the patrols' flagship."),
    ("vossk", "000", "battleship", "Tiamat", "The Vossk Empire's battleship, bristling with turrets from bow to stern."),
    ("vossk", "001", "freighter", "Ashnan", "A Vossk freighter, carrying the Empire's goods and its armies' supplies."),
    ("vossk", "002", "frigate", "Absu", "A Vossk frigate, an engineers' ship that keeps the battle fleet flying."),
    ("nivelian", "000", "battleship", "Garuda", "The Nivelian battleship, the pride of the Nivelian fleet."),
    ("nivelian", "001", "freighter", "Varuna", "A Nivelian freighter, plying the trade routes of the Nivelian systems."),
    ("nivelian", "002", "frigate", "Agni", "A Nivelian frigate, fast for its size and heavily armed."),
]
HADES_SCALE = 0.5
MANTICORE_SYSTEM = 14                     # its home, Magnetar (Dis, where every multiplayer pilot starts)
# Its tour of the Terran systems along their gates, two orbits each (a stay of 20 minutes: 5 h 20 min round): Magnetar,
# Union, Aquila, Prospero, Vulpes, Augmenta, Buntta, Pescal Inartu. A Terran ship wherever it is ("race").
MANTICORE_ROUTE = [70, 73, 55, 57, 36, 38, 81, 83, 66, 68, 98, 95, 40, 43, 91, 93]
ROOM_SCALE = K * 0.05                     # metres per GoF3 unit: the hangar at the ships' scale
# The Hades hangar's markers in GoF3 units (glTF space: the pad at the origin, the open front +z, the back wall -78): the pad's
# deck, the camera in front of the room looking past the pad (the ship right of centre, like the game's hangars), the two lit
# bays beside the pad, and the flights' way in through the open front right of the camera (under the front beam, y 19).
HANGAR_MARKERS_GOF3 = {"pad": [0, -5, 0], "camera": [12, 13, 42], "camera_target": [-4, 0, 0],
                       "parked_1": [150, -4, 5], "parked_2": [-150, -4, 5],
                       "gate": [100, 10, 50], "gate_out": [100, 10, 150]}
BAR_MARKERS = {"camera": [-90, 31, -90.25], "camera_target": [-92.399, 31, -30.298], "camera_start": [-65.75, 58, 136.4],
               "camera_start_target": [-67.55, 58, 196.373], "visitor_1": [-116.25, 0, 48.2], "visitor_2": [-51.15, 10.6, -37.25],
               "visitor_3": [-54.9, 10.6, -21.35], "visitor_4": [-58.2, 10.6, 11.35], "visitor_5": [-98.95, 0, 5.4],
               "visitor_6": [-127.8, 0, -32.3], "visitor_7": [-71.95, 10.6, 43]}


def game(p, scale=1.0):
    """glTF space (the nose -z, GoF3 units) -> position_engine (+x the pilot's left, +z the nose), game units."""
    return [round(-p[0] * K * scale), round(p[1] * K * scale), round(-p[2] * K * scale)]


def spread(items, n):
    """At most 'n' of 'items' spread evenly along the hull (sorted by z)."""
    items = sorted(items, key=lambda h: h[1][0][2])
    if len(items) <= n: return items
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


def build(out_dir, assets, log=print):
    os.makedirs(os.path.join(out_dir, "structures"), exist_ok=True)
    ships = []
    for race, n, role, name, desc in CAPITALS:
        model_dir = f"{assets}/structures/{race}/geometry/props/largeships/{n}"
        glb = f"structures/{race}_{n}.glb"
        info = structures.convert(model_dir, f"structure_{race}_largeship_{n}", race, os.path.join(out_dir, glb), 2048, assets)
        size = np.asarray(info["max"]) - np.asarray(info["min"])
        length = float(size[2] * K)
        helpers = list(info["helpers"].items())
        turrets = spread([h for h in helpers if "_turret_" in h[0]], MAX_TURRETS)
        engines = spread([h for h in helpers if "engine" in h[0] and "_engines" not in h[0]], MAX_ENGINES)
        mounts = []
        for hname, h in turrets:
            m = {"slotType": 2, "position_engine": game(h[0])}
            up = h[2] if len(h) > 2 else None
            if up is not None:
                u = [-up[0], up[1], -up[2]]
                if u[1] < -0.7: m["upsideDown"] = True
                elif u[1] < 0.7: m["turretUp"] = [round(v, 3) for v in u]
            mounts.append(m)
        for hname, h in engines:
            r = round(h[1] * ENGINE_GLOW * K)
            mounts.append({"slotType": 3, "position_engine": game(h[0]), "glowSize": [r, r, r * 3]})
        rid = RACE[race]
        parked = role != "freighter"
        ships.append({
            "id": f"capital_{race}_{n}", "name": name, "description": desc, "race": rid,
            "armor": 20000 if parked else 4000, "cargo": 0, "handling": 10, "price": 0,
            "slots": {"primary": 0, "secondary": 0, "turret": len(turrets), "equipment": 0},
            "model": glb, "modelLength": round(length), "modelYaw": 180,
            "engineGlowRadius": 300, "engineGlowColor": ENGINE_COLOUR[rid],
            "mounts": mounts, "npcTurrets": [TURRET[rid]] * len(turrets),
            "traffic": {"capital": "battleship" if parked else "freighter"},
            "explosionScale": round(min(20.0, max(4.0, length * 0.05 / 250.0)), 1),
        })
        log(f"capital {name}: {round(length * 0.05)} m, {len(turrets)} turrets, {len(engines)} engines, {info['triangles']} triangles")

    # the Manticore: GoF3's Hades as a mobile station
    hades_dir = f"{assets}/structures/terran/geometry/props/hades"
    info = structures.convert(hades_dir, "structure_terran_hades_000", "terran", os.path.join(out_dir, "structures/hades.glb"), 4096, assets)
    size = np.asarray(info["max"]) - np.asarray(info["min"])
    stations = [{
        "id": "manticore", "system": MANTICORE_SYSTEM, "name": "Manticore", "techLevel": 10, "planet": 0, "looksLike": 70,
        "model": "structures/hades.glb", "modelSize": round(float(size.max()) * K * HADES_SCALE), "modelYaw": 180,
        "interior": "terran", "hangar": "manticore_hangar", "bar": "manticore_bar",
        "mobile": {"route": MANTICORE_ROUTE, "stayMinutes": 20, "speed": 0.15, "race": "terran"},
    }]
    room = hangar_room.convert(assets, os.path.join(out_dir, "structures/manticore_hangar.glb"), 4096, log)
    log(f"Manticore hangar: {room['triangles']} triangles")
    # Room metres, Unity's frame (glTFast mirrors x).
    markers = {k: [round(-v[0] * ROOM_SCALE, 2), round(v[1] * ROOM_SCALE, 2), round(v[2] * ROOM_SCALE, 2)]
               for k, v in HANGAR_MARKERS_GOF3.items()}
    interiors = [
        {"id": "manticore_hangar", "type": "hangar", "model": "structures/manticore_hangar.glb", "scale": round(ROOM_SCALE, 4),
         "ambient": [0.1, 0.1, 0.12], "lightIntensity": 0.8, "markers": markers},
        {"id": "manticore_bar", "type": "bar", "model": "gof2:bar_terran", "ambient": [0.18, 0.21, 0.28],
         "lightIntensity": 1.0, "markers": BAR_MARKERS},
    ]
    log(f"Manticore: {round(float(size.max()) * K * HADES_SCALE * 0.05)} m, mobile through {len(MANTICORE_ROUTE)} orbits")
    return ships, stations, interiors


if __name__ == "__main__":
    import json
    out, assets = sys.argv[1], sys.argv[2]
    ships, stations, interiors = build(out, assets)
    json.dump({"ships": ships, "stations": stations, "interiors": interiors}, open(os.path.join(out, "capitals.json"), "w"), indent=1)
