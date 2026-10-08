#!/usr/bin/env python3
"""Convert and attach optional Status illustration art to a private costume.

Preserves native geometry/animation metadata and the original class/save data.
Independent artwork selection requires the opt-in 1.40 illustration getter.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

from PIL import Image,ImageOps
from d2_anm import parse_anm
from d2_appearance_inventory import catalog
from d2_appearance_run import profile_lock
from d2_appearance_stage import clone_tree,member,rebind_anm
from d2_asset_pack import compress_lzs,file_hash,rebuild
from d2_character_export import _no_symlinks,anm_pages,characters,indexed_png,nispack,unlzs
from d2_rpg_map import archive_member,pages_of,page_image,read,rgba
from d2_rpg_palette import encode_images


def convert(donor,source,crop,matte=(255,255,255)):
    meta=parse_anm(donor)
    if len(meta['blocks'])!=1 or len(pages_of(donor))!=1:raise ValueError('Expected a single-resource, single-page illustration')
    block=meta['blocks'][0]
    if not 10000<=block['resource_id']<20000:raise ValueError('Expected a Status illustration resource')
    image=rgba(source)
    if not isinstance(crop,(list,tuple)) or len(crop)!=4 or any(type(v) is not int for v in crop):raise ValueError('Expected four integer source crop coordinates')
    x0,y0,x1,y1=crop
    if not 0<=x0<x1<=image.width or not 0<=y0<y1<=image.height:raise ValueError('Crop exceeds source image')
    if len(matte)!=3 or any(type(v) is not int or not 0<=v<=255 for v in matte):raise ValueError('Expected three matte RGB bytes')
    rects={(r['x'],r['y'],r['width'],r['height']) for r in block['tables']['rectangle_candidates']['records'] if r['width'] and r['height']}
    if len(rects)!=1:raise ValueError('Illustration has several distinct rectangles; explicit multi-region mapping required')
    x,y,w,h=next(iter(rects));pages=pages_of(donor);key=next(iter(pages));page=pages[key]
    if x+w>page['width'] or y+h>page['height']:raise ValueError('Illustration rectangle exceeds atlas')
    patch=ImageOps.fit(image.crop(crop),(w,h),method=Image.Resampling.LANCZOS)
    background=Image.new('RGBA',(w,h),(*matte,255));background.alpha_composite(patch)
    images={key:page_image(page)};images[key].paste(background,(x,y))
    expanded,packed,report=encode_images(donor,images,1)
    report.update(asset_role='status-illustration',donor_resource=block['resource_id'],source_image_sha256=hashlib.sha256(source).hexdigest(),
        crop=list(crop),matte=list(matte),destination=[x,y,w,h],fit='Aspect-preserving cover after explicit crop',
        limits='Single illustration pose and native tags retained; source pose reused across those tags. UI icons and live routing are separate acceptance checks.')
    return expanded,packed,report


def attach(stage,output,anm,class_id,costume_id,resource,donor_resource=10030):
    stage=_no_symlinks(Path(stage).absolute())
    with profile_lock(stage):return _attach(stage,output,anm,class_id,costume_id,resource,donor_resource)


def _attach(stage,output,anm,class_id,costume_id,resource,donor_resource):
    if type(class_id) is not int or not 0<class_id<32768:raise ValueError('Expected a positive signed16 class ID')
    if any(type(v) is not int or not 10000<=v<20000 for v in (resource,donor_resource)) or resource==donor_resource:raise ValueError('Expected distinct Status resources10000..19999')
    if stage.stat().st_size>1024*1024:raise ValueError('Manifest exceeds1MiB')
    data=json.loads(stage.read_text())
    if data.get('mode')!='isolated-runtime-experiment' or data.get('asset_probe') or data.get('baseline_control'):raise ValueError('Expected a private costume profile')
    active,inventory=catalog(data);matches=[e for e in inventory if e['class_id']==class_id and e['costume_id']==costume_id]
    if len(matches)!=1:raise ValueError('Expected one registered costume')
    roots={}
    for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]:
        root=_no_symlinks(Path(data['runtime_environment'][key]).absolute())
        if root!=stage.parent/name or not root.is_dir():raise ValueError('Expected independent private roots')
        roots[name]=root
    output=_no_symlinks(Path(output).absolute())
    if output.exists() or not output.parent.is_dir():raise ValueError('Output must be new with an existing parent')
    if any(output==r or r in output.parents or output in r.parents for r in [stage.parent,*map(Path,data.get('source_roots',[]))]):raise ValueError('Output overlaps source profile/original content')
    data_dir=roots['content']/'PS3_GAME/USRDIR/Data';archives=sorted(data_dir.glob('ANM_HI*.dat'));new_name=f'anm{resource:05d}.lzs'
    if not archives:raise ValueError('No animation archives')
    for archive in archives:
        with archive.open('rb') as f:names={r['name'] for r in nispack(f,archive.stat().st_size)}
        if new_name in names or f'anm{resource:05d}.dat' in names:raise ValueError('Illustration filename collision')
    table_count=0
    for archive in data_dir.glob('START*.dat'):
        with archive.open('rb') as f:names={r['name'] for r in nispack(f,archive.stat().st_size)}
        if 'char.dat' not in names:continue
        table_count+=1
        rows=characters(member(archive,'char.dat')[0]);donors=[r for r in rows if r['id']==class_id]
        if len(donors)!=1 or donors[0]['raw_be16'][0x196//2]+10000!=donor_resource:raise ValueError('Donor class/illustration association mismatch')
    if not table_count:raise ValueError('No donor character tables')
    original,info=member(data_dir/'ANM_HI.dat',f'anm{donor_resource:05d}.lzs');original=unlzs(original)
    input_path=_no_symlinks(Path(anm).absolute());input_bytes=read(input_path);input_sha=hashlib.sha256(input_bytes).hexdigest()
    raw=input_bytes;raw=unlzs(raw) if raw.startswith(b'dat\0') else raw
    meta=parse_anm(original)
    if raw[:meta['payload_start']]!=original[:meta['payload_start']] or len(raw)!=len(original):raise ValueError('Authored illustration metadata/geometry differs from donor')
    expanded,identity=rebind_anm(raw,donor_resource,resource);packed=compress_lzs(expanded)
    total=sum(p.stat().st_size for root in [roots['content'],roots['hdd0']] for p in root.rglob('*') if p.is_file())
    if shutil.disk_usage(output.parent).free<total+max(p.stat().st_size for p in archives)+512*1024**2:raise ValueError('Insufficient illustration copy space')
    source_data={str(p.relative_to(roots['content'])):file_hash(p) for p in data_dir.rglob('*') if p.is_file()}
    saved={str(p.relative_to(roots['hdd0'])):file_hash(p) for p in roots['hdd0'].rglob('*') if p.is_file()}
    output.mkdir()
    try:
        clone_tree(roots['content'],output/'content');clone_tree(roots['hdd0'],output/'hdd0');(output/'hdd1').mkdir()
        settings=stage.parent/'appearance-settings.json'
        if settings.exists():shutil.copy2(_no_symlinks(settings),output/settings.name)
        assets=output/'illustration-assets';assets.mkdir();patch=assets/new_name;patch.write_bytes(packed);(assets/'expanded.bin').write_bytes(expanded)
        presets=stage.parent/'appearance-presets'
        if presets.is_dir():clone_tree(presets,output/presets.name)
        reports=[]
        for archive in archives:
            target=output/'content'/archive.relative_to(roots['content']);rebuilt=target.with_suffix('.illustration.dat')
            report=rebuild(target,rebuilt,{}, {new_name:patch},addition_unknown_words={new_name:info['unknown_be32']});rebuilt.replace(target)
            if member(target,new_name)[0]!=packed or file_hash(archive)!=report['source_sha256']:raise ValueError('Illustration/source readback failed')
            reports.append(report)
        changed={str(Path(r['source']).relative_to(output/'content')):r['output_sha256'] for r in reports}
        for relative,digest in source_data.items():
            if file_hash(roots['content']/relative)!=digest or file_hash(output/'content'/relative)!=changed.get(relative,digest):raise ValueError('Source/unrelated Data preservation failed')
        if file_hash(input_path)!=input_sha:raise ValueError('Input illustration changed during staging')
        for relative,digest in saved.items():
            if file_hash(roots['hdd0']/relative)!=digest or file_hash(output/'hdd0'/relative)!=digest:raise ValueError('Save-root preservation failed')
        costume=matches[0];costume.update(illustration_resource=resource,illustration_donor=donor_resource)
        for entry in active:
            if entry['class_id']==class_id and entry['costume_id']==costume_id:
                entry.update(illustration_resource=resource,illustration_donor=donor_resource)
                if data.get('class_id')==class_id:data.update(illustration_resource=resource,illustration_donor=donor_resource)
        data.update(appearances=active,costumes=inventory,runtime_environment={k:str(output/n) for k,n in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]})
        data['source_roots']=list(dict.fromkeys([*data.get('source_roots',[]),str(stage.parent)]))
        data['illustration_extension']=dict(source_stage=str(stage),input_anm=str(anm),input_sha256=input_sha,resource=resource,donor_resource=donor_resource,
            class_id=class_id,costume_id=costume_id,identity_patch=identity,rebuilds=reports,source_data_sha256=source_data,save_root_sha256=saved,gameplay_validated=False)
        data['gameplay_validated']=False;catalog(data)
        payload=json.dumps(data,indent=2)+'\n'
        if len(payload.encode())>1024*1024:raise ValueError('Result manifest exceeds1MiB')
        (output/'stage.json').write_text(payload);return data
    except BaseException:shutil.rmtree(output);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    c=sub.add_parser('convert');c.add_argument('--archive',type=Path,required=True);c.add_argument('--donor-resource',type=int,default=10030)
    c.add_argument('--source',type=Path,required=True);c.add_argument('--crop',type=int,nargs=4,required=True);c.add_argument('--matte',type=int,nargs=3,default=(255,255,255));c.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('attach')
    for k in ('stage','output','anm'):a.add_argument('--'+k,type=Path,required=True)
    a.add_argument('--class-id',type=int,required=True);a.add_argument('--costume-id',required=True);a.add_argument('--resource',type=int,required=True);a.add_argument('--donor-resource',type=int,default=10030)
    args=vars(parser.parse_args());command=args.pop('command')
    if command=='attach':print(json.dumps(attach(**args)['illustration_extension'],indent=2))
    else:
        output=_no_symlinks(args['output'].absolute())
        if output.exists() or not output.parent.is_dir():parser.error('Output must be new with existing parent')
        donor=archive_member(args['archive'],f"anm{args['donor_resource']:05d}.lzs")
        expanded,packed,report=convert(donor,read(args['source']),args['crop'],args['matte']);output.mkdir()
        report.update(source_image=str(_no_symlinks(args['source'].absolute())),donor_archive=str(_no_symlinks(args['archive'].absolute())))
        (output/'expanded.bin').write_bytes(expanded);(output/f"anm{args['donor_resource']:05d}.lzs").write_bytes(packed)
        for page in anm_pages(expanded,include_rgba=False):
            (output/f"page-{page['texture']}-palette-{page['palette']}.png").write_bytes(indexed_png(page['width'],page['height'],page['indices'],page['colors']))
        (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
