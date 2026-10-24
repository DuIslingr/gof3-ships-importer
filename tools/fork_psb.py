"""Read a Fork Particle Studio .psb (Galaxy on Fire 3's particle effects, romfs particles/) as the game's Fork runtime does
(libgofm.so, decompiled):
- the file: "PSB\\0", ..., +0xc the first chunk's offset; a chunk = a 256-byte name, +0x100 its size (to the next chunk),
  +0x104 its data's offset, +0x108 its type (byte; 0 = an emitter's EData) and flags (0x100: the last chunk)
  (frkPSBChunkGetData / GetDataSize / GetType / IncTracer, frkPSBPrepare);
- an emitter's EData, the fields the runtime reads (frkPEmitterEmit, _frkPEmitterPreProcess, _frkParticleProcessFullSim):
  +0x10 / 0x20 / 0x30 / 0x40 colour keys (rgba) at life 0, +0x50, +0x54, 1 (piecewise linear);
  +0x58 / 0x5c life min / max (s); +0x60 / 0x64 speed min / max; +0x68 flags;
  sizes start / mid / end: max +0x6c / 0x70 / 0x74, min +0xb8 / 0xbc / 0xc0, the mid at life +0x78 (flag +0x1f8 bit 0:
  the start size throughout); +0x7c / 0x80 spin min / max (a random sign unless flags 0x400000); +0x98 / 0xa4 the start
  rotation; +0xcc particles a second; +0xe4 the most alive; +0x110 the emitter's time scale; +0x124 flipbook frames;
- its texture: the asset path the file names (Fork Particle Studio's "...\\Texture\\beam_001.bmp"), shipped as
  particles/<name>.ae4texture.
Emission runs at the rate x the time, spread along the path the emitter moved that frame (_frkPEmitterEmitProcess:
distance interpolation), so a still particle (speed 0) left at the nozzle makes a continuous wake."""
import re, struct, sys


def read(path):
    d = open(path, "rb").read()
    if d[:3] != b"PSB": raise ValueError(f"{path}: not a PSB")
    emitters, chunk = [], struct.unpack_from("<I", d, 0xc)[0]
    while 0 < chunk < len(d) - 0x10c:
        size, data, flags = struct.unpack_from("<3I", d, chunk + 0x100)
        if flags & 0xff == 0:
            e = chunk + data
            f = lambda o: struct.unpack_from("<f", d, e + o)[0]
            u = lambda o: struct.unpack_from("<I", d, e + o)[0]
            col = lambda o: [round(f(o + 4 * k), 4) for k in range(4)]
            uniform = bool(u(0x1f8) & 1)
            em = {"name": d[chunk:chunk + 0x100].split(b"\0")[0].decode("latin-1"),
                  "colors": [col(0x10), col(0x20), col(0x30), col(0x40)],
                  "colorTimes": [0.0, round(f(0x50), 4), round(f(0x54), 4), 1.0],
                  "life": [round(f(0x58), 4), round(f(0x5c), 4)],
                  "speed": [round(f(0x60), 4), round(f(0x64), 4)],
                  "sizeStart": [round(f(0xb8), 4), round(f(0x6c), 4)],
                  "sizeMid": [round(f(0xbc), 4), round(f(0x70), 4)] if not uniform else None,
                  "sizeEnd": [round(f(0xc0), 4), round(f(0x74), 4)] if not uniform else None,
                  "sizeMidTime": round(f(0x78), 4),
                  "spin": [round(f(0x7c), 4), round(f(0x80), 4)],
                  "rotation": [round(f(0x98), 4), round(f(0xa4), 4)],
                  "rate": round(f(0xcc), 4), "max": round(f(0xe4), 1), "timeScale": round(f(0x110), 4),
                  "frames": u(0x124), "flags": hex(u(0x68)), "flags2": hex(u(0x1f8))}
            if uniform: em["sizeMid"] = em["sizeEnd"] = em["sizeStart"]
            emitters.append(em)
        if flags & 0x100 or size == 0: break
        chunk += size
    tex = [m.decode("latin-1").split("\\")[-1].rsplit(".", 1)[0] for m in re.findall(rb"[A-Za-z]:\\[ -~]+?\.(?:bmp|tga|png|dds)", d)]
    for k, em in enumerate(emitters): em["texture"] = tex[k] if k < len(tex) else (tex[0] if tex else None)
    return emitters


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]:
        print(p); print(json.dumps(read(p), indent=1))
