#!/usr/bin/env python3
"""Galaxy on Fire 3 ships for the Galaxy on Fire 2 Unity Remake: builds the gof3_ships mod from your own copy of Galaxy on
Fire 3: Manticore. Nothing of Galaxy on Fire 3 comes with this importer; the mod it writes is for your own use (don't share it).

    python3 import.py <game files> [<game files> ...] [--out FOLDER] [--work FOLDER] [--jobs N] [--blender PATH]
                      [--max-texture 1024] [--no-icons] [--remake FOLDER] [--fresh]          (on Windows: py import.py ...)

<game files>: the Android version's files: its two .obb files (main.*.obb, patch.*.obb) and its APK (the .apk, or an .xapk
/ .apks bundle, or the APK's assets/game.jet); and / or the Switch version's romfs (the folder with game.tin, gfx.tin,
patch*.tin). Files or the folders holding them; both versions together are layered, the Switch's over the Android's (the
Switch romfs alone lacks a few hulls' materials). See README.md.

The stages (each kept in the work folder, so a run that stops goes on where it was; --fresh starts over):
  1 extract   the archives (tools/tinextract.py), then merged into one tree the way the game layers its patches
  2 data      the weapon loadouts from data.pdb (tools/ae4_pdb_arming.py)
  3 ships     every hull: its materials resolved (ae4_resolve.py), its textures baked with the game's shader math
              (ae4_ship_textures.py), the model built in Blender (ae4_ship_to_fbx.py -> .blend, ae4_to_gltf.py -> .glb), and
              each named paint scheme as a model of its own (ae4_scheme_variant.py: its decal sheet)
  4 weapons   the GoF3 guns, mounts and rockets (convert_weapons.py)
  5 loadouts  every hull with its default guns, and which weapon each hardpoint carries (build_loadouts.py)
  6 mod       the mod itself (build_gof3_mod.py): ships.json, shipkits.json, hulls, skins, guns, turret, icons, preview
"""
import argparse, glob, importlib.metadata, json, os, platform, re, shutil, stat, subprocess, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "tools")
MOD_ID = "gof3_ships"
PY = sys.executable
sys.path.insert(0, TOOLS)
import build_cache as cache

# The order the archives are layered in, the later winning a file several hold: the Android files first, the Switch's over
# them (its textures and materials win where both have a file; the Android OBB fills what the Switch romfs lacks: the
# materials of Terran 021 / 022 and Vossk 121, the gold guns). Switch: what the reference build used (its data.pdb is
# patch_1_0_1's; patch_1_0_2 holds an older data set than 1_0_1); unknown archives after these.
ANDROID_ORDER = ["android_main", "android_patch", "android_game"]
SWITCH_ORDER = ["patch", "game", "gfx", "patch_1_0_2", "patch_1_0_1"]
NUMBERED = {"000", "001", "002", "003", "pirate", "huawei"}   # paint schemes that are skins only (no model of their own)


def fail(msg):
    print("\nERROR: " + msg)
    sys.exit(1)


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- checks

def check_python():
    if sys.version_info < (3, 9): fail("Python 3.9 or newer is needed")
    missing = []
    for mod, pip in (("numpy", "numpy"), ("PIL", "pillow"), ("texture2ddecoder", "texture2ddecoder"), ("scipy", "scipy")):
        try: __import__(mod)
        except ImportError: missing.append(pip)
    try:
        import pyzstd  # noqa: F401
    except ImportError:
        sys.path.insert(0, TOOLS)
        import ae4unpack
        try: ae4unpack._load()
        except RuntimeError: missing.append("pyzstd")
    if missing:
        cmd = "py -m pip" if platform.system() == "Windows" else f"{os.path.basename(PY)} -m pip"
        fail(f"missing Python packages: {', '.join(missing)}\n  Install them:   {cmd} install {' '.join(missing)}")


def version_key(path):
    return [int(n) for n in re.findall(r"\d+", path)]


def find_blender(given):
    """Blender's executable: --blender (an .app on a Mac too), the PATH, Program Files / Steam (Windows), Applications (macOS)."""
    if given:
        given = os.path.expanduser(given)
        if os.path.isdir(given) and given.endswith(".app"): given = os.path.join(given, "Contents", "MacOS", "Blender")
        if not os.path.exists(given) and not shutil.which(given): fail(f"Blender not found at {given}")
        return given
    b = shutil.which("blender")
    if b: return b
    system = platform.system()
    if system == "Windows":
        found = []
        for root in {os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", r"C:\Program Files")}:
            found += glob.glob(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe"))
        if found: return sorted(found, key=version_key)[-1]
        for steam in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files")):
            exe = os.path.join(steam, "Steam", "steamapps", "common", "Blender", "blender.exe")
            if os.path.exists(exe): return exe
    if system == "Darwin":
        apps = glob.glob("/Applications/Blender*.app") + glob.glob(os.path.expanduser("~/Applications/Blender*.app"))
        apps += [os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Blender/Blender.app")]
        exes = [e for e in (os.path.join(a, "Contents", "MacOS", "Blender") for a in apps) if os.path.exists(e)]
        if exes: return sorted(exes, key=version_key)[-1]
    fail("Blender (4.2 or newer) is needed: install it from blender.org, or give its path with --blender")


def blender_version(blender):
    r = subprocess.run([blender, "-b", "--version"], capture_output=True, text=True)
    m = re.search(r"Blender (\d+)\.(\d+)", r.stdout)
    if not m: fail(f"{blender} doesn't run as Blender:\n{r.stdout[-500:]}{r.stderr[-500:]}")
    v = (int(m.group(1)), int(m.group(2)))
    if v < (4, 2): fail(f"Blender {v[0]}.{v[1]} is too old: 4.2 or newer is needed")
    return r.stdout[m.start():].splitlines()[0].strip()


# ---------------------------------------------------------------- folders

def remove_tree(path):
    """Deletes a folder; on Windows a read-only file is made writable and a file another program holds is tried again."""
    def clear_readonly(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    for attempt in range(5):
        try:
            if sys.version_info >= (3, 12): shutil.rmtree(path, onexc=clear_readonly)
            else: shutil.rmtree(path, onerror=clear_readonly)
            return
        except FileNotFoundError:
            return
        except OSError as e:
            if attempt == 4:
                fail(f"can't replace {path}: {e}\n  Close anything that has a file of it open (the game, an Explorer / Finder window) and run it again.")
            time.sleep(1)


def prepare_out(out):
    """An empty folder for the mod: an earlier build of it is replaced, anything else is never touched."""
    if os.path.exists(out):
        try:
            with open(os.path.join(out, "mod.json"), encoding="utf-8-sig") as f: ours = json.load(f).get("id") == MOD_ID
        except Exception: ours = False
        if not ours and os.listdir(out): fail(f"{out} exists and isn't a {MOD_ID} mod: choose another --out")
        remove_tree(out)
    os.makedirs(out)


def pid_alive(pid):
    if pid <= 0: return False
    if platform.system() == "Windows":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h: return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)); ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259   # STILL_ACTIVE
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False
    except PermissionError: return True


def lock_work(work):
    """One run per work folder: a second one would convert the same hulls at the same time and break both."""
    lock = os.path.join(work, ".lock")
    try: pid = int(open(lock, encoding="utf-8").read().strip() or 0)
    except (OSError, ValueError): pid = 0
    if pid and pid != os.getpid() and pid_alive(pid):
        fail(f"another run (process {pid}) is using the work folder {work}: wait for it, or stop it first")
    open(lock, "w", encoding="utf-8").write(str(os.getpid()))
    import atexit
    atexit.register(lambda: os.path.exists(lock) and os.remove(lock))


def lp(path):
    """A path Windows opens past its 260-character limit (the extended-length form \\\\?\\C:\\...): the game's archives
    hold paths of almost 200 characters, under a work folder in the user's profile that is too long. Elsewhere the path."""
    path = os.path.abspath(path)
    if platform.system() != "Windows" or path.startswith("\\\\?\\"): return path
    return "\\\\?\\UNC\\" + path[2:] if path.startswith("\\\\") else "\\\\?\\" + path


def place(src, dst):
    """dst becomes src: a hard link (no extra space), else a copy (another drive, a file system without links)."""
    if os.path.exists(dst): os.remove(dst)
    try: os.link(src, dst)
    except OSError: shutil.copy2(src, dst)


# ---------------------------------------------------------------- 1 the game files

def find_sources(paths, work, verified=None):
    """The archives to extract: [(name, path, platform)]. Folders are searched (four levels down); an .apk / .xapk / .apks
    gives up its game.jet (and an .xapk its .obb files), copied into the work folder."""
    verified = {} if verified is None else verified
    files = []
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        if not os.path.exists(p): fail(f"{p} doesn't exist")
        if os.path.isdir(p):   # four levels down: an unpacked .xapk keeps its OBBs in Android/obb/<package>/
            base = p.rstrip("/\\").count(os.sep)
            for d, dirs, fs in os.walk(p):
                if d.count(os.sep) - base >= 4: dirs[:] = []
                dirs[:] = [x for x in dirs if x.lower() not in ("work", "converted", "extracted", "merged")]   # (not our own work folder)
                files += [os.path.join(d, f) for f in fs if f.lower().endswith((".tin", ".obb", ".jet", ".apk", ".xapk", ".apks"))]
        else:
            files.append(p)
    out, seen = [], set()
    unpacked = os.path.join(work, "sources")
    for f in sorted(set(files)):
        low = f.lower()
        if low.endswith(".tin"):
            out.append((os.path.splitext(os.path.basename(f))[0], f, "switch"))
        elif low.endswith(".obb"):
            out.append((obb_name(f), f, "android"))
        elif low.endswith(".jet"):
            out.append(("android_game", f, "android"))
        elif low.endswith((".apk", ".xapk", ".apks")):
            out += from_bundle(f, unpacked, verified)
    unique = []
    for name, f, plat in out:
        if name in seen:
            if source_hash(f, verified) == source_hash(next(x for n, x, _ in unique if n == name), verified): continue   # the same file twice
            fail(f"two different archives are both {name}: give the game files of one version only")
        seen.add(name); unique.append((name, f, plat))
    out = unique
    if not out:
        fail("no Galaxy on Fire 3 game files found (the Switch romfs' .tin files, or the Android .obb files and APK)")
    names = {n for n, _, _ in out}
    plats = {p for _, _, p in out}
    if plats == {"android"}:
        if "android_main" not in names: fail("the Android main .obb file (main.<version>.com.dsfishlabs.gofmanticore.obb) is missing")
        if "android_game" not in names: fail("the Android APK (or its assets/game.jet, which holds the game data) is missing")
    if plats == {"switch"}:
        if "game" not in names or "gfx" not in names: fail("the Switch romfs' game.tin and gfx.tin are both needed")
        log("  note: the Switch romfs alone lacks the materials of a few hulls (Terran 021 / 022, Vossk 121) and the gold guns;\n"
            "        give the Android .obb files too and those are filled in from them")
    return out


def obb_name(path):
    """main.2206081.com.dsfishlabs.gofmanticore.obb -> android_main, patch.* -> android_patch."""
    b = os.path.basename(path).lower()
    return "android_main" if b.startswith("main.") else "android_patch" if b.startswith("patch.") else "android_" + os.path.splitext(b)[0]


def source_hash(path, verified):
    """A hash already computed from full contents in this invocation, never a persisted shortcut."""
    path = os.path.abspath(path)
    if path not in verified: verified[path] = cache.file_hash(path)
    return verified[path]


def from_bundle(path, unpacked, verified=None):
    """An .apk: its assets/game.jet. An .xapk / .apks (a zip of APKs and, for .xapk, Android/obb/...): the game.jet of the
    APK that has it, and the .obb files."""
    verified = {} if verified is None else verified
    unpacked = os.path.join(unpacked, cache.digest(os.path.abspath(path)))
    os.makedirs(unpacked, exist_ok=True)
    found = []
    def apk_jet(z, label):
        if "assets/game.jet" in z.namelist():
            dst = os.path.join(unpacked, cache.digest(label), "game.jet")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            verified[os.path.abspath(dst)] = cache.materialize_member(z, "assets/game.jet", dst)
            found.append(("android_game", dst, "android"))
            return True
        return False
    try:
        with zipfile.ZipFile(path) as z:
            if apk_jet(z, path): return found
            for n in z.namelist():
                if n.lower().endswith(".obb"):
                    dst = os.path.join(unpacked, os.path.basename(n))
                    log(f"  checking {os.path.basename(n)} from {os.path.basename(path)}")
                    verified[os.path.abspath(dst)] = cache.materialize_member(z, n, dst)
                    found.append((obb_name(dst), dst, "android"))
                elif n.lower().endswith(".apk"):
                    import tempfile
                    # Keep small APKs in memory; spill large ones instead of holding the whole bundle member in RAM.
                    with tempfile.SpooledTemporaryFile(max_size=64 << 20) as apk:
                        with z.open(n) as src: shutil.copyfileobj(src, apk, 4 << 20)
                        apk.seek(0)
                        with zipfile.ZipFile(apk) as inner: apk_jet(inner, n)
    except zipfile.BadZipFile:
        fail(f"{path} isn't a readable APK / bundle")
    if not any(n == "android_game" for n, _, _ in found): log(f"  note: no assets/game.jet in {os.path.basename(path)}")
    return found


def extract(sources, work, fingerprints):
    sys.path.insert(0, TOOLS)
    import tinextract
    ex = os.path.join(work, "extracted")
    for name, path, _ in sources:
        dest = os.path.join(ex, name)
        if cache.done(dest, fingerprints[name]): continue
        remove_tree(lp(dest))
        part = os.path.join(ex, name + ".partial")   # renamed once complete, so a stopped run starts that archive over
        remove_tree(lp(part))
        if not tinextract.extract(path, None, dest=lp(part)): fail(f"{path} didn't extract cleanly (see the errors above)")
        os.replace(lp(part), lp(dest))
        cache.mark(dest, fingerprints[name])


def merge(sources, work, fingerprint):
    """One tree of the archives (work/merged: assets/, data.pdb, particles/, ...), the later archive winning a file several
    hold: hard links, so it takes no extra space."""
    merged = os.path.join(work, "merged")
    if cache.done(merged, fingerprint): return merged
    names = [n for n, _, _ in sources]
    known = ANDROID_ORDER + SWITCH_ORDER
    order = [n for n in known if n in names] + sorted(n for n in names if n not in known)
    log(f"  layering {', '.join(order)}")
    files = {}
    for n in order:
        root = lp(os.path.join(work, "extracted", n))
        for d, _, fs in os.walk(root):
            for f in fs:
                if f == ".done" and d == root: continue
                full = os.path.join(d, f)
                files[os.path.relpath(full, root)] = full
    remove_tree(lp(merged))
    for rel, src in files.items():
        dst = os.path.join(lp(merged), rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        place(src, dst)
    for need in ("data.pdb", os.path.join("assets", "ships")):
        if not os.path.exists(os.path.join(merged, need)): fail(f"the game files have no {need}: are these Galaxy on Fire 3's?")
    cache.mark(merged, fingerprint)
    return merged


# ---------------------------------------------------------------- 3 the ships

def ship_list(assets):
    """(key, folder, name) of every hull: assets/ships/<race>/<num> with its LOD 0 body, and ships outside <race>/<num>
    (ships/starfox) named after their model (convert_ship.sh's rule)."""
    out = []
    for body in sorted(glob.glob(os.path.join(assets, "ships", "*", "*_lod_000_body.ae4model"))
                       + glob.glob(os.path.join(assets, "ships", "*", "*", "*_lod_000_body.ae4model"))):
        folder = os.path.dirname(body)
        rel = os.path.relpath(folder, os.path.join(assets, "ships")).replace(os.sep, "/")
        model = os.path.basename(body)[:-len("_lod_000_body.ae4model")]
        if not re.fullmatch(r"ship_[a-z]+_\d{3}", model): continue     # menu / npc / drone models
        parts = rel.split("/")
        name = f"ship_{parts[0]}_{parts[1]}" if len(parts) == 2 else model
        if name != model and len(parts) == 2: continue                 # (a folder whose model is another's)
        out.append((rel, folder, name))
    return out


def run(cmd, logf, env):
    with open(logf, "a", encoding="utf-8", errors="replace") as lf:
        lf.write("\n$ " + " ".join(cmd) + "\n"); lf.flush()
        r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env)
    return r.returncode == 0


def variants_of(resolve):
    """The named paint schemes that get a model of their own (their decal sheet can differ): the material schemes that
    aren't numbered / pirate / huawei and aren't cloak / dissolve states, and the data.pdb skins."""
    named = set()
    for p in resolve.get("schemes") or []:
        m = re.search(r"_body_(\w+)\.ae4material$", p)
        if m and m.group(1) not in NUMBERED and not re.search(r"cloak|dissolve", m.group(1)): named.add(m.group(1))
    named |= {sk["scheme"] for sk in resolve.get("data_skins", []) if sk.get("scheme")}
    return sorted(named)


def convert_ship(job, assets, conv, logs, blender, env, fingerprint):
    key, folder, name = job
    out = os.path.join(conv, name)
    if cache.done(out, fingerprint) and os.path.isfile(os.path.join(out, name + ".glb")):
        return name, True, ""
    # A removed or failed paint scheme must not survive from an earlier conversion.
    for variant in glob.glob(os.path.join(conv, name + "_*")):
        if os.path.isdir(variant): remove_tree(variant)
    remove_tree(out); os.makedirs(out)
    logf = os.path.join(logs, name + ".log")
    if os.path.exists(logf): os.remove(logf)
    rj = os.path.join(out, "resolve.json")
    T = lambda f: os.path.join(TOOLS, f)
    steps = [
        [PY, T("ae4_resolve.py"), assets, key, rj],
        [PY, T("ae4_ship_textures.py"), folder, name, os.path.join(out, "textures"), rj],
        [blender, "-b", "--factory-startup", "-P", T("ae4_ship_to_fbx.py"), "--", folder, name, out],
        [blender, "-b", "--factory-startup", "-P", T("ae4_to_gltf.py"), "--", os.path.join(out, name + ".blend")],
    ]
    for cmd in steps:
        if not run(cmd, logf, env):
            remove_tree(out)
            return name, False, logf
    if not os.path.exists(os.path.join(out, name + ".glb")):
        remove_tree(out)
        return name, False, logf
    with open(rj, encoding="utf-8-sig") as f: resolve = json.load(f)
    bad = []
    for scheme in variants_of(resolve):
        v = f"{name}_{scheme}"
        vdir = os.path.join(conv, v)
        remove_tree(vdir)
        if not (run([blender, "-b", "--factory-startup", "-P", T("ae4_scheme_variant.py"), "--", out, scheme], logf, env)
                and run([blender, "-b", "--factory-startup", "-P", T("ae4_to_gltf.py"), "--", os.path.join(vdir, v + ".blend")], logf, env)
                and os.path.exists(os.path.join(vdir, v + ".glb"))):
            bad.append(scheme); remove_tree(vdir)   # (a skin model is only its decal sheet's source: the skin stays)
    if not bad: cache.mark(out, fingerprint)
    return name, True, ("variants failed: " + ", ".join(bad)) if bad else ""


# ---------------------------------------------------------------- main

def main():
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(errors="replace")
        except (AttributeError, ValueError): pass
    ap = argparse.ArgumentParser(description="Builds the gof3_ships mod for the Galaxy on Fire 2 Unity Remake from your own Galaxy on Fire 3 files.")
    ap.add_argument("sources", nargs="+", help="the Switch romfs folder (.tin files), or the Android .obb files and APK (or their folder)")
    ap.add_argument("--out", default=os.path.join(HERE, MOD_ID), help="where the mod goes (default: gof3_ships next to this script)")
    ap.add_argument("--work", default=os.path.join(HERE, "work"), help="the work folder (default: work next to this script; "
                                                                     "needs about 15 GB for the Switch files, 8 GB for Android)")
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 4) // 2)), help="ships converted at once")
    ap.add_argument("--blender", help="the Blender executable (or Blender.app on a Mac), if it isn't found by itself")
    ap.add_argument("--max-texture", type=int, default=1024, help="the hulls' texture size in the mod (default 1024; 2048 = full size)")
    ap.add_argument("--no-icons", action="store_true", help="skip rendering the ships' shop icons and the preview")
    ap.add_argument("--remake", help="a checkout of the remake's source: its ship tables for the prices and its frame for the icons")
    ap.add_argument("--fbx", action="store_true", help="also write FBX files of the converted models (the work folder)")
    ap.add_argument("--fresh", action="store_true", help="start over: delete the work folder first")
    a = ap.parse_args()

    check_python()
    blender = find_blender(a.blender)
    blender_identity = blender_version(blender)
    log(f"{blender_identity}: {blender}")
    work = os.path.abspath(os.path.expanduser(a.work))
    out = os.path.abspath(os.path.expanduser(a.out))
    if a.fresh: remove_tree(work)
    os.makedirs(work, exist_ok=True)
    lock_work(work)

    packages = {}
    for package in ("numpy", "Pillow", "texture2ddecoder", "scipy", "pyzstd"):
        try: packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: packages[package] = None
    runtime = {"python": platform.python_version(), "platform": platform.platform(), "packages": packages}

    log("1/6 Finding and extracting the game files ...")
    verified = {}
    sources = find_sources(a.sources, work, verified)
    log("  " + ", ".join(f"{os.path.basename(p)} ({plat})" for _, p, plat in sources))
    log("  hashing source archives (SHA-256) ...")
    source_info = [{"name": n, "file": os.path.basename(p), "platform": plat,
                    "bytes": os.path.getsize(p), "sha256": source_hash(p, verified)} for n, p, plat in sources]
    stages = {}
    extract_keys = {}
    for src in source_info:
        recipe = cache.stage(HERE, ["tinextract.py"], src,
                             {"python": runtime["python"], "platform": runtime["platform"], "pyzstd": packages["pyzstd"]})
        stages["extract/" + src["name"]] = recipe
        extract_keys[src["name"]] = recipe["fingerprint"]
    extract(sources, work, extract_keys)
    names = set(extract_keys)
    order = [n for n in ANDROID_ORDER + SWITCH_ORDER if n in names] + sorted(names - set(ANDROID_ORDER + SWITCH_ORDER))
    stages["merge"] = cache.stage(HERE, [], [(n, extract_keys[n]) for n in order])
    merged = merge(sources, work, stages["merge"]["fingerprint"])
    assets = os.path.join(merged, "assets")
    conv = os.path.join(work, "converted")
    logs = os.path.join(work, "logs"); os.makedirs(logs, exist_ok=True)
    data = os.path.join(work, "data"); os.makedirs(data, exist_ok=True)
    env = dict(os.environ, GOF3_BLENDER=blender, GOF3_PDB=os.path.join(merged, "data.pdb"), GOF3_DATA_DIR=data,
               GOF3_CONV=conv, GOF3_LOADOUTS=os.path.join(work, "loadouts"), GOF3_MERGED=merged, GOF3_ASSETS=assets,
               PYTHONIOENCODING="utf-8")
    env.pop("GOF3_NO_FBX", None)
    if not a.fbx: env["GOF3_NO_FBX"] = "1"
    if a.remake: env["GOF3_REMAKE"] = os.path.abspath(os.path.expanduser(a.remake))
    else: env["GOF3_REMAKE"] = os.path.join(work, "no-remake")   # the builder's built-in price fits and drawn icon frame

    conversion_options = dict(runtime, blender=blender_identity, fbx=a.fbx)
    merged_key = stages["merge"]["fingerprint"]
    stages["data"] = cache.stage(HERE, ["ae4_pdb_arming.py"], merged_key, runtime)
    data_key = stages["data"]["fingerprint"]
    log("2/6 Reading the weapon loadouts from data.pdb ...")
    if not cache.done(data, data_key) or not os.path.isfile(os.path.join(data, "data_arming.json")):
        remove_tree(data); os.makedirs(data)
        if not run([PY, os.path.join(TOOLS, "ae4_pdb_arming.py"), os.path.join(merged, "data.pdb"), "--write",
                    os.path.join(data, "data_arming.json")], os.path.join(logs, "data.log"), env):
            fail(f"reading data.pdb failed: see {os.path.join(logs, 'data.log')}")
        cache.mark(data, data_key)

    stages["ships"] = cache.stage(HERE, ["ae4_resolve.py", "ae4_ship_textures.py", "ae4_ship_to_fbx.py",
        "ae4_to_gltf.py", "ae4_scheme_variant.py"], [merged_key, data_key], conversion_options)
    ships_key = stages["ships"]["fingerprint"]
    ships = ship_list(assets)
    log(f"3/6 Converting {len(ships)} hulls and their paint schemes ({a.jobs} at a time; the longest step, minutes per hull) ...")
    os.makedirs(conv, exist_ok=True)
    # Drop hulls removed from the source inventory, including their paint-scheme folders.
    hull_names = {name for _, _, name in ships}
    for folder in glob.glob(os.path.join(conv, "ship_*")):
        if not any(os.path.basename(folder) == n or os.path.basename(folder).startswith(n + "_") for n in hull_names):
            remove_tree(folder)
    failed, warnings = [], []
    with ThreadPoolExecutor(a.jobs) as pool:
        for i, (name, ok, note) in enumerate(pool.map(
                lambda j: convert_ship(j, assets, conv, logs, blender, env, ships_key), ships), 1):
            log(f"  {i}/{len(ships)} {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({note})" if note else ""))
            if not ok: failed.append(name)
            if note: warnings.append({"stage": "ships", "name": name, "detail": note})
    if failed: log(f"  {len(failed)} hulls failed (the mod is built without them): see {logs}")

    log("4/6 Converting the weapons ...")
    stages["weapons"] = cache.stage(HERE, ["convert_weapons.py"], merged_key, conversion_options)
    weapons_key = stages["weapons"]["fingerprint"]
    wdir = os.path.join(conv, "weapons")
    if not cache.done(wdir, weapons_key):
        remove_tree(wdir)
        weapon_log = os.path.join(logs, "weapons.log")
        if os.path.exists(weapon_log): os.remove(weapon_log)
        if not run([PY, os.path.join(TOOLS, "convert_weapons.py"), assets, wdir], weapon_log, env):
            fail(f"converting the weapons failed: see {weapon_log}")
        with open(weapon_log, encoding="utf-8", errors="replace") as f:
            skipped_weapons = [line.strip() for line in f if line.lstrip().startswith("skipped ")]
        cache.mark(wdir, weapons_key, skipped=skipped_weapons)
    skipped_weapons = cache.record(wdir).get("skipped", [])

    log("5/6 The hulls with their default guns ...")
    # Output hashes also catch a previously failed hull/variant succeeding on a later run.
    converted = {os.path.relpath(p, conv).replace(os.sep, "/"): cache.file_hash(p)
                 for pattern in ("ship_*/*.blend", "ship_*/resolve.json", "weapons/*/*.blend")
                 for p in sorted(glob.glob(os.path.join(conv, pattern)))}
    stages["loadouts"] = cache.stage(HERE, ["build_loadouts.py"],
        [ships_key, weapons_key, data_key, converted], conversion_options)
    loadouts_key = stages["loadouts"]["fingerprint"]
    ldir = os.path.join(work, "loadouts")
    if not cache.done(ldir, loadouts_key) or not os.path.isfile(os.path.join(ldir, "manifest.json")):
        remove_tree(ldir)
        if not run([PY, os.path.join(TOOLS, "build_loadouts.py"), conv, ldir, str(a.jobs)], os.path.join(logs, "loadouts.log"), env):
            fail(f"the loadouts failed: see {os.path.join(logs, 'loadouts.log')}")
        with open(os.path.join(ldir, "manifest.json"), encoding="utf-8-sig") as f: loadout_info = json.load(f)
        if not any("error" in row for row in loadout_info.values()): cache.mark(ldir, loadouts_key)
    with open(os.path.join(ldir, "manifest.json"), encoding="utf-8-sig") as f: loadout_info = json.load(f)
    loadout_failures = [name for name, row in loadout_info.items() if "error" in row]
    log("6/6 Building the mod ...")
    prepare_out(out)
    # An interrupted new build must not appear to have the previous build's provenance.
    for previous in (out + ".build-manifest.json", os.path.join(work, "build-manifest.json")):
        if os.path.isfile(previous): os.remove(previous)
    cmd = [PY, os.path.join(TOOLS, "build_gof3_mod.py"), out, "--max-texture", str(a.max_texture)] + (["--no-icons"] if a.no_icons else [])
    mod_log = os.path.join(logs, "mod.log")
    if os.path.exists(mod_log): os.remove(mod_log)
    if not run(cmd, mod_log, env): fail(f"building the mod failed: see {mod_log}")
    importer_code = {"import.py": cache.file_hash(os.path.join(HERE, "import.py"))}
    for filename in sorted(os.listdir(TOOLS)):
        if filename.endswith((".py", ".json", ".txt")):
            importer_code["tools/" + filename] = cache.file_hash(os.path.join(TOOLS, filename))
    remake_inputs = {}
    for relative in ("Assets/Resources/GoF2Data/ships.json", "Assets/Resources/GoF2Data/economy_default.json",
                     "Assets/Resources/GoF2Data/stations.json", "Assets/Resources/GoF2Data/systems.json",
                     "Assets/Resources/GoF2Data/items.json", "Assets/Textures/textures/gof2_interface2_ipad_large.png"):
        path = os.path.join(env["GOF3_REMAKE"], relative)
        if os.path.isfile(path): remake_inputs[relative] = cache.file_hash(path)
    options = {"max_texture": a.max_texture, "icons": not a.no_icons, "fbx": a.fbx,
               "remake": os.path.abspath(os.path.expanduser(a.remake)) if a.remake else None, "jobs": a.jobs}
    stages["mod"] = cache.stage(HERE, [name for name in os.listdir(TOOLS) if name.endswith((".py", ".json", ".txt"))],
        [loadouts_key, converted, remake_inputs], dict(conversion_options, **options))
    with open(mod_log, encoding="utf-8", errors="replace") as f:
        builder_notes = [line.strip() for line in f if any(word in line.lower() for word in ("skipped", "no sounds", "not found"))]
    manifest = {"schema": 1, "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "importer": {"revision": cache.revision(HERE), "files": importer_code,
                             "sha256": cache.digest(importer_code)},
                "sources": source_info, "runtime": dict(runtime, blender=blender_identity),
                "options": options, "remake_inputs": remake_inputs,
                "stages": stages, "failed_hulls": failed, "warnings": warnings,
                "skipped_weapons": skipped_weapons, "failed_loadouts": loadout_failures,
                "loadout_notes": {name: row["note"] for name, row in loadout_info.items() if "note" in row},
                "builder_notes": builder_notes}
    # The game hashes every file inside a mod for saves and multiplayer. Keep build-local
    # metadata beside the mod so timestamps and machine details cannot change those hashes.
    cache.write_json(out + ".build-manifest.json", manifest)
    cache.write_json(os.path.join(work, "build-manifest.json"), manifest)
    with open(os.path.join(out, "ships.json"), encoding="utf-8-sig") as f: n = len(json.load(f))
    log(f"\nDone: {n} ships in {out}\n"
        f"Install: copy the {MOD_ID} folder into the game's Mods folder and turn it on in the main menu's Mods screen.\n"
        f"The work folder ({work}) can be deleted, or kept to rebuild faster.\n"
        "The mod holds Galaxy on Fire 3's models and textures from your own copy of the game: keep it to yourself.")


if __name__ == "__main__":
    main()
