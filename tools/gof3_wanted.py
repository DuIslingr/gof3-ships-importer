"""GoF3's bosses as the remake's Most Wanted criminals (wanted.json, Modding/README.md "Most Wanted") with their portraits as
characters (characters.json, portraits/).

python gof3_wanted.py <mod folder>   writes them into a built GoF3 Ships mod (build_gof3_mod.py calls build() itself)

GoF3's data.pdb gives each boss a BossInfo component (research 2026-11-02):
  8012639   the tier: 2 helper boss (HB), 3 under boss (UB), 4 big boss (BB)
  5732944   its place in the campaign's order (1-31: act 1 1-13, act 2 14-26, act 3 27-31)
  5671259   its internal name, the act first (A01_HB04_T09-...)
  362122-362124  infoSource0-2, its informants (killed to find it): an HB's two grind-boss ships, a UB's two HBs, a BB's
            two UBs (the hierarchy the remake's "requiredBounties" follows here)
  9650601   quoteSnippet, its quote; 597983 entourageSnippets, its lines (a record of text refs, 4095575); 4670436 /
            8403147 its music events; GuiAttribute 4067579 its title, 1210092 its portrait (swf/<name>.png, 1000 x 1200)
  5320137   difficultyConfigs: Normal / Titan / Titan+ (not used: the remake keeps GoF2's difficulty, ROADMAP.md
            "Difficulty: GoF3 against GoF2")
(The field names: libgofm.so's protobuf descriptors, BossInfo / BossDifficultyConfig.)
Left out: the records without a place in the order (the events' bosses, Krotac's arena, Rigant's unused under bosses,
Ti-Nung's decoy), the test record and the "_2" / "Clones" copies; of the records sharing a title the strongest hull counts.

The remake's criminal from it:
  ship        the boss's hull in this mod (Shape /assets/ships/<race>/<n>/ -> "gof3_ships:<race>_<n>")
  race        Identity 9536365 (RACE: the pirates of act 3 fly as pirates); its escorts are of that race
  board       by act: 1 Vossk (Sh'gaal's), 2 Nivelian (Khador's), 3 Terran (Ti-Nung's)
  requiredBounties  HB 0; the act's n-th UB 2n; the BB 3 x the act's UBs (kills on that board's mod criminals)
  hitpoints   GoF2's rule (the user, 2026-11-02: GoF2's difficulty, not GoF3's): GoF2's boards climb 7000 -> 10000 along
              their ladder, so the act's first boss 7000 to its big boss 10000 by its place in the act's order; the
              remake then adds GoF2's rank bonus and multiplies by GoF2's difficulty factor (TrafficPlan.AddWanted)
  reward      likewise GoF2's 60,000 -> 140,000 along the act
  weapon      the boss's first primary (Arming 9719173, a PW_ record: its Shape's gun family) as this mod's GoF3 gun, mark 2
              for an HB, 3 above; a boss arming only a launcher takes the Burst Laser
  secondary   its launcher: rockets by tier (Rocket, Turretschreck, Hunt Down), mine layers and the smart bomb the cluster
  loot        HB 5 Implants, UB 2 / BB 5 Golden Cores (the hulls' blueprints already drop from the boss hulls)
  wingmen     GoF2's 0 -> 4 along the act, at least 2 for an HB (its two informants), 2 for a UB, 4 for a BB
  escorts     an HB's: its informants' hulls (GoF3's grind bosses fly regular hulls); the others' their race's fighters
  taunt       its first entourage line, else its quote
  music       its act's and tier's boss music (BossInfo musicEvent music_boss_<boss>[_helper|_under]): the act's sector bank
              (music_stream_trim / porros / rigant.bank: act 1 "annikett", 2 "khador", 3 "ti_nung") holds per tier a
              combat_low and a combat_high layer, 64 s loops each; GoF3 crossfades them by intensity (FMOD), the mod plays
              low then high as one 128 s loop (music/gof3_boss_<act>_<tier>.ogg); its warm-up and attention stingers left out
  description its quote and its place under its act's big boss

The same bosses are the mod's rift bosses (encounters.json: a "rift" entry adding them to the cruise drive's rift, the
remake's EVERSPACE 2 rift run, Modding/README.md "Cruise drives"): the boss stage brings one of the 31 at random, its hull "raiders"
pirate raiders' hulls. GoF3's own measure: its hull + shield (Hull 1929780, Shield 3522367) over a GoF3 pirate fighter's
(the Groza, Ship_NPC_Pirate_Terran_Fighter_Groza, from its tier 3 on 240.6 + 240.6). The danger level cancels: GoF3 scales
a boss fight's hull by the same factor as a grind mission's at every level (DangerDependentAttributes
hullFactorMediumBossMission = hullFactorMediumGrindMission, libgofm.so's protobuf descriptor). The rift's chance, rank and
stages are the remake's; every mod's rift entry only adds its bosses to one pool."""
import json, os, re, shutil, subprocess, sys
from PIL import Image

MUSIC = {1: ("trim", "annikett"), 2: ("porros", "khador"), 3: ("rigant", "ti_nung")}   # act -> (bank, the music's boss)

TIER_NAMES = {2: "helper", 3: "under", 4: "big"}
BOARD = {1: "vossk", 2: "nivelian", 3: "terran"}
RACE_WORD = {0: "terran", 1: "vossk", 2: "nivelian", 3: "midorian", 8: "pirate"}
SECONDARY = {2: "gof3_crrocket", 3: "gof3_lrturretschreck", 4: "gof3_lrhuntdown"}
LOOT = {2: (113, 5), 3: (165, 2), 4: (165, 5)}
WINGMEN_MIN = {2: 2, 3: 2, 4: 4}
RAIDER_SHIP = "Ship_NPC_Pirate_Terran_Fighter_Groza_T3"   # GoF3's pirate fighter at its steady tier (T3-T7 alike)
RAIDER_HP = 240.625 + 240.625                              # (its hull + shield, should the record be missing)
RIFT = {"id": "gof3_rift", "kind": "rift"}   # (the rift's chance and stages are the remake's: the mod only adds its bosses)
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


def entourage(D, b):
    """A boss's entourage lines (BossInfo entourageSnippets -> its 4095575 text refs)."""
    v = b.get(597983)
    rec = D.R.sub(v[0]).get(1) if v else None
    if rec not in D.R.p.recs: return []
    return [t for t in (D.text_of(x) for x in D.R.fields(rec).get(4095575, [])) if t]


def hull_of(D, rid):
    """A ship record's hull folder as this mod's ship id (Shape /assets/ships/<race>/<n>/ -> <race>_<n>)."""
    if rid not in D.R.p.recs: return None
    sh = (D.R.resolved(rid)[0].get("Shape", {}).get(7803720) or [b""])[0].decode("utf-8", "replace")
    m = re.search(r"/ships/(\w+)/(\d+)/", sh)
    return f"{m.group(1)}_{m.group(2)}" if m else None


def bosses(D):
    """[{rid, title, quote, lines, tier, order, act, hull, race, shape, portrait, informants, weapons}] of the campaign's
    bosses."""
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
             "shield": comps.get("Shield", {}).get(3522367, [0.0])[0],
             "race": comps.get("Identity", {}).get(9536365, [7])[0], "shape": shape,
             "portrait": (comps.get("GuiAttribute", {}).get(1210092) or [b""])[0].decode("utf-8", "replace"),
             "informants": [R.sub(v).get(1) for k in (362122, 362123, 362124) for v in b.get(k, [])], "weapons": weapons,
             "lines": entourage(D, b)}
        if title not in found or e["hull"] > found[title]["hull"]: found[title] = e
    return sorted(found.values(), key=lambda e: e["order"])


def raider_hp(D):
    """A GoF3 pirate fighter's hull + shield (RAIDER_SHIP)."""
    rid = next((r for r in D.R.p.recs if D.R.name(r) == RAIDER_SHIP), None)
    if rid is None: return RAIDER_HP
    c = D.R.resolved(rid)[0]
    return (c.get("Hull", {}).get(1929780, [0.0])[0] + c.get("Shield", {}).get(3522367, [0.0])[0]) or RAIDER_HP


def rift(bosses_, ship_ids, mod_id, raider, race_map=None):
    """The mod's rift encounter (encounters.json's entry): its "bosses" the bosses whose hull the mod has, each its hull +
    shield over 'raider' pirate raiders, flying for its own race (Identity's, as on the Most Wanted boards: 'race_map' GoF3's
    race numbers to the remake's); None without any."""
    out = []
    for e in bosses_:
        m = re.search(r"/ships/(\w+)/(\d+)/", e["shape"])
        ship = f"{m.group(1)}_{m.group(2)}" if m else None
        if ship in ship_ids:
            b = {"ship": f"{mod_id}:{ship}", "raiders": round((e["hull"] + e.get("shield", 0.0)) / raider, 2)}
            if race_map is not None and "race" in e: b["race"] = RACE_WORD.get(race_map.get(e["race"], 8), "pirate")
            out.append(b)
    return dict(RIFT, bosses=out) if out else None


def boss_music(merged, out, log=print):
    """music/gof3_boss_<act>_<tier>.ogg (see the header); returns {(act, tier): track name}."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gof3_sounds
    ff = shutil.which("ffmpeg")
    if not ff: log("wanted: no ffmpeg (the bosses keep the game's wanted music)"); return {}
    tracks = {}
    for act, (bank, key) in MUSIC.items():
        path = os.path.join(merged, "sound", f"music_stream_{bank}.bank")
        folder = gof3_sounds.decode_bank(path) if os.path.exists(path) else None
        if not folder: continue
        waves = {re.sub(r"(\.wav)+$", "", f.lower()): os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".wav")}
        for tier, word in TIER_NAMES.items():
            layer = lambda l: next((p for n, p in sorted(waves.items()) if re.search(rf"mus_{key}_boss_{word}_combat_{l}(_v?\d+)?$", n)), None)
            parts = [x for x in (layer("low"), layer("high")) if x]
            if not parts: continue
            name = f"gof3_boss_{act}_{word}"
            os.makedirs(os.path.join(out, "music"), exist_ok=True)
            cmd = [ff, "-y", "-v", "error"] + [a for x in parts for a in ("-i", x)]
            if len(parts) > 1: cmd += ["-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]", "-map", "[out]"]
            cmd += ["-c:a", "libvorbis", "-q:a", "4", os.path.join(out, "music", name + ".ogg")]
            if subprocess.run(cmd).returncode == 0: tracks[(act, tier)] = name
    log(f"wanted: {len(tracks)} boss tracks")
    return tracks


def build(D, ship_ids, out, merged, mod_id, weapon_id, mixed_case, race_map, log=print):
    """Writes <out>/wanted.json, characters.json, portraits/, music/ and encounters.json (the rift); returns the number of
    criminals."""
    all_b = bosses(D)
    music = boss_music(merged, out, log)
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
        span = [x["order"] for x in all_b if x["act"] == act]
        t = (e["order"] - min(span)) / max(1, max(span) - min(span))   # its place on the act's ladder, 0..1
        hp = int(round((7000 + 3000 * t) / 500.0)) * 500
        reward = int(round((60000 + 80000 * t) / 5000.0)) * 5000
        wingmen = max(WINGMEN_MIN[tier], int(round(4 * t)))
        escorts = [f"{mod_id}:{h}" for h in (hull_of(D, i) for i in e["informants"]) if h in ship_ids] if tier == 2 else []
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
                 "secondary": f"{mod_id}:{secondary}", "hitpoints": hp, "reward": reward,
                 "loot": loot, "lootAmount": amount, "wingmen": wingmen, "requiredBounties": required}
        if escorts: entry["escorts"] = escorts
        taunt = re.sub(r"\s+", " ", (e["lines"] or [quote])[0] or "").strip()
        if taunt: entry["taunt"] = taunt
        if (act, tier) in music: entry["music"] = music[(act, tier)]
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
    r = rift(all_b, ship_ids, mod_id, raider_hp(D), race_map)
    enc = os.path.join(out, "encounters.json")
    if r: json.dump([r], open(enc, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    elif os.path.exists(enc): os.remove(enc)
    log(f"wanted: {len(wanted)} bosses, {len(chars)} portraits; {len(r['bosses']) if r else 0} rift bosses")
    return len(wanted)


if __name__ == "__main__":
    folder = os.path.abspath(sys.argv[1])
    sys.argv = [sys.argv[0], folder]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_gof3_mod as B
    ids = {s["id"] for s in json.load(open(os.path.join(folder, "ships.json"), encoding="utf-8"))}
    build(B.Data(), ids, folder, B.MERGED, B.MOD_ID, B.weapon_id, B.mixed_case, B.RACE)
