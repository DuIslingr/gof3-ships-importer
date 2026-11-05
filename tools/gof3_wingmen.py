"""GoF3's wingmen for the mod (the remake's ships.json "wingmanDevice" and wingmen.json: Modding/README.md "Wingmen").

GoF3 flies the player's other ships as wingmen, each hull with a wingman device (its Wingman component's wingmanDevice:
Device_HullRepair, Device_AmmoSupply, Device_ChargedShots; data.pdb's DeviceConfigurationWingman*). GoF2 hires its
wingmen in the Space Lounges, so the mod's GoF3 hulls get their device ("wingmanDevice": the one most of the hull's tier
records carry; the bosses' hulls none) and wingmen.json makes them a crew: CHANCE % of the bars' wingmen offers fly them,
saying GoF3's wingman radio lines (WINGMAN_*_RADIO_MESSAGE_NN): kill, lost (the lines about another one; the shot-down
pilot's own "punching out" lines left out), help, thanks, warn. GoF3's player-death and revive lines are left out (in GoF2
the player's death ends the flight), its collision lines too.

build(D, ships, out) sets the ships' "wingmanDevice" (ships.json is written after it) and writes <out>/wingmen.json."""
import collections, json, os, re

CHANCE = 40
DEVICE = {"Device_HullRepair": "repair", "Device_AmmoSupply": "ammo", "Device_ChargedShots": "charged"}
LINES = {"kill": "WINGMAN_KILL_RADIO_MESSAGE_", "lost": "WINGMAN_KILLED_RADIO_MESSAGE_", "help": "WINGMAN_NEED_HELP_RADIO_MESSAGE_",
         "thanks": "WINGMAN_THANKS_PLAYER_RADIO_MESSAGE_", "warn": "WINGMAN_WARN_PLAYER_RADIO_MESSAGE_"}
SKIP = {"WINGMAN_KILLED_RADIO_MESSAGE_02", "WINGMAN_KILLED_RADIO_MESSAGE_11"}   # the shot-down pilot speaking
FIXES = [("Theres ", "There's ")]


def _refs(R, rid):
    out = []
    try: f = R.fields(rid)
    except Exception: return out
    for vs in f.values():
        for v in vs:
            if isinstance(v, bytes):
                try: c = R.sub(v).get(1)
                except Exception: continue
                if isinstance(c, int) and c in R.p.recs: out.append(c)
    return out


def devices(D):
    """{GoF3 ship id number: "repair" | "ammo" | "charged"}: the device most of its Ship_*_id<N>_* records carry."""
    R = D.R
    dev = {}
    for r in R.p.recs:
        if R.name(r) != "Wingman": continue
        try: dev[r] = R.name(R.sub(R.fields(r)[4305932][0]).get(1))
        except Exception: pass
    count = collections.defaultdict(collections.Counter)
    for r in R.p.recs:
        m = re.match(r"Ship_(?:\w+?_)?id(\d+)_", R.name(r) or "")
        if not m: continue
        seen, level = set(), [r]
        for _ in range(2):   # the ship -> its components -> the Wingman
            nxt = [c for x in level for c in _refs(R, x) if c not in seen]
            seen.update(nxt); level = nxt
        for c in seen:
            if dev.get(c) in DEVICE: count[int(m.group(1))][DEVICE[dev[c]]] += 1
    return {n: c.most_common(1)[0][0] for n, c in count.items() if c}


def lines(D):
    R = D.R
    plain = lambda x: " ".join(x.replace("“", '"').replace("”", '"').replace("’", "'").replace("…", "...").split())
    found = {}
    for r in R.p.recs:
        n = R.name(r) or ""
        if not n.startswith("WINGMAN_") or n in SKIP: continue
        f = R.fields(r).get(3906420)
        if f: found.setdefault(n, plain(f[0].decode("utf-8", "replace")))
    out = {}
    for kind, prefix in LINES.items():
        texts = [found[k] for k in sorted(found) if k.startswith(prefix) and k[len(prefix):].isdigit()]
        for old, new in FIXES: texts = [t.replace(old, new) for t in texts]
        if texts: out[kind] = texts
    return out


def build(D, ships, out, log=print):
    by = devices(D)
    n = 0
    for s in ships:
        if (s.get("traffic") or {}).get("boss"): continue   # (the bosses' own hulls fly for nobody)
        m = re.search(r"(\d+)$", s["id"])
        d = by.get(int(m.group(1))) if m else None
        if d: s["wingmanDevice"] = d; n += 1
    radio = lines(D)
    json.dump({"chance": CHANCE, "radio": radio}, open(os.path.join(out, "wingmen.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    kinds = collections.Counter(s.get("wingmanDevice") for s in ships if s.get("wingmanDevice"))
    log(f"wingmen: {n} hulls with a wingman device ({dict(kinds)}), {sum(len(v) for v in radio.values())} radio lines")
    return n
