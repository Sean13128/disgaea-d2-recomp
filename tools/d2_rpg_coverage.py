#!/usr/bin/env python3
"""Compare resolved RPG sprite timelines with explicitly selected pose maps.

Source-animation sprite coverage is separate from native D2 action coverage.
"""
import argparse
import json
from pathlib import Path

from d2_character_export import _no_symlinks
from d2_rpg_map import read, sha


def coverage(timelines, poses):
    families={}
    allowed={'front','back','wait_front','wait_back'}
    for source in timelines['sources']:
        path=Path(source['path']);family=path.parent.name if path.parent.name in allowed else None
        for name in source['serialized_files']:
            if name in families and families[name]!=family:
                raise ValueError('Ambiguous serialized-file sprite family')
            families[name]=family
    clips=[];required=set();unclassified=[]
    for clip in timelines['clips']:
        needed=set();unknown=[]
        if 'unsupported' in clip:
            clips.append(dict(name=clip['name'],unsupported=clip['unsupported']));continue
        for timeline in clip['timelines']:
            for switch in timeline['switches']:
                family=families.get(switch['serialized_file'])
                if not switch['resolved'] or not family:
                    unknown.append(switch);continue
                needed.add(family+'/'+switch['sprite_name'])
        required.update(needed);unclassified.extend(unknown)
        clips.append(dict(name=clip['name'],required_poses=sorted(needed),
                          mapped_poses=sorted(needed & poses),missing_poses=sorted(needed-poses),
                          unclassified_switches=unknown))
    return dict(scope='RPG source sprite references; not native D2 action/facing/attachment acceptance',
                unsupported_clips=[c['name'] for c in clips if 'unsupported' in c],
                required_poses=sorted(required),mapped_poses=sorted(required & poses),
                missing_poses=sorted(required-poses),unclassified_switches=len(unclassified),
                selected_poses_not_referenced=sorted(poses-required),clips=clips,gameplay_validated=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timelines',type=Path,required=True)
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=_no_symlinks(args.output.absolute())
    if output.exists():parser.error('Output must be new')
    raw=read(args.composition);config=json.loads(raw)
    if config.get('schema')!=1 or config.get('mode')!='texture-composition':parser.error('Expected reviewed composition')
    evidence=[dict(path=str(args.composition.absolute()),sha256=sha(raw))];poses=set()
    for name in config['mappings']:
        path=Path(name)
        if not path.is_absolute():path=args.composition.absolute().parent/path
        raw=read(path);mapping=json.loads(raw)
        evidence.append(dict(path=str(path.absolute()),sha256=sha(raw)))
        poses.update(e['pose'] for e in mapping['entries'] if e.get('selected') is True)
    raw=read(args.timelines);evidence.append(dict(path=str(args.timelines.absolute()),sha256=sha(raw)))
    report=coverage(json.loads(raw),poses);report['inputs']=evidence
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('missing_poses','unsupported_clips','unclassified_switches','gameplay_validated')}))
