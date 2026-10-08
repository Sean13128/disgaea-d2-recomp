#!/usr/bin/env python3
"""Create an original-archive control with the same private gameplay save.

No character rows, animation resources or gameplay-save fields are authored.
This controls archive changes; it still uses the separately supplied native runner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from d2_character_export import _no_symlinks,characters,nispack
from d2_appearance_stage import clone_tree,member,prepare_save
from d2_appearance_run import profile_lock


def file_hash(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def baseline(repo,stage,output,class_id=30):
    with profile_lock(stage):return _baseline(repo,stage,output,class_id)


def _baseline(repo,stage,output,class_id):
    repo=_no_symlinks(Path(repo).absolute());stage=_no_symlinks(Path(stage).absolute());output=_no_symlinks(Path(output).absolute())
    if type(class_id) is not int or not 0<class_id<32768:raise ValueError('Expected a positive signed-16 class ID')
    if stage.stat().st_size>1024*1024:raise ValueError('Manifest exceeds1MiB')
    data=json.loads(stage.read_text())
    if data.get('mode')!='isolated-runtime-experiment':raise ValueError('Expected an isolated source profile')
    saved_root=_no_symlinks(Path(data['runtime_environment']['PS3_HDD0_ROOT']).absolute())
    if saved_root!=stage.parent/'hdd0':raise ValueError('Expected the independent private save root')
    game=repo/'Disgaea D2 A Brighter Darkness - [BLUS31313]'
    if not game.is_dir() or not saved_root.is_dir():raise ValueError('Missing source game/private save')
    if output.exists() or not output.parent.is_dir():raise ValueError('Output must be new with an existing parent')
    forbidden=[game,saved_root,stage.parent,*map(Path,data.get('source_roots',[]))]
    if any(root==output or root in output.parents or output in root.parents for root in forbidden):raise ValueError('Control output overlaps source content/profile')
    slot=data.get('save_patch',{}).get('slot')
    if not isinstance(slot,str) or not slot or slot in ('.','..') or '/' in slot or '\\' in slot:raise ValueError('Expected a private save slot')
    save=saved_root/'home/00000001/savedata'/slot/'SAVEDATA.DAT'
    before=save.read_bytes();_,save_info=prepare_save(before,class_id,1,renderer_only=True)
    tables=[];body=None
    for archive in sorted((game/'PS3_GAME/USRDIR/Data').glob('START*.dat')):
        with archive.open('rb') as stream:names={r['name'] for r in nispack(stream,archive.stat().st_size)}
        if 'char.dat' not in names:continue
        raw,_=member(archive,'char.dat');rows=characters(raw);matches=[r for r in rows if r['id']==class_id]
        if len(matches)!=1:raise ValueError('Original table lacks a unique donor')
        current=matches[0]['body_animation_ids'][0]
        if body is not None and current!=body:raise ValueError('Conflicting original body definitions')
        body=current;tables.append(dict(name=archive.name,rows=len(rows),char_sha256=hashlib.sha256(raw).hexdigest()))
    if not tables or not body:raise ValueError('No original donor tables')
    total=sum(p.stat().st_size for root in (game,saved_root) for p in root.rglob('*') if p.is_file())
    if shutil.disk_usage(output.parent).free<total+512*1024*1024:raise ValueError('Insufficient control-copy space')
    archive_hashes={str(p.relative_to(game)):file_hash(p) for p in sorted((game/'PS3_GAME/USRDIR/Data').rglob('*')) if p.is_file()}
    output.mkdir()
    try:
        clone_tree(game,output/'content');clone_tree(saved_root,output/'hdd0');(output/'hdd1').mkdir()
        for relative,digest in archive_hashes.items():
            if file_hash(game/relative)!=digest or file_hash(output/'content'/relative)!=digest:raise ValueError('Original archive/source readback changed')
        for item in tables:
            copied,_=member(output/'content/PS3_GAME/USRDIR/Data'/item['name'],'char.dat')
            if hashlib.sha256(copied).hexdigest()!=item['char_sha256']:raise ValueError('Original table readback changed')
        after=output/'hdd0'/save.relative_to(saved_root)
        if after.read_bytes()!=before or save.read_bytes()!=before:raise ValueError('Save copy/source preservation failed')
        save_info.update(slot=slot,source_sha256=hashlib.sha256(before).hexdigest(),output_sha256=hashlib.sha256(before).hexdigest())
        report=dict(mode='isolated-runtime-experiment',baseline_control=True,class_id=class_id,selector=1,
            new_resource=body,visual_class_id=class_id,selection_mode='renderer-only',enabled=False,
            runtime_environment={key:str(output/name) for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]},
            source_roots=[str(game),str(saved_root)],source_stage=str(stage),save_patch=save_info,original_tables=tables,
            original_archive_sha256=archive_hashes,logical_copy_bytes=total,input_mode='Original source archives; no added rows or animation files',gameplay_validated=False)
        (output/'stage.json').write_text(json.dumps(report,indent=2)+'\n');return report
    except BaseException:shutil.rmtree(output);raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    for key in ('stage','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--class-id',type=int,default=30)
    print(json.dumps(baseline(**vars(parser.parse_args())),indent=2))
