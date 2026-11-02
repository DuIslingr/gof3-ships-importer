# Galaxy on Fire 3 ships importer

Builds the **gof3_ships** mod for the Galaxy on Fire 2 Unity Remake from **your own copy of Galaxy on Fire 3: Manticore**:
the GoF3 hulls as customizable ships (one ship per hull), with their paint schemes as skins, the GoF3 guns on their
hardpoints, a GoF3 turret, GoF3's engine effects, and stats and prices from the game's own data.

This importer contains **nothing from Galaxy on Fire 3**: no models, textures or game data, only the scripts that convert
the files of your own copy. The mod it builds does contain Galaxy on Fire 3's models and textures (© Deep Silver FISHLABS),
so it is for your own use: **don't share or upload the built mod**. Share this importer instead.

It runs on **Windows, macOS and Linux**.

## What you need

- A version of the **Galaxy on Fire 2 Unity Remake** with customizable ships (the hangar's *Customize ship* button).
- **Galaxy on Fire 3: Manticore**, the Android version, the Switch version, or both:
  - **Android**: its two expansion files `main.<version>.com.dsfishlabs.gofmanticore.obb` and
    `patch.<version>.com.dsfishlabs.gofmanticore.obb` (on the phone in `Android/obb/com.dsfishlabs.gofmanticore/`) and
    its APK (`com.dsfishlabs.gofmanticore.apk`, or the `.xapk` / `.apks` bundle it came in, unpacked or not). The APK
    holds the game data (`assets/game.jet`), the OBB files the models and textures. This alone builds the whole mod.
  - **Switch**: the romfs dumped from your own console, the folder with `game.tin`, `gfx.tin`, `patch.tin`,
    `patch_1_0_1.tin`, `patch_1_0_2.tin`. On its own it lacks the materials of three hulls (Terran 021 and 022, Vossk 121)
    and the gold guns, which the mod is then built without.
  - **Both**: give the importer the two together and it layers them, the Switch files over the Android ones (the Switch
    version's textures and game data where both have a file, the Android files filling in what the Switch romfs lacks).
  The game versions differ a little: the Android version (2.1.3) has newer game data, with some hulls' hull and shield
  values changed (so their armor and price in the mod) and a few typos in the texts fixed.
- **Python 3.9 or newer** with numpy, Pillow, texture2ddecoder, SciPy and pyzstd:
  - Windows: install Python from python.org (tick "Add python.exe to PATH"), then in a Command Prompt
    `py -m pip install numpy pillow texture2ddecoder scipy pyzstd`
  - macOS: install Python from python.org or Homebrew (`brew install python`), then in Terminal
    `python3 -m pip install numpy pillow texture2ddecoder scipy pyzstd`
  - Linux: `python3 -m pip install numpy pillow texture2ddecoder scipy pyzstd` (in a virtual environment if your distribution
    asks for one: `python3 -m venv venv` and use `venv/bin/python`)
- **For the sounds (optional): vgmstream and ffmpeg.** GoF3's engine, boost and gun sounds are FMOD FADPCM waves only
  vgmstream decodes: `vgmstream-cli` on the PATH (or `GOF3_VGMSTREAM=<path>`), else FModel's own Windows copy
  (`~/Downloads/FModel/Output/.data/vgmstream-cli.exe`, through Wine off Windows). ffmpeg makes them Ogg Vorbis (without
  it they go in as .wav). Without vgmstream the mod is built without sounds and the ships keep the game's.
- **Blender 4.2 or newer** (blender.org): it builds the models. It is found by itself on the PATH, in Program Files
  (Windows; also Steam's copy) or in Applications (macOS); else give its path with `--blender`.
- **Disk space** for the work folder: about 11 GB with the Android files, 21 GB with the Switch and Android files together
  (it can be deleted afterwards; on a FAT / exFAT drive, which has no hard links, a few GB more). The mod itself is about
  250 MB.

## Building the mod

Open a terminal in this folder (Windows: in Explorer type `cmd` in this folder's address bar; macOS: Finder's
*Services > New Terminal at Folder*, or `cd` to it) and give it your game files (dragging a file or folder onto the
terminal window types its path):

- Windows, Android: `py import.py "C:\Users\me\Downloads\Galaxy on Fire 3.xapk"` (or the .obb files and the .apk, or the
  folder holding them)
- Windows, Switch and Android: `py import.py "D:\GoF3\romfs" "D:\GoF3\android"`
- macOS / Linux: `python3 import.py ~/GoF3/android/`, or `python3 import.py ~/GoF3/romfs ~/GoF3/android/`

It checks Python, Blender and the game files first, then works through six stages, printing each:

1. extracts the game's archives and layers them the way the game does (later patches win);
2. reads the weapon loadouts from the game data;
3. converts every hull: its materials, its textures baked with the game's own shader math, the model in Blender, and each
   named paint scheme (this is the long one: about a minute per hull, several at once);
4. converts the guns, the mounts and the rockets;
5. puts each hull together with its default guns (for the icons, and to know what each hardpoint carries);
6. builds the mod: `gof3_ships` next to this script.

Everything a stage makes is kept in the work folder, so if a run stops (or you close it), running the same command again
reuses stages whose fingerprints still match. Source archives are SHA-256 hashed on each run; changed archives are
extracted again, and changes to converter scripts, their helper scripts and tables, Python packages, Blender's version,
or relevant options rebuild the affected stages and their dependents. Unchanged archives and conversions are kept.
Hashing large archives adds disk-reading time even when all conversions are reused. The first run after upgrading from
the old timestamp-only cache rebuilds the cached stages once. The whole run takes about
10 minutes on a fast 24-thread computer, more on a smaller one, mostly stage 3.

Options:

- `--out <folder>`: write the mod somewhere else, for example straight into the game's Mods folder (`.../Mods/gof3_ships`).
  An earlier build there is replaced; any other folder is never touched.
- `--work <folder>`: where the work folder goes (default `work` next to this script), e.g. another drive with more room.
- `--jobs <n>`: how many hulls are converted at once (default: half your processor's cores, at most 8). Each runs Blender:
  lower it if your computer runs out of memory.
- `--max-texture 2048`: the hulls' textures at full size (default 1024: about half the mod's size, and lighter to draw).
- `--no-icons`: skip rendering the shop icons and the mod's preview image.
- `--remake <folder>`: a checkout of the remake's source: the ship prices are fitted to its ship tables as they are now,
  and the icons get the game's own ship frame (without it, built-in price fits and a drawn frame stand in).
- `--blender <path>`: Blender's executable (or `Blender.app` on a Mac), if it isn't found by itself.
- `--fbx`: also write FBX files of the converted models into the work folder (the mod doesn't need them).
- `--fresh`: delete the work folder and start over.

## Build records and cache checks

Every successful build writes `<output-folder>.build-manifest.json` beside the mod and `build-manifest.json` in the work
folder. They record source archive names and SHA-256 hashes, importer Git revision (when available) and source-file
hashes, stage fingerprints, Python/package and Blender versions, build options, failed hulls/loadouts, failed skin
variants, skipped weapons, and selected builder diagnostics. The source-file hashes identify uncommitted converter
changes too. The final mod is assembled on every run, so changes to its builder, texture limit, icon choice or remake
data take effect without repeating unchanged hull conversions.

Keep the build record alongside the mod for troubleshooting. It lives outside the mod folder because the game includes
every mod file in its save and multiplayer hashes; a build timestamp should not change those hashes. Copy only the mod
folder into the game's Mods folder. Failed hulls and variants are retried on the next run, and failed loadouts are not
marked complete. Weapons omitted by their converter are listed in the build record, including on resumed builds.

The cache tests use tiny conversion fixtures and need neither game files nor Blender:

```
python3 -m unittest discover -s tests -v
```

They exercise clean/resumed output equivalence, legacy cache migration, same-size source replacements, helper-script
and conversion-table changes, downstream invalidation, FBX options, failed-stage retries, and provenance. They do not
verify the visual output of Blender or replace a full conversion check with the user's game files.

## Performance without changing asset quality

Ship texture dimensions are read from the texture header, so checking the largest input no longer decodes those pixels
before their actual conversion. Legacy-packed textures still use the existing decompressor. Pixel decoding, shader
math, texture sizes, filtering and PNG output are unchanged.

APK/bundle members already in the work folder are compared byte for byte with the complete archive member. Identical
members keep their existing files; changed or damaged copies are replaced atomically. SHA-256 is computed during that
comparison or copy and reused only within the current invocation. Full checks still run each time; file timestamps,
size and ZIP CRC alone never establish equality. Nested APKs use a memory-limited temporary stream and spill large
members to disk rather than loading the entire APK into RAM.

## Installing

Copy the `gof3_ships` folder into the game's Mods folder (in the game: main menu > Mods > *Open mods folder*) and turn it
on in the Mods screen. Don't put this importer folder itself in the Mods folder.

## In the game

- The ships are sold by visitors in the Space Lounges of their race's systems, from a story step (or rank) that grows with
  the ship's strength. Their blueprints work like Galaxy on Fire 2's: each sold by one lounge visitor at one station of its
  race, the recipe the hull's GoF3 guns plus goods, ores and cores; a few also lie in hackable derelicts, and ships of the
  race drop them now and then as in GoF3. A blueprint is obtained once, then built in the hangar's Blueprints tab.
- The five boss hulls aren't sold: pirate bosses fly them, and a destroyed boss drops its hull's blueprint.
- Each hull has its GoF3 cockpit seat for the cockpit view, smokes from GoF3's damage points when hurt, explodes at its
  GoF3 size, and the bigger hulls (and the gunships) get a chase camera pulled back to fit them.
- GoF3's guns are shop items of their own (27: nine families in three marks), with their GoF3 models, sounds and colours.
- Each ship flies at its GoF3 speed with its class's GoF3 booster built in; ships with GoF3's revive device have the
  Emergency System built in.
- In the hangar, **Customize ship** (under Inspect ship) picks the hull's paint scheme (Skin: GoF3's numbered schemes and
  its special paints like Gold or Dragon) and the colour of the energy weapons' shots, in GoF3's colours.
- The mounted guns show as GoF3 guns on the hull's hardpoints, a turret as a GoF3 turret. The Customize screen's
  **Weapon models** row hides them, with their pylons, for a bare hull (the weapons still fire).
- The engines burn with GoF3's engine effects (each race's flare and exhaust, the Nivelian helix). The mod also brings
  the three GoF3 drives as exhaust styles any ship can wear.
- GoF3's nine capital ships fly in the orbits' traffic: the battleships and frigates parked with their turrets armed (in
  Terran and Vossk systems now and then instead of the game's battleships, in Nivelian systems on their own), the
  freighters cruising among the orbit's freighters ("Mod ships in traffic" option).
- The Manticore, GoF3's Hades, is a moving station that roams every system, two hours in each (half an hour per orbit); the
  star map marks where it is and when it leaves. Find it in that orbit, lock it and dock into its own hangar (GoF3's Hades hangar,
  `tools/hangar_room.py`); it has no Space Lounge.
- The mod's own `README.txt` lists where every value comes from.

## GoF3's star systems (a second mod)

`tools/build_gof3_systems.py` makes a separate mod, `gof3_systems`, from GoF3's galaxy map:

```
python tools/build_gof3_systems.py --pdb <Android data.pdb> --assets <merged GoF3 assets> --out <Mods>/gof3_systems
```

- Every sector of GoF3's map (Trim, Porros, Rigant: 24) is a system below EVERSPACE 2's sectors on the star map, every
  level of a sector one of its station orbits, with GoF3's own station models, jumpgates, skies, suns and lore. Gates link
  each cluster's neighbours, the clusters to each other, and Trim's Anchorage to GoF2's Me'enkk (GoF3 itself travels by
  its Khador drive alone).
- None of the stations can be docked at, as in GoF3: its missions start from the galaxy map and "docking" only ever
  means the Manticore, which roams these systems too (the GoF3 ships mod).
- Kaamo's MKKT BKKT Club sector is left out (GoF2 has its own Kaamo Club).

## When something goes wrong

- Each hull's steps are logged in `work/logs/<hull>.log`, the other stages in `work/logs/*.log`. A hull that fails is left
  out of the mod; the rest is built.
- "missing Python packages": run the pip command the message shows.
- Blender runs out of memory: fewer at once (`--jobs 2`).
- Different game versions: built and checked with the Switch version 1.0.2 and the Android version 2.1.3.
- Only one run at a time can use a work folder: a second one says so and stops.

## License

The importer's scripts are under the MIT license (LICENSE). It covers this code only: the mod it builds holds the
game's own models, textures and data, which stay their owners' and are for your own use.
