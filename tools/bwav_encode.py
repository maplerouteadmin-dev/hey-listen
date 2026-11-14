"""Encode WAV clips as the game's voice streams: BWAV holding Nintendo-framed Opus, 48 kHz mono.

    A:/OotVoiceMod/qwen/venv/Scripts/python.exe -I bwav_encode.py <jobs.json> <results.json>

jobs.json: [{"wav": path, "out": path.bwav}, ...]. results.json: per job, the numbers the bank (AMTA) needs.
Needs numpy, soundfile and soxr (the Qwen venv has them) and libopus (Shotcut's copy is used).
Layout checked against the game's own files: CELT-only low-delay Opus, 20 ms frames, 120-sample pre-skip,
packets as big-endian (size, final range) + data, CRC32 of everything after the 0x80-byte header.
"""
import ctypes
import json
import math
import struct
import sys
import zlib

import numpy as np
import soundfile
import soxr

LIBOPUS = r"C:\Program Files\Shotcut\libopus-0.dll"
RATE, FRAME = 48000, 960
APPLICATION_RESTRICTED_LOWDELAY = 2051
SET_BITRATE, GET_LOOKAHEAD, GET_FINAL_RANGE = 4002, 4027, 4031
BITRATE = 48000
CURVE_STEP = 4800
GAP_SECONDS = 0.3     # pause between text boxes in a joined clip

opus = ctypes.CDLL(LIBOPUS)
opus.opus_encoder_create.restype = ctypes.c_void_p
opus.opus_encoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
opus.opus_encode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_char_p, ctypes.c_int32]
opus.opus_encoder_destroy.argtypes = [ctypes.c_void_p]


def load_pcm(path):
    audio, rate = soundfile.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if rate != RATE:
        audio = soxr.resample(audio, rate, RATE, quality="VHQ")
    return np.clip(audio, -1.0, 1.0)


def encode_packets(pcm):
    err = ctypes.c_int()
    enc = ctypes.c_void_p(opus.opus_encoder_create(RATE, 1, APPLICATION_RESTRICTED_LOWDELAY, ctypes.byref(err)))
    if err.value:
        raise RuntimeError("opus_encoder_create failed %d" % err.value)
    try:
        opus.opus_encoder_ctl(enc, SET_BITRATE, ctypes.c_int(BITRATE))
        lookahead = ctypes.c_int()
        opus.opus_encoder_ctl(enc, GET_LOOKAHEAD, ctypes.byref(lookahead))
        preskip = lookahead.value
        frames = math.ceil((len(pcm) + preskip) / FRAME)
        ints = np.zeros(frames * FRAME, dtype=np.int16)
        ints[:len(pcm)] = np.round(pcm * 32767).astype(np.int16)
        out = bytearray()
        buf = ctypes.create_string_buffer(4000)
        rng = ctypes.c_uint32()
        for i in range(frames):
            chunk = np.ascontiguousarray(ints[i * FRAME:(i + 1) * FRAME])
            n = opus.opus_encode(enc, chunk.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), FRAME, buf, len(buf))
            if n < 0:
                raise RuntimeError("opus_encode failed %d" % n)
            opus.opus_encoder_ctl(enc, GET_FINAL_RANGE, ctypes.byref(rng))
            out += struct.pack(">II", n, rng.value) + buf.raw[:n]
        return bytes(out), preskip
    finally:
        opus.opus_encoder_destroy(enc)


def bwav(samples, packets, preskip):
    body = struct.pack("<II", 0x80000001, 0x18) + struct.pack("<BBH", 0, 1, 0) + struct.pack("<IIIII", RATE, 0x20, 0, 0, preskip)
    body += struct.pack("<II", 0x80000004, len(packets)) + packets
    head = bytearray(0x80)
    struct.pack_into("<4sHHIHH", head, 0, b"BWAV", 0xFEFF, 1, zlib.crc32(body), 0, 1)
    struct.pack_into("<HHIII", head, 0x10, 2, 2, RATE, samples, samples)
    struct.pack_into("<IIIi", head, 0x40, 0x80, 0x80, 1, -1)
    return bytes(head) + body


def stats(pcm):
    """The loudness figures a bank entry carries. Peak is exact; the rest approximates the game's own analysis."""
    a = np.abs(pcm)
    peak = float(a.max()) if len(a) else 0.0
    blocks = [pcm[i:i + 480] for i in range(0, len(pcm), 480)]
    loud = [b for b in blocks if len(b) and math.sqrt(float((b ** 2).mean())) > 0.01]
    active = np.concatenate(loud) if loud else pcm
    rms = math.sqrt(float((active ** 2).mean())) if len(active) else 0.0
    db = 20 * math.log10(rms) if rms > 0 else -96.0
    curve = [(0.0, 0)]
    for p in range(CURVE_STEP, len(pcm), CURVE_STEP):
        w = pcm[p:p + CURVE_STEP]
        curve.append((round(float((w ** 2).mean()) * 0.6, 6), p))
    curve.append((0.0, max(len(pcm), curve[-1][1] + 1)))
    return dict(peak=peak, rms=rms, db=db, db2=db - 1.7, onset=int(np.argmax(a > 0.05)) if (a > 0.05).any() else 0, curve=curve)


def page_breaks(pcm, page_chars):
    """Sample positions where each text box after the first starts, for a clip that reads several boxes.
    Each break is first placed by the share of text read so far, then moved to the middle of the
    longest pause nearby, since a reader pauses between boxes."""
    if len(page_chars) < 2:
        return []
    hop = RATE // 100
    frames = len(pcm) // hop
    if frames < 10:
        return []
    energy = np.sqrt((pcm[:frames * hop].reshape(frames, hop) ** 2).mean(axis=1) + 1e-12)
    quiet = energy < max(float(energy.max()) * 0.03, 1e-4)
    voiced = np.flatnonzero(~quiet)
    start, end = (int(voiced[0]), int(voiced[-1])) if len(voiced) else (0, frames - 1)
    total = float(sum(page_chars))
    breaks, done, last = [], 0, start
    for chars in page_chars[:-1]:
        done += chars
        guess = start + (end - start) * done / total
        reach = max(30, int((end - start) * 0.12))
        lo, hi = max(last + 5, int(guess - reach)), min(end - 5, int(guess + reach))
        best, best_score = int(guess), -1e9
        i = lo
        while i <= hi:
            if quiet[i]:
                j = i
                while j + 1 <= hi and quiet[j + 1]:
                    j += 1
                mid = (i + j) // 2
                score = (j - i + 1) - abs(mid - guess) * 0.15
                if score > best_score:
                    best, best_score = mid, score
                i = j + 1
            else:
                i += 1
        last = best
        breaks.append(best * hop)
    return breaks


def main():
    jobs = json.load(open(sys.argv[1], encoding="utf-8"))
    results = []
    for job in jobs:
        if job.get("parts"):
            # One clip per text box, joined; each later box starts exactly at its marker.
            gap = np.zeros(int(RATE * GAP_SECONDS), dtype=np.float32)
            pieces, breaks, at = [], [], 0
            for i, part in enumerate(job["parts"]):
                audio = load_pcm(part)
                if i:
                    pieces.append(gap)
                    at += len(gap)
                    breaks.append(at)
                pieces.append(audio)
                at += len(audio)
            pcm = np.concatenate(pieces)
        else:
            pcm = load_pcm(job["wav"])
            breaks = page_breaks(pcm, job.get("pages", []))
        packets, preskip = encode_packets(pcm)
        data = bwav(len(pcm), packets, preskip)
        with open(job["out"], "wb") as f:
            f.write(data)
        results.append(dict(job, samples=len(pcm), bytes=len(data), breaks=breaks, **stats(pcm)))
    json.dump(results, open(sys.argv[2], "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
