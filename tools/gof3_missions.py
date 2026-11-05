"""GoF3's freelance challenges and distress calls as the mod's bar missions (events/gof3_*.gof2mission, the remake's
event-graph missions: Modding/README.md "Story missions and bar missions"), and the two frigates the distress calls spawn
(npcships.json; see "distress calls" below).

GoF3 has ten freelance challenges (Mission type 3 / 7, FreelanceChallenge records; texts FT_00-FT_13), set in Mkkt Bkkt's
"underground sporting events". GoF3 has no lounges: the mod offers them in GoF2's Space Lounges, at every station
("stations" empty, its "chance"), by a visitor of the station's race; Mkkt Bkkt speaks over the radio. Six are GoF2's own
freelance missions already and are left out (the user, 2026-11-05: "cross check them and just add new ones"):
  Firing Range (FM01, FT_00)   static targets in a time limit: GoF2's Junk removal (space junk in 121 s)
  Challenger (FT_01)           first to five kills against a rival: GoF2's Challenge
  Breakthrough (FM08, FT_07)   transports between gates, more than three away fails: GoF2's Intercept (convoy freighters)
  Combat Arena (FT_08)         waves in a bounded area: GoF2's Defense / Pirate hunting
  Tunnel Race (FM10, FT_09)    nodes inside laser tubes: GoF2 has no tubes, and without them it is the Sprint
  Season Boss (FM13, FT_13)    the season's final boss in the arena: GoF2's Wanted
The four new ones, with the remake's pickups (/pickup: glowing orbs, collected by an "on near" at the same point):
  Sprint (FT_03)               twelve checkpoints in order, each one adds time
  Orb Rush (FM05, FT_05)       a track of gates with orbs along it: at least ORB_RUSH_NEEDED of them, then the finish
  Obstacle Race (FM11, FT_11)  each gate's orb is shielded until its power nodes are destroyed (held drones here)
  Pick-up and Return (FM12)    orbs scattered around, one carried at a time to the drop-off zone, raiders on the way
GoF3's boost rings and the orb's damage while carried have no remake counterpart (left out); the time limits and rewards
are GoF2's measure (a ship's ~2.5 units/ms, GoF2's freelance pay), the texts GoF3's (data.pdb), its story's names taken out.
"""
import json, math, os, random

MOD_SPEAKER = "vossk Mkkt Bkkt"   # GoF3's organizer of the races (a race and a name: the remake draws a Vossk face)
CHANCE = 12                        # % of the bars offering each one (the remake's default is 35)
RADIUS_M = 150                     # a checkpoint / orb counts within this (metres; the server checks every 0.25 s)
ORB_RADIUS_M = 100
ORB_RUSH_NEEDED = 25
SPEED = 2.5                        # game units per ms, a GoF2 fighter's cruise: the time limits allow 1.5x the track at it


def texts(D, name):
    """Every text record of that name, in data order (GoF3 keeps two or three variants under one name)."""
    out = []
    for r in D.R.p.recs:
        if D.R.name(r) != name: continue
        f = D.R.fields(r).get(3906420)
        if f: out.append(f[0].decode("utf-8", "replace").strip())
    return out


def text(D, name, hint="", edits=(), fallback=""):
    """The variant containing 'hint', with GoF3's story words replaced ('edits': (old, new) pairs, each must match, else
    the fallback; curly quotes and apostrophes are made plain first)."""
    plain = lambda x: " ".join(x.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'").replace("\u2026", "...").split())
    t = next((plain(x) for x in texts(D, name) if hint in plain(x)), None)
    if t is None: return fallback
    for old, new in edits:
        if old not in t: return fallback
        t = t.replace(old, new)
    return t


def xyz(p): return f"{int(round(p[0]))} {int(round(p[1]))} {int(round(p[2]))}"


def track(seed, n, start=20000, step=11000, swing=16000):
    """n points out ahead of the station (game units, +z its launch path), swinging side to side and up and down."""
    rng = random.Random(seed)
    pts, a, b = [], rng.uniform(0, 6.3), rng.uniform(0, 6.3)
    for i in range(n):
        z = start + i * step + rng.uniform(-1500, 1500)
        pts.append((swing * math.sin(a + 0.9 * i), 0.5 * swing * math.sin(b + 0.6 * i) + 6000, z))
    return pts


def path_len(pts, origin=(0, 0, 0)):
    d, last = 0.0, origin
    for p in pts: d += math.dist(last, p); last = p
    return d


def seconds_for(units): return int(round(1.5 * units / SPEED / 1000.0 / 5.0)) * 5


# ---------------------------------------------------------------------------------------------------- building blocks

def radio(t, speaker=MOD_SPEAKER): return {"type": "radio", "speaker": speaker, "text": t}


def start(title, subtitle, intro, extra_vars=(), purpose="for the race", speaker=MOD_SPEAKER):
    """The common opening: the station the visitor sat in, a quiet orbit (the mission's own ships only), the player
    launching, no travel until it is over, the speaker's intro (Mkkt Bkkt's) and the title."""
    variables = [{"name": "st", "value": -1}, {"name": "done", "value": 0}, {"name": "left", "value": 0}] + list(extra_vars)
    steps = [
        {"type": "set", "variable": "st", "value": "station"},
        {"type": "questorbit", "station": "{st}"},
        {"type": "objective", "text": "Launch from {stationname(st)} " + purpose, "station": "{st}"},
        {"type": "checkpoint", "name": "accepted"},
        {"type": "waituntil", "condition": "inorbit({st}) > 0"},
        {"type": "restrict", "what": "all"},
        {"type": "wait", "seconds": 3},
        {"type": "title", "title": title, "subtitle": subtitle, "seconds": 4},
    ] + [radio(t, speaker) for t in intro if t]
    return variables, steps


def clock(seconds, fail_title="Out of time", label="Time left:"):
    """The time limit: 'left' counts down beside the rest (the HUD's timer shows it; a bonus sends it again)."""
    return [
        {"type": "set", "variable": "left", "value": str(seconds)},
        {"type": "timer", "seconds": "left", "label": label},
        {"type": "every", "seconds": 1, "steps": [
            {"type": "if", "condition": "done == 0", "then": [
                {"type": "set", "variable": "left", "value": "left - 1"},
                {"type": "if", "condition": "left <= 0", "then": [
                    {"type": "set", "variable": "done", "value": "2"},
                    {"type": "timer", "stop": True},
                    {"type": "pickup", "action": "clear"},
                    {"type": "waypoint"},
                    {"type": "restrict", "what": "off"},
                    {"type": "fail", "title": fail_title}]}]}]},
    ]


def finish(outro):
    return [
        {"type": "set", "variable": "done", "value": "1"},
        {"type": "timer", "stop": True},
        {"type": "pickup", "action": "clear"},
        {"type": "waypoint"},
        {"type": "restrict", "what": "off"},
        {"type": "questorbit", "station": "{st}", "on": False},
        {"type": "sound", "sound": "success"},
    ] + ([radio(outro)] if outro else []) + [{"type": "complete"}]


def checkpoints(pts, name, counter, bonus, then_last=()):
    """'on near' handlers for points passed in order: the next one shown (orb + waypoint) when one is reached, 'bonus'
    seconds added; 'then_last' runs at the last."""
    out = []
    for i, p in enumerate(pts):
        steps = [{"type": "set", "variable": counter, "value": str(i + 1)},
                 {"type": "pickup", "action": "remove", "name": name},
                 {"type": "sound", "sound": "boost"}]
        if bonus and i + 1 < len(pts):
            steps += [{"type": "set", "variable": "left", "value": f"left + {bonus}"},
                      {"type": "timer", "seconds": "left", "label": "Time left:"}]
        if i + 1 < len(pts):
            steps += [{"type": "pickup", "station": "{st}", "at": xyz(pts[i + 1]), "name": name},
                      {"type": "waypoint", "station": "{st}", "at": xyz(pts[i + 1])}]
        else:
            steps += list(then_last)
        out.append({"type": "on", "trigger": "near", "station": "{st}", "at": xyz(p), "radius": RADIUS_M, "steps": [
            {"type": "if", "condition": f"done == 0 and {counter} == {i}", "then": steps}]})
    return out


def first(pts, name):
    return [{"type": "pickup", "station": "{st}", "at": xyz(pts[0]), "name": name},
            {"type": "waypoint", "station": "{st}", "at": xyz(pts[0])}]


def mission(title, offer, reward, variables, steps, client=""):
    m = {"format": "gof2mission", "title": title, "kind": "mission", "offer": offer, "reward": reward,
         "chance": CHANCE, "takers": "station", "variables": variables, "steps": steps}
    if client: m["client"] = client
    return m


def appear(name, seconds=20):
    """Waits until the ships (or a capital ship's parts) of that name are there, so an 'alive(...) == 0' after it can't
    pass before they came (a capital ship builds its parts after it spawned)."""
    return [{"type": "waituntil", "condition": f'alive("{name}") > 0', "timeout": seconds}]


# ---------------------------------------------------------------------------------------------------- the four

def sprint(D):
    pts = track(3, 12)
    total = seconds_for(path_len(pts))
    bonus = 6
    first_limit = max(20, total - bonus * (len(pts) - 1))
    offer = text(D, "FT_03-Sprint_Desc", "Mkkt Bkkt", [("There are boost zones to help you in this journey. ", ""),
                 ("Haste hunter.", "Haste, pilot.")],
                 "An underground race at the edge of space: fly through every checkpoint of the course within the time window.")
    intro = [text(D, "FT_03-Intro 1"), text(D, "FT_03-Intro 2", edits=[(" and overcharges your engine for an intense speed boost", "")])]
    variables, steps = start("SPRINT", "Pass all checkpoints", intro, [{"name": "cp", "value": 0}])
    steps += checkpoints(pts, "Checkpoint", "cp", bonus)
    steps += [{"type": "objective", "text": "Pass all twelve checkpoints before the time is up", "station": "{st}"}]
    steps += first(pts, "Checkpoint") + clock(first_limit)
    steps += [{"type": "waituntil", "condition": f"cp == {len(pts)}"}]
    steps += finish(text(D, "FT_03-Outro", edits=[(", hunter", ", pilot")]))
    return mission("Sprint", offer, 12000, variables, steps)


def orb_rush(D):
    gates = track(5, 8, step=15000, swing=12000)
    rng = random.Random(55)
    orbs, last = [], (0, 2000, 8000)
    for g in gates:   # four orbs on the way to each gate, off the line by up to 3 km... 150 m either way
        for k in range(1, 5):
            t = k / 5.0
            p = [last[j] + (g[j] - last[j]) * t for j in range(3)]
            orbs.append((p[0] + rng.uniform(-3000, 3000), p[1] + rng.uniform(-3000, 3000), p[2]))
        last = g
    limit = seconds_for(path_len(gates)) + 35
    offer = text(D, "FT_05-CoinRush_Desc", "Mkkt Bkkt", [('"coins"', "orbs"), ("a better hunter", "a better pilot")],
                 "A time trial of sorts: collect the orbs along the track and reach the finish within the time limit.")
    intro = [text(D, "FT_05-Intro 1", "Mkkt Bkkt", [('the "coins"', f"at least {ORB_RUSH_NEEDED} orbs")]),
             text(D, "FT_05-Intro 2", "orbs")]
    variables, steps = start("ORB RUSH", f"Collect at least {ORB_RUSH_NEEDED} orbs", intro,
                             [{"name": "gate", "value": 0}, {"name": "orbs", "value": 0}] + [{"name": f"got{i + 1}", "value": 0} for i in range(len(orbs))])
    for i, p in enumerate(orbs):
        steps += [{"type": "pickup", "station": "{st}", "at": xyz(p), "name": f"Orb {i + 1}", "marked": False},
                  {"type": "on", "trigger": "near", "station": "{st}", "at": xyz(p), "radius": ORB_RADIUS_M, "steps": [
                      {"type": "if", "condition": f"done == 0 and got{i + 1} == 0", "then": [
                          {"type": "set", "variable": f"got{i + 1}", "value": "1"},
                          {"type": "set", "variable": "orbs", "value": "orbs + 1"},
                          {"type": "pickup", "action": "remove", "name": f"Orb {i + 1}"},
                          {"type": "sound", "sound": "info"},
                          {"type": "title", "subtitle": "Orbs collected: {orbs}", "seconds": 2}]}]}]
    steps += checkpoints(gates, "Gate", "gate", 0)
    steps += [{"type": "objective", "text": f"Collect at least {ORB_RUSH_NEEDED} orbs and pass the gates to the finish", "station": "{st}"}]
    steps += first(gates, "Gate") + clock(limit)
    steps += [{"type": "waituntil", "condition": f"gate == {len(gates)}"},
              {"type": "if", "condition": f"orbs < {ORB_RUSH_NEEDED}", "then": [
                  {"type": "set", "variable": "done", "value": "2"},
                  {"type": "timer", "stop": True}, {"type": "pickup", "action": "clear"}, {"type": "restrict", "what": "off"},
                  {"type": "fail", "title": f"Only {{orbs}} orbs: {ORB_RUSH_NEEDED} needed"}]}]
    steps += finish(text(D, "FT_05-Outro", edits=[("Hunter! ", "")]))
    return mission("Orb Rush", offer, 15000, variables, steps)


def obstacle_race(D):
    gates = track(11, 6, step=16000, swing=14000)
    offer = text(D, "FT_11-ObstacleRace_Desc", fallback="Pass a series of shielded gates within the time limit: destroy each gate's power nodes first.")
    intro = [text(D, "FT_11-Intro 1", edits=[("all twelve rings", f"all {len(gates)} rings")]), text(D, "FT_11-Intro 3")]
    variables, steps = start("OBSTACLE RACE", "Destroy the power nodes, collect the orbs", intro, [{"name": "orb", "value": 0}])
    limit = seconds_for(path_len(gates)) + 25 * len(gates)
    steps += [{"type": "objective", "text": "Destroy each gate's power nodes, then collect its orb", "station": "{st}"}] + clock(limit)
    for i, g in enumerate(gates):
        nodes = [(g[0] + 2500 * math.cos(a), g[1] + 2500 * math.sin(a), g[2]) for a in (0.3, 2.4, 4.5)]
        steps += [{"type": "waypoint", "station": "{st}", "at": xyz(g)}]
        steps += [{"type": "spawn", "ship": 32, "race": "pirate", "behaviour": "neutral", "name": "Power node", "hull": 0.5,
                   "at": xyz(n)} for n in nodes]
        steps += [{"type": "shipaction", "ship": "Power node", "action": "hold"}] + appear("Power node")
        steps += [{"type": "waituntil", "condition": "alive(\"Power node\") == 0"},
                  {"type": "sound", "sound": "shield"},
                  {"type": "pickup", "station": "{st}", "at": xyz(g), "name": "Orb"},
                  {"type": "on", "trigger": "near", "station": "{st}", "at": xyz(g), "radius": RADIUS_M, "steps": [
                      {"type": "if", "condition": f"done == 0 and orb == {i}", "then": [
                          {"type": "set", "variable": "orb", "value": str(i + 1)},
                          {"type": "pickup", "action": "remove", "name": "Orb"},
                          {"type": "sound", "sound": "boost"},
                          {"type": "set", "variable": "left", "value": "left + 8"},
                          {"type": "timer", "seconds": "left", "label": "Time left:"}]}]},
                  {"type": "waituntil", "condition": f"orb == {i + 1}"}]
    steps += finish("")
    return mission("Obstacle Race", offer, 20000, variables, steps)


def pickup_and_return(D):
    rng = random.Random(12)
    drop = (0, 3000, 15000)
    orbs = []
    while len(orbs) < 5:
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(25000, 55000)
        p = (r * math.cos(a), rng.uniform(-8000, 12000), 15000 + abs(r * math.sin(a)) + 10000)
        if all(math.dist(p, q) > 15000 for q in orbs): orbs.append(p)
    limit = seconds_for(sum(2 * math.dist(drop, p) for p in orbs)) + 30
    offer = text(D, "FT_12-Pickup_And_Return_Desc", "miners", [("traditional Neox miners sport", "traditional miners' sport"),
                 (" and the orb may damage your ship while carrying it. So keep an eye on your hull and don't forget to boost", ". Don't forget to boost")],
                 "Find the glowing orbs and bring them back to the drop-off zone before the time runs out, one at a time.")
    intro = [text(D, "FT_12-Intro 1"), text(D, "FT_12-Intro 2")]
    variables, steps = start("PICK-UP AND RETURN", "Bring every orb to the drop-off zone", intro,
                             [{"name": "carrying", "value": 0}, {"name": "returned", "value": 0}] + [{"name": f"got{i + 1}", "value": 0} for i in range(len(orbs))])
    for i, p in enumerate(orbs):
        steps += [{"type": "pickup", "station": "{st}", "at": xyz(p), "name": f"Orb {i + 1}"},
                  {"type": "on", "trigger": "near", "station": "{st}", "at": xyz(p), "radius": RADIUS_M, "steps": [
                      {"type": "if", "condition": f"done == 0 and carrying == 0 and got{i + 1} == 0", "then": [
                          {"type": "set", "variable": f"got{i + 1}", "value": "1"},
                          {"type": "set", "variable": "carrying", "value": "1"},
                          {"type": "pickup", "action": "remove", "name": f"Orb {i + 1}"},
                          {"type": "sound", "sound": "charge"},
                          {"type": "waypoint", "station": "{st}", "at": xyz(drop)},
                          {"type": "title", "subtitle": "Orb picked up: bring it to the drop-off zone", "seconds": 2}]}]}]
    steps += [{"type": "on", "trigger": "near", "station": "{st}", "at": xyz(drop), "radius": 250, "steps": [
        {"type": "if", "condition": "done == 0 and carrying == 1", "then": [
            {"type": "set", "variable": "carrying", "value": "0"},
            {"type": "set", "variable": "returned", "value": "returned + 1"},
            {"type": "waypoint"},
            {"type": "sound", "sound": "success"},
            {"type": "title", "subtitle": f"Orb delivered: {{returned}} of {len(orbs)}", "seconds": 2}]}]}]
    # the competitors: two raiders now and then, never more than four
    steps += [{"type": "every", "seconds": 30, "steps": [
        {"type": "if", "condition": "done == 0 and alive(\"Competitor\") < 3", "then": [
            {"type": "spawn", "ship": 22, "race": "pirate", "count": 2, "behaviour": "enemy", "name": "Competitor"}]}]}]
    steps += [{"type": "objective", "text": f"Bring all {len(orbs)} orbs to the drop-off zone, one at a time", "station": "{st}"}]
    steps += clock(limit)
    steps += [{"type": "waituntil", "condition": f"returned == {len(orbs)}"}]
    steps += finish("")
    return mission("Pick-up and Return", offer, 22000, variables, steps)


# ---------------------------------------------------------------------------------------------------- distress calls
# GoF3's distress calls (Mission type 6 / 7 and 0: DC01-DC05), against GoF2's freelance missions:
#   Siege (DC01)        enemy waves besieging a freighter, destroy them: GoF2's Protection / Defense, left out
#   Clean Up (DC02)     toxic waste containers and their guards, destroy them: GoF2's Junk removal, left out
#   Hijack (DC03)       a stranded Vossk frigate's turrets shot off, its guards destroyed: new (HIJACK_TYPE's turret parts)
#   The Trap (DC04)     traps holding a civilian frigate destroyed before time runs out, turrets and scouts about: new
#                       (TRAP_TYPE: the traps are parts on the frigate's hull, which they shield; then it jumps away)
#   Errand Boy (DC05)   three beacons scanned by staying near each, raiders at every one, then the rest of them: new
#                       (the remake's distance(player, x, y, z); GoF3 left it unfinished, without texts of its own: its
#                       task lines "Investigate ... distress beacon" / "Scan finished" and the mod's own words)
# GoF3's mines (The Trap's) have no remake counterpart; its "UFOs" (Hijack's guards) are Vossk fighters here.

HIJACK_TYPE, TRAP_TYPE = "hijack_frigate", "trapped_frigate"
HIJACK_HULL, TRAP_HULL = "capital_vossk_002", "capital_terran_002"   # capitals.CAPITALS: the Absu, the Proteus
TRAP_MOUNTS, TRAP_TURRETS = (0, 3, 5, 7), (1, 4, 6)                  # the Proteus' turret helpers: traps, pirate turrets
SCAN_UNITS, SCAN_SECONDS = 8000, 12                                  # a beacon reads out within 400 m in 12 s
FRIGATE_AT = (30000, 4000, 80000)                                    # 4 km out, off the launch path
CAPTAIN = "terran Frigate captain"
ONCE = "@r[orbit={st}]"   # one of the team in the orbit: a frigate once, not beside every player like the fighters


def npc_types(ships, mod_id):
    """npcships.json: the two frigates the distress calls spawn (spawntype; never in the traffic: no "spawn"), their parts
    at the hull's turret helpers (ships.json mounts slot 2) and named for the missions' alive(...)."""
    by = {s["id"]: s for s in ships}
    def helpers(hull):
        return [m for m in by.get(hull, {}).get("mounts", []) if m.get("slotType") == 2]
    def part(m, **kw):
        p = {"position": m["position_engine"]}
        if m.get("upsideDown"): p["upsideDown"] = True
        if m.get("turretUp"): p["turretUp"] = m["turretUp"]
        p.update(kw)
        return p
    out = []
    hijack = helpers(HIJACK_HULL)
    if hijack:   # each turret shields the hull: the frigate can't be shot down before they are
        out.append({"id": HIJACK_TYPE, "kind": "capital", "name": "Vossk frigate", "ship": f"{mod_id}:{HIJACK_HULL}", "race": "vossk",
                    "hostile": True, "missiles": False, "escorts": {"count": 0}, "loot": False,
                    "hardpoints": [part(m, kind="turret", name="Frigate turret", item=49, shields=True) for m in hijack]})
    trap = helpers(TRAP_HULL)
    if len(trap) > max(TRAP_MOUNTS + TRAP_TURRETS):   # the pirates' traps and turrets on a civilian frigate (theirs: hostile)
        out.append({"id": TRAP_TYPE, "kind": "capital", "name": "Trapped frigate", "ship": f"{mod_id}:{TRAP_HULL}", "race": "pirates",
                    "hostile": True, "missiles": False, "escorts": {"count": 0}, "loot": False,
                    "hardpoints": [part(trap[i], kind="object", name="Trap", shields=True, scale=1.5) for i in TRAP_MOUNTS]
                                + [part(trap[i], kind="turret", name="Pirate turret", item=48) for i in TRAP_TURRETS]})
    return out


def hijack(D, mod_id):
    client = "terran Salvage broker"
    offer = " ".join(x for x in (text(D, "DC_03-Intro 0"), text(D, "DC_03-Hijack_Desc") + ".") if x.strip(" ."))
    intro = [text(D, "DC_03-Intro 2", edits=[("the UFOs protecting it", "the fighters guarding it")])]
    variables, steps = start("HIJACK", text(D, "DC_03-Hijack_Desc", fallback="Disable all turrets"), intro,
                             purpose="to the frigate", speaker=client)
    at = xyz(FRIGATE_AT)
    steps += [{"type": "spawntype", "who": ONCE, "npc": f"{mod_id}:{HIJACK_TYPE}", "name": "Vossk frigate", "at": at},
              {"type": "spawn", "ship": 9, "race": "vossk", "count": 4, "behaviour": "enemy", "name": "Frigate guard",
               "at": xyz((FRIGATE_AT[0], FRIGATE_AT[1] + 6000, FRIGATE_AT[2] - 20000))},
              {"type": "waypoint", "station": "{st}", "at": at},
              {"type": "objective", "text": text(D, "DC_03-Hijack_Obj1", fallback="Disable all turrets"), "station": "{st}"}]
    steps += appear("Frigate turret", 30)
    # the frigate itself must stay whole: "we urgently need to get on board"
    steps += [{"type": "every", "seconds": 2, "steps": [
        {"type": "if", "condition": 'done == 0 and alive("Vossk frigate") == 0', "then": [
            {"type": "set", "variable": "done", "value": "2"}, {"type": "waypoint"}, {"type": "restrict", "what": "off"},
            {"type": "fail", "title": "The frigate was destroyed"}]}]}]
    steps += [{"type": "waituntil", "condition": 'alive("Frigate turret") == 0'},
              {"type": "sound", "sound": "success"},
              {"type": "title", "subtitle": text(D, "DC_03-Kill Task Completion", fallback="Success: All turrets destroyed"), "seconds": 3},
              {"type": "objective", "text": text(D, "DC_03-Hijack_Obj2", fallback="Eliminate all enemies"), "station": "{st}"},
              {"type": "waypoint"},
              {"type": "waituntil", "condition": 'alive("Frigate guard") == 0'}]
    steps += finish("")
    return mission("Hijack", offer, 30000, variables, steps, client)


def the_trap(D, mod_id):
    deeds = [("Ded Moroz sent", "the pirates sent")]
    offer = text(D, "DC_04-The Trap_Desc", "traps", [("Neox-pirate tradition", "pirate tradition")],
                 "Quickly destroy all traps holding the civilian frigate, before time runs out, to help them escape.")
    intro = [text(D, "DC_04-Intro 1a", edits=[("the second part of the Neox Gladiators and a set of brand new rules", "the Gladiators, with a set of brand new rules"),
                                              ("We trapped these frigates", "We trapped this frigate"), ("to free them", "to free it")]),
             text(D, "DC_04-Intro 1b", edits=deeds), text(D, "DC_04-Intro 2b")]
    variables, steps = start("THE TRAP", text(D, "DC_04-The Trap_Obj1", fallback="Destroy the traps"), intro,
                             [{"name": "traps", "value": len(TRAP_MOUNTS)}], purpose="to the trapped frigate")
    at = xyz(FRIGATE_AT)
    steps += [{"type": "spawntype", "who": ONCE, "npc": f"{mod_id}:{TRAP_TYPE}", "name": "Trapped frigate", "at": at},
              {"type": "spawn", "ship": 32, "race": "pirate", "count": 3, "behaviour": "enemy", "name": "Scout",
               "at": xyz((FRIGATE_AT[0] - 8000, FRIGATE_AT[1], FRIGATE_AT[2] - 25000))},
              {"type": "waypoint", "station": "{st}", "at": at},
              {"type": "objective", "text": text(D, "DC_04-Task Kill Traps", fallback="Destroy the traps"), "station": "{st}"}]
    steps += appear("Trap", 30) + clock(150, "Out of time: the traps went off", text(D, "DC_04-Timer - Mission Time", fallback="Mission time:"))
    steps += [{"type": "every", "seconds": 1, "steps": [
        {"type": "if", "condition": 'done == 0 and alive("Trap") < traps', "then": [
            {"type": "set", "variable": "traps", "value": 'alive("Trap")'},
            {"type": "sound", "sound": "smallexplosion"},
            {"type": "title", "subtitle": text(D, "DC_04-Trap destroyed", fallback="Trap destroyed!") + " "
                                          + text(D, "DC_04-Counter Traps", fallback="Traps left:") + " {traps}", "seconds": 2}]}]}]
    steps += [{"type": "waituntil", "condition": 'alive("Trap") == 0'},
              {"type": "set", "variable": "done", "value": "3"},   # (the clock stops; the rest is no race against it)
              {"type": "timer", "stop": True},
              radio(text(D, "DC_04-Free", fallback="You made it, we're free! Now let's get out of here!"), CAPTAIN),
              {"type": "shipaction", "ship": "Trapped frigate", "action": "jump"},
              {"type": "waypoint"},
              {"type": "objective", "text": text(D, "DC_04-Task Kill Remaining Enemies", fallback="Kill the remaining enemies"), "station": "{st}"},
              {"type": "waituntil", "condition": 'alive("Scout") == 0'}]
    steps += finish("")
    return mission("The Trap", offer, 25000, variables, steps, MOD_SPEAKER)


def errand_boy(D):
    client = "midorian Rescue coordinator"
    rng = random.Random(5)
    beacons = []
    while len(beacons) < 3:
        a, r = rng.uniform(-1.2, 1.2), rng.uniform(40000, 70000)
        p = (r * math.sin(a), rng.uniform(-6000, 9000), 20000 + r * math.cos(a))
        if all(math.dist(p, q) > 30000 for q in beacons): beacons.append(p)
    tasks = [text(D, "Task 1st Distress Signal", "beacon", fallback="Investigate the first distress beacon"),
             text(D, "Task 2nd Distress Signal", fallback="Investigate the second distress beacon"),
             text(D, "Task 3rd Distress Signal", fallback="Investigate another distress beacon")]
    offer = ("Three distress beacons went up out there, and nobody answers on them. Fly to each and stay close while your "
             "scanner reads it out. Whoever set them off may still be about.")
    intro = [text(D, "Gen_DistressIntro_02", "distress"),
             f"Stay within {SCAN_UNITS // 20} metres of a beacon until the scan is through."]
    variables, steps = start("ERRAND BOY", "Scan the distress beacons", intro,
                             [{"name": "cur", "value": 0}, {"name": "prog", "value": 0}] + [{"name": f"wave{i + 1}", "value": 0} for i in range(3)],
                             purpose="to the beacons", speaker=client)
    for i, p in enumerate(beacons):
        nxt = []
        if i + 1 < len(beacons):
            nxt = [{"type": "pickup", "station": "{st}", "at": xyz(beacons[i + 1]), "name": "Distress beacon"},
                   {"type": "waypoint", "station": "{st}", "at": xyz(beacons[i + 1])},
                   {"type": "objective", "text": tasks[i + 1], "station": "{st}"}]
        # the raiders come when the player first gets there (2, 3, 4 of them)
        steps += [{"type": "on", "trigger": "near", "station": "{st}", "at": xyz(p), "radius": SCAN_UNITS // 20, "steps": [
            {"type": "if", "condition": f"done == 0 and cur == {i} and wave{i + 1} == 0", "then": [
                {"type": "set", "variable": f"wave{i + 1}", "value": "1"},
                {"type": "sound", "sound": "alarm"},
                {"type": "spawn", "ship": 22, "race": "pirate", "count": i + 2, "behaviour": "enemy", "name": "Raider",
                 "at": xyz((p[0], p[1] + 5000, p[2] + 20000))}]}]}]
        # the scan: a second for every second the player stays near the beacon
        steps += [{"type": "every", "seconds": 1, "steps": [
            {"type": "if", "condition": f"done == 0 and cur == {i} and distance(player, {p[0]:.0f}, {p[1]:.0f}, {p[2]:.0f}) >= 0 and distance(player, {p[0]:.0f}, {p[1]:.0f}, {p[2]:.0f}) <= {SCAN_UNITS}", "then": [
                {"type": "set", "variable": "prog", "value": "prog + 1"},
                {"type": "if", "condition": f"prog < {SCAN_SECONDS}", "then": [
                    {"type": "title", "subtitle": f"Scanning: {{floor(prog * 100 / {SCAN_SECONDS})}} %", "seconds": 1}],
                 "else": [
                    {"type": "set", "variable": "prog", "value": "0"},
                    {"type": "set", "variable": "cur", "value": str(i + 1)},
                    {"type": "pickup", "action": "remove", "name": "Distress beacon"},
                    {"type": "sound", "sound": "info"},
                    {"type": "title", "subtitle": text(D, "Distress Signal Task Done", fallback="Scan finished"), "seconds": 2}] + nxt}]}]}]
    steps += [{"type": "pickup", "station": "{st}", "at": xyz(beacons[0]), "name": "Distress beacon"},
              {"type": "waypoint", "station": "{st}", "at": xyz(beacons[0])},
              {"type": "objective", "text": tasks[0], "station": "{st}"},
              {"type": "waituntil", "condition": f"cur == {len(beacons)}"},
              {"type": "waypoint"},
              {"type": "objective", "text": text(D, "DC_04-Task Kill Remaining Enemies", fallback="Kill the remaining enemies"), "station": "{st}"},
              {"type": "waituntil", "condition": 'alive("Raider") == 0'}]
    steps += finish("")
    return mission("Errand Boy", offer, 20000, variables, steps, client)


MISSIONS = {"gof3_sprint": sprint, "gof3_orb_rush": orb_rush, "gof3_obstacle_race": obstacle_race, "gof3_pickup_return": pickup_and_return,
            "gof3_errand_boy": errand_boy}
TYPED = {"gof3_hijack": (hijack, HIJACK_TYPE), "gof3_the_trap": (the_trap, TRAP_TYPE)}   # (need their NPC ship type)


def build(D, out, ships=(), mod_id="gof3_ships", log=print):
    """Writes <out>/events/gof3_*.gof2mission and <out>/npcships.json (the frigates two of them spawn: from 'ships',
    the mod's ships.json entries); returns the number of missions."""
    folder = os.path.join(out, "events")
    os.makedirs(folder, exist_ok=True)
    types = npc_types(ships, mod_id)
    have = {t["id"] for t in types}
    made = dict(MISSIONS)
    made.update({name: (lambda D, f=f: f(D, mod_id)) for name, (f, t) in TYPED.items() if t in have})
    for name, make in made.items():
        json.dump(make(D), open(os.path.join(folder, name + ".gof2mission"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if types: json.dump(types, open(os.path.join(out, "npcships.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(f"missions: {len(made)} bar missions (GoF3's freelance challenges and distress calls GoF2 has no counterpart for), "
        f"{len(types)} NPC ship types")
    return len(made)

if __name__ == "__main__":
    import sys
    folder = os.path.abspath(sys.argv[1])
    sys.argv = [sys.argv[0], folder]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_gof3_mod as B
    shipfile = next((f for f in (os.path.join(folder, "ships.json"), os.path.expanduser("~/GOF2UnityRemakeMods/gof3_ships/ships.json"))
                     if os.path.exists(f)), None)   # (the built mod's, for the frigates' turret helpers)
    build(B.Data(), folder, json.load(open(shipfile, encoding="utf-8")) if shipfile else [], B.MOD_ID)
