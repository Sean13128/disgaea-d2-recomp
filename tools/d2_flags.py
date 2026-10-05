#!/usr/bin/env python3
"""Show player issue bookmarks, merging append-only note/capture updates."""
import argparse
import json
import os
from pathlib import Path
import sys


def load_flags(path):
    records = {}
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                event = json.loads(line)
                key = (event["session"], event["number"])
                kind = event.get("type", "flag")
                if kind == "flag":
                    records[key] = event
                elif kind in ("note", "screenshot") and key in records:
                    field = "note" if kind == "note" else "screenshot_status"
                    records[key][field] = event[field]
            except (ValueError, KeyError, TypeError) as error:
                print(f"{path}:{number}: skipped invalid record: {error}", file=sys.stderr)
    return list(records.values())


def clean(value):
    return " ".join(str(value).split())


def table(records):
    rows = [["#", "Time", "Map/stage", "Guest FPS 1s/10s", "Display FPS 1s/10s",
             "Worst ms", "Top 3 threads (CPU%)", "Note", "Screenshot"]]
    for record in records:
        fps = lambda kind: ("unavailable" if record.get("frame_metrics_available") is False else
                            "/".join(f"{record.get(f'{kind}_fps_{window}', 0):.1f}" for window in ("1s", "10s")))
        top = sorted(record.get("threads", []), key=lambda t: t.get("cpu_percent", 0), reverse=True)[:3]
        threads = ", ".join(f"{clean(t['name'])} {t['cpu_percent']:.1f}%" for t in top)
        screenshot = record.get("screenshot", "")
        status = record.get("screenshot_status", "pending")
        if status != "saved":
            screenshot += f" ({status})"
        rows.append([str(record["number"]), record.get("time", "?"),
                     f"{record.get('map_id')}/{record.get('stage_id')}", fps("guest"), fps("display"),
                     f"{record.get('worst_frame_ms_10s', 0):.1f}", threads, clean(record.get("note", "")), screenshot])
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows)


def default_path():
    hdd = os.environ.get("PS3_HDD0_ROOT")
    parent = Path(hdd).parent if hdd else Path.home() / "Library/Application Support/DisgaeaD2Recomp"
    return parent / "flags/flags.jsonl"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=default_path())
    args = parser.parse_args()
    try:
        print(table(load_flags(args.path)))
    except OSError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
