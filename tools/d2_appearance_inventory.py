#!/usr/bin/env python3
"""Extend a private profile with another independently numbered costume.

Creates a new profile, retaining saves and existing costumes. Selection takes
effect at the next launch; no personality rows or live actors are modified.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil

from d2_appearance_run import profile_lock
from d2_appearance_stage import member, rebind_anm, append_visual_alias, clone_tree
from d2_asset_pack import compress_lzs, file_hash, rebuild
from d2_character_export import _no_symlinks, characters, nispack, unlzs


FIELDS=('class_id','selector','new_resource','visual_class_id','selection_mode','enabled','costume_id','display_name','illustration_resource','illustration_donor','face_cell')


def face_cell(item):
    cell=item.get('face_cell')
    if 'face_cell' not in item:return None
    keys=('x','y','width','height','donor')
    if not isinstance(cell,dict) or set(cell)!=set(keys) or any(type(cell[k]) is not int for k in keys):
        raise ValueError('Invalid face-cell binding')
    x,y,w,h,donor=(cell[k] for k in keys)
    if not 480<=w<=4096 or not 96<=h<=4096 or not 384<=x or not 0<=y or any(v%96 for v in (x,y,w,h)) or x+96>w or y+96>h or not 0<=donor<500:
        raise ValueError('Face-cell coordinates outside appended unique atlas columns')
    return cell


def catalog(data):
    entries=data.get('appearances',[data])
    if not isinstance(entries,list) or not 1<=len(entries)<=128:
        raise ValueError('Expected 1..128 active character bindings')
    def illustration(item):
        face_cell(item)
        keys=('illustration_resource','illustration_donor')
        if any(k in item for k in keys):
            if not all(type(item.get(k)) is int and 10000<=item[k]<20000 for k in keys) or item[keys[0]]==item[keys[1]]:
                raise ValueError('Invalid independent illustration binding')
    active=[]
    for entry in entries:
        if not isinstance(entry,dict) or entry.get('selection_mode')!='renderer-only':
            raise ValueError('Inventory requires renderer-only bindings')
        item={key:entry[key] for key in FIELDS if key in entry}
        for key in ('class_id','new_resource','visual_class_id'):
            if type(item.get(key)) is not int or not 0<item[key]<32768:
                raise ValueError('Invalid inventory class/resource ID')
        if item.get('selector')!=1 or type(item.get('enabled',True)) is not bool:
            raise ValueError('Invalid inventory selector/enabled flag')
        illustration(item)
        item.setdefault('costume_id',f"resource-{item['new_resource']}")
        active.append(item)
    if len({item['class_id'] for item in active})!=len(active):
        raise ValueError('Duplicate active character binding')
    inventory=copy.deepcopy(data.get('costumes',active))
    if not isinstance(inventory,list) or not 1<=len(inventory)<=128:
        raise ValueError('Expected 1..128 inventory costumes')
    identities=set();resources=set();pictures=set();faces=set();dimensions=set()
    for item in inventory:
        if not isinstance(item,dict) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',str(item.get('costume_id',''))):
            raise ValueError('Costume IDs must be short lowercase names')
        if item.get('selection_mode')!='renderer-only' or item.get('selector')!=1:
            raise ValueError('Invalid costume binding')
        for field in ('class_id','new_resource','visual_class_id'):
            if type(item.get(field)) is not int or not 0<item[field]<32768:
                raise ValueError('Invalid costume resource')
        illustration(item)
        label=item.get('display_name')
        if label is not None and (not isinstance(label,str) or not label.strip() or len(label.encode())>127 or any(ord(c)<32 or ord(c)==127 for c in label)):
            raise ValueError('Invalid costume display name')
        key=(item['class_id'],item['costume_id'])
        if key in identities or item['new_resource'] in resources:
            raise ValueError('Duplicate costume identity or resource')
        identities.add(key);resources.add(item['new_resource'])
        if item.get('face_cell') is not None:
            c=item['face_cell'];location=(c['x'],c['y'])
            if location in faces:raise ValueError('Duplicate face-cell allocation')
            faces.add(location);dimensions.add((c['width'],c['height']))
        if item.get('illustration_resource'):
            if item['illustration_resource'] in pictures:raise ValueError('Duplicate illustration resource')
            pictures.add(item['illustration_resource'])
    if resources & pictures:raise ValueError('Illustration/body resource collision')
    if len(dimensions)>1:raise ValueError('Face-cell atlas dimensions must agree')
    for item in active:
        matches=[c for c in inventory if (c['class_id'],c['costume_id'])==(item['class_id'],item['costume_id'])]
        if len(matches)!=1 or any(matches[0].get(k)!=item.get(k) for k in (*FIELDS[:5],'illustration_resource','illustration_donor','face_cell')):
            raise ValueError('Active binding does not match catalog')
    return active,inventory


def extend(stage,output,anm,class_id,resource,costume_id,display_name=None):
    stage=_no_symlinks(Path(stage).absolute())
    with profile_lock(stage):
        return _extend(stage,output,anm,class_id,resource,costume_id,display_name)


def _extend(stage,output,anm,class_id,resource,costume_id,display_name=None):
    if display_name is not None and (not isinstance(display_name,str) or not display_name.strip() or len(display_name.encode())>127 or any(ord(c)<32 or ord(c)==127 for c in display_name)):
        raise ValueError("Display name must be1..127 UTF-8 bytes without control characters")
    if stage.stat().st_size>1024*1024:raise ValueError('Manifest exceeds 1 MiB')
    data=json.loads(stage.read_text())
    if data.get('baseline_control'):raise ValueError('Original control cannot register costumes')
    if data.get('asset_probe'):raise ValueError('Asset probe cannot register costumes')
    if data.get('mode')!='isolated-runtime-experiment':raise ValueError('Expected private profile')
    active,inventory=catalog(data)
    if len(inventory)>=128:raise ValueError('Costume inventory is full')
    if not isinstance(costume_id,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',costume_id):
        raise ValueError('Costume ID must be a short lowercase name')
    if any(c['class_id']==class_id and c['costume_id']==costume_id for c in inventory):
        raise ValueError('Costume ID already exists for this character')
    if type(class_id) is not int or not 0<class_id<32768 or type(resource) is not int or not 0<resource<32768:
        raise ValueError('Class and resource must be positive signed-16 integers')
    if any(c['new_resource']==resource or c['visual_class_id']==resource for c in inventory):
        raise ValueError('Resource already registered')
    roots=[]
    for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]:
        root=_no_symlinks(Path(data['runtime_environment'][key]).absolute())
        if root!=stage.parent/name or not root.is_dir():raise ValueError('Expected independent profile roots')
        roots.append(root)
    output=_no_symlinks(Path(output).absolute())
    if output.exists() or stage.parent==output or stage.parent in output.parents or output in stage.parent.parents:
        raise ValueError('Output must be new and outside source profile')
    for source in data.get('source_roots',[]):
        source=Path(source).absolute()
        if output==source or source in output.parents or output in source.parents:
            raise ValueError('Output overlaps original content/profile')
    data_dir=roots[0]/'PS3_GAME/USRDIR/Data';tables=[];old_body=None
    for archive in sorted(data_dir.glob('START*.dat')):
        with archive.open('rb') as stream:
            names={row['name'] for row in nispack(stream,archive.stat().st_size)}
        if 'char.dat' not in names:continue
        raw,_=member(archive,'char.dat')
        donors=[row for row in characters(raw) if row['id']==class_id]
        if len(donors)!=1:raise ValueError('Expected one donor class in every table')
        body=donors[0]['body_animation_ids'][0]
        if old_body is not None and old_body!=body:raise ValueError('Conflicting donor bodies')
        old_body=body
        patched,report=append_visual_alias(raw,class_id,resource)
        tables.append((archive,patched,report))
    if not tables:raise ValueError('No character tables')
    archives=sorted(data_dir.glob('ANM_HI*.dat'));new_name=f'anm{resource:05d}.lzs'
    _,donor=member(data_dir/'ANM_HI.dat',f'anm{old_body:05d}.lzs')
    for archive in archives:
        with archive.open('rb') as stream:
            names={row['name'] for row in nispack(stream,archive.stat().st_size)}
        if new_name in names or f'anm{resource:05d}.dat' in names:raise ValueError('Resource filename collision')
    anm=_no_symlinks(Path(anm).absolute())
    if anm.stat().st_size>64*1024**2:raise ValueError('Input exceeds 64 MiB')
    raw=anm.read_bytes();raw=unlzs(raw) if raw.startswith(b'dat\0') else raw
    expanded,identity=rebind_anm(raw,old_body,resource);packed=compress_lzs(expanded)
    output.parent.mkdir(parents=True,exist_ok=True)
    total=sum(p.stat().st_size for root in roots[:2] for p in root.rglob('*') if p.is_file())
    if shutil.disk_usage(output.parent).free<total+512*1024**2:raise ValueError('Insufficient copy budget')
    output.mkdir()
    try:
        for root,name in zip(roots[:2],('content','hdd0')):clone_tree(root,output/name)
        (output/'hdd1').mkdir();assets=output/'assets';assets.mkdir()
        settings=stage.parent/'appearance-settings.json'
        if settings.exists():
            settings=_no_symlinks(settings)
            if not settings.is_file():raise ValueError('Invalid private settings file')
            shutil.copy2(settings,output/settings.name)
        presets=stage.parent/'appearance-presets'
        if presets.exists():clone_tree(presets,output/presets.name)
        patch=assets/new_name;patch.write_bytes(packed);reports=[]
        destination=output/'content/PS3_GAME/USRDIR/Data'
        # Populate every supplied overlay so precedence cannot shadow this ID.
        for archive in archives:
            target=destination/archive.name
            report=rebuild(target,target.with_suffix('.dat.new'),{}, {new_name:patch},
                           addition_unknown_words={new_name:donor['unknown_be32']})
            os.replace(target.with_suffix('.dat.new'),target)
            actual,_=member(target,new_name)
            if unlzs(actual)!=expanded or file_hash(archive)!=report['source_sha256']:
                raise ValueError('ANM readback/source preservation failed')
            reports.append(report)
        for archive,patched,info in tables:
            patch=assets/(archive.stem+'-char.dat');patch.write_bytes(patched)
            target=destination/archive.name
            report=rebuild(target,target.with_suffix('.dat.new'),{'char.dat':patch})
            os.replace(target.with_suffix('.dat.new'),target)
            if member(target,'char.dat')[0]!=patched or file_hash(archive)!=report['source_sha256']:
                raise ValueError('Table readback/source preservation failed')
            reports.append(dict(visual_alias=info,rebuild=report))
        costume=dict(class_id=class_id,selector=1,new_resource=resource,visual_class_id=resource,
                     selection_mode='renderer-only',enabled=True,costume_id=costume_id)
        if display_name is not None:costume['display_name']=display_name
        inventory.append(costume)
        if not any(e['class_id']==class_id for e in active):
            if len(active)>=128:raise ValueError('Active character list is full')
            active.append(dict(costume,enabled=False))
        data.update(appearances=active,costumes=inventory,gameplay_validated=False)
        # Original single-costume build evidence is historical provenance,
        # rather than a claim about whichever catalog item is selected later.
        historical=('internal_id_patch','expanded_sha256','archive_rebuild','tables',
                    'filename_scan','input_mode','new_member','logical_copy_bytes')
        provenance={key:data.pop(key) for key in historical if key in data}
        if provenance:data.setdefault('base_stage_provenance',provenance)
        data['runtime_environment']={key:str(output/name) for key,name in
            [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]}
        data['inventory_extension']=dict(source_stage=str(stage),source_sha256=file_hash(stage),
            input_anm=str(anm),input_sha256=file_hash(anm),identity_patch=identity,
            new_costume=costume,rebuilds=reports,gameplay_validated=False,
            selection='Existing characters retain active choice; new characters start disabled')
        payload=json.dumps(data,indent=2)+'\n'
        if len(payload.encode())>1024*1024:raise ValueError('Result manifest exceeds 1 MiB')
        (output/'stage.json').write_text(payload)
        return data
    except BaseException:
        shutil.rmtree(output);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--list',action='store_true',help='Read registered costumes and active choices')
    for key in ('output','anm'):parser.add_argument('--'+key,type=Path)
    for key in ('class-id','resource'):parser.add_argument('--'+key,type=int)
    parser.add_argument('--costume-id')
    parser.add_argument('--display-name',help='Name shown in the live appearance menu')
    args=parser.parse_args()
    if args.list:
        path=_no_symlinks(args.stage.absolute())
        if path.stat().st_size>1024*1024:raise ValueError('Manifest exceeds 1 MiB')
        data=json.loads(path.read_text())
        if data.get('mode')!='isolated-runtime-experiment':raise ValueError('Expected private profile')
        active,costumes=catalog(data)
        print(json.dumps(dict(active=active,costumes=costumes),indent=2))
    else:
        options=vars(args);options.pop('list')
        if any(v is None for k,v in options.items() if k!='display_name'):parser.error('Extension requires output, anm, class-id, resource and costume-id')
        result=extend(**options)
        print(json.dumps(dict(stage=str(args.output/'stage.json'),costumes=len(result['costumes'])),indent=2))
