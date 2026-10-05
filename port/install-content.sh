#!/bin/bash
# Default: install into a fresh copy of port/hdd0. --into selects an existing hdd0.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
exec "$root/.venv/bin/python" - "$root" "$@" <<'PY'
import argparse,pathlib,shutil,sys,tempfile
root=pathlib.Path(sys.argv[1])
a=argparse.ArgumentParser(description='Install D2 1.40 update and DLC (never changes the disc dump)')
a.add_argument('--into',type=pathlib.Path,help='destination hdd0; default is a new copy of port/hdd0')
x=a.parse_args(sys.argv[2:])
if x.into is None:
    dst=pathlib.Path(tempfile.mkdtemp(prefix='AD-content.',dir=root/'port/runs'))/'hdd0'
    shutil.copytree(root/'port/hdd0',dst)
else:
    dst=x.into.resolve()
    dump=root/'Disgaea D2 A Brighter Darkness - [BLUS31313]'
    if dst==dump or dump in dst.parents:
        a.error('destination must be outside the game dump')
    dst.mkdir(parents=True,exist_ok=True)
for source,title in [('update-140','BLUS31313'),('dlc-pack','NPUB31321')]:
    src=root/'dlc'/source
    if not (src/'PARAM.SFO').is_file() or not (src/'USRDIR').is_dir():
        a.error(f'incomplete source: {src}')
    out=dst/'game'/title
    out.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src/'PARAM.SFO',out/'PARAM.SFO')
    shutil.copytree(src/'USRDIR',out/'USRDIR',dirs_exist_ok=True)
print(dst)
PY
