#!/usr/bin/env python3
"""Summarize observed native resource usage without claiming rendered coverage.

Load requests, bank state, texture binding and model selections are separate
observations. A bound texture is not proof that every frame was displayed.
"""
import argparse
import json
from pathlib import Path
import re

from d2_anm import parse_anm
from d2_character_export import _no_symlinks
from d2_rpg_map import archive_member

MAX_LOG_BYTES=64*1024*1024
FIELDS=re.compile(r'([a-z_]+)=([^\s]+)')


def summarize(log,resource,metadata=None):
    if type(resource) is not int or not 0<resource<100000:raise ValueError('Expected a positive five-digit file ID')
    if len(log.encode('utf-8'))>MAX_LOG_BYTES:raise ValueError('Trace log exceeds64MiB')
    member=f'anm{resource:05d}.lzs';observations=[];models=set();frame=None
    tags=set();tag_resource_matched=False
    if metadata is not None:
        for block in metadata['blocks']:
            if block['resource_id']==resource:
                tag_resource_matched=True;tags.update(t[0] for t in block['tables']['tags']['records'])
    for line_no,line in enumerate(log.splitlines(),1):
        capture=re.search(r'captured frame (\d+)',line)
        if capture:frame=int(capture[1])
        marker='[D2 appearance] '
        if marker not in line:continue
        message=line.split(marker,1)[1];fields=dict(FIELDS.findall(message));kind=message.split(' ',1)[0]
        if kind.startswith('manager='):kind='bank-state'
        def decimal(key):
            try:return int(fields.get(key,''),10)
            except ValueError:return None
        wanted=False
        if kind in ('request','bank-state','illustration','face_cell'):wanted=decimal('resource')==resource
        elif kind in ('file_size','file_read'):wanted=fields.get('name')==member
        elif kind=='texture_bind':
            wanted=decimal('resource')==resource
            if wanted:models.add(fields.get('model'))
        elif kind=='model_select':
            wanted=decimal('library')==resource or fields.get('model') in models
            if decimal('library')==resource:models.add(fields.get('model'))
        if not wanted:continue
        event=dict(line=line_no,kind=kind,previous_capture_frame=frame,fields=fields)
        if kind=='model_select':
            event['library_matches_target_resource']=decimal('library')==resource
            event['variant_present_in_supplied_resource']=decimal('variant') in tags if tag_resource_matched and decimal('library')==resource else None
            event['association']='Model selects the target library or was previously observed using it; lifetime/reuse is not established'
        observations.append(event)
    kinds={event['kind'] for event in observations}
    return dict(resource=resource,member=member,requests_observed='request' in kinds,
        illustration_routing_observed='illustration' in kinds,face_routing_observed='face_cell' in kinds,file_read_observed='file_read' in kinds,bank_states_observed='bank-state' in kinds,
        texture_binding_observed='texture_bind' in kinds,library_selection_observed=any(e['kind']=='model_select' and e['fields'].get('library')==str(resource) for e in observations),observed_models=sorted(m for m in models if m),
        animation_tags=sorted(tags) if tag_resource_matched else None,container_resource_ids=[b['resource_id'] for b in metadata['blocks']] if metadata else None,
        metadata_resource_matches_filter=tag_resource_matched if metadata else None,observations=observations,
        rendered_coverage_validated=False,
        limits='Ordered trace observations only. Capture references identify the preceding logged capture, not an exact event time. Model reuse and visible output require native capture review.')


def inspect(run,resource=None,archive=None,member=None):
    run=_no_symlinks(Path(run).absolute());path=_no_symlinks(run/'runtime.log')
    if path.stat().st_size>MAX_LOG_BYTES:raise ValueError('Trace log exceeds64MiB')
    result_path=_no_symlinks(run/'result.json')
    if result_path.exists() and result_path.stat().st_size>1024*1024:raise ValueError('Run result exceeds1MiB')
    result=json.loads(result_path.read_text()) if result_path.exists() else {}
    if resource is None:resource=result.get('trace_resource')
    if resource is None:raise ValueError('Supply an explicit resource for a run without recorded trace selection')
    metadata=None
    if archive is not None:
        if type(resource) is not int or not 0<resource<100000:raise ValueError('Expected a positive five-digit file ID')
        if member is not None and member!=f'anm{resource:05d}.lzs':raise ValueError('Resource/member mismatch')
        metadata=parse_anm(archive_member(archive,f'anm{resource:05d}.lzs'))
        # A compound file can contain several distinct animation-block IDs.
        # Retain those IDs without interpreting them as the external file ID.
    elif member is not None:raise ValueError('Member requires an archive')
    report=summarize(path.read_text(),resource,metadata)
    report.update(run=str(run),process_result=result or None,metadata_sha256=metadata['sha256'] if metadata else None)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--resource',type=int)
    parser.add_argument('--archive',type=Path);parser.add_argument('--member')
    parser.add_argument('--output',type=Path)
    args=vars(parser.parse_args());output=args.pop('output');report=inspect(**args)
    serialized=json.dumps(report,indent=2)+'\n'
    if output is not None:
        output=_no_symlinks(output.absolute())
        with output.open('x') as stream:stream.write(serialized)
    else:print(serialized,end='')
