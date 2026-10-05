#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import os

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("d2_flags", root / "tools/d2_flags.py")
flags = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flags)
with tempfile.TemporaryDirectory(dir=os.environ["D2_TEST_TMPDIR"], prefix="AN-summary-") as temp:
    path = Path(temp) / "flags.jsonl"
    record = dict(type="flag", session="a", number=1, time="2026-10-05T18:00:00Z", map_id=30101,
                  stage_id=7, guest_fps_1s=60., guest_fps_10s=59.5, display_fps_1s=30., display_fps_10s=29.5,
                  worst_frame_ms_10s=45., threads=[dict(name=f"thread {n}", cpu_percent=n * 10.) for n in range(5)],
                  note="", screenshot="/flags/test.png")
    lines = [record, dict(type="note", session="a", number=1, note="white\nportrait 日本語"),
             dict(type="screenshot", session="a", number=1, screenshot_status="saved"),
             dict(record, session="b", note="separate session")]
    path.write_text("\n".join(json.dumps(line) for line in lines) + '\n{"incomplete":', encoding="utf-8")
    rows = flags.load_flags(path)
    assert len(rows) == 2 and rows[0]["note"] == "white\nportrait 日本語"
    output = flags.table(rows)
    for expected in ("30101/7", "60.0/59.5", "30.0/29.5", "45.0", "white portrait 日本語", "/flags/test.png", "separate session"):
        assert expected in output, expected
    assert "thread 4 40.0%, thread 3 30.0%, thread 2 20.0%" in output
    assert "thread 1" not in output
    assert "(pending)" in output  # second session has no completion event
    assert flags.table([]).startswith("#")
    os.environ["PS3_HDD0_ROOT"] = str(Path(temp) / "hdd0")
    assert flags.default_path() == Path(temp) / "flags/flags.jsonl"
print("[AN summary] table, top three, note/capture merge, session isolation, truncated-line recovery: PASS")
