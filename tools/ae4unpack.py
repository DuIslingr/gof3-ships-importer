"""Decompress a GoF3 .ae4* file: a zstd v0.6 legacy frame (magic 26 b5 2f fd), followed by
unrelated bytes (the extraction cut each file at its decompressed size). Only the first frame is read.
Data without the magic (files from tinextract.py, already decompressed) is returned as it is.

zstd: $GOF3_LIBZSTD or a libzstd beside this file, the pyzstd package (pip install pyzstd; recent wheels decode the legacy
v0.6 frames, 0.16 doesn't), or the system's libzstd through ctypes, each tried in turn (_load). Loaded only when a compressed frame comes up, so the Blender scripts, which read the
already extracted files, need neither."""
import ctypes, ctypes.util, os, sys

MAGIC = b"\x26\xb5\x2f\xfd"
_backends = None


def _pyzstd():
    import pyzstd
    def dec(blob, size=None):
        d = pyzstd.ZstdDecompressor()
        out = d.decompress(blob)   # stops at the end of the first frame; the rest is d.unused_data
        if size is not None and len(out) != size: raise ValueError(f"decompressed {len(out)} bytes, expected {size}")
        return out
    return dec


def _libzstd(name):
    z = ctypes.CDLL(name)
    z.ZSTD_findFrameCompressedSize.restype = ctypes.c_size_t
    z.ZSTD_findFrameCompressedSize.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    z.ZSTD_isError.argtypes = [ctypes.c_size_t]
    z.ZSTD_getErrorName.restype = ctypes.c_char_p
    z.ZSTD_getErrorName.argtypes = [ctypes.c_size_t]
    z.ZSTD_decompress.restype = ctypes.c_size_t
    z.ZSTD_decompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]

    def dec(blob, size=None):
        n = z.ZSTD_findFrameCompressedSize(blob, len(blob))
        if z.ZSTD_isError(n): raise ValueError(z.ZSTD_getErrorName(n).decode())
        cap = size if size is not None else max(len(blob) * 4, 1 << 16)
        while True:
            out = ctypes.create_string_buffer(max(cap, 1))
            r = z.ZSTD_decompress(out, cap, blob[:n], n)
            if not z.ZSTD_isError(r):
                if size is not None and r != size: raise ValueError(f"decompressed {r} bytes, expected {size}")
                return out.raw[:r]
            if size is not None or cap > 1 << 28: raise ValueError(z.ZSTD_getErrorName(r).decode())
            cap *= 4
    return dec


def _load():
    """The decoders there are, in order: $GOF3_LIBZSTD (a libzstd file), a libzstd beside this file, pyzstd, the system's
    libzstd. Some pyzstd wheels (0.16) import fine but reject the legacy v0.6 frames ("Unknown frame descriptor"), so a
    decoder that fails hands the frame to the next one (decompress) rather than only a missing one being skipped."""
    global _backends
    if _backends is not None: return _backends
    here = os.path.dirname(os.path.abspath(__file__))
    libs = [os.environ.get("GOF3_LIBZSTD")] + [os.path.join(here, f) for f in ("libzstd.dll", "libzstd.dylib", "libzstd.so.1", "libzstd.so")]
    found = []
    for lib in libs:
        if lib and os.path.exists(lib):
            try: found.append(_libzstd(lib)); break
            except OSError: pass
    try: found.append(_pyzstd())
    except ImportError: pass
    name = ctypes.util.find_library("zstd") or {"win32": "libzstd.dll", "darwin": "libzstd.dylib"}.get(sys.platform, "libzstd.so.1")
    try: found.append(_libzstd(name))
    except OSError: pass
    if not found: raise RuntimeError("zstd isn't available: install the pyzstd package (python -m pip install pyzstd)")
    _backends = found
    return found


def decompress(blob, size=None):
    """One zstd frame (the legacy v0.6 ones too); 'size' = the expected decompressed size, when known."""
    backends = _load(); err = None
    for i, dec in enumerate(backends):
        try:
            out = dec(blob, size)
            if i: backends.insert(0, backends.pop(i))   # (the one that works goes first from now on)
            return out
        except Exception as e:
            err = e
    raise err


def unpack(data: bytes) -> bytes:
    if data[:4] != MAGIC:   # already decompressed (the .tin / .obb / .jet extraction, tinextract.py)
        return data
    return decompress(data)


if __name__ == "__main__":
    d = unpack(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(d)
    print(len(d))
