"""GoF3's bosses as the remake's Most Wanted criminals (wanted.json, Modding/README.md "Most Wanted") with their portraits as
characters (characters.json, portraits/).

python gof3_wanted.py <mod folder>   writes them into a built GoF3 Ships mod (build_gof3_mod.py calls build() itself)

GoF3's data.pdb gives each boss a BossInfo component (research 2026-11-02):
  8012639   the tier: 2 helper boss (HB), 3 under boss (UB), 4 big boss (BB)
  5732944   its place in the campaign's order (1-31: act 1 1-13, act 2 14-26, act 3 27-31)
  5671259   its internal name, the act first (A01_HB04_T09-...)
  362122 / 362124  its two minions: an HB's two escort ships, a UB's two HBs, a BB's two UBs (the hierarchy the remake's
            "requiredBounties" follows here)
  9650601   its quote (a text record), 4670436 / 8403147 its music; GuiAttribute 4067579 its title, 1210092 its portrait
            (swf/<name>.png, a 1000 x 1200 cut-out)
Left out: the records without a place in the order (the events' bosses, Krotac's arena, Rigant's unused under bosses,
Ti-Nung's decoy), the test record and the "_2" / "Clones" copies; of the records sharing a title the strongest hull counts.

The remake's criminal from it:
  ship        the boss's hull in this mod (Shape /assets/ships/<race>/<n>/ -> "gof3_ships:<race>_<n>")
  race        Identity 9536365 (RACE: the pirates of act 3 fly as pirates); its escorts are of that race
  board       by act: 1 Vossk (Sh'gaal's), 2 Nivelian (Khador's), 3 Terran (Ti-Nung's)
  requiredBounties  HB 0; the act's n-th UB 2n; the BB 3 x the act's UBs (kills on that board's mod criminals)
  hitpoints   the GoF3 hull (Hull 1929780, 1200-7300) onto GoF2's 5000-12000 (the game's criminals: 5000-10000)
  reward      hitpoints x 12 / 16 / 25 by tier (the game's: 50,000-140,000)
  weapon      the boss's first primary (Arming 9719173, a PW_ record: its Shape's gun family) as this mod's GoF3 gun, mark 2
              for an HB, 3 above; a boss arming only a launcher takes the Burst Laser
  secondary   its launcher: rockets by tier (Rocket, Turretschreck, Hunt Down), mine layers and the smart bomb the cluster
  loot        HB 5 Implants, UB 2 / BB 5 Golden Cores (the hulls' blueprints already drop from the boss hulls)
  wingmen     2 / 3 / 4 by tier
  description its quote and its place under its act's big boss"""
import json, os, re, sys
from PIL import Image

TIER_NAMES = {2: "helper", 3: "under", 4: "big"}
BOARD = {1: "vossk", 2: "nivelian", 3: "terran"}
RACE_WORD = {0: "terran", 1: "vossk", 2: "nivelian", 3: "midorian", 8: "pirate"}
SECONDARY = {2: "gof3_crrocket", 3: "gof3_lrturretschreck", 4: "gof3_lrhuntdown"}
LOOT = {2: (113, 5), 3: (165, 2), 4: (165, 5)}
WINGMEN = {2: 2, 3: 3, 4: 4}
REWARD = {2: 12, 3: 16, 4: 25}
SKIP = re.compile(r"NOT USED|Test|Clones|_2$|FakeBoss|Vortex")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def cased(title, record, mixed_case):
    """The all-caps title with each word as the record name writes it where it does (SH'GAAL in Ship_A01_BB01_Sh'gaal ->
    Sh'gaal, D'RAK -> D'rak), else mixed_case's."""
    def word(w):
        m = re.search(re.escape(w), record, re.I)
        return m.group(0) if m and len(w) > 1 else mixed_case(w)
    return " ".join(word(w) for w in title.split())


def bosses(D):
    """[{rid, title, quote, tier, order, act, hull, race, shape, portrait, minions, weapons}] of the campaign's bosses."""
    R = D.R
    found = {}
    for rid in list(R.p.recs):
        name = R.name(rid) or ""
        if not name.startswith("Ship_") or SKIP.search(name): continue
        try: comps = R.resolved(rid)[0]
        except Exception: continue
        b = comps.get("BossInfo")
        if not b or not b.get(5732944) or not b.get(9650601): continue
        title = D.gui_text(rid, 4067579)
        internal = (b.get(5671259) or [b""])[0].decode("utf-8", "replace")
        act = re.match(r"A0(\d)", internal)
        shape = (comps.get("Shape", {}).get(7803720) or [b""])[0].decode("utf-8", "replace")
        if not title or not act or not shape: continue
        weapons = []
        for v in comps.get("Arming", {}).get(9719173, []):
            w = R.sub(v).get(1)
            if w not in R.p.recs: continue
            wsh = (R.resolved(w)[0].get("Shape", {}).get(7803720) or [b""])[0].decode("utf-8", "replace")
            weapons.append((R.name(w) or "", wsh))
        e = {"rid": rid, "record": name, "title": title,"quote": D.text_of(b[9650601][0]), "tier": b.get(8012639, [2])[0],
             "order": b[5732944][0], "act": int(act.group(1)), "hull": comps.get("Hull", {}).get(1929780, [0.0])[0],
             "race": comps.get("Identity", {}).get(9536365, [7])[0], "shape": shape,
             "portrait": (comps.get("GuiAttribute", {}).get(1210092) or [b""])[0].decode("utf-8", "replace"),
             "minions": [R.name(R.sub(v).get(1)) for k in (362122, 362124) for v in b.get(k, [])], "weapons": weapons}
        if title not in found or e["hull"] > found[title]["hull"]: found[title] = e
    return sorted(found.values(), key=lambda e: e["order"])


def build(D, ship_ids, out, merged, mod_id, weapon_id, mixed_case, race_map, log=print):
    """Writes <out>/wanted.json, characters.json and portraits/; returns the number of criminals."""
    all_b = bosses(D)
    big = {e["act"]: e for e in all_b if e["tier"] == 4}
    unders = {}
    wanted, chars = [], []
    os.makedirs(os.path.join(out, "portraits"), exist_ok=True)
    for e in all_b:
        title = cased(e["title"], e["record"], mixed_case)
        wid = slug(title)
        m = re.search(r"/ships/(\w+)/(\d+)/", e["shape"])
        ship = f"{m.group(1)}_{m.group(2)}" if m else None
        if ship not in ship_ids:
            log(f"wanted: {title}: no hull {ship} in the mod (left out)"); continue
        tier, act = e["tier"], e["act"]
        race = race_map.get(e["race"], 8)
        hp = int(round((5000 + max(0.0, e["hull"] - 1200) / 6100 * 7000) / 500.0)) * 500
        if tier == 3: unders[act] = unders.get(act, 0) + 1
        required = 0 if tier == 2 else 2 * unders[act] if tier == 3 else 3 * sum(1 for x in all_b if x["act"] == act and x["tier"] == 3)
        mk = 2 if tier == 2 else 3
        prim = next((sh for n, sh in e["weapons"] if "_PW_" in n or n.startswith("PW_")), None)
        fam = re.search(r"weapon_generic_(\d{3})_mk", prim or "")
        sec_name = next((n for n, _ in e["weapons"] if n.startswith("SW_")), "")
        secondary = "gof3_mrcluster" if re.search(r"(?i)mine|bomb", sec_name) else SECONDARY[tier]
        loot, amount = LOOT[tier]
        boss = cased(big[act]["title"], big[act]["record"], mixed_case) if act in big else None
        role = ("The boss behind them all." if tier == 4 else
                f"One of {boss}'s lieutenants." if tier == 3 and boss else
                f"A captain under {boss}." if boss else "")
        quote = re.sub(r"\s+", " ", e["quote"] or "").strip()
        entry = {"id": wid, "name": title, "description": (f"“{quote}” " if quote else "") + role,
                 "board": BOARD.get(act, "terran"), "race": RACE_WORD.get(race, "pirate"),
                 "ship": f"{mod_id}:{ship}", "weapon": f"{mod_id}:{weapon_id(fam.group(1) if fam else '000', mk)}",
                 "secondary": f"{mod_id}:{secondary}", "hitpoints": hp, "reward": int(round(hp * REWARD[tier], -4)),
                 "loot": loot, "lootAmount": amount, "wingmen": WINGMEN[tier], "requiredBounties": required}
        src = os.path.join(merged, "swf", e["portrait"] + ".png") if e["portrait"] else None
        if src and os.path.exists(src):
            Image.open(src).convert("RGBA").resize((320, 384), Image.LANCZOS).save(os.path.join(out, "portraits", f"{wid}.png"), optimize=True)
            ch = {"id": wid, "name": title, "portrait": f"portraits/{wid}.png"}
            if race in (0, 1, 2, 3): ch["race"] = RACE_WORD[race]
            chars.append(ch)
            entry["character"] = wid
        wanted.append(entry)
    json.dump(wanted, open(os.path.join(out, "wanted.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if chars: json.dump(chars, open(os.path.join(out, "characters.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(f"wanted: {len(wanted)} bosses, {len(chars)} portraits")
    return len(wanted)


if __name__ == "__main__":
    folder = os.path.abspath(sys.argv[1])
    sys.argv = [sys.argv[0], folder]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_gof3_mod as B
    ids = {s["id"] for s in json.load(open(os.path.join(folder, "ships.json"), encoding="utf-8"))}
    build(B.Data(), ids, folder, B.MERGED, B.MOD_ID, B.weapon_id, B.mixed_case, B.RACE)
