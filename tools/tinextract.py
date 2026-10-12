"""Extract Galaxy on Fire 3 .tin archives (Switch romfs), Android .obb files and the Android APK's assets/game.jet (the same container).

Layout (little endian):
  0x00  "(C) Deep Silver FISHLABS Koch Media GmbH" (40 bytes), then a version byte (4)
  ...   the files' data blobs
  index zlib stream: per file  name\\0, u64 (always 34), u64 offset, u64 size, u64 stored size, u16 method
        (method 0 = stored, 3 = zstd v0.6 legacy frame, magic 26 b5 2f fd)
  end   18-byte footer: u64 index offset, u64 index size (uncompressed), u16 version (4)

usage: python tinextract.py OUT_DIR ARCHIVE.tin [ARCHIVE.tin ...]
Each archive goes to OUT_DIR/<archive name without .tin>/<path in the archive>.
"""
import os, struct, sys, zlib
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ae4unpack import decompress


def read_index(path):
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(size - 18)
        ioff, ilen, ver = struct.unpack("<QQH", f.read(18))
        f.seek(ioff)
        raw = zlib.decompress(f.read(size - 18 - ioff))
    if len(raw) != ilen:
        raise ValueError(f"{path}: index is {len(raw)} bytes, footer says {ilen}")
    entries, p = [], 0
    while p < len(raw):
        e = raw.index(b"\0", p)
        name = raw[p:e].decode("utf-8")
        p = e + 1
        _, off, usize, csize, method = struct.unpack_from("<QQQQH", raw, p)
        p += 34
        entries.append((name, off, usize, csize, method))
    return ver, entries


def decode(blob, usize, method):
    if method == 0:
        return blob
    if method == 3 and usize == len(blob) and blob[:4] != b"\x26\xb5\x2f\xfd":
        return blob   # flagged zstd but stored (21 tiny .ae4animation stubs in the Android main OBB)
    if method == 3:
        return decompress(blob, usize)
    raise ValueError(f"unknown method {method}")


def extract(path, out_root, dest=None):
    """Extracts the archive into out_root/<its name without the extension>, or into 'dest' when given."""
    ver, entries = read_index(path)
    dest = dest or os.path.join(out_root, os.path.splitext(os.path.basename(path))[0])
    print(f"{path}: version {ver}, {len(entries)} files -> {dest}", flush=True)
    errors = []

    def one(entry):
        name, off, usize, csize, method = entry
        with open(path, "rb") as f:
            f.seek(off)
            blob = f.read(csize)
        try:
            data = decode(blob, usize, method)
        except ValueError as ex:
            errors.append(f"{name}: {ex}")
            return
        target = os.path.join(dest, *name.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)

    with ThreadPoolExecutor(os.cpu_count() or 4) as pool:
        for i, _ in enumerate(pool.map(one, entries), 1):
            if i % 2000 == 0:
                print(f"  {i}/{len(entries)}", flush=True)
    for e in errors:
        print("  ERROR", e)
    print(f"  done: {len(entries) - len(errors)} ok, {len(errors)} failed", flush=True)
    return not errors


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ok = all([extract(a, sys.argv[1]) for a in sys.argv[2:]])
    sys.exit(0 if ok else 1)
