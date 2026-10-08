#!/usr/bin/env python3
"""Persist original/imported appearance choice for the next private launch.

Renderer-only manifests preserve gameplay save fields. This is a command-line
choice, not an in-game menu or a live renderer refresh.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile
import fcntl
from contextlib import contextmanager

from d2_character_export import _no_symlinks


@contextmanager
def choice_lock(path):
    descriptor=os.open(Path(path).parent/'.appearance-choice.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX)
        yield
    finally:os.close(descriptor)


def select(stage, imported, class_id=None, costume_id=None):
    path=_no_symlinks(Path(stage).absolute())
    with choice_lock(path):return _select(path,imported,class_id,costume_id)


def _select(stage, imported, class_id=None, costume_id=None):
    path=_no_symlinks(Path(stage).absolute())
    if type(imported) is not bool:raise ValueError('Choice must be boolean')
    if path.stat().st_size>1024*1024:raise ValueError('Manifest exceeds 1 MiB')
    data=json.loads(path.read_text())
    if data.get('mode')!='isolated-runtime-experiment':raise ValueError('Expected private stage manifest')
    if data.get('baseline_control') and imported:raise ValueError('Original control cannot select an imported appearance')
    if data.get('asset_probe') and imported:raise ValueError('Asset probe cannot select an imported appearance')
    entries=data.get('appearances',[data])
    if class_id is None:
        if len(entries)!=1:raise ValueError('Choose a class ID for multiple bindings')
        class_id=entries[0]['class_id']
    matches=[entry for entry in entries if entry['class_id']==class_id]
    if len(matches)!=1:raise ValueError('Expected exactly one class binding')
    entry=matches[0]
    if entry.get('selection_mode')!='renderer-only' or not entry.get('visual_class_id'):
        raise ValueError('Choice requires renderer-only visual binding')
    previous=entry.get('enabled',True)
    if type(previous) is not bool:raise ValueError('Invalid stored choice')
    if costume_id is not None:
        if not imported:raise ValueError('A costume can only be selected with imported choice')
        from d2_appearance_inventory import catalog, FIELDS
        active,inventory=catalog(data)
        matches=[c for c in inventory if c['class_id']==class_id and c['costume_id']==costume_id]
        if len(matches)!=1:raise ValueError('Unknown costume for this character')
        entries=active;data['appearances']=entries;data['costumes']=inventory
        entry=next(e for e in entries if e['class_id']==class_id)
        for key in FIELDS:entry.pop(key,None)
        entry.update({key:matches[0][key] for key in FIELDS if key in matches[0]})
        if data.get('class_id')==class_id:
            # Keep the legacy diagnostic trace target aligned with selection.
            for key in ('new_resource','visual_class_id','illustration_resource','illustration_donor','face_cell'):
                data.pop(key,None)
                if key in entry:data[key]=entry[key]
    entry['enabled']=imported
    payload=json.dumps(data,indent=2)+'\n'
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.appearance-choice-',delete=False) as f:
            temporary=Path(f.name);f.write(payload);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists():temporary.unlink()
    return dict(stage=str(path),class_id=class_id,costume_id=entry.get('costume_id'),previous='imported' if previous else 'original',
                selected='imported' if imported else 'original',effective='Next process launch; save files untouched')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('choice',choices=('original','imported'))
    parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--class-id',type=int)
    parser.add_argument('--costume-id',help='Select a registered costume with imported choice')
    args=parser.parse_args()
    print(json.dumps(select(args.stage,args.choice=='imported',args.class_id,args.costume_id),indent=2))
