"""GoF3's capital ships and the Hades (as the Manticore, a mobile station) for the GoF3 Ships mod.

The nine capital ships (structures/<race>/geometry/props/largeships/000-002: per race a battleship, a freighter and a frigate)
are baked by structures.convert into structures/<race>_<n>.glb and written as ships.json ships the remake flies in its traffic
("traffic": { "capital": ... }, Modding.ModCapitalShips): the battleships and frigates parked in the orbits' capital ship
special with their turret helpers armed (npcTurrets, at most MAX_TURRETS: the multiplayer copies carry 8), the freighters
cruising among the orbits' freighters. Never sold. At GoF3's own scale (K), so the Nemesis is 4.4 km long.

The Hades (structures/terran/geometry/props/hades) becomes the Manticore, stations.json's mobile station (Modding.
MobileStations): no planet, it roams every system (two hours in each, a Terran ship wherever it is, GoF3's capital ship engines lit at its stern)
and is docked at where it is, its system the one of the orbit it is in, into
its own hangar and bar (interiors.json): the hangar GoF3's own Hades hangar (hangar_room: the ShipSelectionB room, GoF3's
lighting baked in, at GoF3's scale like the ships), the bar the game's Terran bar lit cooler (its markers the game's own, read
from StationLevel.GameRoomMarkers). At HADES_SCALE of GoF3's (12.6 km would reach past the flight level's 15 km far plane).

build(out_dir, assets) -> (ships, stations, interiors): the ships.json, stations.json and interiors.json entries."""
import math, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
import structures, hangar_room, ae4_meshgroup, ae4_scene, ae4_material, nozzle_outline

K = 1231.49 / 23.02                       # game units per GoF3 unit (build_gof3_mod.K)
MAX_TURRETS = 8
MAX_ENGINES = 16                          # every nozzle lit (the Vossk battleship has 13, its freighter 14)
FLARE = 1.6                               # the flare streak against GoF3's quad (see large_engine_fx)
FLARE_BRIGHT = 1.67
NOZZLE = 2.09                             # an engine helper's scale x this = its nozzle's radius (GoF3 units: the large
                                          # engine's body, which GoF3 sizes to the nozzle)
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
# It roams every system ("route": "any"), two hours in each before it moves on, so a pilot who leaves it can come back to it
# soon, its orbits there half an hour each; a Terran ship wherever it is ("race"); the star map marks where it is.
MANTICORE_STAY = 30
MANTICORE_SYSTEM_MINUTES = 120
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


def astern(h):
    """An engine helper blowing astern (the effect is drawn backward from it; the Agni's nose thruster faces forward)."""
    return len(h) < 4 or h[3][2] > 0.5


def exhausts(glb, engines, scale, origin=(0.0, 0.0, 0.0)):
    """The exhaust mounts (slotType 3) of 'engines' [(name, helper)]: at the helper (position_engine from 'origin', x 'scale'),
    GoF3's engine effect at its helper's scale (fxScale) and its nozzle's shape measured on the hull ('outline', game units
    around the mount, position_engine's axes; nozzle_outline), 'glowSize' its extents (a round one without an outline)."""
    P, I = nozzle_outline.read_glb(glb)
    shapes = nozzle_outline.measure(P, I, [(h[0], h[1]) for _, h in engines], lambda s: NOZZLE * s)
    out = []
    for (_, h), shape in zip(engines, shapes):
        m = {"slotType": 3, "position_engine": game(np.asarray(h[0]) - np.asarray(origin), scale), "fxScale": round(h[1] * scale, 3)}
        r = round(h[1] * NOZZLE * K * scale)
        m["glowSize"] = [r, r, r * 3]
        if shape:
            pts = [(-x * K * scale, y * K * scale) for x, y in shape]          # glTF x -> position_engine's -x
            m["outline"] = [round(v, 1) for p in pts for v in p]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            hw, hh = (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2
            m["glowSize"] = [round(hw), round(hh), round(max(hw, hh) * 3)]
        out.append(m)
    return out


def spread(items, n):
    """At most 'n' of 'items' spread evenly along the hull (sorted by z)."""
    items = sorted(items, key=lambda h: h[1][0][2])
    if len(items) <= n: return items
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


def _ring_profile(path, offset):
    """A large engine mesh's rings behind its nozzle (scene z 'offset' added; z > 0 = backward): [(z, radius, colour)]."""
    g = ae4_meshgroup.read_all(path)[0]
    P = np.asarray(g["a_position"]); C = np.asarray(g["a_vtxColor"])[:, :3]
    out = []
    for z in sorted(set(np.round(P[:, 2], 3))):
        at = np.round(P[:, 2], 3) == z
        out.append((float(z) + offset, float(np.hypot(P[at, 0], P[at, 1]).max()), C[at].mean(0)))
    return [r for r in out if r[0] >= 0.0]


def _tapered(rings, length, rmax, out_png, size=(256, 128)):
    """The cone cards' texture: along u the share of the length, across v a soft band as wide as the mesh's radius there (the
    remake's cards are as wide everywhere: the taper is in the picture)."""
    zs = np.array([r[0] for r in rings]) / length; rs = np.array([r[1] for r in rings]) / rmax
    u = (np.arange(size[0]) + 0.5) / size[0]; v = (np.arange(size[1]) + 0.5) / size[1]
    w = np.clip(np.interp(u, zs, rs), 0.02, 1.0)
    d = np.abs(v[:, None] * 2 - 1) / w[None, :]
    a = np.clip(1 - d, 0, 1) ** 1.5
    img = (a * 255).astype(np.uint8)
    Image.merge("RGBA", [Image.fromarray(img)] * 4).save(out_png)


def _soft(out_png, size, sx, sy):
    """A soft gaussian spot (the flare) or streak (the core's trail): grey with the same alpha."""
    x = (np.arange(size[0]) + 0.5) / size[0] * 2 - 1; y = (np.arange(size[1]) + 0.5) / size[1] * 2 - 1
    a = np.exp(-(x[None, :] / sx) ** 2 - (y[:, None] / sy) ** 2)
    img = (a / a.max() * 255).astype(np.uint8)
    Image.merge("RGBA", [Image.fromarray(img)] * 4).save(out_png)


def _bright(c):
    c = np.asarray(c, float)
    return [round(float(x), 3) for x in c / max(1e-6, c.max())]


def large_engine_fx(out_dir, assets, race):
    """ships.json "engineFx" for GoF3's capital ship engine (vfx/engines/large/vfx_enigne_large_<race>: a glowing nozzle body
    8 units long, a hot core reaching 11.5 behind it and a flat flare streak 32 x 4.6 across the nozzle, all drawn in their
    vertex colours, the flare in its material's colours x 3), sized for an engine helper of scale 1 (each engine's
    "fxScale" = its helper's scale): the body as the cone (its rings' brightness and its taper, the cards' picture), the core
    as one straight trail, the flare as the glow's streak."""
    base = f"{assets}/vfx/engines/large/vfx_enigne_large_{race}"
    scene = {v["name"]: v for v in ae4_scene.read(base + ".ae4scene").values()}
    main_z = scene[f"vfx_enigne_large_{race}"]["pos"][2]
    core_z = main_z + scene[f"vfx_enigne_large_{race}_core"]["pos"][2]   # (the core and the flare are the body's children)
    body = _ring_profile(base + ".ae4meshgroup", main_z)
    core = _ring_profile(base + "_core.ae4meshgroup", core_z)
    length = body[-1][0]; rmax = max(r[1] for r in body)
    fx = os.path.join(out_dir, "fx"); os.makedirs(fx, exist_ok=True)
    _tapered(body, length, rmax, os.path.join(fx, f"large_{race}_cone.png"))
    _soft(os.path.join(fx, "large_glow.png"), (128, 128), 0.65, 0.65)   # (flat: the streak takes its whole length)
    if not os.path.exists(os.path.join(fx, "large_core.png")): _soft(os.path.join(fx, "large_core.png"), (64, 128), 0.4, 3.0)
    profile = []
    for z, r, c in body: profile += [round(z / length, 4), round(float(max(c)), 3), round(z / length, 4)]
    weights = np.array([max(c) for _, _, c in body])
    cone = _bright(sum(w * c for w, (_, _, c) in zip(weights, body)) / max(1e-6, weights.sum()))
    cw = np.array([max(c) for _, _, c in core])
    trail = _bright(sum(w * c for w, (_, _, c) in zip(cw, core)) / max(1e-6, cw.sum()))
    v, _ = ae4_material.read(base + "_flare.ae4material")
    flare = _bright((np.asarray(v["Colorize_Color1"][:3]) + np.asarray(v["Colorize_Color2"][:3])) / 2)
    fl = np.asarray(ae4_meshgroup.read_all(base + "_flare.ae4meshgroup")[0]["a_position"])
    # The glow square twice the body's radius, the streak FLARE x GoF3's flare quad (its texture is named by GUID only: ours
    # fades toward the ends, theirs shows the quad's whole length), brighter than its vertex grey x Colorize_Multiplier.
    return {"glow": "fx/large_glow.png", "glowSize": [round(2 * rmax * K), round(FLARE * float(fl[:, 0].max()) * K), round(FLARE * float(fl[:, 1].max()) * K)],
            "glowIntensity": round(FLARE_BRIGHT * 0.5 * float(v.get("Colorize_Multiplier", 3.0)), 2),
            "cone": f"fx/large_{race}_cone.png", "coneLength": round(length * K), "coneWidth": round(rmax * K),
            "coneProfile": profile, "coneFade": [0.0, 0.3], "coneFlow": [0, 1, 0.5],
            "trail": "fx/large_core.png", "trailCount": 1, "trailLength": round(core[-1][0] * K),
            "trailWidth": round(max(r[1] for r in core) * K), "trailWander": 0, "trailTime": 0.75,
            "color": flare, "flareColor": flare, "coneColor": cone, "trailColor": trail}


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
        engines = spread([h for h in helpers if "engine" in h[0] and "_engines" not in h[0] and astern(h[1])], MAX_ENGINES)
        mounts = []
        for hname, h in turrets:
            m = {"slotType": 2, "position_engine": game(h[0])}
            up = h[2] if len(h) > 2 else None
            if up is not None:
                u = [-up[0], up[1], -up[2]]
                if u[1] < -0.7: m["upsideDown"] = True
                elif u[1] < 0.7: m["turretUp"] = [round(v, 3) for v in u]
            mounts.append(m)
        mounts += exhausts(os.path.join(out_dir, glb), engines, 1.0)
        rid = RACE[race]
        parked = role != "freighter"
        ships.append({
            "id": f"capital_{race}_{n}", "name": name, "description": desc, "race": rid,
            "armor": 20000 if parked else 4000, "cargo": 0, "handling": 10, "price": 0,
            "slots": {"primary": 0, "secondary": 0, "turret": len(turrets), "equipment": 0},
            "model": glb, "modelLength": round(length), "modelYaw": 180,
            "engineGlowRadius": 300, "engineGlowColor": ENGINE_COLOUR[rid], "engineFx": large_engine_fx(out_dir, assets, race),
            "mounts": mounts, "npcTurrets": [TURRET[rid]] * len(turrets),
            "traffic": {"capital": "battleship" if parked else "freighter"},
            "explosionScale": round(min(20.0, max(4.0, length * 0.05 / 250.0)), 1),
        })
        log(f"capital {name}: {round(length * 0.05)} m, {len(turrets)} turrets, {len(engines)} engines, {info['triangles']} triangles")

    # the Manticore: GoF3's Hades as a mobile station
    hades_dir = f"{assets}/structures/terran/geometry/props/hades"
    info = structures.convert(hades_dir, "structure_terran_hades_000", "terran", os.path.join(out_dir, "structures/hades.glb"), 4096, assets)
    size = np.asarray(info["max"]) - np.asarray(info["min"])
    centre = (np.asarray(info["max"]) + np.asarray(info["min"])) / 2   # the remake centres a station's model on its bounds
    engines = exhausts(os.path.join(out_dir, "structures/hades.glb"),
                       [(k, h) for k, h in sorted(info["helpers"].items()) if "_engine_" in k and astern(h)], HADES_SCALE, centre)
    for m in engines: del m["slotType"]                                        # (the station's "engines": exhausts by definition)
    stations = [{
        "id": "manticore", "system": MANTICORE_SYSTEM, "name": "Manticore", "techLevel": 10, "planet": 0, "looksLike": 70,
        "model": "structures/hades.glb", "modelSize": round(float(size.max()) * K * HADES_SCALE), "modelYaw": 180,
        "interior": "terran", "hangar": "manticore_hangar", "bar": "manticore_bar",
        "mobile": {"route": "any", "stayMinutes": MANTICORE_STAY, "systemMinutes": MANTICORE_SYSTEM_MINUTES, "speed": 0.15,
                   "race": "terran", "engines": engines, "engineColor": ENGINE_COLOUR[0],
                   "engineFx": large_engine_fx(out_dir, assets, "terran")},
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
    log(f"Manticore: {round(float(size.max()) * K * HADES_SCALE * 0.05)} m, {len(engines)} engines, roaming every system")
    return ships, stations, interiors


if __name__ == "__main__":
    import json
    out, assets = sys.argv[1], sys.argv[2]
    ships, stations, interiors = build(out, assets)
    json.dump({"ships": ships, "stations": stations, "interiors": interiors}, open(os.path.join(out, "capitals.json"), "w"), indent=1)
