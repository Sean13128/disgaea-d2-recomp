#!/usr/bin/env python3
"""Copy a private profile and mark one indexed ANM resource for causal checks.

This is a diagnostic profile, not a costume import. Only palette RGB bytes
change; alpha, indices, resource ID, animation metadata and save bytes remain.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

from d2_anm import parse_anm
from d2_asset_pack import compress_lzs,rebuild,file_hash
from d2_character_export import _no_symlinks,anm_pages,indexed_png,nispack,unlzs
from d2_appearance_run import profile_lock
from d2_appearance_stage import clone_tree,member


def mark(raw,resource,rgb=(255,0,255)):
    if type(resource) is not int or not 0<resource<100000:raise ValueError('Expected a positive five-digit file ID')
    if not isinstance(rgb,(list,tuple)) or len(rgb)!=3 or any(type(c) is not int or not 0<=c<=255 for c in rgb):raise ValueError('Expected three RGB bytes')
    raw=unlzs(raw) if raw.startswith(b'dat\0') else raw
    if len(raw)>64*1024**2:raise ValueError('Expanded marker exceeds64MiB')
    meta=parse_anm(raw)
    if len(meta['blocks'])!=1 or meta['blocks'][0]['resource_id']!=resource:raise ValueError('Expected one matching ANM resource block')
    pairs=anm_pages(raw,include_rgba=False);output=bytearray(raw);allowed=set();palettes={}
    for pair in pairs:
        start=meta['payload_start']+struct.unpack_from('>I',raw,pair['palette_header_offset']+12)[0]
        count=len(pair['colors'])
        if start in palettes:
            if palettes[start]!=count:raise ValueError('Ambiguous shared palette extent')
            continue
        extent=set(range(start,start+4*count))
        if any(start<p['data_offset']+len(p['indices']) and p['data_offset']<start+4*count for p in pairs):raise ValueError('Palette overlaps texture indices')
        if extent & allowed:raise ValueError('Palette extents overlap')
        palettes[start]=count
        for i in range(count):
            offset=start+4*i+1;output[offset:offset+3]=bytes(rgb);allowed.update(range(offset,offset+3))
    if not palettes:raise ValueError('No indexed palettes to mark')
    if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(raw,output))):raise ValueError('Unexpected non-RGB changes')
    if output[:meta['payload_start']]!=raw[:meta['payload_start']]:raise ValueError('Metadata changed')
    after=anm_pages(output,include_rgba=False)
    for before,now in zip(pairs,after):
        if before['indices']!=now['indices'] or [c[3] for c in before['colors']]!=[c[3] for c in now['colors']]:raise ValueError('Indices or alpha changed')
    packed=compress_lzs(bytes(output))
    if unlzs(packed)!=output:raise ValueError('Marker compression roundtrip failed')
    return bytes(output),packed,dict(resource=resource,rgb=list(rgb),source_sha256=hashlib.sha256(raw).hexdigest(),
        marked_sha256=hashlib.sha256(output).hexdigest(),metadata_sha256=hashlib.sha256(raw[:meta['payload_start']]).hexdigest(),
        changed_rgb_bytes=sum(a!=b for a,b in zip(raw,output)),palettes=len(palettes),expanded_bytes=len(raw),packed_bytes=len(packed),
        preserved='ANM metadata, resource ID, texture indices and palette alpha',
        limits='RGB marker only; an alpha-only consumer may remain visually unchanged',visible_consumer_validated=False)


def probe(stage,output,resource,rgb=(255,0,255)):
    stage=_no_symlinks(Path(stage).absolute())
    with profile_lock(stage):return _probe(stage,output,resource,rgb)


def probe_face(stage,output,face_member,row,rgb=(255,0,255)):
    if face_member not in ('wf_unique1.lzs','wf_unique2.lzs','wf_human.lzs','wf_monster.lzs','wf_other.lzs'):
        raise ValueError('Expected a known face atlas member')
    stage=_no_symlinks(Path(stage).absolute())
    with profile_lock(stage):return _probe(stage,output,None,rgb,(face_member,row))


def _probe(stage,output,resource,rgb,face=None):
    if stage.stat().st_size>1024*1024:raise ValueError('Manifest exceeds1MiB')
    data=json.loads(stage.read_text())
    if data.get('mode')!='isolated-runtime-experiment' or data.get('asset_probe'):raise ValueError('Expected an isolated non-probe source profile')
    if face is None and (type(resource) is not int or not 0<resource<100000):raise ValueError('Expected a positive five-digit file ID')
    roots={}
    for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]:
        root=_no_symlinks(Path(data['runtime_environment'][key]).absolute())
        if root!=stage.parent/name or not root.is_dir():raise ValueError('Expected independent source profile roots')
        roots[name]=root
    output=_no_symlinks(Path(output).absolute())
    if output.exists() or not output.parent.is_dir():raise ValueError('Output must be new with an existing parent')
    if any(output==root or root in output.parents or output in root.parents for root in [stage.parent,*map(Path,data.get('source_roots',[]))]):raise ValueError('Output overlaps source profile/original content')
    source_data=roots['content']/'PS3_GAME/USRDIR/Data';target=face[0] if face else f'anm{resource:05d}.lzs';patches=[]
    for archive in sorted(source_data.glob('START*.dat' if face else 'ANM_HI*.dat')):
        with archive.open('rb') as stream:names=[r['name'] for r in nispack(stream,archive.stat().st_size)]
        if target not in names:continue
        raw,_=member(archive,target)
        if face:
            from d2_face_atlas import mark_row
            expanded,packed,report=mark_row(raw,face[1],rgb)
        else:expanded,packed,report=mark(raw,resource,rgb)
        patches.append((archive,expanded,packed,report))
    if not patches:raise ValueError('Resource absent from supplied asset archives')
    all_hashes={str(p.relative_to(roots['content'])):file_hash(p) for p in sorted(source_data.rglob('*')) if p.is_file()}
    save_hashes={str(p.relative_to(roots['hdd0'])):file_hash(p) for p in roots['hdd0'].rglob('*') if p.is_file()}
    total=sum(p.stat().st_size for root in [roots['content'],roots['hdd0']] for p in root.rglob('*') if p.is_file())
    if shutil.disk_usage(output.parent).free<total+max(a.stat().st_size for a,_,_,_ in patches)+512*1024**2:raise ValueError('Insufficient probe-copy space')
    output.mkdir()
    try:
        clone_tree(roots['content'],output/'content');clone_tree(roots['hdd0'],output/'hdd0');(output/'hdd1').mkdir()
        artifacts=output/'probe-artifacts';artifacts.mkdir();changes=[]
        for index,(archive,expanded,packed,report) in enumerate(patches):
            bundle=artifacts/str(index);bundle.mkdir();payload=bundle/target;payload.write_bytes(packed)
            (bundle/'expanded.bin').write_bytes(expanded)
            copied=output/'content'/archive.relative_to(roots['content']);rebuilt=copied.with_suffix('.probe.dat')
            rebuild(copied,rebuilt,{target:payload});rebuilt.replace(copied)
            if member(copied,target)[0]!=packed:raise ValueError('Marked member readback mismatch')
            report.update(archive=str(archive.relative_to(roots['content'])),source_archive_sha256=all_hashes[str(archive.relative_to(roots['content']))],marked_archive_sha256=file_hash(copied))
            changes.append(report)
            if index==0:
                if face:
                    from d2_face_atlas import image
                    image(expanded,report['width'],report['height']).crop((0,face[1]*96,report['width'],(face[1]+1)*96)).save(artifacts/'marked-row.png')
                else:
                    for page in anm_pages(expanded,include_rgba=False):
                        (artifacts/f"marked-page-{page['texture']}-palette-{page['palette']}.png").write_bytes(indexed_png(page['width'],page['height'],page['indices'],page['colors']))
        changed={r['archive']:r['marked_archive_sha256'] for r in changes}
        for relative,digest in all_hashes.items():
            if file_hash(roots['content']/relative)!=digest or file_hash(output/'content'/relative)!=changed.get(relative,digest):raise ValueError('Source/unrelated Data preservation failed')
        for relative,digest in save_hashes.items():
            if file_hash(roots['hdd0']/relative)!=digest or file_hash(output/'hdd0'/relative)!=digest:raise ValueError('Save-root preservation failed')
        data.pop('original_archive_sha256',None);data['baseline_control']=False
        data['runtime_environment']={key:str(output/name) for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]}
        data['asset_probe']=dict(mode='face-row-rgb-marker' if face else 'palette-rgb-marker',resource=resource,rgb=list(rgb),source_stage=str(stage),archives=changes,
            source_data_sha256=all_hashes,save_root_sha256=save_hashes,logical_copy_bytes=total,visible_consumer_validated=False)
        if face:data['asset_probe'].update(member=target,row=face[1])
        data['input_mode']='Diagnostic marked resource; not a costume or pristine archive baseline'
        data['source_roots']=list(dict.fromkeys([*data.get('source_roots',[]),str(stage.parent)]));data['gameplay_validated']=False
        (output/'stage.json').write_text(json.dumps(data,indent=2)+'\n');return data
    except BaseException:shutil.rmtree(output);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('stage','output'):parser.add_argument('--'+key,type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--resource',type=int)
    group.add_argument('--face-member')
    parser.add_argument('--face-row',type=int)
    parser.add_argument('--rgb',type=int,nargs=3,default=(255,0,255));args=parser.parse_args()
    if args.face_member:
        if args.face_row is None:parser.error('--face-member requires --face-row')
        result=probe_face(args.stage,args.output,args.face_member,args.face_row,args.rgb)
    else:
        if args.face_row is not None:parser.error('--face-row requires --face-member')
        result=probe(args.stage,args.output,args.resource,args.rgb)
    print(json.dumps(result['asset_probe'],indent=2))
