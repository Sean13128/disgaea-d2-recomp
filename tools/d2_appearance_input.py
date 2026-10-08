#!/usr/bin/env python3
"""Queue a bounded PAD_FILE press for a currently running private experiment.

The audit records queued presses, not native consumption. Inspect the game's
captured response before issuing the next menu action.
"""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import stat
import time
from d2_character_export import _no_symlinks


def press(output,mask,polls=4):
    output=_no_symlinks(Path(output).absolute())
    if type(mask) is not int or not 0<mask<=0xffff or type(polls) is not int or not 1<=polls<=30:
        raise ValueError('Expected a16-bit button mask and1..30 polls')
    if (output/'result.json').exists():raise ValueError('Native run is terminal')
    process=json.loads((output/'process.json').read_text())
    snapshot=json.loads((output/'stage-snapshot.json').read_text())
    if snapshot.get('mode')!='isolated-runtime-experiment':raise ValueError('Expected an isolated appearance run')
    plan=json.loads((output/'planned-input.json').read_text())
    cutoff=plan.get('last_scripted_input')
    if type(cutoff) not in (int,float) or not math.isfinite(cutoff):raise ValueError('Scripted input schedule is unknown')
    if time.time()-process['started']<cutoff+0.5:raise ValueError('Scripted input is still scheduled')
    pid=process.get('pid')
    if type(pid) is not int or pid<1:raise ValueError('Invalid native process')
    try:os.kill(pid,0)
    except ProcessLookupError:raise ValueError('Native process is no longer live') from None
    pad=_no_symlinks(output/'pad.txt')
    lock=os.open(output/'.pad-input.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):raise ValueError('Invalid input lock')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fd=os.open(pad,os.O_RDWR|os.O_NOFOLLOW)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_size>64:raise ValueError('Invalid pad file')
            if os.read(fd,64).strip():raise ValueError('Previous pad command is not consumed')
            if (output/'result.json').exists():raise ValueError('Native run became terminal')
            event=dict(pid=pid,queued_at=time.time(),elapsed=time.time()-process['started'],mask=mask,polls=polls)
            audit_path=_no_symlinks(output/'input-presses.jsonl')
            audit=os.open(audit_path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
            try:
                if not stat.S_ISREG(os.fstat(audit).st_mode) or os.fstat(audit).st_size>1024*1024:raise ValueError('Invalid input audit')
                os.lseek(fd,0,os.SEEK_SET);os.ftruncate(fd,0)
                payload=f'0x{mask:04x} {polls}\n'.encode()
                if os.write(fd,payload)!=len(payload):raise OSError('Incomplete pad command write')
                os.write(audit,(json.dumps(event)+'\n').encode())
            finally:os.close(audit)
            return event
        finally:os.close(fd)
    finally:os.close(lock)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mask',type=lambda value:int(value,0),required=True)
    parser.add_argument('--polls',type=int,default=4)
    print(json.dumps(press(**vars(parser.parse_args())),indent=2))
