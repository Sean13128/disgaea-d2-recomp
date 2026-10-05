#!/usr/bin/env python3
"""Measure cellAudio's raw float mix and write a listenable stereo WAV."""
import argparse
import array
import math
from pathlib import Path
import sys
import wave

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("raw", type=Path)
parser.add_argument("--start", type=float, default=25, help="BGM interval start in seconds")
parser.add_argument("--end", type=float, default=None)
parser.add_argument("--wav", type=Path)
args = parser.parse_args()
samples = array.array("f")
data = args.raw.read_bytes()
samples.frombytes(data[:len(data) // 2048 * 2048])
if sys.byteorder != "little":
    samples.byteswap()
if not samples or any(not math.isfinite(x) for x in samples):
    sys.exit("empty capture or non-finite PCM")
blocks = [math.sqrt(sum(x * x for x in samples[i:i + 512]) / 512)
          for i in range(0, len(samples), 512)]
first = int(args.start * 187.5)
last = int(args.end * 187.5) if args.end is not None else len(blocks)
rms = blocks[first:last]
if len(rms) < 100:
    sys.exit("BGM interval too short; capture longer or adjust --start")

def correlation(lag):
    a, b = rms[:-lag], rms[lag:]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    norm = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return cov / norm if norm else 0

silent = sum(x < 1e-8 for x in rms) / len(rms)
even, odd = sum(rms[::2]) / len(rms[::2]), sum(rms[1::2]) / len(rms[1::2])
contrast = abs(even - odd) / (even + odd) if even + odd else 0
print(f"capture: {len(samples) / 96000:.3f}s, peak={max(abs(x) for x in samples):.6f}")
print(f"BGM {first / 187.5:.3f}-{(first + len(rms)) / 187.5:.3f}s: "
      f"blocks={len(rms)} silent={100 * silent:.3f}% "
      f"RMS={math.sqrt(sum(x*x for x in rms) / len(rms)):.6f}")
print(f"RMS autocorrelation: lag1={correlation(1):.6f} lag2={correlation(2):.6f}; "
      f"odd/even contrast={contrast:.6f}")
print("block pattern: " + "".join("." if x < 1e-8 else "#" for x in rms[:96]))
if args.wav:
    pcm = array.array("h", (round(max(-1, min(1, x)) * 32767) for x in samples))
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(args.wav), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(pcm.tobytes())
    print(f"WAV: {args.wav}")
