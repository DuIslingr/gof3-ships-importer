"""Decompress a GoF3 .ae4* file: a zstd v0.6 legacy frame (magic 26 b5 2f fd), followed by
unrelated bytes (the extraction cut each file at its decompressed size). Only the first frame is read.
Data without the magic (files from tinextract.py, already decompressed) is returned as it is.

zstd: the pyzstd package (pip install pyzstd; its wheels decode the legacy v0.6 frames on Windows, macOS and Linux), else
the system's libzstd through ctypes. Loaded only when a compressed frame comes up, so the Blender scripts, which read the
already extracted files, need neither."""
import ctypes, ctypes.util, sys

MAGIC = b"\x26\xb5\x2f\xfd"
_backend = None


def _load():
    global _backend
    if _backend is not None: return _backend
    try:
        import pyzstd
        def dec(blob, size=None):
            d = pyzstd.ZstdDecompressor()
            out = d.decompress(blob)   # stops at the end of the first frame; the rest is d.unused_data
            if size is not None and len(out) != size: raise ValueError(f"decompressed {len(out)} bytes, expected {size}")
            return out
        _backend = dec
        return dec
    except ImportError:
        pass
    name = ctypes.util.find_library("zstd") or {"win32": "libzstd.dll", "darwin": "libzstd.dylib"}.get(sys.platform, "libzstd.so.1")
    try:
        z = ctypes.CDLL(name)
    except OSError:
        raise RuntimeError("zstd isn't available: install the pyzstd package (python -m pip install pyzstd)")
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
    _backend = dec
    return dec


def decompress(blob, size=None):
    """One zstd frame (the legacy v0.6 ones too); 'size' = the expected decompressed size, when known."""
    return _load()(blob, size)


def unpack(data: bytes) -> bytes:
    if data[:4] != MAGIC:   # already decompressed (the .tin / .obb / .jet extraction, tinextract.py)
        return data
    return decompress(data)


if __name__ == "__main__":
    d = unpack(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(d)
    print(len(d))
