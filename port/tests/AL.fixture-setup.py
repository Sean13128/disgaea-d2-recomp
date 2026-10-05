#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import shutil
import struct
import sys
root = Path(sys.argv[1])
project = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('installer', project/'port/src/d2_install_content.py')
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
def sfo(path, fields):
    keys=bytearray(); values=bytearray(); table=bytearray()
    for key,value in fields.items():
        data=value.encode()+b'\0'
        table+=struct.pack('<HHIII',len(keys),0x204,len(data),len(data),len(values))
        keys+=key.encode()+b'\0'; values+=data
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(struct.pack('<4s4I',b'\0PSF',0x101,20+len(table),20+len(table)+len(keys),len(fields))+table+keys+values)
sfo(root/'dump/PS3_GAME/PARAM.SFO', {'TITLE_ID':'BLUS31313'})
sfo(root/'wrong-dump/PS3_GAME/PARAM.SFO', {'TITLE_ID':'BLES00000'})
sfo(root/'packages/update-140/PARAM.SFO', {'TITLE_ID':'BLUS31313','APP_VER':'01.40'})
sfo(root/'packages/dlc-pack/PARAM.SFO', {'TITLE_ID':'NPUB31321'})
start=root/'packages/update-140/USRDIR/Data/START_7.dat'
start.parent.mkdir(parents=True,exist_ok=True); start.write_bytes(b'synthetic update')
flags=root/'packages/dlc-pack/USRDIR/Data/flag'; flags.mkdir(parents=True,exist_ok=True)
for flag in installer.REQUIRED_FLAGS: (flags/flag).write_bytes(b'x'*256)
resources=root/'relocated/Disgaea D2.app/Contents/Resources'; resources.mkdir(parents=True,exist_ok=True)
shutil.copy2(project/'port/src/d2_install_content.py', resources/'d2_install_content.py')
