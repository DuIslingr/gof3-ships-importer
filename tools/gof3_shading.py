"""GoF3's shading per kind of surface, for the remake's GoF2/Hull (its GoF3ShipShader, a port of GoF3's ship / structure / glass /
gun shaders: Modding/README.md "materials": "environment", "rim", "highlightMultiplier", "multiplierInMap").

python gof3_shading.py <gof3_ships folder> [<gof3_systems folder>]   rewrites a built mod's materials in place (the builders
                                                                    call ships() and systems() themselves)

GoF3's fragment shaders (their .ae4shader variants, ae4_shaders.text; 2026-11-02) light every surface alike (gamma space,
Phong, a fresnel on the specular and gloss, the diffuse cut by the highlight) and differ in:
  kind                       environment          rim   Specular_Multiplier          the importer's map / colour
  ship body (ShipShader)     Environment_Amount   yes   x the whole specular         x it (ae4_ship_textures): in the map
  ship glass                 Environment_Amount   no    x the highlight              Specular_Color: not in it
  gun (weapon_generic)       no                   yes   x the whole specular         x it (ae4_weapon_textures): in the map
  structure platings         no                   no    in GoF3's own map already    x it (structure_materials): as GoF3
  structure glass            no                   yes   x the highlight              x it: in the map
  capital-ship parts         no                   yes   x the highlight              x it, baked with the platings
So:
  hulls/*.glb   the body: its ship's matid01_body values, multiplierInMap; the glass (until now metallic-roughness, lit as
                URP's PBR) becomes KHR_materials_pbrSpecularGlossiness: its texture as the diffuse, Specular_Color (as glTF's
                linear factor) and Gloss_Amount (as smoothness, the importer's 1 - (2 / (n + 2))^0.25), with its
                Environment_Amount and Specular_Multiplier on the highlight
  guns/*.glb    the gun family's material: no environment, rim, its Specular_Multiplier in the map
  structures/*.glb (the capital ships, the Hades / Manticore)   no environment; the capital ships' rim on (their largeship
                materials), the Hades' off (structure platings); glass parts rim on with their multiplier in the map
  gof3_systems  every specular material of stations.json, systems.json (the gates) and ships.json (the traffic hulls): the
                baked structure atlases no environment and no rim, their own see-through parts (opacity below 1, glass) the
                rim and their Specular_Multiplier, read from their GoF3 material (gof3[own_<race>_...] ->
                structures/<race>/materials/**/structure_<race>_....ae4material), in the map"""
import glob, json, math, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ae4_material

SHIP = {"environment": 1.0, "rim": 1.0, "highlightMultiplier": 1.5, "multiplierInMap": True}
STRUCTURE = {"environment": 0.0, "rim": 0.0, "highlightMultiplier": 1.0, "multiplierInMap": False}


def smoothness(gloss):
    """GoF3's gloss (Phong exponent exp2(9 g + 1)) as the importer's smoothness (1 - (2 / (n + 2))^0.25)."""
    n = 2.0 ** (9.0 * gloss + 1.0)
    return round(1.0 - (2.0 / (n + 2.0)) ** 0.25, 4)


def srgb_to_linear(c):
    return [round(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4, 5) for x in c]


def _material(path):
    if not path or not os.path.exists(path): return {}
    try: return ae4_material.read(path)[0]
    except Exception: return {}


def _write(path, data):
    """Through a new file (os.replace): the build caches share files by hard link, which an in-place write would change too."""
    tmp = path + ".tmp"
    open(tmp, "wb").write(data)
    os.replace(tmp, path)


def glb_edit(path, edit):
    """Rewrites a GLB's JSON chunk by edit(j) -> changed (the binary chunk as it is)."""
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    if not edit(j): return False
    js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    rest = b[20 + n:]
    out = struct.pack("<II", len(js), 0x4E4F534A) + js + rest
    _write(path, struct.pack("<III", 0x46546C67, 2, 12 + len(out)) + out)
    return True


def _ship_dir(assets, hull):
    race, num = hull.rsplit("_", 1)
    return os.path.join(assets, "ships", race, num), f"ship_{race}_{num}"


def ship_terms(v):
    return {"environment": float(v.get("Environment_Amount", 1.0)) if v.get("Environment_Enabled", True) else 0.0,
            "rim": 1.0 if float(v.get("RimLight_LightStrength", 1.0)) > 0 else 0.0,
            "highlightMultiplier": float(v.get("Specular_Multiplier", 1.5)), "multiplierInMap": True}


def glass_terms(v):
    return {"environment": float(v.get("Environment_Amount", 1.0)) if v.get("Environment_Enabled", True) else 0.0,
            "rim": 0.0, "highlightMultiplier": float(v.get("Specular_Multiplier", 1.0)), "multiplierInMap": False}


def ships(mod, assets, log=print):
    """gof3_ships: hulls, guns and structures (see the header)."""
    count = {"bodies": 0, "glass": 0, "guns": 0, "structures": 0}
    for path in sorted(glob.glob(os.path.join(mod, "hulls", "*.glb"))):
        hull = os.path.basename(path)[:-4]
        d, base = _ship_dir(assets, hull)
        body, glass = _material(f"{d}/{base}_matid01_body.ae4material"), _material(f"{d}/{base}_matid02_glass.ae4material")

        def edit(j):
            changed = False
            for m in j.get("materials", []):
                name = m.get("name", "")
                sg = m.get("extensions", {}).get("KHR_materials_pbrSpecularGlossiness")
                if sg is not None and name.endswith("_body"):
                    m.setdefault("extras", {}).update(ship_terms(body) if body else SHIP); count["bodies"] += 1; changed = True
                elif name.endswith("_glass") and m.get("alphaMode") == "BLEND":
                    v = glass or {}
                    pbr = m.get("pbrMetallicRoughness", {})
                    ext = {"specularFactor": srgb_to_linear(list(v.get("Specular_Color", (1, 1, 1, 1)))[:3]),
                           "glossinessFactor": smoothness(float(v.get("Gloss_Amount", 0.8)))}
                    if "baseColorTexture" in pbr: ext["diffuseTexture"] = pbr["baseColorTexture"]
                    dc = list(v.get("Diffuse_Color", (1, 1, 1, 1)))[:3]
                    ext["diffuseFactor"] = srgb_to_linear(dc) + [round(float(v.get("Opacity_Amount", 1.0)), 4)]
                    m.setdefault("extensions", {})["KHR_materials_pbrSpecularGlossiness"] = ext
                    m.setdefault("extras", {}).update(glass_terms(v))
                    used = j.setdefault("extensionsUsed", [])
                    if "KHR_materials_pbrSpecularGlossiness" not in used: used.append("KHR_materials_pbrSpecularGlossiness")
                    count["glass"] += 1; changed = True
            return changed
        glb_edit(path, edit)
    for path in sorted(glob.glob(os.path.join(mod, "guns", "*.glb"))):
        def edit(j):
            changed = False
            for m in j.get("materials", []):
                fam = re.match(r"weapon_generic_(\d{3})", m.get("name", ""))
                if not fam or "KHR_materials_pbrSpecularGlossiness" not in m.get("extensions", {}): continue
                v = _material(os.path.join(assets, "weapons", "generic", fam.group(1), f"weapon_generic_{fam.group(1)}.ae4material"))
                m.setdefault("extras", {}).update({"environment": 0.0, "rim": 1.0,
                    "highlightMultiplier": float(v.get("Specular_Multiplier", 1.0)), "multiplierInMap": True})
                count["guns"] += 1; changed = True
            return changed
        glb_edit(path, edit)
    for path in sorted(glob.glob(os.path.join(mod, "structures", "*.glb"))):
        hades = "hades" in os.path.basename(path).lower()
        def edit(j):
            changed = False
            for m in j.get("materials", []):
                if "KHR_materials_pbrSpecularGlossiness" not in m.get("extensions", {}): continue
                name = m.get("name", "").lower()
                t = dict(STRUCTURE)
                if m.get("alphaMode") == "BLEND" and "glass" in name: t.update(rim=1.0, multiplierInMap=True)
                elif not hades and "hades" not in name: t["rim"] = 1.0   # (a capital ship: its largeship materials)
                m.setdefault("extras", {}).update(t)
                count["structures"] += 1; changed = True
            return changed
        glb_edit(path, edit)
    log(f"shading: {count['bodies']} hull bodies, {count['glass']} glass (now specular), {count['guns']} guns, "
        f"{count['structures']} structure materials")
    return count


_OWN = {}


def own_material(assets, name):
    """A gof3_systems own material's GoF3 values: gof3[own_<race>_<rest>] -> structures/<race>/**/structure_<race>_<rest>."""
    m = re.match(r"gof3\[own_([a-z]+)_(.+)\]$", name or "")
    if not m: return {}
    key = (m.group(1), m.group(2))
    if key not in _OWN:
        hits = glob.glob(os.path.join(assets, "structures", m.group(1), "**", f"structure_{m.group(1)}_{m.group(2)}.ae4material"), recursive=True)
        _OWN[key] = _material(hits[0]) if hits else {}
    return _OWN[key]


def systems(mod, assets, log=print):
    """gof3_systems: every specular material entry of its JSON files (see the header)."""
    count = {"atlas": 0, "glass": 0}

    def walk(o):
        if isinstance(o, dict):
            if "material" in o and ("specularGlossiness" in o or "specularColor" in o):
                see_through = 0.0 < float(o.get("opacity", 0) or 0) < 1.0
                if see_through:
                    v = own_material(assets, o.get("material"))
                    o.update(environment=0.0, rim=1.0, highlightMultiplier=float(v.get("Specular_Multiplier", 1.0)) or 1.0,
                             multiplierInMap=True)
                    count["glass"] += 1
                else:
                    o.update(STRUCTURE); count["atlas"] += 1
            for x in o.values(): walk(x)
        elif isinstance(o, list):
            for x in o: walk(x)
    for name in ("stations.json", "systems.json", "ships.json"):
        p = os.path.join(mod, name)
        if not os.path.exists(p): continue
        j = json.load(open(p, encoding="utf-8"))
        walk(j)
        _write(p, json.dumps(j, indent=1, ensure_ascii=False).encode("utf-8"))
    log(f"shading: {count['atlas']} structure materials, {count['glass']} see-through")
    return count


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    assets = os.environ.get("GOF3_ASSETS") or os.path.join(here, "..", "work", "merged", "assets")
    ships(os.path.abspath(sys.argv[1]), assets)
    if len(sys.argv) > 2: systems(os.path.abspath(sys.argv[2]), assets)
