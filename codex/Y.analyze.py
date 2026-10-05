#!/usr/bin/env python3
"""Measure distinct retired flips and correlated ring-full/drain waits."""
import re
import sys
from collections import defaultdict

log = sys.argv[1]
rows = defaultdict(list)
recycles = {}
kicks = {}
retired = set()
flip = defaultdict(dict)
frames = []
now = 0
settle = None
last_wake = None
held = submits = undrained = duplicate = overcap = no_kick = 0


def fields(line):
    return dict(re.findall(r"(\w+)=([\w.]+)", line))


def latency(name, first, last):
    if first is not None and last is not None and last >= first:
        rows[name].append((last - first) / 1e6)


with open(log) as source:
    for line in source:
        d = fields(line)
        if "map30001.lzs" in line:
            settle = now + 2_000_000_000
        if "[gcm-flip]" in line:
            now = int(d["time_ns"])
        if settle is None or now < settle:
            continue
        if "[gcm-submit]" in line:
            submits += 1
            undrained += d["put"] != d["get"]
        if "[gcm-recycle]" in line:
            ident = int(d["id"])
            if d["event"] == "begin":
                recycles[ident] = int(d["time_ns"])
            elif d["event"] == "kick":
                kicks[ident] = int(d["time_ns"])
            elif d["event"] == "end" and ident in recycles:
                rows["recycle"].append(int(d["wait_ns"]) / 1e6)
                rows["tail_condition_waits"].append(int(d["tail_waits"]))
                rows["jump_condition_waits"].append(int(d["jump_waits"]))
                no_kick += int(d["kicks"]) == 0
                del recycles[ident]
                kicks.pop(ident, None)
        if "[gcm-recycle-drain]" in line:
            ident = int(d["id"])
            held += int(d["held"])
            start, end = int(d["start_ns"]), int(d["end_ns"])
            latency("drain", start, end)
            if ident in kicks and start >= kicks[ident]:
                latency("kick_to_drain", kicks.pop(ident), start)
        if "[gcm-flip]" not in line:
            continue
        seq, event = int(d["seq"]), d["event"]
        flip[seq][event] = now
        if event == "submit" and last_wake and last_wake[0] == seq - 1:
            latency("wake_next_submit", last_wake[1], now)
        if event == "retire":
            if seq in retired:
                duplicate += 1
                continue
            tick = int(d["vblank"])
            if frames and tick == frames[-1][2]:
                overcap += 1
            frames.append((now, seq, tick))
            retired.add(seq)
            for name, a, b in (("submit_reach", "submit", "reach"),
                               ("reach_select", "reach", "select"),
                               ("select_retire", "select", "retire")):
                latency(name, flip[seq].get(a), flip[seq].get(b))
        if event == "wake":
            last_wake = seq, now
            latency("retire_wake", flip[seq].get("retire"), now)
            flip.pop(seq, None)

if len(frames) < 120:
    sys.exit("FAIL: insufficient settled Castle Hallway (map30001) flips; use Y_MANUAL=1 or adjust Y_PAD_SCRIPT")
duration = (frames[-1][0] - frames[0][0]) / 1e9
fps = (len(frames) - 1) / duration
print(f"Castle Hallway: {fps:.3f} distinct flips/s; {len(frames)-1} flips / "
      f"{frames[-1][2]-frames[0][2]} vblanks in {duration:.3f}s")
print(f"Direct submissions with unread FIFO: {undrained}/{submits}; held recycle drains: {held}; "
      f"recycles without a kick: {no_kick}")
for name, values in sorted(rows.items()):
    values.sort()
    units = "" if "condition_waits" in name else " ms"
    p95 = values[min(len(values) - 1, int(len(values) * .95))]
    print(f"{name}: count={len(values)} mean={sum(values)/len(values):.3f} "
          f"p95={p95:.3f} max={values[-1]:.3f}{units}")
if duplicate or overcap:
    sys.exit(f"FAIL: duplicate flips={duplicate}, multiple flips in one vblank={overcap}")
print("PASS: distinct sequences, at most one retired flip per vblank")
if fps < 58.5:
    print("SLOW: below 60-flip target; compare recycle and wake_next_submit times with the profile")
