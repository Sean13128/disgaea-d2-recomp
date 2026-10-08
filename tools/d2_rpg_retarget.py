#!/usr/bin/env python3
"""Reuse reviewed D2 pose identities for another extracted RPG appearance.

Proposals retain rectangle/mirror/orientation choices, recompute source crops
and donor-anchored placement, and require fresh review before palette authoring.
Missing named poses are reported rather than replaced by a guessed pose.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw

from d2_character_export import _no_symlinks
from d2_rpg_map import (archive_member, box, build, page_image, pages_of, read,
                        render_sprite, sha, sprite_catalog)


def retarget(donor,common,mapping,sprites):
    # Validate the reviewed source map against the actual donor geometry first.
    build(donor,common,mapping)
    pages=pages_of(donor,mapping['palette']);entries=[];missing=[]
    for old in mapping['entries']:
        if old.get('selected') is not True:continue
        source=sprites.get(old['pose'])
        if source is None:
            missing.append(dict(pose=old['pose'],rectangle_index=old['rectangle_index'],reason='Named pose absent'))
            continue
        entry=copy.deepcopy(old)
        for key in ('visual_score','second_candidate','review_note'):entry.pop(key,None)
        image=source['image'];crop=box(image)
        x,y,w,h=old['destination'];bounds=box(page_image(pages[old['page']]).crop((x,y,x+w,y+h)))
        if image.getchannel('A').getextrema()[1]==0:
            crop=(0,0,image.width,image.height);placement=[x,y,w,h];operation='clear'
        elif crop is None or bounds is None:
            missing.append(dict(pose=old['pose'],rectangle_index=old['rectangle_index'],reason='No visible source or donor anchor'))
            continue
        else:
            sw,sh=crop[2]-crop[0],crop[3]-crop[1]
            if old.get('quarter_turns',0)%2:sw,sh=sh,sw
            scale=min((bounds[2]-bounds[0])/sw,(bounds[3]-bounds[1])/sh)
            dw=max(1,round(sw*scale));dh=max(1,round(sh*scale))
            placement=[x+(bounds[0]+bounds[2]-dw)//2,y+bounds[3]-dh,dw,dh];operation='replace'
        entry.update(source=source['path'],source_sha256=source['sha256'],source_crop=list(crop),
                     placement=placement,operation=operation,selected=False,
                     review_required=True,retarget_source_sha256=old['source_sha256'])
        render_sprite(entry,pages[entry['page']])
        entries.append(entry)
    result=copy.deepcopy(mapping)
    result.update(entries=entries,skipped=missing,
        placement_policy='Named-pose reuse; new opaque bounds fit to original donor bottom/center',
        retarget=dict(proposed=len(entries),missing=len(missing),review_required=True,
                      gameplay_validated=False))
    return result


def propose(archive,composition,appearance,output):
    output=_no_symlinks(Path(output).absolute())
    if output.exists():raise ValueError('Output must be new')
    composition=_no_symlinks(Path(composition).absolute())
    config=json.loads(read(composition))
    if config.get('schema')!=1 or config.get('mode')!='texture-composition':raise ValueError('Expected texture composition')
    names=config.get('mappings')
    if not isinstance(names,list) or not 1<=len(names)<=16:raise ValueError('Expected 1..16 mapping components')
    sprites=sprite_catalog(appearance);results=[];review=[];member_name=None
    for name in names:
        path=Path(name);path=path if path.is_absolute() else composition.parent/path
        mapping=json.loads(read(path))
        if len(mapping.get('entries',[]))>4096:raise ValueError('Mapping exceeds 4096 entries')
        if member_name is not None and member_name!=mapping['member']:raise ValueError('Mixed donor members')
        member_name=mapping['member'];donor=archive_member(archive,member_name)
        common=archive_member(archive,mapping['common_member'])
        result=retarget(donor,common,mapping,sprites);results.append(result);pages=pages_of(donor,mapping['palette'])
        old_by_index={e['rectangle_index']:e for e in mapping['entries'] if e.get('selected') is True}
        for entry in result['entries']:
            old=old_by_index[entry['rectangle_index']];page=pages[entry['page']]
            review.append((len(results)-1,entry,render_sprite(old,page),render_sprite(entry,page)))
    output.mkdir(parents=True)
    try:
        retained=dict(schema=1,mode='texture-composition',mappings=[])
        for i,result in enumerate(results):
            name=f'mapping-{i}.json';(output/name).write_text(json.dumps(result,indent=2)+'\n');retained['mappings'].append(name)
        (output/'composition.json').write_text(json.dumps(retained,indent=2)+'\n')
        # Each panel compares the previous mapped crop with the new proposal.
        for offset in range(0,len(review),20):
            group=review[offset:offset+20];canvas=Image.new('RGBA',(1280,190*((len(group)+3)//4)),(32,32,32,255));draw=ImageDraw.Draw(canvas)
            for i,(component,entry,old,new) in enumerate(group):
                x=(i%4)*320;y=(i//4)*190
                for j,im in enumerate((old,new)):
                    im=im.copy();im.thumbnail((148,148),Image.Resampling.NEAREST)
                    canvas.alpha_composite(im,(x+j*160+(148-im.width)//2,y+(148-im.height)//2))
                draw.text((x,y+150),f"map{component} rect{entry['rectangle_index']} {entry['pose']}",fill='white')
                draw.text((x,y+168),'previous                  proposal',fill='white')
            canvas.convert('RGB').save(output/f'review-{offset//20:02d}.png')
        report=dict(proposed=len(review),missing=[e for r in results for e in r['skipped']],
            composition_source=str(composition),composition_sha256=sha(read(composition)),
            appearance=str(Path(appearance).absolute()),appearance_manifest_sha256=sha(read(Path(appearance)/'manifest.json')),
            approval='All proposals start selected:false; review crops and select explicitly',gameplay_validated=False)
        (output/'retarget.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    except BaseException:
        shutil.rmtree(output);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','composition','appearance','output'):parser.add_argument('--'+name,type=Path,required=True)
    print(json.dumps(propose(**vars(parser.parse_args())),indent=2))
