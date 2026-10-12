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
import argparse, glob, json, os, platform, re, shutil, stat, subprocess, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "tools")
MOD_ID = "gof3_ships"
PY = sys.executable

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
    for mod, pip in (("numpy", "numpy"), ("PIL", "pillow"), ("texture2ddecoder", "texture2ddecoder")):
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
    return f"{v[0]}.{v[1]}"


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
        try: ours = json.load(open(os.path.join(out, "mod.json"), encoding="utf-8-sig")).get("id") == MOD_ID
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


def done(path): return os.path.exists(os.path.join(path, ".done"))


def mark(path):
    os.makedirs(path, exist_ok=True)
    open(os.path.join(path, ".done"), "w", encoding="utf-8").write(time.strftime("%Y-%m-%d %H:%M:%S\n"))


def place(src, dst):
    """dst becomes src: a hard link (no extra space), else a copy (another drive, a file system without links)."""
    if os.path.exists(dst): os.remove(dst)
    try: os.link(src, dst)
    except OSError: shutil.copy2(src, dst)


# ---------------------------------------------------------------- 1 the game files

def find_sources(paths, work):
    """The archives to extract: [(name, path, platform)]. Folders are searched (four levels down); an .apk / .xapk / .apks
    gives up its game.jet (and an .xapk its .obb files), copied into the work folder."""
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
            out += from_bundle(f, unpacked)
    unique = []
    for name, f, plat in out:
        if name in seen:
            if os.path.getsize(f) == os.path.getsize(next(x for n, x, _ in unique if n == name)): continue   # the same file twice
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


def from_bundle(path, unpacked):
    """An .apk: its assets/game.jet. An .xapk / .apks (a zip of APKs and, for .xapk, Android/obb/...): the game.jet of the
    APK that has it, and the .obb files."""
    os.makedirs(unpacked, exist_ok=True)
    found = []
    def apk_jet(z, label):
        if "assets/game.jet" in z.namelist():
            dst = os.path.join(unpacked, "game.jet")
            if not (os.path.exists(dst) and os.path.getsize(dst) == z.getinfo("assets/game.jet").file_size):
                with z.open("assets/game.jet") as s, open(dst, "wb") as d: shutil.copyfileobj(s, d, 1 << 20)
            found.append(("android_game", dst, "android"))
            return True
        return False
    try:
        with zipfile.ZipFile(path) as z:
            if apk_jet(z, path): return found
            for n in z.namelist():
                if n.lower().endswith(".obb"):
                    dst = os.path.join(unpacked, os.path.basename(n))
                    if not (os.path.exists(dst) and os.path.getsize(dst) == z.getinfo(n).file_size):
                        log(f"  unpacking {os.path.basename(n)} from {os.path.basename(path)}")
                        with z.open(n) as s, open(dst, "wb") as d: shutil.copyfileobj(s, d, 1 << 20)
                    found.append((obb_name(dst), dst, "android"))
                elif n.lower().endswith(".apk"):
                    import io
                    with zipfile.ZipFile(io.BytesIO(z.read(n))) as inner:
                        apk_jet(inner, n)
    except zipfile.BadZipFile:
        fail(f"{path} isn't a readable APK / bundle")
    if not any(n == "android_game" for n, _, _ in found): log(f"  note: no assets/game.jet in {os.path.basename(path)}")
    return found


def extract(sources, work):
    sys.path.insert(0, TOOLS)
    import tinextract
    ex = os.path.join(work, "extracted")
    for name, path, _ in sources:
        dest = os.path.join(ex, name)
        if done(dest): continue
        remove_tree(lp(dest))
        part = os.path.join(ex, name + ".partial")   # renamed once complete, so a stopped run starts that archive over
        remove_tree(lp(part))
        if not tinextract.extract(path, None, dest=lp(part)): fail(f"{path} didn't extract cleanly (see the errors above)")
        os.replace(lp(part), lp(dest))
        mark(dest)


def merge(sources, work):
    """One tree of the archives (work/merged: assets/, data.pdb, particles/, ...), the later archive winning a file several
    hold: hard links, so it takes no extra space."""
    merged = os.path.join(work, "merged")
    if done(merged): return merged
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
    mark(merged)
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


def convert_ship(job, assets, conv, logs, blender, env):
    key, folder, name = job
    out = os.path.join(conv, name)
    if done(out): return name, True, ""
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
        if not run(cmd, logf, env): return name, False, logf
    if not os.path.exists(os.path.join(out, name + ".glb")): return name, False, logf
    resolve = json.load(open(rj, encoding="utf-8-sig"))
    bad = []
    for scheme in variants_of(resolve):
        v = f"{name}_{scheme}"
        vdir = os.path.join(conv, v)
        remove_tree(vdir)
        if not (run([blender, "-b", "--factory-startup", "-P", T("ae4_scheme_variant.py"), "--", out, scheme], logf, env)
                and run([blender, "-b", "--factory-startup", "-P", T("ae4_to_gltf.py"), "--", os.path.join(vdir, v + ".blend")], logf, env)
                and os.path.exists(os.path.join(vdir, v + ".glb"))):
            bad.append(scheme); remove_tree(vdir)   # (a skin model is only its decal sheet's source: the skin stays)
    mark(out)
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
    log(f"Blender {blender_version(blender)}: {blender}")
    work = os.path.abspath(os.path.expanduser(a.work))
    out = os.path.abspath(os.path.expanduser(a.out))
    if a.fresh: remove_tree(work)
    os.makedirs(work, exist_ok=True)
    lock_work(work)

    log("1/6 Finding and extracting the game files ...")
    sources = find_sources(a.sources, work)
    log("  " + ", ".join(f"{os.path.basename(p)} ({plat})" for _, p, plat in sources))
    extract(sources, work)
    # The merged tree and everything made from it belong to one set of game files: another set (the Android files added to
    # a Switch run, a newer version) starts those over; the extracted archives are kept.
    signature = sorted([n, os.path.getsize(p)] for n, p, _ in sources)
    sig_file = os.path.join(work, "sources.json")
    try: old = json.load(open(sig_file, encoding="utf-8-sig"))
    except Exception: old = None
    if old != signature:
        for d in ("merged", "data", "converted", "loadouts"): remove_tree(lp(os.path.join(work, d)))
        json.dump(signature, open(sig_file, "w", encoding="utf-8"))
    merged = merge(sources, work)
    assets = os.path.join(merged, "assets")
    conv = os.path.join(work, "converted")
    logs = os.path.join(work, "logs"); os.makedirs(logs, exist_ok=True)
    data = os.path.join(work, "data"); os.makedirs(data, exist_ok=True)
    env = dict(os.environ, GOF3_BLENDER=blender, GOF3_PDB=os.path.join(merged, "data.pdb"), GOF3_DATA_DIR=data,
               GOF3_CONV=conv, GOF3_LOADOUTS=os.path.join(work, "loadouts"), GOF3_MERGED=merged, GOF3_ASSETS=assets,
               PYTHONIOENCODING="utf-8")
    if not a.fbx: env["GOF3_NO_FBX"] = "1"
    if a.remake: env["GOF3_REMAKE"] = os.path.abspath(os.path.expanduser(a.remake))
    else: env["GOF3_REMAKE"] = os.path.join(work, "no-remake")   # the builder's built-in price fits and drawn icon frame

    log("2/6 Reading the weapon loadouts from data.pdb ...")
    if not os.path.exists(os.path.join(data, "data_arming.json")):
        if not run([PY, os.path.join(TOOLS, "ae4_pdb_arming.py"), os.path.join(merged, "data.pdb"), "--write",
                    os.path.join(data, "data_arming.json")], os.path.join(logs, "data.log"), env):
            fail(f"reading data.pdb failed: see {os.path.join(logs, 'data.log')}")

    ships = ship_list(assets)
    log(f"3/6 Converting {len(ships)} hulls and their paint schemes ({a.jobs} at a time; the longest step, minutes per hull) ...")
    os.makedirs(conv, exist_ok=True)
    failed = []
    with ThreadPoolExecutor(a.jobs) as pool:
        for i, (name, ok, note) in enumerate(pool.map(lambda j: convert_ship(j, assets, conv, logs, blender, env), ships), 1):
            log(f"  {i}/{len(ships)} {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({note})" if note else ""))
            if not ok: failed.append(name)
    if failed: log(f"  {len(failed)} hulls failed (the mod is built without them): see {logs}")

    log("4/6 Converting the weapons ...")
    wdir = os.path.join(conv, "weapons")
    if not done(wdir):
        if not run([PY, os.path.join(TOOLS, "convert_weapons.py"), assets, wdir], os.path.join(logs, "weapons.log"), env):
            fail(f"converting the weapons failed: see {os.path.join(logs, 'weapons.log')}")
        mark(wdir)

    log("5/6 The hulls with their default guns ...")
    ldir = os.path.join(work, "loadouts")
    if not done(ldir):
        if not run([PY, os.path.join(TOOLS, "build_loadouts.py"), conv, ldir, str(a.jobs)], os.path.join(logs, "loadouts.log"), env):
            fail(f"the loadouts failed: see {os.path.join(logs, 'loadouts.log')}")
        mark(ldir)

    log("6/6 Building the mod ...")
    prepare_out(out)
    cmd = [PY, os.path.join(TOOLS, "build_gof3_mod.py"), out, "--max-texture", str(a.max_texture)] + (["--no-icons"] if a.no_icons else [])
    if not run(cmd, os.path.join(logs, "mod.log"), env): fail(f"building the mod failed: see {os.path.join(logs, 'mod.log')}")
    n = len(json.load(open(os.path.join(out, "ships.json"), encoding="utf-8-sig")))
    log(f"\nDone: {n} ships in {out}\n"
        f"Install: copy the {MOD_ID} folder into the game's Mods folder and turn it on in the main menu's Mods screen.\n"
        f"The work folder ({work}) can be deleted, or kept to rebuild faster.\n"
        "The mod holds Galaxy on Fire 3's models and textures from your own copy of the game: keep it to yourself.")


if __name__ == "__main__":
    main()
