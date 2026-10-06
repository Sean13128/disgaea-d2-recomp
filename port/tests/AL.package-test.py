#!/usr/bin/env python3
"""Verify publication failure preserves the old bundle, and atomic replacement."""
import os
from pathlib import Path
import hashlib
import subprocess
import sys
import re
import tempfile
root = Path(__file__).resolve().parents[2]
build = Path(sys.argv[1]).resolve()
def destination(directory):
    text = (directory/'d2_package.cmake').read_text()
    return Path(re.search(r'file\(MAKE_DIRECTORY "([^"\n]+/dist/[^"\n]+)"\)', text)[1])/'Disgaea D2.app'
app = destination(build)
def digest():
    return {str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*') if p.is_file()}
before = digest(); assert before
p = subprocess.run(['cmake', f'-DAPP={build}/Disgaea D2.app', '-DRUNNER=/nonexistent/runner',
                    f'-DPUBLISH={build}/DisgaeaD2Publish', '-P', str(build/'d2_package.cmake')], capture_output=True)
assert p.returncode != 0 and digest() == before
print('[AL-package] failed staging preserves signed published app: PASS')
with tempfile.TemporaryDirectory(prefix='AL-package.', dir=os.environ.get('D2_TEST_TMPDIR')) as tmp:
    work = Path(tmp); dst=work/'App'; dst.mkdir(); (dst/'version').write_text('old')
    publisher = build/'DisgaeaD2Publish'
    assert subprocess.run([publisher, work/'missing', dst], capture_output=True).returncode == 1
    assert (dst/'version').read_text() == 'old'
    stage = work/'stage'; stage.mkdir(); (stage/'version').write_text('new')
    assert subprocess.run([publisher, stage, dst]).returncode == 0
    assert (dst/'version').read_text() == 'new' and (stage/'version').read_text() == 'old'
    print('[AL-package] failed publication keeps old bundle; replacement exchanges complete directories: PASS')
for path in (app, destination(build/'version100')):
    assert path.exists()
    assert subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',path]).returncode == 0
print('[AL-package] isolated signed v140 and v100 distributions: PASS')
