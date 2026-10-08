#!/usr/bin/env python3
"""Inspect RPG sprite-reference timelines with exact Unity file/path identity.

This decodes sprite switches, not composed transforms, layering or effects.
UnityPy is needed only to resolve serialized-file identities and dependencies.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from d2_character_export import _no_symlinks
from d2_rpg_map import read


def streamed_frames(words, curve_count):
    if len(words)>1024*1024 or not 0<=curve_count<=65536:
        raise ValueError('Streamed clip exceeds bounds')
    if any(type(w) is not int or not 0<=w<=0xffffffff for w in words):
        raise ValueError('Invalid streamed word')
    raw=struct.pack('<'+str(len(words))+'I',*words)
    frames=[];offset=0;previous=-math.inf
    while offset<len(raw):
        if offset+8>len(raw):raise ValueError('Truncated streamed frame')
        time,count=struct.unpack_from('<fI',raw,offset);offset+=8
        if math.isnan(time) or time<previous or count>curve_count or offset+count*20>len(raw):
            raise ValueError('Invalid streamed frame time/count')
        keys={}
        for _ in range(count):
            index,*coefficients=struct.unpack_from('<I4f',raw,offset);offset+=20
            if index>=curve_count or index in keys or not all(math.isfinite(v) for v in coefficients):
                raise ValueError('Invalid streamed curve key')
            keys[index]=coefficients
        if math.isinf(time) and (time<0 or keys or offset!=len(raw)):
            raise ValueError('Invalid streamed end sentinel')
        frames.append((time,keys));previous=time
    return frames


def sprite_timelines(clip):
    muscle=clip['m_MuscleClip'];data=muscle['m_Clip']['data']
    streamed=data['m_StreamedClip'];dense=data['m_DenseClip'];constant=data['m_ConstantClip']['data']
    frames=streamed_frames(streamed['data'],streamed['curveCount'])
    pointers=clip['m_ClipBindingConstant']['pptrCurveMapping']
    offset=0;timelines=[]
    for binding in clip['m_ClipBindingConstant']['genericBindings']:
        width=1
        if binding['typeID']==4 and not binding['isPPtrCurve']:
            if binding['attribute'] not in (1,2,3,4):raise ValueError('Unknown transform binding width')
            width=4 if binding['attribute']==2 else 3
        if binding['isPPtrCurve']:
            if offset<streamed['curveCount']:
                keys=[(max(muscle['m_StartTime'],t),values[offset][-1]) for t,values in frames
                      if offset in values and t<=muscle['m_StopTime']]
            elif offset>=streamed['curveCount']+dense['m_CurveCount']:
                index=offset-streamed['curveCount']-dense['m_CurveCount']
                if index>=len(constant):raise ValueError('Constant curve outside bank')
                keys=[(muscle['m_StartTime'],constant[index])]
            else:
                raise ValueError('Dense sprite curves require separate evaluation')
            switches=[]
            for time,value in keys:
                if not math.isfinite(value) or value!=int(value) or not 0<=value<len(pointers):
                    raise ValueError('Sprite pointer index outside mapping')
                reference=pointers[int(value)]
                item=dict(time=time,file_id=reference['m_FileID'],path_id=str(reference['m_PathID']))
                if switches and switches[-1]['time']==time:switches[-1]=item
                elif not switches or (item['file_id'],item['path_id'])!=(switches[-1]['file_id'],switches[-1]['path_id']):
                    switches.append(item)
            timelines.append(dict(curve_index=offset,binding=binding,switches=switches))
        offset+=width
    if offset!=streamed['curveCount']+dense['m_CurveCount']+len(constant):
        raise ValueError('Binding widths do not match curve banks')
    return timelines


def inspect(extraction, source):
    import UnityPy
    extraction=_no_symlinks(Path(extraction).absolute());source=_no_symlinks(Path(source).absolute())
    manifest=json.loads(read(extraction/'manifest.json'))
    prefab=next(b for b in manifest['bundles'] if b['label']=='prefab')
    paths={Path(b['path']):b['sha256'] for b in manifest['bundles']}
    for dep in prefab['dependencies']:
        path=source/dep['name']
        if path.is_file():paths.setdefault(path,None)
    files={};sources=[];owners={}
    for path,expected in paths.items():
        raw=read(path);digest=hashlib.sha256(raw).hexdigest()
        if expected and digest!=expected:raise ValueError('Original bundle hash mismatch')
        env=UnityPy.load(raw);names=[]
        for bundle in env.files.values():
            for name,serialized in getattr(bundle,'files',{}).items():
                if not hasattr(serialized,'externals'):continue
                sprites={str(obj.path_id):obj.parse_as_dict()['m_Name'] for obj in serialized.objects.values()
                         if obj.type.name=='Sprite'}
                value=dict(sprites=sprites,externals=[e.path.rsplit('/',1)[-1] for e in serialized.externals])
                if name in files and files[name]!=value:raise ValueError('Conflicting serialized-file identity')
                files[name]=value;names.append(name)
        owners[str(path)]=names
        if read(path)!=raw:raise ValueError('Bundle changed during clip inspection')
        sources.append(dict(path=str(path),sha256=digest,serialized_files=names))
    prefab_files=owners[prefab['path']]
    if len(prefab_files)!=1:raise ValueError('Ambiguous prefab serialized file')
    owner=prefab_files[0];clips=[]
    for entry in manifest['clips']:
        path=extraction/entry['metadata'];raw=read(path)
        if hashlib.sha256(raw).hexdigest()!=manifest['files'][entry['metadata']]['sha256']:
            raise ValueError('Extracted clip metadata hash mismatch')
        data=json.loads(raw)
        try:
            timelines=sprite_timelines(data)
            for timeline in timelines:
                for switch in timeline['switches']:
                    file_id=switch['file_id'];external=files[owner]['externals']
                    target=owner if file_id==0 else external[file_id-1] if 1<=file_id<=len(external) else None
                    switch['serialized_file']=target
                    switch['sprite_name']=files.get(target,{}).get('sprites',{}).get(switch['path_id'])
                    switch['resolved']=switch['sprite_name'] is not None
            clips.append(dict(name=data['m_Name'],sample_rate=data['m_SampleRate'],
                start=data['m_MuscleClip']['m_StartTime'],stop=data['m_MuscleClip']['m_StopTime'],
                loop=data['m_MuscleClip']['m_LoopTime'],metadata_sha256=hashlib.sha256(raw).hexdigest(),
                timelines=timelines))
        except (KeyError,ValueError) as error:
            clips.append(dict(name=data['m_Name'],unsupported=str(error)))
    return dict(character_id=manifest['character_id'],sources=sources,clips=clips,
                limitations=['Sprite switches only; transforms, anchors, interpolation and effects not reconstructed.',
                             'Dependency sprites can belong to a shared reference character; no automatic appearance substitution.',
                             'Sprite-switch path IDs are strings to preserve 64-bit identity.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extraction',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=_no_symlinks(args.output.absolute())
    if output.exists():parser.error('Output must be new')
    result=inspect(args.extraction,args.source)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(clips=len(result['clips']),unsupported=sum('unsupported' in c for c in result['clips']))))
