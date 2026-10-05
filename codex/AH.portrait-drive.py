#!/usr/bin/env python3
"""Drive native pad controls against real captures; never write guest state."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

out, pad, ocr = map(Path, sys.argv[1:4])
seconds = int(sys.argv[4])
deadline = time.monotonic() + seconds
seen = set()
phase = "load"
last_press = 0
attempts = 0
sequence = []
sequence_at = 0
portrait_frames = []
log_offset = 0
log_tail = ""
warped = False
cross, circle, triangle = 0x4000, 0x2000, 0x1000
up, right, down, left, r2 = 0x10, 0x20, 0x40, 0x80, 0x2

def press(mask, polls=4):
    global last_press
    pad.write_text(f"0x{mask:04X} {polls}\n")
    last_press = time.monotonic()
    print(f"[AH-pad] {phase}: 0x{mask:04X}", flush=True)

def enqueue(*buttons):
    global sequence, sequence_at
    sequence = list(buttons)
    sequence_at = time.monotonic()

def ppm(path):
    with path.open("rb") as f:
        assert f.readline().strip() == b"P6"
        w, h = map(int, f.readline().split())
        assert f.readline().strip() == b"255"
        pixels = f.read()
        assert len(pixels) == w*h*3
        return w, h, pixels

def corners(path):
    w, h, pixels = ppm(path)
    assert (w, h) == (1280, 720), (w, h)
    # Mask/backing quad measured by V: (40,28)..(212,200).
    # These four patches lie outside its circular portrait, away from the label.
    fractions = []
    for x, y in ((43,31), (191,31), (43,179), (191,179)):
        colors = [pixels[(yy*w+xx)*3:(yy*w+xx)*3+3]
                  for yy in range(y, y+18) for xx in range(x, x+18)]
        white = sum(min(c) >= 240 for c in colors) / len(colors)
        assert white < .95, f"white portrait corner at {x},{y}: {white:.1%} ({path})"
        fractions.append(round(white, 4))
    print(f"[AH-portrait] {path.name}: corner white fractions {fractions}: PASS", flush=True)

while time.monotonic() < deadline:
    time.sleep(.2)
    now = time.monotonic()
    with (out / "run.log").open(errors="replace") as f:
        f.seek(log_offset)
        chunk = f.read()
        log_offset = f.tell()
    if "OOB access" in chunk or "HOST CORRUPTION" in chunk or "FAULT" in chunk:
        raise SystemExit("FAIL: guest/runtime fault during navigation; inspect run.log")
    warped |= "confirm stage=101" in chunk
    log_tail = (log_tail + chunk)[-131072:]
    if sequence and now >= sequence_at and now - last_press > .6 and not pad.read_text().strip():
        press(sequence.pop(0))
        sequence_at = now + .8
        continue
    frames = sorted((out / "frames").glob("f*.ppm"), key=lambda p: int(p.stem[1:]))
    if not frames:
        # Boot title has Continue selected when saved data exists.
        if phase == "load" and now > deadline - seconds + 10 and now - last_press > 4:
            press(cross)
        continue
    frame = frames[-1]
    if frame in seen or now - frame.stat().st_mtime < .15:
        continue
    try:
        result = subprocess.run([str(ocr), str(frame)], capture_output=True, text=True, timeout=8)
        if result.returncode:
            continue  # dump may still be writing
        lines = json.loads(result.stdout)
    except (ValueError, subprocess.TimeoutExpired):
        continue
    seen.add(frame)
    with (out / "ocr.jsonl").open("a") as f:
        f.write(json.dumps({"frame": frame.name, "phase": phase, "lines": lines}) + "\n")
    text = " ".join(line["text"] for line in lines).upper()
    label = re.sub(r"[^A-Z]", "", " ".join(line["text"] for line in lines
                    if line["x"] < 230 and line["y"] < 115))
    if "ATTACKENTRY" in label:
        corners(frame)
        portrait_frames.append(str(frame))
        if len(portrait_frames) == 3:
            (out / "portrait.json").write_text(json.dumps({"frames": portrait_frames}, indent=2))
            # Exercise Execute after preserving the queued attack's portrait.
            phase = "execute"
            press(triangle)
            time.sleep(1)
            press(cross)
            print("[AH-portrait] three ATTACK ENTRY captures verified; Execute requested", flush=True)
            sys.exit(0)
        continue
    if sequence or now - last_press < 1.2 or pad.read_text().strip():
        continue
    log = log_tail
    if phase == "load":
        if not warped:
            if now >= deadline - seconds + 10 and now - last_press >= 4:
                press(cross)
            continue
        phase = "dialogue"
    if "VISITING" in text or "NETHERWORLD!" in text:
        press(cross)  # DLC visitor announcements vary with installed flags.
        continue
    if phase == "dialogue":
        flags = re.findall(r"stage=5011 map_id=101 battle_flags=(\d+)/(\d+)", log)
        if "BASE PANEL" in text or (flags and flags[-1] == ("0", "0") and "MENU" in text):
            phase = "deploy"
            press(cross)
        elif "SKIP" in text:
            press(cross)
        else:
            # Triangle opens the event skip confirmation; next Cross accepts.
            enqueue(triangle, cross)
        continue
    if phase == "deploy":
        if "MOVE" in text and "ATTACK" in text:
            phase = "move"
            # Move is the first command. R2 jumps to an enemy, then step off
            # its occupied square before confirming a neighbouring destination.
            enqueue(cross, r2, left, cross)
        elif "LAHARL" in text or "BASE" in text:
            press(cross)  # roster -> deploy, deployed unit -> command menu
        else:
            attempts += 1
            if attempts < 10:
                press(cross)
        continue
    if phase == "move":
        if "MOVE" in text and "ATTACK" in text:
            phase = "attack"
            enqueue(down, cross, r2, cross)
        else:
            # If the first neighbour is blocked, try the other neighbours.
            attempts += 1
            if attempts <= 14:
                enqueue((up, right, down, left)[attempts % 4], cross)
        continue
    if phase == "attack":
        # A target may be out of range. Cycle directions around the target
        # before returning to the unit's Move command and trying another tile.
        attempts += 1
        if attempts <= 22:
            enqueue((up, right, down, left)[attempts % 4], cross)
        elif attempts <= 25:
            phase = "deploy"
            enqueue(circle, circle, cross)
        else:
            break
raise SystemExit("FAIL: no confirmed ATTACK ENTRY; inspect ocr.jsonl/frames/driver.log (no pixel pass claimed)")
