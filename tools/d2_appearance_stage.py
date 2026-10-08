#!/usr/bin/env python3
"""Stage a separately numbered D2 appearance in isolated game/profile copies.

This is a runtime research package, not installation into the user's app.
Only a single-block donor is supported. Legacy selection needs a free second
body slot; renderer-only selection preserves existing personality/body slots.
Internal ANM ID rebinding is an explicit experiment requiring gameplay validation.
"""
import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys

from d2_anm import parse_anm
from d2_asset_pack import compress_lzs, file_hash, rebuild
from d2_character_export import _no_symlinks, characters, nispack, unlzs


def member(path, name):
    with path.open('rb') as f:
        matches=[r for r in nispack(f,path.stat().st_size) if r['name']==name]
        if len(matches)!=1:
            raise ValueError('Missing or ambiguous member: '+name)
        row=matches[0]
        if row['size']>64*1024*1024:
            raise ValueError('Member exceeds 64 MiB')
        f.seek(row['offset'])
        return f.read(row['size']),row


def rebind_anm(raw, old_id, new_id):
    if type(new_id) is not int or not 0<new_id<32768 or new_id==old_id:
        raise ValueError('New body ID must be distinct and positive signed-16')
    meta=parse_anm(raw)
    if len(meta['blocks'])!=1 or meta['blocks'][0]['resource_id']!=old_id:
        raise ValueError('Rebinding supports only a matching single-block donor')
    offset=meta['blocks'][0]['offset']+4
    output=bytearray(raw)
    struct.pack_into('>H',output,offset,new_id)
    assert output[:offset]==raw[:offset] and output[offset+2:]==raw[offset+2:]
    assert parse_anm(output)['blocks'][0]['resource_id']==new_id
    return bytes(output),dict(offset=offset,old_id=old_id,new_id=new_id,
                              scope='Only empirical block identity changed; native binding requires runtime validation')


def patch_character_table(raw, class_id, resource):
    rows=[r for r in characters(raw) if r['id']==class_id]
    if len(rows)!=1 or rows[0]['body_animation_ids'][1]!=0:
        raise ValueError('Expected one class with an empty second body resource')
    offset=rows[0]['record_offset']+0x1be
    output=bytearray(raw)
    struct.pack_into('>H',output,offset,resource)
    assert output[:offset]==raw[:offset] and output[offset+2:]==raw[offset+2:]
    return bytes(output),dict(class_id=class_id,row=rows[0]['row'],offset=offset,
                              selector=1,original_body=rows[0]['body_animation_ids'][0],new_body=resource)


def prepare_character_table(raw,class_id,resource,renderer_only=False):
    if not renderer_only:return patch_character_table(raw,class_id,resource)
    rows=[r for r in characters(raw) if r['id']==class_id]
    if len(rows)!=1:raise ValueError('Expected one renderer donor class')
    row=rows[0]
    return bytes(raw),dict(class_id=class_id,row=row['row'],offset=row['record_offset']+0x1be,
        selector=1,original_body=row['body_animation_ids'][0],
        preserved_body_ids=row['body_animation_ids'],visual_resource=resource,
        scope='Renderer-only donor record unchanged; native personality/body slots retained')


def append_visual_alias(raw,class_id,resource):
    rows=characters(raw)
    if isinstance(resource,bool) or not isinstance(resource,int) or not 1<=resource<32768:
        raise ValueError('Visual resource must be an integer from 1 through 32767')
    donors=[r for r in rows if r['id']==class_id]
    if len(donors)!=1 or len(rows)>=65535:
        raise ValueError('Expected one donor and room for an additional visual record')
    if resource in {r['id'] for r in rows}:
        raise ValueError('Visual class ID already exists')
    donor=donors[0]
    record=bytearray.fromhex(donor['raw_hex'])
    # The renderer resolves its body ANM through class +0x196. A separate
    # visual definition keeps the gameplay class and portrait source intact.
    for offset in (0x194,0x196,0x1bc):struct.pack_into('>H',record,offset,resource)
    struct.pack_into('>H',record,0x1be,0)
    output=bytearray(raw+record)
    struct.pack_into('>H',output,0,len(rows)+1)
    assert output[2:len(raw)]==raw[2:]
    alias=characters(output)[-1]
    assert alias['id']==resource and alias['body_animation_ids']==[resource,0]
    return bytes(output),dict(visual_class_id=resource,row=len(rows),
        scope='Cloned visual definition; gameplay units retain original class ID')


def patch_save_selector(raw, class_id, selector=1, cached_body=None):
    if len(raw)!=1498152 or selector not in (0,1):
        raise ValueError('Expected plaintext native D2 save and selector zero/one')
    count=struct.unpack_from('>H',raw,0x1507ec)[0]
    if not 1<=count<=128:
        raise ValueError('Invalid party count')
    units=[i for i in range(count) if struct.unpack_from('>H',raw,0x598+i*0x1a60+0x1158)[0]==class_id]
    if len(units)!=1:
        raise ValueError('Expected exactly one matching saved unit')
    offset=0x598+units[0]*0x1a60+0x117a
    if raw[offset] not in (0,1):
        raise ValueError('Unexpected saved selector')
    output=bytearray(raw);output[offset]=selector
    allowed={offset}
    report=dict(unit=units[0],offset=offset,old_selector=raw[offset],new_selector=selector,
                scope='Selector only; class/stats/equipment/skills unchanged')
    if cached_body is not None:
        if type(cached_body) is not int or not 0<cached_body<32768:
            raise ValueError('Invalid cached body ID')
        body_offset=0x598+units[0]*0x1a60+0x11d8
        old_body,secondary=struct.unpack_from('>2H',raw,body_offset)
        struct.pack_into('>H',output,body_offset,cached_body)
        allowed.update((body_offset,body_offset+1))
        report.update(cached_body_offset=body_offset,old_body=old_body,new_body=cached_body,
                      secondary_body_preserved=secondary,
                      scope='Selector and primary cached body only; class/stats/equipment/skills/secondary body unchanged')
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,output)))
    report['changed_bytes']=sum(a!=b for a,b in zip(raw,output))
    return bytes(output),report


def clone_tree(source, target):
    """Independent files; APFS copy-on-write when possible, never shared symlinks."""
    source=_no_symlinks(source.absolute())
    for parent, dirs, files in os.walk(source):
        for name in dirs+files:
            mode=(Path(parent)/name).lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError('Source tree contains a symlink or special file')
    clone=None
    if sys.platform=='darwin':
        libc=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
        clone=libc.clonefile
        clone.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int]
        clone.restype=ctypes.c_int
    def copy(src,dst):
        if clone is not None:
            if clone(os.fsencode(src),os.fsencode(dst),0)==0:
                return dst
            error=ctypes.get_errno()
            if error not in (errno.EXDEV,errno.ENOTSUP,errno.EINVAL):
                raise OSError(error,os.strerror(error),src)
        return shutil.copy2(src,dst)
    return shutil.copytree(source,target,copy_function=copy)


def prepare_save(raw, class_id, resource, renderer_only=False):
    patched, report = patch_save_selector(raw,class_id,cached_body=None if renderer_only else resource)
    if renderer_only:
        # Use the existing bounded unique-unit validation, retaining all bytes.
        selector=raw[report['offset']]
        report.update(new_selector=selector,changed_bytes=0,
                      scope='Byte-identical private save; appearance selected only in renderer manifest')
        return raw, report
    return patched, report


def stage(repo, output, class_id=30, resource=30000, anm=None, save_slot=None,visual_alias=False,renderer_only=False):
    if renderer_only and not visual_alias:
        raise ValueError('Renderer-only selection requires a visual alias')
    repo=_no_symlinks(repo.absolute())
    output=_no_symlinks(output.absolute())
    if output.exists():
        raise ValueError('Output directory must be new')
    if type(resource) is not int or not 0<resource<32768:
        raise ValueError('Resource must be positive signed-16')
    game=repo/'Disgaea D2 A Brighter Darkness - [BLUS31313]'
    sources=[game,repo/'port/hdd0',repo/'port/hdd1']
    if any(p==output or p in output.parents or output in p.parents for p in sources):
        raise ValueError('Output overlaps source content/profile')
    if not all(p.is_dir() for p in sources):
        raise ValueError('Missing game or HDD roots')
    data=game/'PS3_GAME/USRDIR/Data'
    tables=[]
    old_body=None
    for path in sorted(data.glob('START*.dat')):
        with path.open('rb') as f:
            names={r['name'] for r in nispack(f,path.stat().st_size)}
        if 'char.dat' not in names:
            continue
        raw,_=member(path,'char.dat')
        patched,info=prepare_character_table(raw,class_id,resource,renderer_only)
        if visual_alias:
            patched,alias_info=append_visual_alias(patched,class_id,resource)
            info['visual_alias']=alias_info
        if old_body is not None and info['original_body']!=old_body:
            raise ValueError('Conflicting primary body resources across START variants')
        old_body=info['original_body'];tables.append((path,patched,info))
    if not tables or resource==old_body:
        raise ValueError('No eligible table or resource matches original')
    new_name=f'anm{resource:05d}.lzs'
    archive=data/'ANM_HI.dat'
    donor_name=f'anm{old_body:05d}.lzs'
    donor_packed,donor_row=member(archive,donor_name)
    scans=[]
    for path in sorted(data.glob('ANM_HI*.dat')):
        with path.open('rb') as f:
            names={r['name'] for r in nispack(f,path.stat().st_size)}
        if new_name in names or f'anm{resource:05d}.dat' in names:
            raise ValueError('Resource filename already exists')
        scans.append(dict(archive=str(path),entries=len(names)))
    if anm:
        anm=_no_symlinks(anm.absolute())
        if anm.stat().st_size>64*1024*1024:
            raise ValueError('Input ANM exceeds 64 MiB')
        packed=anm.read_bytes()
        expanded=unlzs(packed) if packed.startswith(b'dat\0') else packed
    else:
        expanded=unlzs(donor_packed)
    rebound,rebind_info=rebind_anm(expanded,old_body,resource)
    packed=compress_lzs(rebound)
    if unlzs(packed)!=rebound:
        raise ValueError('Rebound resource roundtrip failed')
    save_source=None
    save_report=None
    if save_slot:
        if save_slot not in ('NPUB31321_NORMAL_00','NPUB31321_NORMAL_01'):
            raise ValueError('Unsupported diagnostic save slot')
        save_source=sources[1]/'home/00000001/savedata'/save_slot/'SAVEDATA.DAT'
        if (save_source.parent/'PARAM.PFD').exists():
            raise ValueError('Encrypted/PFD save requires separate verified import first')
        save_before=_no_symlinks(save_source).read_bytes()
        save_after,save_report=prepare_save(save_before,class_id,resource,renderer_only)
        save_report.update(source_sha256=hashlib.sha256(save_before).hexdigest(),
                           output_sha256=hashlib.sha256(save_after).hexdigest(),slot=save_slot)
    # Check volume capacity before cloning approximately 3 GiB of supplied content.
    output.parent.mkdir(parents=True,exist_ok=True)
    total=sum(p.stat().st_size for tree in sources[:2] for p in tree.rglob('*') if p.is_file())
    if shutil.disk_usage(output.parent).free<total+512*1024*1024:
        raise ValueError('Insufficient space for independent content/profile copies')
    output.mkdir()
    try:
        for source,name in zip(sources[:2],('content','hdd0')):
            clone_tree(source,output/name)
        # D2 caches archive members by name/version; an old cache could return
        # the unmodified character table even when staged archive bytes differ.
        (output/'hdd1').mkdir()
        assets=output/'assets';assets.mkdir()
        (assets/new_name).write_bytes(packed)
        staged_data=output/'content/PS3_GAME/USRDIR/Data'
        pack_report=rebuild(staged_data/'ANM_HI.dat',staged_data/'ANM_HI.dat.new',{},
                            {new_name:assets/new_name},
                            addition_unknown_words={new_name:donor_row['unknown_be32']})
        os.replace(staged_data/'ANM_HI.dat.new',staged_data/'ANM_HI.dat')
        table_reports=[]
        for source,patched,info in tables:
            patch_path=assets/(source.stem+'-char.dat');patch_path.write_bytes(patched)
            target=staged_data/source.name
            report=rebuild(target,target.with_suffix('.dat.new'),{'char.dat':patch_path})
            os.replace(target.with_suffix('.dat.new'),target)
            original,_=member(source,'char.dat');actual,_=member(target,'char.dat')
            if actual!=patched or (not renderer_only and original[info['offset']:info['offset']+2]!=b'\0\0'):
                raise ValueError('Table readback or source preservation failed')
            if file_hash(source)!=report['source_sha256']:
                raise ValueError('Original START archive changed')
            table_reports.append(dict(source=str(source),patch=info,rebuild=report))
        if file_hash(archive)!=pack_report['source_sha256']:
            raise ValueError('Original ANM archive changed')
        added,_=member(staged_data/'ANM_HI.dat',new_name)
        original,_=member(staged_data/'ANM_HI.dat',donor_name)
        if unlzs(added)!=rebound or original!=donor_packed:
            raise ValueError('New resource or original-body readback failed')
        if save_source:
            target=output/'hdd0'/save_source.relative_to(sources[1])
            target.write_bytes(save_after)
            if save_source.read_bytes()!=save_before or target.read_bytes()!=save_after:
                raise ValueError('Save copy/source validation failed')
        report=dict(mode='isolated-runtime-experiment',class_id=class_id,new_resource=resource,
                    selector=1,internal_id_patch=rebind_info,new_member=new_name,
                    expanded_sha256=hashlib.sha256(rebound).hexdigest(),archive_rebuild=pack_report,
                    tables=table_reports,save_patch=save_report,filename_scan=scans,
                    source_roots=list(map(str,sources[:2])),logical_copy_bytes=total,
                    cache_policy='New empty HDD1; original cache untouched',
                    runtime_environment={'PS3_VFS_ROOT':str(output/'content'),
                                         'PS3_HDD0_ROOT':str(output/'hdd0'),
                                         'PS3_HDD1_ROOT':str(output/'hdd1')},
                    input_mode='Converted ANM' if anm else 'Original donor as control',
                    gameplay_validated=False,
                    limitations=['Internal ANM block identity patch is empirical and unvalidated until runtime.',
                                 'Existing selector also has personality/voice consumers; cosmetic isolation unproven.',
                                 'Save selection is an isolated diagnostic; no new menu option is authored.',
                                 'Collision scan covers filenames in supplied ANM_HI archives, not all internal IDs.'])
        if visual_alias:report['visual_class_id']=resource
        report['selection_mode']='renderer-only' if renderer_only else 'selector'
        if renderer_only:
            report['limitations'][1]='Renderer manifest selection preserves saved personality and body fields; full runtime voice/menu behavior needs validation.'
        (output/'stage.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    except BaseException:
        shutil.rmtree(output)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--class-id',type=int,default=30)
    parser.add_argument('--resource',type=int,default=30000)
    parser.add_argument('--anm',type=Path,help='Optional converted expanded ANM or LZS; default uses original donor')
    parser.add_argument('--save-slot',choices=('NPUB31321_NORMAL_00','NPUB31321_NORMAL_01'))
    parser.add_argument('--visual-alias',action='store_true',help='Append a separate renderer definition; requires experimental importer build')
    parser.add_argument('--renderer-only',action='store_true',help='Select appearance in renderer manifest without modifying save personality/body fields')
    args=parser.parse_args()
    result=stage(args.repo,args.output,args.class_id,args.resource,args.anm,args.save_slot,args.visual_alias,args.renderer_only)
    print(json.dumps(dict(stage=str(args.output/'stage.json'),resource=result['new_resource'],
                          mode=result['mode'],table_variants=len(result['tables']),save_patch=result['save_patch']),indent=2))
