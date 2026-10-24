"""The GoF3 Ships mod's sounds: Galaxy on Fire 3's own engine, boost and gun sounds from its sfx.bank (romfs sound/), for
the remake's ships.json "sounds" and the kit's hardpoint rules' "sound".

sfx.bank is an FMOD Studio bank around an FSB5 of 500 waves in FMOD's FADPCM, which only vgmstream decodes: a native
vgmstream-cli (GOF3_VGMSTREAM, the PATH, ~/.local/bin), else FModel's Windows copy (~/Downloads/FModel/Output/.data) through
Wine. The waves are decoded once into ~/.cache/gof3_ships_importer (by the bank's size and date) and only those the mod uses
go into it, as Ogg Vorbis through ffmpeg (else .wav: the game takes a .wav of the same name in an .ogg's place, so the JSON
stays the same).

Which waves: the bank's FMOD events aren't decoded here (their wave lists are in the bank's own chunks); the waves are
named after them, so each ship's sound list (data.pdb SoundList: "Engine MAIN Terran Scout Styx", "Engine Boost Nivelian
Gunship Asura") picks its race's set by name, and each gun family's records name their shot ("Shoot CR1 Laser",
"Shoot LR2 Plasma") as the waves do ("cr1_burst_laser", the LR2 ion cannon). The Inouac ships (no waves of their own) take
the Nivelian set, whose engine textures they borrow too.

Volumes: each wave at the game's own level, measured like the ES2 importer's (a loop's RMS, a shot's loudest 60 ms) against
the game's engine (0.388 x 0.27), its shots (0.371 x 0.7), its booster (0.407 x 0.81) and its
boost loop at full strength (0.343 x 0.6). Unity plays an AudioSource at
volume 1 at most, so a wave that needs more (the Nivelian engine loop x2.65: GoF3 mixes it quiet) is written louder (its gain
baked in, kept under 0.98 at its peak) and its volume taken down by as much."""
import functools, glob, os, re, shutil, subprocess, wave
import numpy as np

ENGINE_LEVEL, SHOT_LEVEL, BOOST_LEVEL = 0.388 * 0.27, 0.371 * 0.7, 0.407 * 0.81
BOOST_LOOP_LEVEL = 0.343 * 0.6   # (the game's boost loop at full strength, RMS)

# The race sets: the engine loop and the boost's start / loop / end (their wave names without the _NN take number).
SETS = {
    "terran":       {"engine": "MC_sfx_terran_fighter_high_on_loop", "boost": "MC_sfx_terran_fighter_boost_"},
    "terran_scout": {"engine": "MC_sfx_terran_scout_high_on_loop", "boost": "MC_sfx_terran_fighter_boost_"},
    "nivelian":     {"engine": "MC_sfx_nivelian_high_loop", "boost": "MC_sfx_nivelian_boost_"},
    "vossk":        {"engine": "MC_sfx_ignition_vossk_loop", "boost": "MC_sfx_vossk_boost_"},
}
SET_OF_RACE = {"Terran": "terran", "Nivelian": "nivelian", "Vossk": "vossk", "Inouac": "nivelian"}
SET_OF_IDENTITY = {3: "terran", 4: "vossk", 6: "nivelian", 7: "terran", 5: "nivelian"}   # the bosses: no engine events

# The gun families (build_gof3_mod's weapon_generic_NNN) -> their shot waves (patterns) or a beam's ignition / loop / end.
SHOTS = {
    "000": r"^(Mc_sfx_weapon_cr1_burst_laser|MC_sfdx_weapon_burst_laser)_\d+$",   # Burst Laser: Shoot CR1 Laser
    "001": r"^MC_sfx_weapon_scatter_cannon_\d+$",                                 # Scatter Plasma: Shoot CR2 Plasma
    "002": r"^MC_sfx_weapon_ion_cannon_\d+$",                                     # Plasma Focus: Shoot LR2 Plasma
    "003": r"^MC_sfx_weapon_ricochet_gun_\d+$",                                   # Dismantler: Shoot MR3 Ballistic
    "004": r"^MC_sfx_weapon_lr1_auto_cannon_\d+$",                                # Mass Driver: Shoot LR1 Ballistic
    "005": r"^MC_sfx_weapon_plasma_sprayer_\d+$",                                 # Plasma Blast: Shoot MR1 Plasma
    "006": r"^MC_sfx_weapon_machine_gun_shot_new_\d+$",                           # Auto Laser: Shoot CR3 Cannon
    "007": r"^MC_sfx_weapon_railgun_\d+$",                                        # Railgun: Shoot LR3 Laser
}
BEAM = {"008": ("MC_sfx_weapon_mr2_pulse_laser_in_", "MC_sfx_weapon_mr2_pulse_laser_loop_")}   # Beam Laser: Shoot MR2 Beam
LAUNCHERS = {"rocket": r"^MC_sfx_weapon_cr_rocket_\d+$", "homing": r"^MC_sfx_weapon_cr_homing_\d+$"}


def vgmstream():
    """The vgmstream command: [cli] or ["wine", cli.exe]; None without one."""
    own = os.environ.get("GOF3_VGMSTREAM")
    for c in [own, shutil.which("vgmstream-cli"), os.path.expanduser("~/.local/bin/vgmstream-cli")]:
        if c and os.path.exists(c):
            return (["wine", c] if c.lower().endswith(".exe") else [c])
    exe = os.path.expanduser("~/Downloads/FModel/Output/.data/vgmstream-cli.exe")
    if os.path.exists(exe) and (os.name == "nt" or shutil.which("wine")):
        return [exe] if os.name == "nt" else ["wine", exe]
    return None


def decode_bank(bank):
    """Every wave of the bank as <cache>/<name>.wav (decoded once); the folder, or None without vgmstream."""
    st = os.stat(bank)
    cache = os.path.expanduser(f"~/.cache/gof3_ships_importer/sfx_{st.st_size}_{int(st.st_mtime)}")
    if os.path.exists(os.path.join(cache, ".done")): return cache
    cmd = vgmstream()
    if not cmd: return None
    os.makedirs(cache, exist_ok=True)
    src = bank if cmd[0] != "wine" else "Z:" + os.path.abspath(bank).replace("/", "\\")
    r = subprocess.run(cmd + ["-S", "0", "-o", "?n.wav", src], cwd=cache, capture_output=True, text=True)
    if r.returncode != 0 or not glob.glob(os.path.join(cache, "*.wav")): return None
    open(os.path.join(cache, ".done"), "w").close()
    return cache


def read_wav(path):
    with wave.open(path) as w:
        n, ch, sw, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        data = np.frombuffer(w.readframes(n), dtype={2: np.int16, 4: np.int32}[sw]).astype(np.float32)
    data /= 32768.0 if sw == 2 else 2147483648.0
    return data.reshape(-1, ch).mean(axis=1), rate


@functools.lru_cache(maxsize=None)
def loudness(path, loop=False):
    """A loop's RMS, a shot's in its loudest 60 ms."""
    x, rate = read_wav(path)
    if loop or len(x) < rate * 0.06: return float(np.sqrt(np.mean(x * x)) + 1e-9)
    win = int(rate * 0.06)
    e = np.convolve(x * x, np.ones(win) / win, mode="valid")
    return float(np.sqrt(e.max()) + 1e-9)


class Sounds:
    """The waves the mod uses, written into <out>/audio/ as they are asked for."""
    def __init__(self, bank, out):
        self.dir = decode_bank(bank) if os.path.exists(bank) else None
        self.out = out
        self.written = set()
        self.names = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(self.dir, "*.wav"))) if self.dir else []

    def __bool__(self): return bool(self.names)

    def find(self, pattern):
        return [n for n in self.names if re.match(pattern, n)]

    def write(self, name, gain=1.0):
        """The wave into the mod as audio/<name lower case>.ogg, 'gain' baked in; the path ships.json names."""
        rel = "audio/" + name.lower() + ("" if gain == 1.0 else f"_x{gain:g}") + ".ogg"
        if rel in self.written: return rel
        self.written.add(rel)
        dst = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        src = os.path.join(self.dir, name + ".wav")
        ff = shutil.which("ffmpeg")
        if not (ff and subprocess.run([ff, "-y", "-loglevel", "error", "-i", src, *(["-af", f"volume={gain:g}"] if gain != 1.0 else []),
                                       "-c:a", "libvorbis", "-q:a", "5",
                                       "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", dst],
                                      capture_output=True).returncode == 0):
            shutil.copy(src, dst[:-4] + ".wav")
        return rel

    def level(self, names, target, loop=False):
        """The volume that plays these waves (their mean loudness) at 'target', and the gain to bake into them when that is
        over 1 (as far as their peak allows): (volume within 0.05..1, gain)."""
        lv = float(np.mean([loudness(os.path.join(self.dir, n + ".wav"), loop) for n in names]))
        v = target / lv
        gain = 1.0
        if v > 1.0:
            peak = max(float(np.abs(read_wav(os.path.join(self.dir, n + ".wav"))[0]).max()) for n in names)
            gain = round(max(1.0, min(v, 0.98 / max(peak, 1e-6))), 2)
            v /= gain
        return round(min(1.0, max(0.05, v)), 3), gain

    def one(self, names, target, loop=False, pitch=None, low=None):
        """A sounds entry: { files, volume ([low share x v, v] with 'low'), pitch }."""
        v, gain = self.level(names, target, loop)
        e = {"files": [self.write(n, gain) for n in names]} if len(names) > 1 else {"file": self.write(names[0], gain)}
        e["volume"] = [round(v * low, 3), v] if low is not None else v
        if pitch: e["pitch"] = pitch
        return e

    def ship(self, sound_list, identity, cls):
        """A ship's ships.json "sounds" from its SoundList event names; None when there are no waves."""
        if not self: return None
        race = next((m.group(1) for n in sound_list if (m := re.match(r"Engine (?:MAIN|Boost|Accel) (\w+) (\w+)", n or ""))), None)
        key = SET_OF_RACE.get(race) or SET_OF_IDENTITY.get(identity, "terran")
        if key == "terran" and any(re.match(r"Engine \w+ Terran Scout", n or "") for n in sound_list): key = "terran_scout"
        s = SETS[key]
        out = {}
        eng = self.find("^" + s["engine"] + "(_\\d+)?$")
        if eng: out["engine"] = self.one(eng[:1], ENGINE_LEVEL, loop=True, pitch=[0.85, 1.1], low=0.6)
        for part, wave_part, loop in (("boostStart", "in", False), ("boostLoop", "loop", True), ("boostStop", "out", False)):
            w = self.find("^" + s["boost"] + wave_part + "(_\\d+)?$")
            if not w: continue
            if part == "boostLoop": out[part] = self.one(w[:1], BOOST_LOOP_LEVEL, loop=True, pitch=[1.0, 1.15], low=0.5)
            elif part == "boostStart": out[part] = self.one(w, BOOST_LEVEL, pitch=[0.95, 1.05])
            else: out[part] = self.one(w, BOOST_LEVEL * 0.6, pitch=[0.95, 1.05])
        return out or None

    def weapon(self, family):
        """A hardpoint rule's "sound" for a gun family (weapon_generic_NNN); None without waves."""
        if not self: return None
        if family in BEAM:
            ign, loop = (self.find("^" + p + r"\d+$") for p in BEAM[family])
            if not ign or not loop: return None
            return {"shot": self.one(ign, SHOT_LEVEL, pitch=[0.95, 1.05]), "loop": self.one(loop[:1], SHOT_LEVEL, loop=True), "release": 120}
        w = self.find(SHOTS.get(family, "^$"))
        return {"shot": self.one(w, SHOT_LEVEL, pitch=[0.95, 1.05])} if w else None

    def item_shot(self, family):
        """An item's fx "shot" (files only: the game plays them at its shots' 0.7): the family's shot waves (a beam's
        ignition) written at the game's shot loudness at that volume; None without waves."""
        if not self: return None
        w = self.find("^" + BEAM[family][0] + r"\d+$") if family in BEAM else self.find(SHOTS.get(family, "^$"))
        if not w: return None
        lv = float(np.mean([loudness(os.path.join(self.dir, n + ".wav")) for n in w]))
        peak = max(float(np.abs(read_wav(os.path.join(self.dir, n + ".wav"))[0]).max()) for n in w)
        gain = round(min(SHOT_LEVEL / 0.7 / lv, 0.98 / max(peak, 1e-6)), 2)
        return [self.write(n, gain) for n in w]

    def launcher(self, kind):
        w = self.find(LAUNCHERS[kind])
        return {"shot": self.one(w, SHOT_LEVEL, pitch=[0.95, 1.05])} if w and self else None
