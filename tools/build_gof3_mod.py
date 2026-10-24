"""The GoF3 ships as a Galaxy on Fire 2 Unity Remake mod of customizable ships: <out>/mod.json, ships.json, shipkits.json,
hulls/, guns/, turret/, skins/, icons/, preview.png, README.txt.
python build_gof3_mod.py [out, default ~/GOF2UnityRemakeMods/gof3_ships] [--max-texture 1024] [--no-icons] [--icons-from DIR]
                         [--jobs N]
Needs ../gof3converted (the hulls without guns, their paint-scheme textures, the guns in weapons/), ../gof3converted_loadouts
(manifest.json = each folder's data.pdb record and default arming; its .glb files for the icons), ../romfs_merged/data.pdb,
the venv (numpy, Pillow, SciPy: the floating-gun check) and Blender on PATH (the turret, the icons).
(build_gof3_mod_v1.py made the old layout: one ship per paint scheme, each its own model with its guns baked in.)

One kit ("gof3", shipkits.json) holds every hull as a part of the slot "hull", each part only for its own ship type, so a
GoF3 ship is one ships.json entry with "kit": "gof3", "kitType" its id, and:
  skins      every paint scheme of the hull (Galaxy on Fire 3's numbered schemes 001-003 and pirate / huawei, the data.pdb
             skins that were ships of their own before: Gold, Gr'Gath, R.E.D., Atlas II...): texture sets for the hull's
             body (base colour, emission, metallic / smoothness when the scheme's roughness differs), its glass and its decal
             sheet where the scheme has its own, and the exhausts' glow colour where the scheme lights them differently.
             Picked in the hangar's Customize screen (Skin); cosmetic only (the stats are the hull's plain record's).
  guns       the GoF3 generic guns as the kit's hardpoint models (ModHardpoints): each GoF2 primary weapon shows the GoF3 gun
             family nearest to it (pulse lasers Burst Laser, beams Beam Laser, blasters Plasma Blast, the Micro Guns / Scram
             Cannon Auto Laser, railguns Railgun, mass drivers Mass Driver, thermo guns Plasma Focus, scatter guns Scatter
             Plasma, the Disruptor / Dark Matter lasers Dismantler), mk1-3 by the weapon's rank in its family, on the hull's
             hardpoints turned as GoF3 turns them; the shots leave from the gun's muzzle. Secondaries show nothing (GoF3's
             launchers have no model).
  turret     every hull gets turret mounts (1, the bosses 2) with "builtIn": a turret item shows a GoF3 turret (a GoF3 weapon
             mount as its swivel, the GoF3 gun its item maps to on top) instead of the game's turret models, keeping the item's
             stats and behaviour. Mounts at the hull's own turret_NNN sockets (upright or under the hull), else on top of the
             hull's rear half.
  toggle     the guns, their pylons and the turret model can be hidden in the hangar's Customize screen (Weapon models:
             Shown / Hidden; the kit's hardpoints "toggle"): the hull as GoF3 shows it bare, the shots then leave from the mounts.
Every stat comes from the hull's data.pdb record (templates merged field by field, ae4_pdb_arming.Records), as before:
  name / description   GuiAttribute 4067579 / 9934023 -> the text records' English string (3906420)
  race                 Identity 9536365: 3 Terran -> 0, 4 Vossk -> 1, 6 Nivelian -> 2, 7 pirates -> 8, 5 Inouac -> 3 Midorian
  class                ShipType 531157: 2 fighter, 3 gunship, absent = scout
  armor                Hull 1929780 + Shield 3522367 (GoF3 has no armour pool; its shield is built in)
  price, priceDefault  from the stats as GoF2 prices its own ships, in each economy (gof2_price_fits, fitted at build
                       time to the remake's ships.json / economy_default.json: equipment slots on a curve, primary,
                       secondary and turret slots, armor, cargo, handling)
  handling             Steering 1007915 (turn rates, rad/s): the mean of the first two
  slots                primary / secondary = the Arming hardpoints of those groups, equipment = class + DeviceEquip 2232171,
                       turret = the turret mounts
  cargo                GoF3 ships have no hold: by class and hull length
Scale: the kit's 53.5 game units per GoF3 unit (GoF2's Groza is 1231 units long, GoF3's 23.02), yaw 180 (the GoF3 models face
-Z); the Nunam's model is turned round first (TURN: GoF3 models it backwards against its concept art). Hulls without engine
helpers (the Inouac ships) get thin exhausts at their wing tips (one per contrail helper), the Nunam also at its spike tips (TIP_EXHAUSTS). Exhaust glows: each engine's colour and nozzle size from the hull's emissive texture around its helper (engine_glows.py),
the flame's length from the GoF3 engine effect's plume. Hulls without a ship record (manifest note "no ship record") are left
out."""
import functools, glob, time, hashlib, io, json, math, os, re, shutil, struct, subprocess, sys, threading, unicodedata
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = os.environ.get("GOF3_BLENDER") or "blender"   # import.py sets it (Blender found by itself on any system)
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ae4_pdb_arming import Records
from glb_layout import layout, read, trs
from engine_glows import engines as measure_engines, _accessor
import gof3_sounds
import capitals

args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and not sys.argv[i - 1] in ("--max-texture", "--icons-from", "--jobs")]
OUT = os.path.abspath(args[0] if args else os.path.expanduser("~/GOF2UnityRemakeMods/gof3_ships"))
MAXTEX = int(sys.argv[sys.argv.index("--max-texture") + 1]) if "--max-texture" in sys.argv else 1024
ICONS = "--no-icons" not in sys.argv
JOBS = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 0   # 0: by the memory free (jobs())
ICONS_FROM = os.path.abspath(sys.argv[sys.argv.index("--icons-from") + 1]) if "--icons-from" in sys.argv else None
# Where the earlier stages put their results (import.py sets these; the defaults are the original layout next to tools/).
CONV = os.environ.get("GOF3_CONV") or os.path.join(HERE, "..", "gof3converted")
LOAD = os.environ.get("GOF3_LOADOUTS") or os.path.join(HERE, "..", "gof3converted_loadouts")
MERGED = os.environ.get("GOF3_MERGED") or os.path.join(HERE, "..", "romfs_merged")   # data.pdb, particles/, assets/
ASSETS = os.environ.get("GOF3_ASSETS") or os.path.join(HERE, "..", "assets_best")
GUNS = os.path.join(CONV, "weapons")
PDB = os.path.join(MERGED, "data.pdb")
# A checkout of the remake's source (optional): its ship tables for the price fits and its interface atlas for the icons'
# frame. Without one the fits below and a drawn frame stand in.
REMAKE = os.path.expanduser(os.environ.get("GOF3_REMAKE") or "~/Github/Galaxy-on-Fire-2-Unity-Remake")
PLATE = os.path.join(REMAKE, "Assets", "Textures", "textures", "gof2_interface2_ipad_large.png")
PLATE_RECT = (1821, 1, 178, 86)          # frame_ship (image 1276), Reference/research/item_icons.json

K = 1231.49 / 23.02                      # game units per GoF3 unit (the two Grozas)
KIT = "gof3"
RACE = {3: 0, 4: 1, 6: 2, 7: 8, 5: 3}
CLASS = {2: "fighter", 3: "gunship", None: "scout"}
CAMERA_FIT_LENGTH = 1400.0                 # ships.json "camera": GoF2's chase camera fits a hull this long (game units)
CAMERA_BASE_DISTANCE = 7.0                 # GoF3's CameraThirdPerson distance for its scouts and fighters (gunships 8)
EXPLOSION_BASE = 1.5                       # GoF3's EffectScale of most fighters = a GoF2 fighter's explosion (1)

# Speeds: GoF3's cruising speed (Steering 6741857: scouts 190-200, fighters 175-180, gunships 150-185, the bosses 170) against
# a fighter's 175, as ships.json "flight" "topSpeed" in % (both flight styles); the remake's ships all fly 2 u/ms otherwise.
CRUISE_BASE = 175.0
# The built-in booster: every GoF3 player ship carries its class's Device_Special_EngineBooster (the bosses none), whose
# configuration boosts x3 (scout), x2.5 (fighter) or x2 (gunship) (DeviceConfigurationEngineBooster_* field 1475543). As
# the mod's own booster items (items.json, built in through ships.json "integrated"): GoF2's boost speed int(2b / 100) + 2
# u/ms gives those factors at b = 200 / 150 / 100 (the Me'al's, the Synchrotron's and between), free flight's boost the
# same factor (freeBoostFactor). A booster the player fits takes the built-in one's place. Duration 2857 ms (the
# configuration's 485920), recharge 12 s (a remake pick between GoF2's boosters: the configuration's 60 is seconds of a
# special device's cooldown in GoF3's own flight). Look and sound: the Synchrotron's (73).
BOOSTERS = {
    "scout":   {"device": "Device_Special_EngineBooster_Scout", "boostSpeed": 200, "factor": 300},
    "fighter": {"device": "Device_Special_EngineBooster_Fighter", "boostSpeed": 150, "factor": 250},
    "gunship": {"device": "Device_Special_EngineBooster_Gunship", "boostSpeed": 100, "factor": 200},
}
BOOSTER_BASE, BOOSTER_DURATION, BOOSTER_RECHARGE = 73, 2857, 12000
# GoF3's Device_Revive_Cloak (24 of the 32 player ships): when the ship is destroyed it comes back cloaked for a moment
# (DeviceConfigurationCloak: 4 and 10 s). GoF2's own Emergency System (185) is that: the hull's end turned into 10 s of
# invulnerability, once a sortie (a built-in one used up is back at the next docking).
REVIVE_DEVICE, REVIVE_ITEM = "Device_Revive_Cloak", 185
# GoF3's bosses (a BossInfo component: Khador, Rh'ash, Snotch, Sh'gaal, Bl'Arek): not sold, the pirate bosses' hulls
# instead (ships.json "traffic": { "boss": true }), every turret mount armed (npcTurrets) with their race's heavy turret.
BOSS_TURRET = {1: 49}   # by race: the Vossk L'ksaar; the others the Hammerhead D2A2 (48)

# Blueprints (blueprints.json), in Galaxy on Fire 2's own way (its 25 item blueprints, Reference/research/blueprints_mods.md
# in the remake): the recipe is the product's lower tier (the Wolverine needs a Wolf, the Archimedes two H'nookks: here
# the hull's own GoF3 gun, from GOF3_WEAPONS, its race's families, the mark by the ship's price, two for the dearest), the
# race's goods and ores (energy cells in most of GoF2's), a few ore cores (GoF2 asks 1-40) and for the dearest a Void
# Essence (the Disruptor's), worth BLUEPRINT_VALUE of the ship's price (GoF2's: 0.6-1.0, most 0.7-0.8), in odd amounts
# (up to GoF2's ~1000). Each is sold by one visitor at one fixed station of its race for a fixed price (GoF2's sellers:
# 0.2-0.75 of the product, prices like 59 999), once the campaign is past step 16 (GoF2's story agents); the three GoF3
# hides in exploration (BlueprintPart_Explore_argus / scorpion / shaanragrth) also lie in a derelict at a fixed spot of a
# fixed orbit (GoF2's hidden-blueprint wrecks). Kept from GoF3: its race's ships drop it at GoF3's chance (its Blueprint
# 722713, at most BLUEPRINT_DROP_MAX %). A boss hull's blueprint has one source: the boss itself, destroyed as a pirate
# boss, always drops it (blueprints.json "drops" { "ship" }). A blueprint is handed out once: known, no source offers it.
BLUEPRINT_VALUE, BLUEPRINT_SELLER, BLUEPRINT_DROP_MAX = (0.62, 0.80), (0.35, 0.55), 5.0
BLUEPRINT_GUNS = {0: ["000", "004", "006"], 1: ["005", "003", "001"], 2: ["002", "008", "007"], 3: ["001", "002"]}
BLUEPRINT_GOODS = {   # by race (the Inouac as Midorian, 3): GoF2 goods and ores of that race's trade
    0: [118, 129, 127, 120, 125, 157, 155],   # Electronics, Optics, Microchips, Plastics, Mech. Supplies, Orichalzine, Titanium
    1: [125, 155, 130, 124, 114, 156, 119],   # Mech. Supplies, Titanium, Hydraulics, Radioactive Goods, Explosives, Iron, Chemicals
    2: [121, 154, 127, 129, 126, 163, 119],   # Nanotech, Gold, Microchips, Optics, Noble Gas, Hypanium, Chemicals
    3: [164, 121, 126, 128, 163, 158],        # Void Crystals, Nanotech, Noble Gas, Com. Devices, Hypanium, Pyresium
}
BLUEPRINT_CORES = {0: [168, 166], 1: [166, 172], 2: [165, 174], 3: [169, 175]}   # Orichalzin / Titanium / Cesogen / Golden / Hypanium / Pyresium core, Void Essence
ENERGY_CELLS, VOID_ESSENCE = 122, 175
# stations no seller or derelict uses: the pirate bases (unmanned), the Kaamo Club, the battlestation, deep science, the
# empty and supernova orbits; and systems: Loma (the black market), Ginoya (the supernova), the pirate systems 32 / 33
NO_BLUEPRINT_STATIONS = {1, 33, 47, 86, 100, 101, 102, 103, 104, 108, 109, 110, 111, 112, 113, 132, 133, 134}
NO_BLUEPRINT_SYSTEMS = {25, 27, 32, 33}
DROP_RACE = {0: "terran", 1: "vossk", 2: "nivelian", 3: "midorian"}
EXPLORED = {"argus": "terran_001", "scorpion": "vossk_109", "shaanragrth": "vossk_103"}


def odd_amount(x):
    """An amount as GoF2's recipes write them: exact under 30, else in fives; at least 1."""
    x = max(1, int(round(x)))
    return x if x < 30 else int(round(x / 5.0)) * 5


def blueprint_stations():
    """By race (0-3): the stations a blueprint seller or derelict may use, in systems visible from a new game first."""
    stations = json.load(open(os.path.join(REMAKE, "Assets/Resources/GoF2Data/stations.json"), encoding="utf-8-sig"))
    systems = {s["index"]: s for s in json.load(open(os.path.join(REMAKE, "Assets/Resources/GoF2Data/systems.json"), encoding="utf-8-sig"))}
    out = {r: [] for r in range(4)}
    for st in stations:
        sy = systems.get(st["system"])
        if not sy or st["index"] in NO_BLUEPRINT_STATIONS or sy["index"] in NO_BLUEPRINT_SYSTEMS: continue
        r = sy["raceId"]
        if r in out: out[r].append((0 if sy.get("initiallyVisible") else 1, st["index"]))
    return {r: [i for _, i in sorted(v)] for r, v in out.items()}


def blueprints(ships, info, D):
    """blueprints.json: a blueprint for each GoF3 ship (GoF2's way, see above)."""
    import random, zlib
    items = {it["index"]: it for it in json.load(open(os.path.join(REMAKE, "Assets/Resources/GoF2Data/items.json"), encoding="utf-8-sig"))}
    weapon_price = {f"{MOD_ID}:{weapon_id(f, mk)}": int(WEAPON_PRICE[mk] * 1.05) for f in GOF3_WEAPONS for mk in (1, 2, 3)}
    stations = blueprint_stations()
    used = {r: [] for r in stations}   # the stations given out, so the sellers spread over the race's bars
    out = []
    for e in sorted(ships, key=lambda x: x["price"]):
        rng = random.Random(zlib.crc32(e["id"].encode()))
        race = e["race"] if e["race"] in BLUEPRINT_GOODS else 3
        price = e["price"]
        target = price * rng.uniform(*BLUEPRINT_VALUE)
        mk = 1 if price < 1500000 else 2 if price < 3500000 else 3
        gun = f"{MOD_ID}:{weapon_id(rng.choice(BLUEPRINT_GUNS[race]), mk)}"
        guns = 2 if price < 2500000 else max(2, e["slots"]["primary"])   # (the hull's guns: two, or all of them)
        cores = BLUEPRINT_CORES[race][:2 if price >= 2500000 else 1]
        core_amount = max(5, min(40, int(price / 120000)))
        essence = (1 + (price >= 4500000)) if price >= 4000000 and VOID_ESSENCE not in cores else 0
        fixed = guns * weapon_price[gun] + sum(core_amount * items[c]["maxPrice"] for c in cores) + essence * items[VOID_ESSENCE]["maxPrice"]
        goods = rng.sample(BLUEPRINT_GOODS[race], 4 if price >= 2500000 else 3)
        # GoF2's amounts: ores 40-215, goods 10-150 a recipe; more for a dearer ship; energy cells carry the rest of the value
        scale = min(2.5, max(0.6, price / 1000000.0))
        amounts = {g: rng.uniform(60, 180 if items[g]["maxPrice"] < 200 else 140) * scale for g in goods}
        value = fixed + sum(a * items[g]["maxPrice"] for g, a in amounts.items())
        amounts[ENERGY_CELLS] = min(990, max(20 * scale, (target - value) / items[ENERGY_CELLS]["maxPrice"]))
        value += amounts[ENERGY_CELLS] * items[ENERGY_CELLS]["maxPrice"]
        if value < target * 0.9:   # still short: the goods a little more, at most 600 of one
            f = min((target * 0.9 - fixed - amounts[ENERGY_CELLS] * items[ENERGY_CELLS]["maxPrice"])
                    / max(1, sum(amounts[g] * items[g]["maxPrice"] for g in goods)), 600 / max(amounts[g] for g in goods))
            for g in goods: amounts[g] *= max(1.0, f)
        goods.append(ENERGY_CELLS)
        ingredients = [{"item": gun, "amount": guns}]
        ingredients += [{"item": g, "amount": odd_amount(amounts[g])} for g in goods if g != ENERGY_CELLS]
        ingredients += [{"item": c, "amount": core_amount} for c in cores]
        ingredients.append({"item": ENERGY_CELLS, "amount": odd_amount(amounts[ENERGY_CELLS])})
        if essence: ingredients.append({"item": VOID_ESSENCE, "amount": essence})
        bp = {"id": e["id"], "ship": f"{MOD_ID}:{e['id']}", "ingredients": ingredients}
        if e.get("traffic", {}).get("boss"):
            bp["drops"] = [{"ship": f"{MOD_ID}:{e['id']}", "chance": 100}]
            out.append(bp); continue
        bp["available"] = "campaign < 0 or campaign > 16"   # (free play and sessions: -1)
        pool = [s for s in stations[race] if s not in used[race]] or stations[race]
        at = pool[rng.randrange(min(len(pool), 8))]   # (the first eight: the systems a new game sees first)
        used[race].append(at)
        bp["lounge"] = {"stations": [at], "price": int(round(price * rng.uniform(*BLUEPRINT_SELLER) / 10000.0)) * 10000 - rng.choice((1, 1, 2))}
        rid = D.R.p.byname[info[e["id"]]["record"]][0]
        chance = D.num(rid, "Blueprint", 722713) or 0.0
        if 0 < chance < 1:
            bp["drops"] = [{"race": DROP_RACE[race], "chance": round(min(BLUEPRINT_DROP_MAX, chance * 100), 2)}]
        if e["id"] in EXPLORED.values():
            far = [s for s in reversed(stations[race]) if s != at]
            bp["derelict"] = {"race": DROP_RACE[race], "stations": [far[rng.randrange(min(len(far), 4))]],
                              "position": [rng.choice((-1, 1)) * rng.randrange(20, 80) * 1000, rng.choice((-1, 1)) * rng.randrange(20, 80) * 1000,
                                           rng.randrange(80, 140) * 1000]}
        out.append(bp)
    return out


MOD_ID = "gof3_ships"


def booster_items():
    """items.json: the three built-in boosters (never sold: occurrence 0)."""
    return [{"id": f"engine_booster_{cls}", "base": BOOSTER_BASE, "name": f"{cls.title()} Engine Booster",
             "description": f"Galaxy on Fire 3's engine booster, built into every {cls}: it briefly lifts the ship to "
                            f"{b['factor'] / 100:g} times its top speed.",
             "occurrence": 0,
             "stats": {"boostSpeed": b["boostSpeed"], "boostDurationMs": BOOSTER_DURATION, "boostRechargeMs": BOOSTER_RECHARGE,
                       "freeBoostFactor": b["factor"]}}
            for cls, b in BOOSTERS.items()]
CONVERT = {
    # power = GoF3 hull + shield; log-mapped from [P_LO, P_HI] onto the GoF2 ranges below
    "P_LO": 1500.0, "P_HI": 33000.0,
    "armor": (120, 520), "armor_clamp": (100, 560),
    # price: as GoF2 prices its own ships, fitted to them at build time (gof2_price_fits): the sold ships of the remake's
    # ships.json (Android) and with economy_default.json's ships over them (the Default Economy -> "priceDefault"); not the
    # freighters / battleship (13-15), the Cronus (37, a gift), 50 / 53 (unnamed), the Rhino (51, a 1200-hull freighter) or
    # the Specter (44, a story reward). See gof2_price_fits for the model.
    "price_clamp": (20000, 20000000),
    # handling: the mean turn rate, gunship 1.37 rad/s -> 95, scout 2.234 -> 155, clamped 60..160
    "handling": ((1.37, 95), (2.234, 155)), "handling_default": {"scout": 155, "fighter": 114, "gunship": 95},
    "cargo": {"scout": (45, 900), "fighter": (80, 1300), "gunship": (160, 1900)},   # (tonnes, at this length)
    "equipment": {"scout": 8, "fighter": 10, "gunship": 12},
    "lounge": {"minCampaign": (8, 40), "minRank": (1, 14), "chance": 3},
}
ENGINE_FX = {"TerranEngine": ((0.0, 0.533, 1.0), 10.48 / 2.59), "TerranEngineLarge": ((1.0, 0.416, 0.0), 7.23 / 2.09),
             "NivelianEngine": ((0.216, 0.859, 1.0), 12.09 / 1.62), "NivelianEngineLarge": ((0.0, 0.569, 1.0), 7.23 / 2.2),
             "VosskEngine": ((0.0, 1.0, 0.639), 15.45 / 2.59), "PirateEngine": ((1.0, 0.0, 0.18), 10.48 / 2.59),
             "InouacEngine": ((0.0, 1.0, 0.835), 10.48 / 2.59)}
NOZZLE_DEFAULT = 0.6      # GoF3 units: a nozzle's half size when the model shows none
FLAME = 0.35              # the flame's length = the nozzle's mean half size x the plume's length / radius x this
NAMES = {"ship_terran_020": "CRONUS"}   # its record is the dragon paint's (Ship_id020_DragonShip_Name); the plain hull
# paint scheme -> its name in the Customize screen (the data.pdb skins' as the old variant ships were named)
SCHEME = {"001": "Scheme 1", "002": "Scheme 2", "003": "Scheme 3", "000": "Scheme 0", "pirate": "Pirate", "huawei": "Huawei",
          "gold": "Gold", "red": "R.E.D.", "grgath": "Gr'Gath", "blackred": "Black Red", "mkktbkkt": "Mkkt Bkkt",
          "sutoeshii": "Sutoé-Shii Event", "khador_e2017s03": "Season 3", "dragon": "Dragon", "atlas2": "Atlas II",
          "acheron2": "Acheron II", "mardk2": "Mar'Dk II", "moornta2": "Moornta II", "shamash2": "Black Red",
          "greyshadow": "Grey Shadow", "goldgorgon": "Golden Gorgon"}
SCHEME_ORDER = ["001", "002", "003", "000", "pirate", "huawei"]   # then the data.pdb skins by name, Gold last
MAX_TURRETS = 2
# Hulls GoF3 models the other way round from their concept art: turned about the up axis (degrees) before anything reads them,
# so their hardpoints, pylons, turret sockets and helpers turn with them. The Nunam: Fishlabs' concept (M. Nagel, 2013) flies
# it canopy first, the two long spikes trailing; GoF3's model has the spikes where every other hull has its nose (-Z).
TURN = {"ship_inouac_600": 180}
# Hulls without engine helpers (the Inouac ships) get exhausts at their contrail helpers (GoF3's wing-tip trails) and at these
# points (glTF units, the converted model before its TURN): the Nunam's two spike tips, which its concept art shows glowing
# and trailing cyan like its wing tips.
TIP_EXHAUSTS = {"ship_inouac_600": [(3.05, 5.4, -9.39), (-3.05, 5.4, -9.39)]}
TIP_SIZE = 0.25           # GoF3 units: a tip exhaust's nozzle half size
TIP_FX_SCALE = 0.45       # its engine effect at this size (a thin streak off the tip, not an engine's plume)

# GoF2 weapon -> GoF3 gun (family, mk). Families: 000 Burst Laser, 001 Scatter Plasma, 002 Plasma Focus, 003 Dismantler,
# 004 Mass Driver, 005 Plasma Blast, 006 Auto Laser, 007 Railgun, 008 Beam Laser.
PRIMARY_GUNS = [
    ("000", 1, [0, 1, 2]), ("000", 2, [3, 4, 5, 6]), ("000", 3, [7, 8]),                    # pulse lasers
    ("008", 1, [9]), ("008", 2, [10]), ("008", 3, [11, 228]),                                # M6 beams
    ("003", 2, [183]), ("003", 3, [229]),                                                   # Disruptor, Dark Matter
    ("005", 1, [12, 13, 16]), ("005", 2, [14, 15, 17, 18]), ("005", 3, [19, 20, 21, 231]),  # blasters (EMP too)
    ("006", 1, [22]), ("006", 2, [23]), ("006", 3, [26]),                                   # Micro Guns, Scram Cannon
    ("007", 1, [24]), ("007", 2, [25]),                                                     # railguns
    ("004", 2, [27]), ("004", 3, [230]),                                                    # mass drivers
    ("002", 1, [28]), ("002", 2, [29]), ("002", 3, [30, 193]),                              # thermo guns
    ("001", 1, [176]), ("001", 2, [177]), ("001", 3, [178]),                                # scatter guns
]
PRIMARY_CATEGORIES = [("000", 2, 0), ("005", 2, 1), ("006", 2, 2), ("002", 2, 3), ("001", 2, 25)]   # other (mod) weapons
PRIMARY_DEFAULT = ("000", 1)
TURRET_GUNS = [("006", 1, [47]), ("006", 2, [48]), ("005", 2, [49]), ("004", 1, [180]), ("007", 2, [181]),
               ("004", 3, [182]), ("000", 3, [224]), ("002", 1, [198]), ("002", 2, [199]), ("002", 3, [200])]
TURRET_CATEGORIES = [("002", 2, 35)]
TURRET_DEFAULT = ("006", 2)

# GoF3's own guns as items of their own (items.json), sold in the shops beside GoF2's: each of the nine families in its three
# marks, named and described as GoF3 names them (GuiAttribute), on its own GoF3 gun model and shot sound (the kit rules put
# them first), its projectile, muzzle flash and impact the GoF2 base item's recoloured in the family's GoF3 projectile colour
# (Colorize_Color1 / 2 of its effect material: the textures are named by GUID only), a short tracer of that colour.
# GoF3's numbers don't carry over (its damage is per upgrade level and rises with the player's level), so what does: the
# family's range class (CR 1000 / MR 1500 / LR 2000 m, the gun's reach as a GoF2 projectile's lifetime at its speed), its
# projectile speed (GoF3 m/s / 75 = GoF2 units per ms: 1500 -> 20, GoF2's lasers), its shots per trigger (the Scatter
# Plasma's spread, side by side; the Burst Laser's three-shot salvo) and its character in the table below (a slow heavy
# Plasma Focus, a fast Auto Laser). The damage per second is GoF2's own by tech level: mark 1 at tech 3 like GoF2's tech 3-6
# weapons (12), mark 2 at 6 (24), mark 3 at 9 (45, below the Mimung / Mass Driver MD 12's 70), x1.25 at close range and
# x0.85 at long range; each shot's damage is the table's, its reload what gives that rate.
#   family: (data.pdb name, GoF2 base item (behaviour, look, icon), range m, GoF3 speed m/s (None: a beam), damage per shot by
#            mark, extra stats, colour material, colour key)
GOF3_WEAPONS = {
    "000": ("MR3_BurstLaser", 7, 1500, 1800, (3, 5, 9), {"salvoCount": 3, "salvoGapMs": 70},
            "unique/burstlaser/vfx_projectile_burstlaser_000_sprite", "Colorize_Color1"),
    "001": ("CR1_ScatterPlasma", 12, 1000, 1500, (2, 4, 7), {"salvoShots": 4},
            "unique/scattercannon/vfx_projectile_scattercannon_000_core", "Colorize_Color1"),
    "002": ("LR2_PlasmaFocus", 19, 2000, 2000, (9, 18, 32), {},
            "unique/ioncannon/vfx_projectile_ioncannon_000_sprite", "Colorize_Color1"),
    "003": ("CR3_Dismantler", 24, 1000, 1500, (2, 4, 7), {},
            "unique/ricochetweapon/vfx_projectile_ricochetweapon_000_sprite", "Colorize_Color1"),
    "004": ("MR2_MassDriver", 27, 1500, 1800, (2, 3, 6), {},
            "unique/autocannon/vfx_projectile_autocannon_000_sprite", "Colorize_Color2"),
    "005": ("MR1_PlasmaBlast", 19, 1500, 1700, (4, 7, 12), {},
            "unique/plasmasprayer/vfx_projectile_plasmasprayer_000_sprite", "Colorize_Color1"),
    "006": ("CR2_AutoLaser", 0, 1000, 1500, (2, 3, 6), {},
            "unique/machinegun/vfx_projectile_machinegun_000_sprite", "Colorize_Color2"),
    "007": ("LR3_Railgun", 10, 2000, None, (16, 30, 55), {},
            "unique/railgun/vfx_projectile_railgun_000_sprite", "Colorize_Color1"),
    "008": ("LR1_BeamLaser", 9, 2000, None, (10, 20, 36), {},
            "unique/pulselaser/vfx_projectile_pulselaser_000_p", "Colorize_Color1"),
}
WEAPON_DPS = {1: 12.0, 2: 24.0, 3: 45.0}
WEAPON_TECH = {1: 3, 2: 6, 3: 9}
WEAPON_PRICE = {1: 9000, 2: 32000, 3: 140000}      # (GoF2's weapons of those tech levels and rates)
WEAPON_OCCURRENCE = {1: 25, 2: 15, 3: 8}            # (below GoF2's own: 27 more guns in the shops)
RANGE_DPS = {1000: 1.25, 1500: 1.0, 2000: 0.85}

# The kit's weapon colours (the Customize screen's Weapon colour; the remake's palette "weapons"): GoF3's own projectile colours,
# Colorize_Color1 of each weapon effect's material (assets_best/vfx/projectiles), named after the GoF3 weapon it belongs to.
VFX = os.path.join(ASSETS, "vfx", "projectiles")
WEAPON_COLOURS = [
    ("burst_laser", "Burst Laser", "unique/burstlaser/vfx_projectile_burstlaser_000_sprite"),
    ("pulse_laser", "Pulse Laser", "unique/pulselaser/vfx_projectile_pulselaser_000_p"),
    ("ion_cannon", "Ion Cannon", "unique/ioncannon/vfx_projectile_ioncannon_000_sprite"),
    ("pirate_ion_cannon", "Pirate Ion Cannon", "unique/ioncannon/vfx_projectile_ioncannon_000_sprite_pirate"),
    ("plasma_sprayer", "Plasma Sprayer", "unique/plasmasprayer/vfx_projectile_plasmasprayer_000_sprite"),
    ("emp", "EMP", "unique/emp/vfx_projectile_emp_core"),
    ("ricochet", "Ricochet", "unique/ricochetweapon/vfx_projectile_ricochetweapon_000_sprite"),
    ("scatter_cannon", "Scatter Cannon", "unique/scattercannon/vfx_projectile_scattercannon_000_core"),
    ("amber", "Amber", "generic/000/vfx_projectile_000_sprite_pulsing"),
    ("white", "White", "generic/001/vfx_projectile_001"),
]


# ---------------------------------------------------------------- data.pdb


class Data:
    def __init__(self):
        self.R = Records(PDB)

    def comp(self, rid, name):
        return self.R.resolved(rid)[0].get(name, {})

    def num(self, rid, comp, field):
        v = self.comp(rid, comp).get(field)
        return v[0] if v else None

    def text_of(self, ref):
        tid = self.R.sub(ref).get(1)
        if tid not in self.R.p.recs: return None
        f = self.R.fields(tid).get(3906420)
        return f[0].decode("utf-8", "replace").strip() if f else None

    def gui_text(self, rid, field):
        v = self.comp(rid, "GuiAttribute").get(field)
        return self.text_of(v[0]) if v else None

    def vec(self, rid, comp, field):
        v = self.comp(rid, comp).get(field)
        if not v: return None
        s = self.R.sub(v[0]); return [s.get(k, 0.0) for k in (1, 2, 3)]


def mixed_case(name):
    """All-caps names as the game's texts write them (GROZA -> Groza, SH'GAAL -> Sh'Gaal); roman numerals and R.E.D. stay."""
    def word(w):
        if w in ("R.E.D.",) or re.fullmatch(r"[IVX]+", w) or not w.isupper(): return w
        return "".join(p.capitalize() if p not in ("'", "-") else p for p in re.split(r"(['-])", w))
    return re.sub(r"[^\s]+", lambda m: word(m.group(0)), name.replace('"', "")).strip()


def lerp_log(p, lo, hi):
    t = (math.log(max(p, 1.0)) - math.log(CONVERT["P_LO"])) / (math.log(CONVERT["P_HI"]) - math.log(CONVERT["P_LO"]))
    return t, lo + (hi - lo) * t


# ---------------------------------------------------------------- glTF


def write_glb(path, j, binc):
    js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    binc = bytes(binc) + b"\0" * (-len(binc) % 4)
    open(path, "wb").write(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(binc)) + struct.pack("<II", len(js), 0x4E4F534A)
                           + js + struct.pack("<II", len(binc), 0x004E4942) + binc)


def turned(src, deg, dst):
    """'src' with its scene turned 'deg' degrees about the up axis (a new root node over the scene's nodes), written to 'dst';
    'src' itself when there is no turn."""
    if not deg: return src
    j, b, n = read(src)
    binc = b[28 + n:28 + n + struct.unpack_from("<I", b, 20 + n)[0]]
    scene = j["scenes"][j.get("scene", 0)]
    h = math.radians(deg) / 2
    j["nodes"].append({"name": "turn", "rotation": [0.0, math.sin(h), 0.0, math.cos(h)], "children": scene["nodes"]})
    scene["nodes"] = [len(j["nodes"]) - 1]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    write_glb(dst, j, binc)
    return dst


def slim_glb(src, dst, maxtex, edit=None):
    """A converted .glb for the game: textures scaled to maxtex, the specular / iridescence maps and extensions left out (the
    remake reads base colour, metallic-roughness, normal and emission only); 'edit(j)' may change the JSON (nodes) first."""
    j, b, n = read(src)
    binc = b[28 + n:28 + n + struct.unpack_from("<I", b, 20 + n)[0]]
    if edit: edit(j)
    used = set()
    for m in j.get("materials", []):
        m.get("extensions", {}).pop("KHR_materials_specular", None)
        m.get("extensions", {}).pop("KHR_materials_iridescence", None)
        if "extensions" in m and not m["extensions"]: m.pop("extensions")
        pbr = m.get("pbrMetallicRoughness", {})
        for t in (pbr.get("baseColorTexture"), pbr.get("metallicRoughnessTexture"), m.get("normalTexture"),
                  m.get("emissiveTexture"), m.get("occlusionTexture")):
            if t: used.add(j["textures"][t["index"]]["source"])
    for k in ("extensionsUsed", "extensionsRequired"):
        if k in j:
            j[k] = [e for e in j[k] if e not in ("KHR_materials_specular", "KHR_materials_iridescence")]
            if not j[k]: j.pop(k)
    newdata = {}
    for i, im in enumerate(j.get("images", [])):
        bv = j["bufferViews"][im["bufferView"]]; o = bv.get("byteOffset", 0)
        raw = binc[o:o + bv["byteLength"]]
        if i not in used:
            out = io.BytesIO(); Image.new("RGBA", (1, 1)).save(out, "PNG"); newdata[im["bufferView"]] = out.getvalue(); continue
        img = Image.open(io.BytesIO(raw))
        if max(img.size) > maxtex:
            img = img.resize((max(1, img.width * maxtex // max(img.size)), max(1, img.height * maxtex // max(img.size))), Image.LANCZOS)
            out = io.BytesIO(); img.save(out, "PNG", optimize=True); newdata[im["bufferView"]] = out.getvalue()
    nb = bytearray()
    for i, bv in enumerate(j["bufferViews"]):
        o = bv.get("byteOffset", 0)
        data = newdata.get(i, binc[o:o + bv["byteLength"]])
        while len(nb) % 8: nb.append(0)
        bv["byteOffset"] = len(nb); bv["byteLength"] = len(data); nb += data
    while len(nb) % 4: nb.append(0)
    j["buffers"][0]["byteLength"] = len(nb)
    write_glb(dst, j, nb)


# ---------------------------------------------------------------- floating guns and turrets

SNAP_GAP = 0.05           # GoF3 units: a gun or turret further than this from the hull (with its pylons) is moved onto it
SNAP_SPACING = 0.03       # the surface sampling step for the measurement


def surface_points(path, spacing=SNAP_SPACING):
    """Points on a .glb's LOD0 surfaces (no shadows), glTF space: the vertices and area-weighted samples of every triangle."""
    j, b, n = read(path); W = world(j); out = []
    rng = np.random.default_rng(7)
    for i, nd in enumerate(j["nodes"]):
        name = nd.get("name", "")
        if "mesh" not in nd or i not in W or any(t in name for t in ("LOD1", "LOD2", "shadow")): continue
        for pr in j["meshes"][nd["mesh"]]["primitives"]:
            P = _accessor(j, b, n, pr["attributes"]["POSITION"]).astype(np.float64)
            P = (np.c_[P, np.ones(len(P))] @ W[i].T)[:, :3]
            I = _accessor(j, b, n, pr["indices"]).reshape(-1, 3) if "indices" in pr else np.arange(len(P)).reshape(-1, 3)
            A, B, C = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
            cnt = np.minimum(np.ceil(0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1) / spacing ** 2).astype(int), 400) + 1
            k = np.repeat(np.arange(len(I)), cnt)
            u, v = rng.random(len(k)), rng.random(len(k)); f = u + v > 1; u[f] = 1 - u[f]; v[f] = 1 - v[f]
            out += [P, A[k] + (B[k] - A[k]) * u[:, None] + (C[k] - A[k]) * v[:, None]]
    return np.concatenate(out) if out else np.zeros((0, 3))


JOB_GB = 1.0              # what one hull's worker adds at its peak (one worker 1.1 GB in all, four the same)


def jobs():
    """Workers for the per-hull steps: --jobs, else half the CPUs, fewer when the memory available is short (JOB_GB each,
    4 GB kept back). Every core at once froze the whole machine (2026-10-24, no out-of-memory kill logged: the build
    held under 3 GB); four take the build from 251 s to 67 s with the same output. The process also runs at a lower
    priority (main), so the desktop stays usable."""
    if JOBS: return max(1, JOBS)
    try:
        avail = next(int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemAvailable:")) / 1024 ** 2
    except (OSError, StopIteration):
        avail = 8.0
    return max(1, min((os.cpu_count() or 4) // 2, int((avail - 4) / JOB_GB)))


GUN_POINTS = 3000         # each gun model's surface thinned to this many points for the check (their spacing stays well
                          # under SNAP_GAP; the full 25 000-70 000 made it the build's slowest step by far)


def snap_floating_mounts(ships, parts, rules):
    """Guns and turrets that would float: GoF3's hardpoints are made for one gun each (a boss's for its big gun, a turret
    socket for its own large base), and the kit hangs whichever GoF3 gun a GoF2 weapon maps to (or the remake's turret) on
    them. Each primary and turret mount's gap to the hull (its pylons included) is measured with every gun model it may
    carry (the turret base for a turret), and a mount whose median gap is over SNAP_GAP is moved that far toward the hull
    along the gap, in steps (the Cronus' wing guns 0.57 units out, the Krotac's lower turret socket 3.7). The hulls are
    checked in parallel (SciPy's KD-tree queries let go of the GIL)."""
    try:
        from scipy.spatial import cKDTree
    except ImportError:
        print("scipy isn't installed: floating guns and turrets not checked"); return
    guns = sorted({r["model"] for r in rules if r.get("slot") == "primary"})
    rng = np.random.default_rng(11)
    def thin(P): return P if len(P) <= GUN_POINTS else P[rng.choice(len(P), GUN_POINTS, replace=False)]
    G = {f: thin(surface_points(os.path.join(OUT, f), 0.02)) for f in guns + ["turret/turret.glb"]}
    by_id = {p["id"]: p for p in parts}
    def check(s):
        log = []
        hull = surface_points(os.path.join(OUT, by_id[s["id"]]["model"]))
        if not len(hull): return log
        tree = cKDTree(hull)
        for m in s["mounts"]:
            if m["slotType"] not in (0, 2): continue
            models = guns if m["slotType"] == 0 else ["turret/turret.glb"]
            r = m.get("rotation"); x, y, z, w = r if r else (0.0, 0.0, 0.0, 1.0)
            R = quat_matrix(-x, -y, z, w)   # (the remake's mount turn back in glTF space, ship_rotation's mirror)
            if m.get("upsideDown"): R = R @ np.diag([-1.0, -1.0, 1.0])
            p = np.array([-m["position_engine"][0], m["position_engine"][1], -m["position_engine"][2]], dtype=float) / K
            moved = np.zeros(3)
            for _ in range(4):
                gaps, dirs = [], []
                for f in models:
                    g = G[f] @ R.T + p + moved
                    d, idx = tree.query(g)
                    k = int(np.argmin(d)); gaps.append(float(d[k]))
                    dirs.append((hull[idx[k]] - g[k]) / max(1e-9, d[k]))
                med = float(np.median(gaps))
                if med <= SNAP_GAP: break
                dvec = np.mean(dirs, axis=0); dvec /= max(1e-9, np.linalg.norm(dvec))
                moved += dvec * (med - 0.5 * SNAP_GAP)
            if np.linalg.norm(moved) > 1e-6:
                q = p + moved
                log.append(f"{s['id']}: {'gun' if m['slotType'] == 0 else 'turret'} at {m['position_engine']} moved "
                           f"{np.linalg.norm(moved):.2f} units onto the hull")
                m["position_engine"] = [round(-q[0] * K), round(q[1] * K), round(-q[2] * K)]
        return log
    with ThreadPoolExecutor(jobs()) as ex:
        for log in ex.map(check, ships):
            for line in log: print(line)


def quat_matrix(x, y, z, w):
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def world(j):
    """Every node's world matrix (glTF space)."""
    nodes = j["nodes"]; W = {}
    def walk(i, P):
        W[i] = P @ trs(nodes[i])
        for c in nodes[i].get("children", []): walk(c, W[i])
    for root in j["scenes"][j.get("scene", 0)]["nodes"]: walk(root, np.eye(4))
    return W


def quat_of(M):
    """The rotation of a 3x3 matrix (scale removed) as a quaternion [x, y, z, w]."""
    R = M[:3, :3] / np.cbrt(abs(np.linalg.det(M[:3, :3])))
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2; w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([x, y, z, w]); return q / np.linalg.norm(q)


def ship_rotation(M):
    """A hardpoint's turn as the remake's mount "rotation" (the ship model's frame: glTF (x, y, z) -> (x, y, -z), a mirror,
    so the quaternion (x, y, z, w) becomes (-x, -y, z, w)); None when it is (nearly) none."""
    x, y, z, w = quat_of(M)
    q = np.array([-x, -y, z, w])
    if q[3] < 0: q = -q
    return None if q[3] > 0.99999 else [round(float(v), 5) for v in q]


def game(p): return [round(-p[0] * K), round(p[1] * K), round(-p[2] * K)]


def centreline_turn(q):
    """An engine on the centreline: its turn without the sideways part (the quaternion's y, about the up axis), None when
    nothing is left. A centred nozzle has no side to angle to: the K'ssshar Ka's centre helper carries its right engine's
    8.5 deg outward turn (copied from it), so its plume veered off to one side."""
    x, y, z, w = q
    n = math.sqrt(x * x + z * z + w * w)
    if n < 1e-6: return None
    r = [x / n, 0.0, z / n, w / n]
    if r[3] < 0: r = [-v for v in r]
    return None if r[3] > 0.99999 else [round(float(v), 5) for v in r]


def outline_plausible(points, r):
    """Whether a measured nozzle outline (glTF units around its mount) can stand for a nozzle of mean half size 'r': its
    mean radius at least half of it and its centre within 1.5 x it (a nozzle may sit a little off its helper; the remake
    centres the effect on it). The Vossk nozzle rings light only a few scattered pixels hot enough, which gave slivers a
    fifth of the nozzle across beside it (the Shaan'ra-Grth's); a few others caught a lit panel beside the hull."""
    P = np.asarray(points, dtype=float)
    if len(P) < 3: return False
    c = P.mean(0)
    return float(np.linalg.norm(P - c, axis=1).mean()) >= 0.5 * r and float(np.linalg.norm(c)) <= 1.5 * r


def outline_game(points):
    """A nozzle outline (glTF units around its mount) as a mount's "outline": [x0, y0, x1, y1, ...] in game units, position_engine's axes."""
    return [v for x, y in points for v in (round(-x * K, 1), round(y * K, 1))]


def hull_points(path):
    """The hull's LOD0 body vertices (glTF space)."""
    j, b, n = read(path); W = world(j); out = []
    for i, nd in enumerate(j["nodes"]):
        if "mesh" not in nd or not nd["name"].endswith("_LOD0"): continue
        for prim in j["meshes"][nd["mesh"]]["primitives"]:
            if not j["materials"][prim.get("material", 0)]["name"].endswith("_body"): continue
            P = _accessor(j, b, n, prim["attributes"]["POSITION"]).astype(np.float64)
            out.append((np.c_[P, np.ones(len(P))] @ W[i].T)[:, :3])
    return np.concatenate(out) if out else np.zeros((0, 3))


# ---------------------------------------------------------------- engines (GoF3's engine effect: the remake's "engineFx")

# Each ship's EngineAttachment names its engine effect (NivelianEngine -> /assets/vfx/engines/nivelian/vfx_engine_nivelian_000
# .ae4scene: a flare "glow_mesh", the exhaust, a spiral) and its VfxList a trail (TrailNivelian -> the Fork particle system
# particles/ship_engine_nivelian.psb). The remake draws both as GoF3 does (EngineFx): the scene's parts with their own meshes,
# textures and shader options (engine_meshes.py) and the Fork emitters (fork_psb.py). (Until 2026-10-24 the remake drew an
# imitation from three PNGs: flare and cone cards, a ribbon helix and wavering streams; gone with its settings.)
ENGINE_VFX = os.path.join(ASSETS, "vfx", "engines")
PARTICLES = os.path.join(MERGED, "particles")
ENGINE_RACE = {"NivelianEngine": "nivelian", "TerranEngine": "terran", "VosskEngine": "vossk", "InouacEngine": "inouac"}
# The nozzle radius each engine effect is drawn for (game units; the engineFx's "nozzle": the remake sizes exhaust styles
# against it, on these ships and as styles on others), measured on the hulls in the remake from behind: the Nivelian exhaust
# fills its nozzles (the Atauno Rheep's hexagons ~85-95 against its 87), the Terran one overhangs them a little (the Argus'
# 75-110 against 138), the Vossk one by about three times (the K'ssshar Ka's ~46, the Shaan'ra-Grth's ~34). The engine_glows
# measurement is only the hottest core of each nozzle's glow, 1 to 5 x smaller, so it can't give this. Others: their exhaust
# mesh's radius (engine_nozzle). The Nivelian 60, not its exhaust's 87: as a style on other ships (the game's Phantom) it came
# out the smallest of the three, its glare dimmer than the Terran one (the user's report, 2026-10-24); 87 / 1.45 matched by eye.
ENGINE_NOZZLE = {"nivelian": 60, "terran": 100, "vossk": 45}


def decode_texture(path, png):
    subprocess.run([sys.executable, os.path.join(HERE, "ae4_texture.py"), path, png], check=True, capture_output=True)


MESH_GLOW = 1.0   # GoF3's engines' brightness in the remake (engineFx "meshGlow")
_fork_emitters = {}


def fork_emitter(name):
    """A Fork particle file's (romfs particles/<name>.psb) first emitter as the remake's CustomForkEmitter (fork_psb: life,
    sizes, colour keys, rate, its texture written once to fx/particles/), None when it isn't there."""
    if name in _fork_emitters: return _fork_emitters[name]
    import fork_psb
    path = os.path.join(PARTICLES, name + ".psb")
    ems = fork_psb.read(path) if os.path.exists(path) else []
    out = None
    if ems and ems[0].get("texture"):
        e = ems[0]
        src = next(iter(sorted(glob.glob(os.path.join(PARTICLES, e["texture"] + ".*.ae4texture")))), None)
        if src:
            rel = f"fx/particles/{e['texture']}.png"
            dst = os.path.join(OUT, rel)
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                decode_texture(src, dst)
            out = {"texture": rel, "life": e["life"], "sizeStart": e["sizeStart"], "sizeMid": e["sizeMid"], "sizeEnd": e["sizeEnd"],
                   "sizeMidTime": e["sizeMidTime"], "colors": [round(v, 4) for c in e["colors"] for v in c],
                   "colorTimes": e["colorTimes"], "rate": e["rate"], "max": int(e["max"]),
                   **({"local": True} if int(e["flags"], 16) & 0x20000 else {})}
    _fork_emitters[name] = out
    return out
_engine_meshes = {}


def engine_nozzle(rel, body):
    """The nozzle radius (game units) an engine file (fx/engines/<name>.json) is drawn for: its part 'body''s (name ending
    so) widest reach from the axis, x its scale, x K; None without it."""
    try: parts = json.load(open(os.path.join(OUT, rel)))["parts"]
    except (OSError, ValueError, KeyError): return None
    for p in parts:
        if p.get("sprite") or not p["name"].endswith(body): continue
        V = np.asarray(p["v"], dtype=float).reshape(-1, 3) * np.asarray(p.get("scale", [1, 1, 1]), dtype=float)
        return round(float(np.hypot(V[:, 0], V[:, 1]).max()) * K)
    return None


def engine_fx(fx_name):
    """The ships.json "engineFx" for a GoF3 engine effect as GoF3 draws it (engine_meshes: its scene's parts with their own
    meshes, textures and shader options): "meshes", its scale, the nozzle it is drawn for. None when it isn't known or has
    no scene."""
    race = ENGINE_RACE.get(fx_name)
    if race is None: return None
    if race not in _engine_meshes:
        import engine_meshes
        rel = engine_meshes.build(OUT, ASSETS, MERGED, f"vfx/engines/{race}/vfx_engine_{race}_000.ae4scene", f"engine_{race}")
        nozzle = ENGINE_NOZZLE.get(race) or (engine_nozzle(rel, "exhaust") if rel else None)
        _engine_meshes[race] = {"meshes": rel, "meshScale": round(K, 3), "meshGlow": MESH_GLOW, **({"nozzle": nozzle} if nozzle else {})} if rel else None
    return dict(_engine_meshes[race]) if _engine_meshes[race] else None


# GoF3's engines as exhaust styles any ship can wear (exhausts.json: the remake's Customize screen, ModExhausts), drawn as GoF3
# draws them (its own meshes and particles, in its own colours unless the build picks others): the fighters' Nivelian (with
# its helix), Terran and Vossk engines with their trails and booster flashes, and the capital ships' three.
EXHAUST_STYLES = [("NivelianEngine", "nivelian", "GoF3 Nivelian drive"), ("TerranEngine", "terran", "GoF3 Terran drive"),
                  ("VosskEngine", "vossk", "GoF3 Vossk drive")]
LARGE_STYLES = [("terran", "terran_large", "GoF3 Terran capital drive"), ("nivelian", "nivelian_large", "GoF3 Nivelian capital drive"),
                ("vossk", "vossk_large", "GoF3 Vossk capital drive")]
# Each engine's trail: the Fork system its race's ships carry (data.pdb's TrailNivelian / TrailTerran / TrailVossk name these).
STYLE_TRAIL = {"nivelian": "ship_engine_nivelian", "terran": "ship_engine_pirate", "vossk": "ship_engine_nivelian"}
EXHAUST_COLOURS = [("terran", "Terran blue", "TerranEngine"), ("terran_large", "Terran orange", "TerranEngineLarge"),
                   ("nivelian", "Nivelian cyan", "NivelianEngine"), ("nivelian_large", "Nivelian blue", "NivelianEngineLarge"),
                   ("vossk", "Vossk green", "VosskEngine"), ("inouac", "Inouac teal", "InouacEngine"), ("pirate", "Pirate red", "PirateEngine")]
EXHAUST_EXTRA = [("helix", "Helix blue", (0.216, 0.557, 1.0)), ("violet", "Violet", (0.61, 0.3, 1.0)), ("gold", "Gold", (1.0, 0.78, 0.25)),
                 ("white", "White", (0.95, 0.97, 1.0))]


def exhaust_styles():
    """exhausts.json: GoF3's fighter engines (with their trails and booster flashes) and its capital engines as exhaust
    styles."""
    import capitals
    hexrgb = lambda c: "#%02X%02X%02X" % tuple(round(255 * float(x)) for x in c)
    palette = [{"id": i, "name": n, "color": hexrgb(ENGINE_FX[f][0])} for i, n, f in EXHAUST_COLOURS]
    palette += [{"id": i, "name": n, "color": hexrgb(c)} for i, n, c in EXHAUST_EXTRA]
    out = []
    for fx_name, sid, name in EXHAUST_STYLES:
        fx = engine_fx(fx_name)
        if not fx: continue
        race = ENGINE_RACE[fx_name]
        trail = fork_emitter(STYLE_TRAIL[race])
        boost = fork_emitter(f"ad_engine_booster_{race}")
        fx = {**fx, **({"trailParticles": trail} if trail else {}), **({"boostParticles": boost} if boost else {})}
        helix = race == "nivelian"
        out.append({"id": sid, "name": name, "engineFx": fx, "palette": palette, "mainName": "Engine colour",
                    "secondName": "Helix and trail colour" if helix else "Trail colour"})
    for race, sid, name in LARGE_STYLES:
        fx = capitals.large_engine_fx(OUT, ASSETS, race, MERGED)
        if not fx: continue
        nozzle = engine_nozzle(fx["meshes"], f"large_{race}")
        out.append({"id": sid, "name": name, "engineFx": {**fx, **({"nozzle": nozzle} if nozzle else {})}, "palette": palette,
                    "mainName": "Engine colour", "secondName": "Second colour"})
    return out


# ---------------------------------------------------------------- icons

ICON_SCRIPT = r'''
import bpy, sys, mathutils
glb, out = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in sc.objects if o.type == "MESH" and "shadow" not in o.name]
for o in sc.objects:
    if o.type == "MESH" and o not in objs: o.hide_render = True
pts = [o.matrix_world @ mathutils.Vector(c) for o in objs for c in o.bound_box]
lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
c = (lo + hi) / 2; r = (hi - lo).length / 2
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = r * 2.1; cam.data.clip_end = r * 10
d = mathutils.Vector((1.0, 0.45, 0.75)).normalized()
cam.location = c + d * r * 4
cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
for i, (v, e) in enumerate([((0.7, -0.3, 1.0), 4.5), ((-0.8, 0.5, 0.4), 1.8), ((1.0, 0.2, -0.3), 1.2)]):
    l = bpy.data.objects.new(f"s{i}", bpy.data.lights.new(f"s{i}", "SUN")); l.data.energy = e; sc.collection.objects.link(l)
    l.rotation_euler = mathutils.Vector(v).to_track_quat("Z", "Y").to_euler()
w = bpy.data.worlds.new("w"); sc.world = w; w.color = (0.55, 0.58, 0.65)
eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in eng else "BLENDER_EEVEE"
sc.render.film_transparent = True; sc.render.resolution_x = 720; sc.render.resolution_y = 720
sc.render.image_settings.color_mode = "RGBA"; sc.render.filepath = out
bpy.ops.render.render(write_still=True)
'''


_plate = None
def plate():
    """The game's ship frame (image 1276 of the remake's interface atlas) when a checkout of the remake's source is at hand,
    else a drawn look-alike (the ES2 importer's)."""
    global _plate
    if _plate is None:
        if os.path.exists(PLATE):
            a = Image.open(PLATE).convert("RGBA")
            x, y, w, h = PLATE_RECT
            _plate = Image.new("RGBA", (180, 88), (0, 0, 0, 0)); _plate.alpha_composite(a.crop((x, y, x + w, y + h)), (1, 1))
        else:
            _plate = drawn_plate()
    return _plate.copy()


def drawn_plate():
    """The ship frame drawn to its measurements: a dark plate with corners rounded 9 px, scanlines 2 rows bright / 2 at 70 %,
    narrow brighter diagonal bands every 48 px leaning right, blue (green 0.66 of the blue) brightest in the middle and fading
    to black at both ends."""
    w, h = PLATE_RECT[2], PLATE_RECT[3]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    band = ((x + 0.55 * y) % 48.0) < 21.0
    scan = np.where((y.astype(int) // 2) % 2 == 0, 1.0, 0.7)
    env = np.sin(np.pi * np.clip((x + 0.5) / w, 0, 1)) ** 1.1
    blue = 0.34 * env * np.where(band, 1.0, 0.62) * scan
    alpha = np.where(band, 0.38, 0.45)
    pm = np.stack([0 * blue, 0.66 * blue, blue], -1)
    r = 9.0
    cx, cy = np.clip(x, r, w - 1 - r), np.clip(y, r, h - 1 - r)
    alpha = alpha * np.clip(r + 0.5 - np.hypot(x - cx, y - cy), 0, 1)
    rgb = np.where(alpha[..., None] > 0, pm / np.maximum(alpha[..., None], 1e-3), 0)
    img = np.dstack([np.clip(rgb * 255, 0, 255), alpha * 255]).astype(np.uint8)
    out = Image.new("RGBA", (180, 88), (0, 0, 0, 0)); out.alpha_composite(Image.fromarray(img, "RGBA"), (1, 1))
    return out


def icon(render_png, out_png):
    shot = Image.open(render_png).convert("RGBA")
    shot = shot.crop(shot.getbbox() or (0, 0, shot.width, shot.height))
    s = min(170 / shot.width, 80 / shot.height)
    shot = shot.resize((max(1, round(shot.width * s)), max(1, round(shot.height * s))), Image.LANCZOS)
    p = plate(); p.alpha_composite(shot, ((180 - shot.width) // 2, (88 - shot.height) // 2)); p.save(out_png)


# ---------------------------------------------------------------- the turret (Blender)

# GoF3 player ships have no turret: the kit's is built from GoF3 parts: the generic weapon mount (the hull's gun pylon) as a
# flat socket and, turned larger, as the swivel ("pivot"); the turret item's GoF3 gun goes on the "gun" node on top
# (ModHardpoints: a turret without a muzzle takes the gun's own). Exported as glTF, nose -Z like the hulls.
TURRET_SCRIPT = r'''
import bpy, sys, mathutils
src, mesh_name, out = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=src)
mount = next(o for o in sc.objects if o.type == "MESH" and o.name.startswith(mesh_name))
data = mount.data
for o in list(sc.objects): bpy.data.objects.remove(o, do_unlink=True)
zs = [v.co.z for v in data.vertices]   # Blender: z up (glTF y)
lo, hi = min(zs), max(zs)
def obj(name, mesh=None, parent=None, loc=(0, 0, 0), scale=(1, 1, 1)):
    o = bpy.data.objects.new(name, mesh); sc.collection.objects.link(o)
    o.parent = parent; o.location = loc; o.scale = scale
    return o
root = obj("gof3_turret")
base_s = (2.3, 2.3, 0.55)
obj("socket", data, root, (0, 0, -lo * base_s[2]), base_s)
top = (hi - lo) * base_s[2]
pivot = obj("pivot", None, root, (0, 0, top))
piv_s = 1.7
obj("swivel", data, pivot, (0, 0, -lo * piv_s), (piv_s, piv_s, piv_s))
obj("gun", None, pivot, (0, 0, (hi - lo) * piv_s - 0.25))
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False, export_apply=False)
'''


def build_turret(out_glb):
    src = os.path.join(CONV, "ship_terran_000", "ship_terran_000.glb")
    tmp = os.path.join(OUT, ".turret"); os.makedirs(tmp, exist_ok=True)
    script = os.path.join(tmp, "turret.py"); open(script, "w", encoding='utf-8').write(TURRET_SCRIPT)
    raw = os.path.join(tmp, "turret_raw.glb")
    r = subprocess.run([BLENDER, "-b", "-P", script, "--", src, "ship_terran_000_weapon_mount_000_mesh", raw],
                       capture_output=True, text=True)
    if not os.path.exists(raw): sys.exit("turret: Blender failed\n" + r.stdout[-3000:] + r.stderr[-3000:])
    slim_glb(raw, out_glb, 512)
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- guns


def gun_file(family, mk): return f"guns/weapon_generic_{family}_mk{mk}.glb"


def build_gun(family, mk):
    """A GoF3 gun as a hardpoint model: the converted .glb (LOD0) with a centred "muzzle" node at its barrels' mean (the
    remake fires from the node whose name starts with "muzzle"; the barrel tips become "barrel_NNN")."""
    src = os.path.join(GUNS, f"weapon_generic_{family}", f"weapon_generic_{family}_mk{mk}.glb")
    def edit(j):
        W = world(j); tips = []
        for i, nd in enumerate(j["nodes"]):
            m = re.search(r"_muzzle_(\d{3})$", nd["name"])
            if m: tips.append(W[i][:3, 3]); nd["name"] = "barrel_" + m.group(1)
        root = j["scenes"][j.get("scene", 0)]["nodes"][0]
        c = np.mean(tips, axis=0) if tips else np.zeros(3)
        Wr = W[root]; local = np.linalg.inv(Wr) @ np.r_[c, 1.0]
        j["nodes"].append({"name": "muzzle", "translation": [round(float(v), 5) for v in local[:3]]})
        j["nodes"][root].setdefault("children", []).append(len(j["nodes"]) - 1)
    slim_glb(src, os.path.join(OUT, gun_file(family, mk)), 512, edit)


PRICE_SKIP = {13, 14, 15, 37, 44, 50, 51, 53}


def price_features(equipment, primary, secondary, turret, armor, cargo, handling):
    return [1.0, equipment, equipment * equipment, primary, secondary, turret, armor / 100, cargo / 100, handling / 100]


# gof2_price_fits' result on the remake's ship tables of 2026-10-11 (56 GoF2 ships each, median error x1.23): used when
# no checkout of the remake's source is at hand.
PRICE_FITS = {"android": [6.58251, 0.66334, -0.01552, 0.45451, 0.01794, 0.10794, 0.03309, 0.15971, 0.22253],
              "default": [6.16489, 0.69924, -0.01515, 0.49339, 0.0236, 0.14465, 0.06074, 0.19484, 0.37301]}


def gof2_price_fits():
    """How GoF2 prices its ships, per economy: log(price) = a + b E + c E^2 + d primary + e secondary + f turret + g armor/100
    + h cargo/100 + k handling/100 (E = equipment slots), least squares over its sold ships. Chosen by leave-one-out cross-
    validation over simpler models (one rate per equipment slot, all weapon slots together, armor at a fixed weight): it
    predicts an unseen GoF2 ship within x1.27 (median), they x1.31-1.48. What it says: equipment slots weigh most, on a curve
    (about x1.65 a slot at 5, x1.24 at 14: GoF2's prices flatten at the top); each primary slot about x1.58; a turret slot
    x1.11; a secondary slot next to nothing; armor +3 % per 100 (it rises with the slots, so the slots carry its price);
    cargo and handling a little. Returns {"android": [...], "default": [...]} (the coefficients) and prints the fit."""
    if not os.path.exists(os.path.join(REMAKE, "Assets/Resources/GoF2Data/ships.json")):
        print("price fits: no remake checkout (GOF3_REMAKE), the built-in fits", flush=True)
        return dict(PRICE_FITS)
    ships = json.load(open(os.path.join(REMAKE, "Assets/Resources/GoF2Data/ships.json"), encoding='utf-8-sig'))
    ships = ships["ships"] if isinstance(ships, dict) else ships
    android = {s["index"]: dict(E=s["slots"]["equipment"], P=s["slots"]["primary"], S=s["slots"]["secondary"], T=s["slots"]["turret"],
                                armor=s["armor"], cargo=s["cargo"], handling=s["handling"], price=s["price"]) for s in ships}
    default = {i: dict(v) for i, v in android.items()}
    for d in json.load(open(os.path.join(REMAKE, "Assets/Resources/GoF2Data/economy_default.json"), encoding='utf-8-sig'))["ships"]:
        if d["index"] in default:
            default[d["index"]].update(E=d["equipment"], P=d["primary"], S=d["secondary"], T=d["turret"], armor=d["armor"],
                                       cargo=d["cargo"], handling=d["handling"], price=d["price"])
    fits = {}
    for name, table in (("android", android), ("default", default)):
        rows = [v for i, v in table.items() if i not in PRICE_SKIP and v["price"] > 0]
        X = np.array([price_features(r["E"], r["P"], r["S"], r["T"], r["armor"], r["cargo"], r["handling"]) for r in rows])
        y = np.log([r["price"] for r in rows])
        w = np.linalg.lstsq(X, y, rcond=None)[0]
        err = float(np.exp(np.median(np.abs(X @ w - y))))
        fits[name] = [round(float(v), 5) for v in w]
        print(f"price fit ({name}, {len(rows)} GoF2 ships, median error x{err:.2f}):", fits[name], flush=True)
    return fits


def weapon_palette():
    """The kit's "weapons" palette: [{id, name, color "#RRGGBB"}] from the GoF3 effect materials' Colorize_Color1."""
    import ae4_material
    out = []
    for cid, name, mat in WEAPON_COLOURS:
        v, _ = ae4_material.read(os.path.join(VFX, mat + ".ae4material"))
        c = v.get("Colorize_Color1")
        if not c or not all(0.0 <= x <= 1.0 for x in c[:3]): sys.exit(f"weapon colour {cid}: no Colorize_Color1 in {mat}")
        out.append({"id": cid, "name": name, "color": "#" + "".join(f"{round(x * 255):02X}" for x in c[:3])})
    return out


def with_sounds(rules, snd):
    """The kit's rules with GoF3's gun and launcher sounds (gof3_sounds), by each rule's gun family."""
    for r in rules:
        kind = r.pop("_launcher", None)
        if not snd or r["slot"] == "turret" and (set(r.get("items", [])) & {198, 199, 200} or 35 in r.get("categories", [])):
            continue   # (the plasma collectors fire nothing)
        m = re.search(r"weapon_generic_(\d{3})", r.get("model", ""))
        sound = snd.launcher(kind) if kind else snd.weapon(m.group(1)) if m else None
        if sound: r["sound"] = sound
    return rules


def weapon_id(family, mk):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", "_", GOF3_WEAPONS[family][0].split("_", 1)[1]).lower() + f"_{mk}"


def weapon_name(raw):
    """GoF3's all-caps weapon names in GoF2's way: brands and words written in capitals stay so when they are short (AMR,
    XCY, SR, LR, II, XN, KAT.), the others mixed case per hyphen part (P-BLAST -> P-Blast, AUTO-L -> Auto-L)."""
    def word(w):
        if len(re.sub(r"[^A-Za-z]", "", w)) <= 3: return w
        return "-".join(p if len(p) <= 1 else p[:1] + p[1:].lower() for p in w.split("-"))
    return " ".join(word(w) for w in raw.split())


def weapon_items(D, snd):
    """items.json: GoF3's guns (GOF3_WEAPONS), each mark its own item."""
    import ae4_material
    out = []
    for fam, (rec, base, rng, speed, dmg, extra, mat, key) in GOF3_WEAPONS.items():
        v, _ = ae4_material.read(os.path.join(VFX, mat + ".ae4material"))
        c = v.get(key)
        if not c: sys.exit(f"weapon {rec}: no {key} in {mat}")
        colour = "#" + "".join(f"{round(min(1.0, max(0.0, x)) * 255):02X}" for x in c[:3])
        shot = snd.item_shot(fam) if snd else None
        names = {}
        for mk in (1, 2, 3):
            rn = next((n for n in (f"PW_{rec}_{mk}", f"PW_{rec}_{mk}_DuplicateActive", f"PW_{rec}_{mk}_DuplicateOff",
                                   f"PW_{rec}_{mk}_Original") if n in D.R.p.byname), None)
            if rn is None: sys.exit(f"weapon {rec} mark {mk}: no record")
            rid = D.R.p.byname[rn][0]
            name = weapon_name(D.gui_text(rid, 4067579) or rec)
            if mk == 3 and name == names.get(2):   # (GoF3 names several mark 3s as their mark 2: its XN marks those it tells apart)
                name = re.sub(r"\s+II$", "", name) + " XN"
            names[mk] = name
            dps = WEAPON_DPS[mk] * RANGE_DPS[rng]
            per_shot = dmg[mk - 1] * extra.get("salvoShots", 1) * extra.get("salvoCount", 1)
            reload = per_shot * 1000.0 / dps - (extra.get("salvoCount", 1) - 1) * extra.get("salvoGapMs", 0)
            stats = {"damage": dmg[mk - 1], "loadingTimeMs": int(round(reload / 10.0)) * 10}
            if speed:
                u = round(speed / 75.0)
                stats["projectileSpeed"] = u
                stats["range"] = int(round(rng / (u * 0.05) / 50.0)) * 50   # (the lifetime that reaches it)
            stats.update(extra)
            fx = {"projectile": {"color": colour}, "muzzle": {"color": colour}, "impact": {"color": colour}}
            if speed: fx["trail"] = {"color": colour, "width": 18, "length": 110}
            if shot: fx["shot"] = shot
            item = {"id": weapon_id(fam, mk), "base": base, "name": name, "techLevel": WEAPON_TECH[mk],
                    "occurrence": WEAPON_OCCURRENCE[mk], "price": [WEAPON_PRICE[mk], int(WEAPON_PRICE[mk] * 1.05)],
                    "stats": stats, "fx": fx}
            desc = D.gui_text(rid, 9934023)
            if desc: item["description"] = re.sub(r"\s+", " ", desc).strip()
            out.append(item)
    return out


def weapon_rules():
    # GoF3's own guns first (the rules below match items based on theirs too)
    rules = [{"slot": "primary", "model": gun_file(f, mk), "items": [f"{MOD_ID}:{weapon_id(f, mk)}"]}
             for f in GOF3_WEAPONS for mk in (1, 2, 3)]
    rules += [{"slot": "primary", "model": gun_file(f, mk), "items": items} for f, mk, items in PRIMARY_GUNS]
    rules += [{"slot": "primary", "model": gun_file(f, mk), "categories": [cat]} for f, mk, cat in PRIMARY_CATEGORIES]
    rules.append({"slot": "primary", "model": gun_file(*PRIMARY_DEFAULT)})
    # the launchers have no model; GoF2's rockets (4) and its missiles and cluster missiles (5, 40) get GoF3's launch sounds
    rules.append({"slot": "secondary", "model": "", "categories": [4], "_launcher": "rocket"})
    rules.append({"slot": "secondary", "model": "", "categories": [5, 40], "_launcher": "homing"})
    rules.append({"slot": "secondary", "model": ""})
    rules += [{"slot": "turret", "model": gun_file(f, mk), "items": items} for f, mk, items in TURRET_GUNS]
    rules += [{"slot": "turret", "model": gun_file(f, mk), "categories": [cat]} for f, mk, cat in TURRET_CATEGORIES]
    rules.append({"slot": "turret", "model": gun_file(*TURRET_DEFAULT)})
    return rules


# ---------------------------------------------------------------- skins


@functools.lru_cache(maxsize=None)
def file_hash(p): return hashlib.md5(open(p, "rb").read()).hexdigest() if p and os.path.exists(p) else None   # (asked again and again)


def scaled(img, maxtex):
    if max(img.size) > maxtex:
        img = img.resize((max(1, img.width * maxtex // max(img.size)), max(1, img.height * maxtex // max(img.size))), Image.LANCZOS)
    return img


class SkinWriter:
    """Writes each skin texture once (by its source content and kind; many schemes share a file). The hulls are built in
    parallel, so the first to reach a texture encodes it under a temporary name and every hull gets a placeholder; finish()
    then puts the file under the smallest of the paths asked for and fills the placeholders in, so a build doesn't depend
    on which thread came first (it did: the same texture landed in another hull's folder from run to run)."""
    def __init__(self):
        self.done = {}
        self.lock = threading.Lock()

    def write(self, src, kind, rel):
        key = (file_hash(src), kind)
        rel += ".jpg" if kind == "color" else ".png"
        with self.lock:
            entry = self.done.get(key)
            if entry:
                entry["best"] = min(entry["best"], rel)
                return entry["token"]
            n = len(self.done)
            entry = self.done[key] = {"token": f"\0skin{n}\0", "best": rel,
                                      "tmp": os.path.join(OUT, ".skin_tmp", f"{n}{os.path.splitext(rel)[1]}")}
        os.makedirs(os.path.dirname(entry["tmp"]), exist_ok=True)
        dst = entry["tmp"]
        img = Image.open(src)
        if kind == "color":          # base colour / emission: opaque, JPG
            scaled(img.convert("RGB"), MAXTEX).save(dst, "JPEG", quality=90, optimize=True)
        elif kind == "alpha":        # glass / decals: their alpha matters
            scaled(img.convert("RGBA"), MAXTEX).save(dst, "PNG", optimize=True)
        elif kind == "ms":           # glTF roughness (G) -> URP Lit metallic / smoothness (R 0, A 1 - roughness); metallicFactor 0
            g = np.asarray(scaled(img.convert("RGB"), MAXTEX), dtype=np.uint8)[:, :, 1]
            a = np.zeros(g.shape + (4,), dtype=np.uint8); a[:, :, 3] = 255 - g
            Image.fromarray(a, "RGBA").save(dst, "PNG", optimize=True)
        return entry["token"]

    def finish(self, skins):
        """Moves every texture to its path and puts the paths into the skins (their placeholders)."""
        paths = {}
        for entry in self.done.values():
            dst = os.path.join(OUT, entry["best"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(entry["tmp"], dst)
            paths[entry["token"]] = entry["best"]
        def fill(v):
            if isinstance(v, dict): return {k: fill(x) for k, x in v.items()}
            if isinstance(v, list): return [fill(x) for x in v]
            return paths.get(v, v) if isinstance(v, str) else v
        skins[:] = fill(skins)
        shutil.rmtree(os.path.join(OUT, ".skin_tmp"), ignore_errors=True)
        root = os.path.join(OUT, "skins")   # a hull folder whose textures all went to another hull's
        for d in os.listdir(root) if os.path.isdir(root) else []:
            if os.path.isdir(os.path.join(root, d)) and not os.listdir(os.path.join(root, d)): os.rmdir(os.path.join(root, d))


def glb_image(path, role):
    """The image (bytes hash, PIL) of a converted ship .glb's material of a role ("decals" / "glass": its base colour)."""
    j, b, n = read(path)
    binc = b[28 + n:]
    for m in j.get("materials", []):
        bc = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if not bc: continue
        im = j["images"][j["textures"][bc["index"]]["source"]]
        if role == "decals" and not im.get("name", "").startswith("ship_decals"): continue
        if role == "glass" and "glass" not in im.get("name", ""): continue
        bv = j["bufferViews"][im["bufferView"]]; o = bv.get("byteOffset", 0)
        raw = binc[o:o + bv["byteLength"]]
        return hashlib.md5(raw).hexdigest(), raw
    return None, None


def skins_of(base, man, sw, engine_colour):
    """The hull's paint schemes as kit skins: [{id, name, types, materials, engineColor?}]."""
    tex = os.path.join(CONV, base, "textures")
    plain = {k: os.path.join(tex, f"{base}_{k}.png") for k in ("basecolor", "emissive", "roughness", "glass")}
    seen = {file_hash(plain["basecolor"])}
    schemes = sorted({m.group(1) for f in os.listdir(tex) if (m := re.fullmatch(rf"{base}_basecolor_(\w+)\.png", f))})
    order = {s: i for i, s in enumerate(SCHEME_ORDER)}
    schemes.sort(key=lambda s: (order.get(s, 50 if s != "gold" else 99), SCHEME.get(s, s)))
    sid = base[len("ship_"):]
    base_glb = os.path.join(CONV, base, base + ".glb")
    base_decals, _ = glb_image(base_glb, "decals")
    out = []
    for s in schemes:
        f = {k: os.path.join(tex, f"{base}_{k}_{s}.png") for k in ("basecolor", "emissive", "roughness", "glass")}
        h = file_hash(f["basecolor"])
        if h in seen: continue                      # the same paint as the hull's own or another scheme
        seen.add(h)
        d = os.path.join("skins", sid); os.makedirs(os.path.join(OUT, d), exist_ok=True)
        body = {"material": f"{base}_body", "diffuse": sw.write(f["basecolor"], "color", f"{d}/{s}_basecolor")}
        if os.path.exists(f["emissive"]) and file_hash(f["emissive"]) != file_hash(plain["emissive"]):
            body["emission"] = sw.write(f["emissive"], "color", f"{d}/{s}_emissive")
        if os.path.exists(f["roughness"]) and file_hash(f["roughness"]) != file_hash(plain["roughness"]):
            body["metallicSmoothness"] = sw.write(f["roughness"], "ms", f"{d}/{s}_metallic")
        mats = [body]
        if os.path.exists(f["glass"]) and file_hash(f["glass"]) != file_hash(plain["glass"]):
            g = sw.write(f["glass"], "alpha", f"{d}/{s}_glass")
            mats.append({"material": f"{base}_glass", "diffuse": g, "emission": g})
        variant = os.path.join(CONV, f"{base}_{s}", f"{base}_{s}.glb")   # a data.pdb skin's own model: its decal sheet
        if os.path.exists(variant):
            vh, raw = glb_image(variant, "decals")
            if vh and vh != base_decals:
                tmp = os.path.join(OUT, d, f"{s}_decals_src.png"); open(tmp, "wb").write(raw)
                mats.append({"material": f"{base}_decals", "diffuse": sw.write(tmp, "alpha", f"{d}/{s}_decals")})
                os.remove(tmp)
        skin = {"id": f"{sid}_{s}", "name": SCHEME.get(s, s.replace("_", " ").title()), "types": [sid], "materials": mats}
        col = engine_colour(f["emissive"] if "emission" in body else None)
        if col is not None: skin["engineColor"] = col
        out.append(skin)
    return out


# ---------------------------------------------------------------- ships


def turret_mounts(path, pts_hull):
    """The hull's turret mounts: its turret_NNN sockets standing up or hanging under the hull (at most MAX_TURRETS, the top
    ones first), else one on top of the hull's rear half."""
    j, _, _ = read(path); W = world(j); found = []
    for i, nd in enumerate(j["nodes"]):
        if i not in W or not re.search(r"_turret_\d{3}$", nd["name"]): continue
        up = W[i][:3, :3] @ np.array([0.0, 1.0, 0.0]); up /= np.linalg.norm(up)
        if abs(up[1]) < 0.9: continue                # a side socket: the remake's turrets stand upright or hang
        found.append((up[1] < 0, W[i][:3, 3]))
    found.sort(key=lambda f: f[0])
    if not found and len(pts_hull):
        lo, hi = pts_hull.min(0), pts_hull.max(0); L = hi[2] - lo[2]; width = hi[0] - lo[0]
        sel = pts_hull[(np.abs(pts_hull[:, 0]) < max(0.06 * width, 0.4)) & (pts_hull[:, 2] > lo[2] + 0.45 * L) & (pts_hull[:, 2] < lo[2] + 0.8 * L)]
        if len(sel): found.append((False, sel[np.argmax(sel[:, 1])]))
    return [{"slotType": 2, "position_engine": game(p), "builtIn": True, **({"upsideDown": True} if down else {})}
            for down, p in found[:MAX_TURRETS]]


T0 = time.perf_counter()
def phase(what): print(f"[{time.perf_counter() - T0:6.1f} s] {what}", flush=True)


def main():
    try: os.nice(10)
    except (AttributeError, OSError): pass
    man = json.load(open(os.path.join(LOAD, "manifest.json"), encoding='utf-8-sig'))
    D = Data()
    for d in ("hulls", "guns", "turret", "skins", "icons"): os.makedirs(os.path.join(OUT, d), exist_ok=True)
    price_fits = gof2_price_fits()
    ships, info, parts, skins = [], {}, [], []
    sw = SkinWriter()
    def locked_engine_fx(fx_name):
        with fx_lock:   # (writes the fx/ files once)
            return engine_fx(fx_name)

    def ship_particles(rid, contrail_points, fx_name):
        """The ship's own GoF3 trail and contrails: its VfxList's Trail* / Contrails entries (the others are buffs, impacts and
        explosions) and their VfxEffectData (5928412 the particle file; 2623219 where: 2 the engine helpers, 3 the contrail
        helpers) as the engineFx's "trailParticles" / "contrailParticles" (Fork's
        emitters, run by the remake as GoF3 runs them) and the contrail points."""
        out = {}
        for x in D.comp(rid, "VfxList").get(580509, []):
            rec = D.R.sub(x).get(1)
            link = D.R.fields(rec).get(1469832) if rec in D.R.p.recs else None
            data = D.R.sub(link[0]).get(1) if link else None
            if data not in D.R.p.recs: continue
            f = D.R.fields(data)
            psb = f.get(5928412, [b""])[0]
            psb = psb.decode("latin-1") if isinstance(psb, bytes) else None
            rname = D.R.name(rec) or ""
            key = "trailParticles" if rname.startswith("Trail") else "contrailParticles" if rname.startswith("Contrail") else None   # (not the buffs')
            if not psb or not key or key in out or (key == "contrailParticles" and not contrail_points): continue
            with fx_lock: em = fork_emitter(psb)
            if em: out[key] = em
        if "contrailParticles" in out: out["contrails"] = [c for p in contrail_points for c in game(p)]
        # the booster's flash at the engines (ad_engine_booster_<race>: the Nivelian, Terran and Vossk engines have one)
        with fx_lock: boost = fork_emitter(f"ad_engine_booster_{ENGINE_RACE.get(fx_name)}") if ENGINE_RACE.get(fx_name) else None
        if boost: out["boostParticles"] = boost
        return out

    def ship_view(rid, j, W, length, L):
        """How the ship is seen (the remake's ModShipView): the chase camera, the cockpit seat, the damage smoke's points
        and the explosion's size, from the hull's helpers and its record."""
        out = {}
        # the chase camera: GoF2's (1338 behind, 600 up, looking at 600 up 650 behind the pivot) for a ship of up to
        # CAMERA_FIT_LENGTH units, pulled back with the hull past it, and a gunship's further out, as GoF3's
        # CameraThirdPerson distance (field 89702: 7 scouts and fighters, 8 gunships). Its other fields can't be read
        # with any confidence (unnamed), so only that ratio is taken.
        cls_dist = D.num(rid, "CameraThirdPerson", 89702) or CAMERA_BASE_DISTANCE
        s = max(1.0, length / CAMERA_FIT_LENGTH)
        d = cls_dist / CAMERA_BASE_DISTANCE
        if s > 1.01 or abs(d - 1) > 0.01:
            out["camera"] = {"distance": round(1338 * s * d), "height": round(600 * s), "lookHeight": round(600 * s),
                             "lookAhead": round(-650 * s)}
        # the cockpit seat: GoF3's own first-person camera helper (ship_X_cam, on the canopy near the nose)
        named = {nd.get("name", ""): i for i, nd in enumerate(j["nodes"]) if i in W}
        cam = next((i for n, i in named.items() if re.search(r"^ship_[a-z]+_\d{3}_cam$", n)), None)
        # (not behind the hull's middle: a hull the builder turned round (TURN) has it at its stern)
        middle = -0.5 * (L["min"][2] + L["max"][2]) * K
        if cam is not None and game(W[cam][:3, 3])[2] > middle: out["cockpit"] = game(W[cam][:3, 3])
        # the damage smoke: GoF3's damage helpers (ship_X_damaged_000 / 001)
        smoke = [game(W[i][:3, 3]) for n, i in sorted(named.items()) if re.search(r"_damaged_\d{3}$", n)]
        if smoke: out["smoke"] = smoke[:4]
        # the explosion: GoF3's EffectScale against its fighters' (1.5 = a GoF2 fighter's 1)
        eff = D.num(rid, "EffectScale", 7443144)
        if eff and abs(eff / EXPLOSION_BASE - 1) > 0.01: out["explosionScale"] = round(eff / EXPLOSION_BASE, 2)
        return out

    def build_one(folder, e):
        """One hull's ships.json entry, source.json record, kit part, skins and log line; None for a paint scheme's
        folder or a hull without a ship record."""
        rec = e.get("record")
        if not rec or e.get("note") == "no ship record": return None
        base = re.match(r"ship_[a-z]+_\d{3}", folder).group(0)
        if folder != base: return None                 # a paint scheme: one of the hull's skins
        rid = D.R.p.byname[rec][0]
        cls = CLASS.get(D.num(rid, "ShipType", 531157), "gunship")
        hull = D.num(rid, "Hull", 1929780) or 0.0; shield = D.num(rid, "Shield", 3522367) or 0.0
        steer = D.vec(rid, "Steering", 1007915)
        ident = D.num(rid, "Identity", 9536365)
        name = NAMES.get(folder) or D.gui_text(rid, 4067579) or base
        desc = D.gui_text(rid, 9934023) or ""
        glb = turned(os.path.join(CONV, base, base + ".glb"), TURN.get(base), os.path.join(OUT, ".turned", base + ".glb"))
        # a turned hull's helpers turned with it, guns included: their turns are taken in the hull's new frame (the turn
        # undone on both sides), so its guns still point at its new nose and its engines blow out of its new stern
        h = math.radians(TURN.get(base, 0)) / 2
        U = trs({"rotation": [0.0, math.sin(-h), 0.0, math.cos(-h)]})
        def own_turn(M): return ship_rotation(M @ U)
        L = layout(glb); length = (L["max"][2] - L["min"][2]) * K
        j, _, _ = read(glb); W = world(j)
        node = {nd["name"]: i for i, nd in enumerate(j["nodes"])}
        hpnode = {re.search(r"_weapon_(\d{3})$", k).group(1): k for k in node if re.search(r"_weapon_\d{3}$", k)}

        mounts = []
        # by the weapon each hardpoint carries (a story / boss record's group 0 can be its launcher): SW_ = secondary
        secs = [hp for hp, h in e["hardpoints"].items() if hp in hpnode and (
            (h["weapon"] or "").startswith("SW_") or (h["group"] == "secondary" and not (h["weapon"] or "").startswith("PW_")))]
        prim = [hp for hp in e["hardpoints"] if hp not in secs and hp in hpnode]
        for hp in ("000", "001", "002", "003"):   # fewer than two guns (boss records): the hull's first hardpoints too
            if len(prim) >= 2 and len(prim) % 2 == 0: break
            if hp in hpnode and hp not in secs and hp not in prim: prim.append(hp)
        def pylon(hp):   # the hardpoint's pylon (its mesh and contact shadow): shown only while the mount carries a weapon
            # (by its number, whatever ship it's named after: several hulls borrow another's pylons, the Nestaar's are
            # ship_nivelian_210_weapon_mount_helper_NNN; looked up by this ship's name alone they stayed always shown)
            n = next((k for k in node if k.endswith(f"_weapon_mount_helper_{hp}")), None)
            return {"nodes": [n]} if n else {}
        for hp in prim:
            M = W[node[hpnode[hp]]]; m = {"slotType": 0, "position_engine": game(M[:3, 3]), **pylon(hp)}
            r = own_turn(M)
            if r: m["rotation"] = r
            mounts.append(m)
        # TODO (noted 2026-10-11, undecided): every GoF3 record arms one secondary launcher, so every ship has 1 secondary slot
        # (GoF2 ships often 2-4). Possibly give fighters 2 / gunships 3 on the unused hardpoints (keep their pylons, list them
        # in "nodes" instead of stripping them in slim()).
        for hp in secs: mounts.append({"slotType": 1, "position_engine": game(W[node[hpnode[hp]]][:3, 3]), **pylon(hp)})
        pts_hull = hull_points(glb)
        turrets = turret_mounts(glb, pts_hull)
        mounts += turrets
        # engines: colour and nozzle as the model shows them (engine_glows.py), else the GoF3 engine effect's colour
        att = D.comp(rid, "EngineAttachment").get(1002168)
        fx_name = D.R.name(D.R.sub(att[0]).get(1)) if att else None
        fx_colour, plume = ENGINE_FX.get(fx_name, ENGINE_FX["TerranEngine"])
        measured = measure_engines(glb)
        good = [m["size"] for m in measured if m["size"] and m["lit"] >= 0.02 and min(m["size"]) >= 0.15]
        typical = list(np.median(np.array(good), axis=0)) if good else [NOZZLE_DEFAULT, NOZZLE_DEFAULT]
        lit = [m["color"] for m in measured if m["color"]]
        ship_colour = [round(float(v), 3) for v in np.mean(np.array(lit), axis=0)] if lit else list(fx_colour)
        for m in measured:
            sz = m["size"] if m["size"] and m["lit"] >= 0.02 and min(m["size"]) >= 0.15 else typical
            sz = [min(1.6, max(0.25, v)) * m["scale"] for v in sz]
            r = 0.5 * (sz[0] + sz[1])
            part = round(min(1.3, max(0.35, 0.75 * r * K / 35)), 2)
            ex = {"slotType": 3, "position_engine": game(m["pos"]), "turretAngles": [part, part, part],
                  "glowColor": m["color"] or ship_colour,
                  "glowSize": [round(sz[0] * K), round(sz[1] * K), round(r * plume * FLAME * K)]}
            if abs(m["scale"] - 1.0) > 0.01: ex["fxScale"] = round(float(m["scale"]), 3)   # the engine helper's scale (engineFx)
            if m.get("outline") and outline_plausible(m["outline"], r / max(1e-6, m["scale"])):
                ex["outline"] = outline_game(m["outline"])   # the nozzle's shape (the remake's exhaust styles)
            turn = own_turn(W[node[m["node"]]]) if m.get("node") in node else None
            if turn and abs(m["pos"][0]) < 0.15: turn = centreline_turn(turn)
            if turn: ex["rotation"] = turn   # the engine helper's turn: the way the engineFx blows (the Vossk engines angle out)
            mounts.append(ex)
        contrail_pts = [W[i][:3, 3] for i, nd in enumerate(j["nodes"]) if i in W and re.search(r"_contrail_\d{3}$", nd["name"])]
        if not measured:
            # no engine helpers: thin exhausts at the wing tips (one per contrail helper: the hull's outermost point on
            # its side) and the hull's own tips (TIP_EXHAUSTS). Not at the helpers themselves: the Nunam's sit 3.5 units
            # ahead of its wing tips once it is turned round, so the plumes streamed back over the wings (the user's
            # report, 2026-10-24); the Kinac's sit on its tips (0.7 units off)
            helpers = [W[i][:3, 3] for i, nd in enumerate(j["nodes"]) if i in W and re.search(r"_contrail_\d{3}$", nd["name"])]
            hull_pts = surface_points(glb) if helpers else np.zeros((0, 3))
            tips = []
            for h in helpers:
                side = hull_pts[np.sign(hull_pts[:, 0]) == np.sign(h[0])]
                tips.append(side[np.argmax(np.abs(side[:, 0]))] if len(side) else h)
            R = trs({"rotation": [0.0, math.sin(math.radians(TURN.get(base, 0)) / 2), 0.0, math.cos(math.radians(TURN.get(base, 0)) / 2)]})
            tips += [(R @ np.array([*p, 1.0]))[:3] for p in TIP_EXHAUSTS.get(base, [])]
            for p in tips:
                sz = TIP_SIZE * TIP_FX_SCALE
                mounts.append({"slotType": 3, "position_engine": game(p), "turretAngles": [0.35, 0.35, 0.35],
                               "glowColor": ship_colour, "glowSize": [round(sz * K), round(sz * K), round(sz * plume * FLAME * K)],
                               "fxScale": TIP_FX_SCALE})

        def engine_colour(emissive_png):
            """A paint scheme's exhaust colour (its emissive texture around the nozzles), None = the hull's own."""
            if not emissive_png: return None
            lit2 = [m["color"] for m in measure_engines(glb, emissive=emissive_png) if m["color"]]
            if not lit2: return None
            c = [round(float(v), 3) for v in np.mean(np.array(lit2), axis=0)]
            return None if max(abs(a - b) for a, b in zip(c, ship_colour)) < 0.08 else c

        power = hull + shield
        t, armor = lerp_log(power, *CONVERT["armor"])
        armor = round(min(max(armor, CONVERT["armor_clamp"][0]), CONVERT["armor_clamp"][1]))
        if steer:
            (r0, h0), (r1, h1) = CONVERT["handling"]
            handling = round(min(160, max(60, h0 + ((steer[0] + steer[1]) / 2 - r0) * (h1 - h0) / (r1 - r0))))
        else:
            handling = CONVERT["handling_default"][cls] - (10 if length > 2200 else 0)
        cb, cl = CONVERT["cargo"][cls]
        cargo = int(round(min(400, max(25, cb * length / cl)) / 5) * 5)
        dev = D.num(rid, "DeviceEquip", 2232171) or 0
        tt = min(1.0, max(0.0, t))
        lc = CONVERT["lounge"]
        sid = folder[len("ship_"):]
        race = RACE.get(ident, 0)
        hull_file = f"hulls/{sid}.glb"
        part = ({"id": sid, "slot": "hull", "name": None, "model": hull_file, "types": [sid], "_src": glb,
                      "_unused": sorted(set(hpnode) - set(prim) - set(secs))})
        ship_skins = skins_of(base, man, sw, engine_colour)
        equip = CONVERT["equipment"][cls] + int(dev)
        n_prim = sum(1 for m in mounts if m["slotType"] == 0); n_sec = sum(1 for m in mounts if m["slotType"] == 1)
        def fitted(w):
            p = math.exp(float(np.dot(w, price_features(equip, n_prim, n_sec, len(turrets), armor, cargo, handling))))
            return int(round(min(max(p, CONVERT["price_clamp"][0]), CONVERT["price_clamp"][1]), -3))
        price, price_default = fitted(price_fits["android"]), fitted(price_fits["default"])
        cruise = D.vec(rid, "Steering", 6741857)
        top = round((cruise[2] / CRUISE_BASE - 1) * 100) if cruise and cruise[2] > 0 else 0
        devices = [D.R.name(D.R.sub(x).get(1)) for x in D.comp(rid, "DeviceEquip").get(5883687, [])]
        booster = next((c for c, b in BOOSTERS.items() if b["device"] in devices), None)
        built_in = ([f"{MOD_ID}:engine_booster_{booster}"] if booster else []) + ([REVIVE_ITEM] if REVIVE_DEVICE in devices else [])
        boss = bool(D.comp(rid, "BossInfo"))
        view = ship_view(rid, j, W, length, L)
        entry = {
            "id": sid, "name": None, "description": desc, "race": race,
            "armor": armor, "cargo": cargo, "handling": handling, "price": price, "priceDefault": price_default,
            "slots": {"primary": sum(1 for m in mounts if m["slotType"] == 0), "secondary": sum(1 for m in mounts if m["slotType"] == 1),
                      "turret": len(turrets), "equipment": equip},
            "kit": KIT, "kitType": sid, "build": {"hull": sid},
            "icon": f"icons/{sid}.png",
            "engineGlowRadius": round(min(70, max(18, 24 * length / 1000)), 1),
            "engineGlowColor": ship_colour,
            "mounts": mounts,
            **({"engineFx": {**fx, **ship_particles(rid, contrail_pts, fx_name)}} if (fx := locked_engine_fx(fx_name)) else {}),
            **({"flight": {"topSpeed": top}} if top else {}),
            **({"integrated": {"items": built_in}} if built_in else {}),
            **({"traffic": {"boss": True}, "npcTurrets": [BOSS_TURRET.get(race, 48)] * len(turrets)} if boss else {}),
            **view,
            "lounge": {"systemRace": race if race in (0, 1, 2, 3) and ident != 5 else -1,
                       "minCampaign": round(lc["minCampaign"][0] + (lc["minCampaign"][1] - lc["minCampaign"][0]) * tt),
                       "minRank": round(lc["minRank"][0] + (lc["minRank"][1] - lc["minRank"][0]) * tt),
                       "chance": lc["chance"]},
        }
        if boss: del entry["lounge"]   # (not sold: no seller in the lounges)
        info_item = {"folder": folder, "record": rec, "raw_name": name, "class": cls, "identity": ident, "engine": fx_name,
                     "engines_measured": sum(1 for m in measured if m["color"]), "engines": len(measured), "hull": hull,
                     "shield": shield, "steering": steer, "deviceEquip": dev, "length": round(length),
                     "turrets": len(turrets), "skins": [s["id"] for s in ship_skins]}
        return entry, info_item, part, ship_skins, f"{sid}: {len(ship_skins)} skins, {len(turrets)} turret mount(s)"

    # the hulls in parallel (their models read, measured and their skins written: mostly NumPy and Pillow, which let go
    # of the GIL), kept in the manifest's order
    fx_lock = threading.Lock()
    with ThreadPoolExecutor(jobs()) as ex:
        for r in ex.map(lambda fe: build_one(*fe), list(man.items())):
            if r is None: continue
            entry, info_item, part, ship_skins, line = r
            ships.append(entry); parts.append(part); skins += ship_skins; info[entry["id"]] = info_item
            print(line, flush=True)
    sw.finish(skins)

    phase("hulls measured, skins written")
    # the sounds (one pass: a wave is written once, whichever hulls share it)
    snd = gof3_sounds.Sounds(os.path.join(MERGED, "sound", "sfx.bank"), OUT)
    if snd:
        for e in ships:
            rid = D.R.p.byname[info[e["id"]]["record"]][0]
            names = [D.R.name(D.R.sub(x).get(1)) for x in D.comp(rid, "SoundList").get(754122, [])]
            sounds = snd.ship(names, info[e["id"]]["identity"], info[e["id"]]["class"])
            if sounds: e["sounds"] = sounds
    else:
        print("no sounds: sfx.bank not found or vgmstream missing (GOF3_VGMSTREAM, vgmstream-cli on the PATH, or FModel's copy with Wine)")
    phase("sounds")
    # names: mixed case, the same name told apart (a boss / retro hull)
    for s in ships: s["name"] = mixed_case(info[s["id"]]["raw_name"])
    def fold(n): return unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    by = {}
    for s in ships: by.setdefault(fold(s["name"]), []).append(s)
    for group in by.values():
        if len(group) < 2: continue
        for s in group:
            boss = not re.match(r"Ship_(Fighter|Gunship|Scout)_", info[s["id"]]["record"])
            label = "Retro" if s["id"].startswith("retro_") else "Boss" if boss else ""
            if label and label.lower() not in s["name"].lower(): s["name"] = f"{s['name']} {label}"
    names = [s["name"] for s in ships]
    for s in ships:
        if names.count(s["name"]) > 1: s["name"] += f" ({s['id']})"
    for p in parts: p["name"] = next(s["name"] for s in ships if s["id"] == p["id"])

    # models: the hulls (no guns), the guns, the turret
    def slim(p):
        base = "ship_" + p["id"]
        unused = p.pop("_unused"); src = p.pop("_src")
        def strip(j):   # the pylons of hardpoints no slot uses: never carry a weapon, so never shown
            for nd in j["nodes"]:
                m = re.search(r"_weapon_(?:mount_(\d{3})_mesh|shadow_(\d{3}))$", nd["name"])
                if m and (m.group(1) or m.group(2)) in unused: nd.pop("mesh", None)
        slim_glb(src, os.path.join(OUT, p["model"]), MAXTEX, strip)
        return p["id"]
    with ThreadPoolExecutor(jobs()) as ex: list(ex.map(slim, parts))
    guns = sorted({(f, mk) for f, mk, _ in PRIMARY_GUNS + TURRET_GUNS} | {(f, mk) for f, mk, _ in PRIMARY_CATEGORIES + TURRET_CATEGORIES}
                  | {PRIMARY_DEFAULT, TURRET_DEFAULT} | {(f, mk) for f in GOF3_WEAPONS for mk in (1, 2, 3)})
    phase("hull models written")
    for f, mk in guns: build_gun(f, mk)
    build_turret(os.path.join(OUT, "turret", "turret.glb"))
    phase("guns and turret written")
    snap_floating_mounts(ships, parts, weapon_rules())
    phase("floating guns checked")

    # icons and preview (rendered from the loadout .glb: the hull with its GoF3 default guns)
    if ICONS:
        tmp = os.path.join(OUT, ".icon_renders"); os.makedirs(tmp, exist_ok=True)
        script = os.path.join(tmp, "render.py"); open(script, "w", encoding='utf-8').write(ICON_SCRIPT)
        def render(s):
            out_png = os.path.join(OUT, s["icon"])
            if ICONS_FROM and os.path.exists(os.path.join(ICONS_FROM, s["id"] + ".png")) and not s["id"] in PREVIEW \
                    and info[s["id"]]["folder"] not in TURN:   # (a turned hull's old icon shows it the old way round)
                shutil.copy(os.path.join(ICONS_FROM, s["id"] + ".png"), out_png); return s["id"], True
            png = os.path.join(tmp, s["id"] + ".png")
            folder = info[s["id"]]["folder"]
            src = turned(os.path.join(LOAD, folder + ".glb"), TURN.get(folder), os.path.join(tmp, folder + "_turned.glb"))
            subprocess.run([BLENDER, "-b", "-P", script, "--", src, png],
                           capture_output=True)
            if os.path.exists(png): icon(png, out_png)
            return s["id"], os.path.exists(png)
        with ThreadPoolExecutor(6) as ex:
            for sid, ok in ex.map(render, ships):
                if not ok: print("icon failed:", sid)
        prev = Image.new("RGB", (640, 360), (14, 18, 28)); d = ImageDraw.Draw(prev)
        for i, sid in enumerate(PREVIEW):
            png = os.path.join(tmp, sid + ".png")
            if not os.path.exists(png): continue
            im = Image.open(png).convert("RGBA"); im = im.crop(im.getbbox())
            sc = min(200 / im.width, 130 / im.height); im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
            cx, cy = 113 + (i % 3) * 207, 120 + (i // 3) * 150
            prev.paste(im, (cx - im.width // 2, cy - im.height // 2), im)
        font = None
        for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Helvetica.ttc"):   # Linux, Windows, macOS
            try: font = ImageFont.truetype(name, 26); break
            except OSError: pass
        font = font or ImageFont.load_default()
        d.text((20, 14), f"Galaxy on Fire 3 Ships  ·  {len(ships)}", fill=(235, 240, 250), font=font)
        prev.save(os.path.join(OUT, "preview.png"))
        shutil.rmtree(tmp, ignore_errors=True)

    phase("icons and preview")
    kit = {"id": KIT, "name": "Galaxy on Fire 3 hulls", "slots": ["hull"], "scale": round(K * 0.05, 5), "yaw": 180,
           "parts": parts, "skins": skins, "palettes": {"weapons": weapon_palette()},
           "hardpoints": {"turret": "turret/turret.glb", "toggle": True, "weapons": with_sounds(weapon_rules(), snd)}}
    json.dump([kit], open(os.path.join(OUT, "shipkits.json"), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    # GoF3's capital ships in the orbits' traffic and the Hades as the Manticore, a mobile station with its own hangar and
    # bar (capitals.py; the remake's ships.json "traffic": { "capital" } and stations.json "mobile").
    cap_ships, cap_stations, cap_interiors = ([], [], [])
    if os.path.isdir(os.path.join(ASSETS, "structures")):
        cap_ships, cap_stations, cap_interiors = capitals.build(OUT, ASSETS, log=phase)
    json.dump(ships + cap_ships, open(os.path.join(OUT, "ships.json"), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    for name, data in (("stations.json", cap_stations), ("interiors.json", cap_interiors)):
        if data: json.dump(data, open(os.path.join(OUT, name), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump(info, open(os.path.join(OUT, "source.json"), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump(booster_items() + weapon_items(D, snd), open(os.path.join(OUT, "items.json"), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    if os.path.exists(os.path.join(REMAKE, "Assets/Resources/GoF2Data/items.json")):   # (the goods' prices)
        json.dump(blueprints(ships, info, D), open(os.path.join(OUT, "blueprints.json"), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump({
        "id": "gof3_ships", "name": "Galaxy on Fire 3 Ships", "version": "2.3", "author": "DuIslingr",
        "description": f"{len(ships)} ships from Galaxy on Fire 3: Manticore as customizable ships, sold by visitors in the Space "
                       f"Lounges of their race's systems: {len(skins)} GoF3 paint schemes to pick in the hangar's Customize "
                       "screen, GoF3 guns that follow the weapons mounted, and GoF3 turrets. Names, descriptions, races and "
                       "stats come from the game's own data (data.pdb), scaled to Galaxy on Fire 2's ranges. "
                       f"{len(cap_ships)} GoF3 capital ships (battleships, frigates, freighters) in the orbits' traffic, and the "
                       "Manticore: GoF3's Hades as a moving station in the Magnetar system, with its own hangar and bar.",
        "credits": "Ships, guns, textures and texts: Galaxy on Fire 3: Manticore (c) Deep Silver FISHLABS. For personal use.",
        "preview": "preview.png"}, open(os.path.join(OUT, "mod.json"), "w", encoding='utf-8'), indent=4, ensure_ascii=False)
    shutil.copy(os.path.join(HERE, "gof3_mod_readme.txt"), os.path.join(OUT, "README.txt"))
    json.dump(exhaust_styles(), open(os.path.join(OUT, "exhausts.json"), "w", encoding='utf-8'), indent=1, ensure_ascii=False)
    shutil.rmtree(os.path.join(OUT, ".turned"), ignore_errors=True)   # (the TURN hulls' turned copies)
    phase("done")
    print(f"{len(ships)} ships, {len(skins)} skins, {len(guns)} guns written to {OUT}")


PREVIEW = ["terran_000", "vossk_107", "nivelian_222", "terran_031", "vossk_103", "nivelian_201"]

if __name__ == "__main__":
    main()
