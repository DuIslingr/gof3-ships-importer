"""A GoF3 material's compiled shader variants, from any of the game's builds.

A material (.ae4material) names each of its passes' shaders by resource id (ae4_ids), the id of the file's path in its
own build's layout (found 2026-11-02):
  - iOS: a folder beside the material, "/assets/<material path>_/shader_<N>.ae4shader" (all five of
    vfx_engine_generic_000_exhaust's);
  - Android (OBB) and Switch (romfs): one folder of every material's shaders at the archive's root,
    "/shaders/shader_<N>.ae4shader" (six of vfx_engine_terran_000_exhaust's, four of them the iOS folder's files), so only
    the material's ids tell which are its own.
variants() takes either, so the importer works from each build on its own.

variants(material, assets, shaders_dir=None) -> [paths of the material's shader files]; text(path) -> its source."""
import functools, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import ae4_ids
from ae4unpack import unpack


@functools.lru_cache(maxsize=None)
def _flat(shaders_dir):
    """{N: path} of a flat shaders folder."""
    out = {}
    if shaders_dir and os.path.isdir(shaders_dir):
        for f in os.listdir(shaders_dir):
            m = re.fullmatch(r"shader_(\d+)\.ae4shader", f)
            if m: out[m.group(1)] = os.path.join(shaders_dir, f)
    return out


def shaders_dir_of(assets):
    """The flat shaders folder beside an assets tree (the merged Android / Switch layout: <root>/assets, <root>/shaders)."""
    d = os.path.join(os.path.dirname(os.path.abspath(assets).rstrip("/\\")), "shaders")
    return d if os.path.isdir(d) else None


def variants(material, assets, shaders_dir=None):
    """The material's shader files: its iOS folder's, else those of the flat folder its passes name."""
    folder = material + "_"
    if os.path.isdir(folder):
        return [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".ae4shader")]
    flat = _flat(shaders_dir or shaders_dir_of(assets))
    if not flat: return []
    d = unpack(open(material, "rb").read())
    words = {d[o:o + 8] for o in range(len(d) - 7)}
    base = "/assets/" + os.path.relpath(material, assets).replace(os.sep, "/") + "_/shader_"
    def named(n):
        return any(ae4_ids.resource_id(p).to_bytes(8, "little") in words
                   for p in (f"/shaders/shader_{n}.ae4shader", f"{base}{n}.ae4shader"))
    return [flat[n] for n in sorted(flat) if named(n)]


def text(path):
    """A shader file's source (the legacy zstd frame unpacked when it is one)."""
    return unpack(open(path, "rb").read()).decode("latin-1")
