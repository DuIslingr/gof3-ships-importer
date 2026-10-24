"""GoF3's resource ids (ae::resource::getResourceId, libgofm.so 0x15fdad8): MurmurHash3_x86_128 with seed 1 of the
asset's path as the game names it ("/assets/" + its path under assets, extension and all), the two 64-bit halves
folded by xor: id = (h1 ^ h3) | (h2 ^ h4) << 32. Materials, scenes and models refer to their textures and meshes by it."""
import functools, glob, os, struct
import mmh3

def resource_id(path):
    a = struct.unpack("<4I", mmh3.hash_bytes(path.encode(), 1, x64arch=False))
    return ((a[1] ^ a[3]) << 32) | (a[0] ^ a[2])

@functools.lru_cache(maxsize=None)
def index(assets):
    """{id: file} of every file under assets."""
    out = {}
    for p in glob.glob(os.path.join(assets, "**", "*"), recursive=True):
        if os.path.isfile(p):
            out[resource_id("/assets/" + os.path.relpath(p, assets).replace(os.sep, "/"))] = p
    return out

def resolve(assets, ident):
    """The file a material / scene id (8 bytes as stored, or an int) names, or None."""
    if isinstance(ident, (bytes, bytearray)): ident = int.from_bytes(ident, "little")
    elif isinstance(ident, str): ident = int.from_bytes(bytes.fromhex(ident), "little")
    return index(assets).get(ident)
