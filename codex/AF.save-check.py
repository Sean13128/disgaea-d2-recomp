#!/usr/bin/env python3
"""Compare an edited native save against plaintext or a verified retail PFD save."""
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'tools'))
import d2_save_import as importer

def payload(path):
    path=Path(path)
    if (path/'PARAM.PFD').exists():
        files,_,_,checks=importer.convert(path)
        print('Retail PFD decrypt/verify:',checks['pfd_version'],checks['verified'])
        return files['SAVEDATA.DAT']
    data=(path/'SAVEDATA.DAT').read_bytes()
    assert len(data)==importer.EXPECTED_SIZE
    importer.parse_sfo((path/'PARAM.SFO').read_bytes())
    return data

before,after=map(payload,sys.argv[1:3])
for label,offset,size in [('HL',0x568,8),('Laharl Mana',0x16e8,4),('Laharl base ATK',0x1668,8),('item0 HP',0xdd590,8),('item0 level',0xdd5d2,2),('inventory count',0x13ee08,2)]:
    a=int.from_bytes(before[offset:offset+size],'big');b=int.from_bytes(after[offset:offset+size],'big')
    assert b==a+(0 if label=='inventory count' else 1),(label,a,b)
    print(f'{label}: {a} -> {b}; persisted offset=0x{offset:x} PASS')
assert int.from_bytes(after[0x1507ec:0x1507ee],'big')==118
for index in range(118):
    c=0x598+index*0x1a60
    assert before[c+0x650:c+0x680]==after[c+0x650:c+0x680]
    assert before[c+0x1154:c+0x1156]==after[c+0x1154:c+0x1156]
print('118 names / levels preserved: PASS')
print('Source SHA256',hashlib.sha256(before).hexdigest())
print('Edited SHA256',hashlib.sha256(after).hexdigest())
print('Changed payload bytes',sum(x!=y for x,y in zip(before,after)))
