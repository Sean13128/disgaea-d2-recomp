#!/usr/bin/env python3
"""Attach an authored face cell to one costume in a new private profile."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from d2_appearance_inventory import catalog
from d2_appearance_run import profile_lock
from d2_appearance_stage import clone_tree,member
from d2_asset_pack import file_hash,rebuild
from d2_character_export import _no_symlinks,characters,nispack
from d2_face_atlas import decode


def validate_change(original,authored,x,y):
    before,w,h=decode(original);after,nw,nh=decode(authored)
    if w<384 or w%96 or h%96 or nh!=h or nw not in (w,w+96) or type(x) is not int or type(y) is not int or x<384 or x%96 or y<0 or y%96 or x+96>nw or y+96>h:
        raise ValueError('Invalid appended face-cell geometry')
    expected=bytearray(nw*h*4)
    for row in range(h):expected[row*nw*4:row*nw*4+w*4]=before[16+row*w*4:16+(row+1)*w*4]
    for row in range(y,y+96):
        begin=(row*nw+x)*4
        if any(expected[begin:begin+96*4]):raise ValueError('Requested cell already contains artwork')
        expected[begin:begin+96*4]=after[16+begin:16+begin+96*4]
    header=bytearray(before[:16]);header[4:6]=after[4:6];header[12:16]=after[12:16]
    if after!=bytes(header)+expected:raise ValueError('Authored atlas changes unrelated artwork or headers')
    return nw,h


def attach(stage,atlas,class_id,costume_id,x,y,output):
    stage=_no_symlinks(Path(stage).absolute())
    with profile_lock(stage):return _attach(stage,atlas,class_id,costume_id,x,y,output)


def _attach(stage,atlas,class_id,costume_id,x,y,output):
    atlas=_no_symlinks(Path(atlas).absolute());output=_no_symlinks(Path(output).absolute())
    if type(class_id) is not int or not 0<class_id<32768 or stage.stat().st_size>1024*1024:
        raise ValueError('Invalid class ID or manifest size')
    data=json.loads(stage.read_text())
    if data.get('mode')!='isolated-runtime-experiment' or data.get('asset_probe') or data.get('baseline_control'):
        raise ValueError('Expected a private costume profile')
    active,inventory=catalog(data);matches=[c for c in inventory if c['class_id']==class_id and c['costume_id']==costume_id]
    if len(matches)!=1 or 'face_cell' in matches[0]:raise ValueError('Expected one costume without a face cell')
    roots={}
    for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]:
        root=_no_symlinks(Path(data['runtime_environment'][key]).absolute())
        if root!=stage.parent/name or not root.is_dir():raise ValueError('Expected private profile roots')
        roots[name]=root
    if output.exists() or not output.parent.is_dir():raise ValueError('Output must be new with an existing parent')
    if any(output==r or r in output.parents or output in r.parents for r in [stage.parent,*map(Path,data.get('source_roots',[]))]) or output in atlas.parents:
        raise ValueError('Output overlaps source')
    data_dir=roots['content']/'PS3_GAME/USRDIR/Data';target='wf_unique1.lzs';patches=[];donors=set();tables=0
    authored=atlas.read_bytes();input_sha=hashlib.sha256(authored).hexdigest();shape=None
    for archive in sorted(data_dir.glob('START*.dat')):
        with archive.open('rb') as f:names=[r['name'] for r in nispack(f,archive.stat().st_size)]
        if 'char.dat' in names:
            rows=characters(member(archive,'char.dat')[0]);found=[r for r in rows if r['id']==class_id]
            if len(found)!=1:raise ValueError('Character face association absent or ambiguous')
            donors.add(found[0]['raw_be16'][0x19E//2]);tables+=1
        if target in names:
            current,_=member(archive,target);dims=validate_change(current,authored,x,y)
            if shape and dims!=shape:raise ValueError('Face overlay dimensions disagree')
            shape=dims;patches.append(archive)
    if not patches or not tables or len(donors)!=1 or not 0<=next(iter(donors))<500:
        raise ValueError('Expected a unique-group face association and atlas')
    cell=dict(x=x,y=y,width=shape[0],height=shape[1],donor=next(iter(donors)))
    if any(c.get('face_cell',{}).get('x')==x and c.get('face_cell',{}).get('y')==y for c in inventory):
        raise ValueError('Face cell already assigned')
    total=sum(p.stat().st_size for root in [roots['content'],roots['hdd0']] for p in root.rglob('*') if p.is_file())
    if shutil.disk_usage(output.parent).free<total+max(p.stat().st_size for p in patches)+512*1024**2:raise ValueError('Insufficient copy space')
    hashes={str(p.relative_to(roots['content'])):file_hash(p) for p in data_dir.rglob('*') if p.is_file()}
    saves={str(p.relative_to(roots['hdd0'])):file_hash(p) for p in roots['hdd0'].rglob('*') if p.is_file()}
    output.mkdir()
    try:
        clone_tree(roots['content'],output/'content');clone_tree(roots['hdd0'],output/'hdd0');(output/'hdd1').mkdir()
        for name in ['appearance-settings.json','appearance-presets']:
            p=stage.parent/name
            if p.exists():
                p=_no_symlinks(p)
                if p.is_dir():clone_tree(p,output/name)
                else:shutil.copy2(p,output/name)
        assets=output/'face-assets';assets.mkdir();patch=assets/target;patch.write_bytes(authored);reports=[]
        for archive in patches:
            copied=output/'content'/archive.relative_to(roots['content']);rebuilt=copied.with_suffix('.face.dat')
            report=rebuild(copied,rebuilt,{target:patch});rebuilt.replace(copied);reports.append(report)
            if member(copied,target)[0]!=authored:raise ValueError('Face atlas readback mismatch')
        changed={str(Path(r['source']).relative_to(output/'content')):r['output_sha256'] for r in reports}
        for relative,digest in hashes.items():
            if file_hash(roots['content']/relative)!=digest or file_hash(output/'content'/relative)!=changed.get(relative,digest):raise ValueError('Source/unrelated Data changed')
        for relative,digest in saves.items():
            if file_hash(roots['hdd0']/relative)!=digest or file_hash(output/'hdd0'/relative)!=digest:raise ValueError('Save root changed')
        if file_hash(atlas)!=input_sha:raise ValueError('Authored atlas changed')
        matches[0]['face_cell']=cell
        for c in inventory:
            if 'face_cell' in c:c['face_cell'].update(width=shape[0],height=shape[1])
        for entry in active:
            selected=next(c for c in inventory if (c['class_id'],c['costume_id'])==(entry['class_id'],entry['costume_id']))
            if 'face_cell' in selected:entry['face_cell']=dict(selected['face_cell'])
            if data.get('class_id')==entry['class_id']:
                data.pop('face_cell',None)
                if 'face_cell' in entry:data['face_cell']=dict(entry['face_cell'])
        data.update(appearances=active,costumes=inventory,runtime_environment={k:str(output/n) for k,n in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]})
        data['source_roots']=list(dict.fromkeys([*data.get('source_roots',[]),str(stage.parent)]))
        data['face_extension']=dict(source_stage=str(stage),input_atlas=str(atlas),input_sha256=input_sha,class_id=class_id,costume_id=costume_id,cell=cell,rebuilds=reports,source_data_sha256=hashes,save_root_sha256=saves,native_validated=False)
        data['gameplay_validated']=False;catalog(data);payload=json.dumps(data,indent=2)+'\n'
        if len(payload.encode())>1024*1024:raise ValueError('Result manifest exceeds1MiB')
        (output/'stage.json').write_text(payload);return data
    except BaseException:shutil.rmtree(output);raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['stage','atlas','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--class-id',type=int,required=True);p.add_argument('--costume-id',required=True)
    p.add_argument('--x',type=int,required=True);p.add_argument('--y',type=int,required=True)
    a=vars(p.parse_args());result=attach(**a);extension=result['face_extension']
    print(json.dumps(dict(stage=str(a['output'].absolute()/'stage.json'),class_id=extension['class_id'],
        costume_id=extension['costume_id'],face_cell=extension['cell'],
        replaced_overlays=len(extension['rebuilds']),source_data_files_checked=len(extension['source_data_sha256']),
        hdd0_files_checked=len(extension['save_root_sha256']),native_validated=False),indent=2))
