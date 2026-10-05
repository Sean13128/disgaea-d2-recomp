#!/bin/bash
# Extract callbacks from this local lift; no game code is copied into the SDK.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p port/build-p port/runs
python3 - <<'PY'
from pathlib import Path
import re
src = Path('port/src/recomp/ppu_recomp_007.cpp').read_text()
addresses = (0x16382c, 0x16440c, 0x163c20, 0x163ebc, 0x164c3c, 0x164d74, 0x1635a4, 0x1635bc)
text = src[:src.index('void func_0013AF1C')]
text += '\nextern "C" {\n'
for bits in (8, 16, 32, 64):
    text += f'uint{bits}_t l_vm_read{bits}(uint64_t); void l_vm_write{bits}(uint64_t, uint{bits}_t);\n'
text += 'void* l_guest_ptr(uint64_t);\n}\n'
for address in addresses:
    match = re.search(r'void func_%08X\(.*?(?=\nvoid func_|\Z)' % address, src, re.S)
    assert match, hex(address)
    text += re.sub(r'\bvm_(read|write)(8|16|32|64)\b', r'l_vm_\1\2', match[0]) + '\n'
probe = Path('port/src/recomp/ppu_recomp_008.cpp').read_text()
for address in (0x17d410, 0x17d448):
    match = re.search(r'void func_%08X\(.*?(?=\nvoid func_|\Z)' % address, probe, re.S)
    assert match
    text += re.sub(r'\bvm_(read|write)(8|16|32|64)\b', r'l_vm_\1\2', match[0]) + '\n'
text += r'''
extern "C" PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*) = nullptr;
extern "C" void ps3_indirect_call(ppu_context*) { abort(); }
void func_0032A4A0(ppu_context* c) { strcpy((char*)l_guest_ptr(c->gpr[3]), (char*)l_guest_ptr(c->gpr[4])); }
void func_0032A34C(ppu_context* c) { c->gpr[3] = (int64_t)strcmp((char*)l_guest_ptr(c->gpr[3]), (char*)l_guest_ptr(c->gpr[4])); }
void func_0032D948(ppu_context* c) { memset(l_guest_ptr(c->gpr[3]), (int)c->gpr[4], (size_t)c->gpr[5]); }
void func_0032AD68(ppu_context* c) { snprintf((char*)l_guest_ptr(c->gpr[3]), 256, (char*)l_guest_ptr(c->gpr[4]), (char*)l_guest_ptr(c->gpr[5]), (int)c->gpr[6]); }
// NisSaveData option queries: enable new slots (8), disable confirm/recreate (7).
void func_0016385C(ppu_context* c) { c->gpr[3] = c->gpr[3] == 8; }
extern "C" void l_d2_callback(uint32_t opd, uint64_t cb, uint64_t get, uint64_t set,
                               uint64_t, uint64_t, uint64_t, uint64_t, uint64_t)
{
    ppu_context c = {};
    c.gpr[1] = 0xF00000; c.gpr[2] = 0x3FDE60;
    c.gpr[3] = cb; c.gpr[4] = get; c.gpr[5] = set;
    switch (l_vm_read32(opd)) {
    case 0x16382c: func_0016382C(&c); break;
    case 0x16440c: func_0016440C(&c); break;
    case 0x163c20: func_00163C20(&c); break;
    case 0x164404: case 0x164408: func_00163EBC(&c); break;
    case 0x164c3c: func_00164C3C(&c); break;
    case 0x164d74: func_00164D74(&c); break;
    case 0x17d410: func_0017D410(&c); break;
    case 0x17d448: func_0017D448(&c); break;
    default: abort();
    }
    DRAIN_TRAMPOLINE(&c);
}
'''
text = text.replace('#include <math.h>', '#include <math.h>\n#include <stdlib.h>')
Path('port/build-p/L-save-callbacks.cpp').write_text(text)
PY
flags=(-O1 -g -I ps3recomp/include)
if [ "${L_SANITIZE:-0}" = 1 ]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang -std=gnu17 "${flags[@]}" -c codex/L.savedata-test.c -o port/build-p/L-save-test.o
clang++ -std=c++20 "${flags[@]}" -I port/src/recomp -c port/build-p/L-save-callbacks.cpp -o port/build-p/L-save-callbacks.o
clang++ "${flags[@]}" -Wl,-dead_strip port/build-p/L-save-test.o port/build-p/L-save-callbacks.o -o port/build-p/L-save-test
./port/build-p/L-save-test work/EBOOT.elf "Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/ICON0.PNG"
