#!/bin/bash
# Recreate the audited SDK without relying on a local branch or patch order.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
exec "${PYTHON:-python3}" - "$root" "$@" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
if len(sys.argv) != 3:
    sys.exit('Usage: tools/bootstrap_sdk.sh <new-sdk-directory>')
lock = json.loads((root / 'patches/SDK.lock').read_text())
patch = root / 'patches' / lock['patch']
if hashlib.sha256(patch.read_bytes()).hexdigest() != lock['patch_sha256']:
    sys.exit('SDK patch SHA256 mismatch; update SDK.lock only after auditing the export')
dest = pathlib.Path(sys.argv[2]).resolve()
if dest.exists():
    sys.exit(f'Refusing existing SDK directory: {dest}')
def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()
git('clone', '--no-checkout', lock['repository'], dest)
git('-C', dest, 'checkout', '--detach', lock['base'])
if git('-C', dest, 'rev-parse', 'HEAD') != lock['base']:
    sys.exit('SDK base revision mismatch')
git('-C', dest, 'apply', '--check', '--index', patch)
git('-C', dest, 'apply', '--index', patch)
if git('-C', dest, 'write-tree') != lock['tree']:
    sys.exit('Patched SDK tree differs from the audited revision; do not build it')
print(f'SDK bootstrap PASS: base={lock["base"]} revision={lock["revision"]} patch_sha256={lock["patch_sha256"]}')
print(f'SDK ready: {dest} (base HEAD plus indexed patch; no local commit needed)')
PY
