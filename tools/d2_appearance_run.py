#!/usr/bin/env python3
"""Bounded native appearance experiment using explicitly isolated stage roots.

This does not install an appearance. Pass the opt-in 1.40 research runner.
Frames and logs remain in a new output directory for review.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import math
import re
from pathlib import Path
import shutil
import subprocess
import threading
import time

ELF_140_SHA256='0ec183e580a270b0bb1b3a554794a9e4ec2d57a2be251ebdcf81fe21b78d225c'


def validate_profile(stage,runner,elf):
    stage=Path(stage).resolve(strict=True)
    if stage.stat().st_size>1024*1024:raise ValueError('Manifest exceeds 1 MiB')
    data=json.loads(stage.read_text())
    if data.get('mode')!='isolated-runtime-experiment':raise ValueError('Expected an isolated stage manifest')
    roots=data['runtime_environment']
    for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]:
        path=Path(roots[key])
        if path.is_symlink() or path.resolve(strict=True)!=stage.parent/name:
            raise ValueError('Runtime roots must be the independent stage directories')
    slot=data.get('save_patch',{}).get('slot')
    if not slot or '/' in slot or '\\' in slot:raise ValueError('A staged private save slot is required')
    elf=Path(elf).resolve(strict=True);runner=Path(runner).resolve(strict=True)
    if hashlib.sha256(elf.read_bytes()).hexdigest()!=ELF_140_SHA256:raise ValueError('Expected the verified 1.40 ELF')
    return stage,data,roots,slot,elf,runner


@contextmanager
def profile_lock(stage):
    path=Path(stage).parent/'.appearance.lock'
    descriptor=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Private profile is already in use') from None
        yield descriptor
    finally:
        os.close(descriptor)


def parse_live_sequence(sequence,duration,scene):
    if sequence is None:return []
    if scene!='hub':raise ValueError('Live sequence requires hub scene')
    events=[]
    for item in sequence.split(','):
        second,token=item.split(':',1);second=float(second)
        if not math.isfinite(second) or not 0<=second<duration or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',token):
            raise ValueError('Invalid live sequence event')
        events.append(dict(second=second,token='' if token=='original' else token))
    if not 1<=len(events)<=16 or any(b['second']-a['second']<0.5 for a,b in zip(events,events[1:])):
        raise ValueError('Live sequence must contain1..16 ordered events at least half a second apart')
    return events


def run(stage,runner,elf,output,duration=90,frame_every=120,pad_script=None,fresh_cache=False,pad_events=None,scene='battle',hub_character=None,live_sequence=None,persist_choice=False,battle_after=None,trace_resource=None):
    if trace_resource is not None and (type(trace_resource) is not int or not 0<trace_resource<100000):
        raise ValueError('Trace resource requires a positive five-digit file ID')
    if scene not in ('battle','hub','normal'):raise ValueError('Scene must be battle, hub or normal')
    if hub_character is not None and (scene!='hub' or type(hub_character) is not int or not 0<hub_character<32768):
        raise ValueError('Hub character requires hub scene and positive signed-16 class ID')
    if battle_after is not None and (scene!='hub' or type(battle_after) is not int or not 1<=battle_after<duration-10):
        raise ValueError('Delayed battle requires hub scene and1..duration-11 seconds')
    parse_live_sequence(live_sequence,duration,scene)
    stage,*_=validate_profile(stage,runner,elf)
    with profile_lock(stage) as descriptor:
        return _run(stage,runner,elf,output,duration,frame_every,pad_script,fresh_cache,pad_events,descriptor,scene,hub_character,live_sequence,persist_choice,battle_after,trace_resource)


def _run(stage,runner,elf,output,duration=90,frame_every=120,pad_script=None,fresh_cache=False,pad_events=None,lock_fd=None,scene='battle',hub_character=None,live_sequence=None,persist_choice=False,battle_after=None,trace_resource=None):
    stage,data,roots,slot,elf,runner=validate_profile(stage,runner,elf)
    with runner.open('rb') as stream:runner_sha256=hashlib.file_digest(stream,'sha256').hexdigest()
    if not 1<=duration<=600 or not 1<=frame_every<=3600:raise ValueError('Invalid duration or frame interval')
    if trace_resource is not None and (type(trace_resource) is not int or not 0<trace_resource<100000):
        raise ValueError('Trace resource requires a positive five-digit file ID')
    if scene not in ('battle','hub','normal'):raise ValueError('Scene must be battle, hub or normal')
    if hub_character is not None and (scene!='hub' or type(hub_character) is not int or not 0<hub_character<32768):
        raise ValueError('Hub character requires hub scene and positive signed-16 class ID')
    if battle_after is not None and (scene!='hub' or type(battle_after) is not int or not 1<=battle_after<duration-10):
        raise ValueError('Delayed battle requires hub scene and1..duration-11 seconds')
    live_events=parse_live_sequence(live_sequence,duration,scene)
    events=[]
    if pad_events:
        for item in pad_events.split(','):
            second,mask=item.split(':');second=float(second);mask=int(mask,0)
            if not 0<=second<duration or not 0<mask<=0xffff:
                raise ValueError('Pad events must fall within the run and use a 16-bit button mask')
            events.append((second,mask))
        if events!=sorted(events) or any(b[0]-a[0]<0.5 for a,b in zip(events,events[1:])):
            raise ValueError('Pad events must be ordered and at least half a second apart')
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Output must be a new directory')
    if not output.parent.is_dir() or output.parent.is_symlink():raise ValueError('Output parent must exist')
    if any(Path(root) in output.parents for root in roots.values()):
        raise ValueError('Output overlaps runtime content/save/cache')
    # Conservative capture budget: up to120 presents/s and1920x1080 RGB PPM.
    capture_bytes=((duration+5)*120//frame_every+1)*(1920*1080*3+64)
    if shutil.disk_usage(output.parent).free<capture_bytes+2*1024**3:
        raise ValueError('Insufficient free space for requested frame capture budget')
    output.mkdir()
    snapshot=output/'stage-snapshot.json'
    snapshot.write_text(json.dumps(data,indent=2)+'\n')
    # Existing disk caches can shadow rebuilt archives even when file roots
    # are correct. Move only this explicitly staged cache; preserve it for
    # inspection and let the guest rebuild an empty replacement.
    if fresh_cache:
        cache=Path(roots['PS3_HDD1_ROOT'])
        cache.rename(output/'cache-before-run')
        cache.mkdir()
    frames=output/'frames';frames.mkdir();pad=output/'pad.txt';pad.write_text('')
    env=dict(os.environ,**roots)
    for key in list(env):
        if key.startswith('D2_CHEATS_TEST_') or key in ('D2_CHEATS_UI_OPEN','PS3RECOMP_METAL_HEADLESS','D2_WARP_STAGE','D2_WARP_TRACE','D2_HUB_CHARACTER','D2_APPEARANCE_TEST_SEQUENCE','D2_APPEARANCE_PERSIST','D2_APPEARANCE_PERSIST_PATH','D2_WARP_DELAY_SECONDS'):
            env.pop(key)
    env.update(D2_SETTINGS_PATH=str(output/'settings.json'),D2_CHEATS_PRESET_DIR=str(output/'presets'),
        D2_MOVIE_SKIP='1',PS3_SAVEDATA_UI='headless',PS3_SAVEDATA_DIR=slot,SDL_AUDIODRIVER='dummy',
        PAD_NO_KEYBOARD='1',PAD_SCRIPT=pad_script or '10:0x4000,14:0x4000',PAD_FILE=str(pad),
        PS3_TITLE='D2 appearance diagnostic — private profile',D2_APPEARANCE_TRACE=str(data['new_resource'] if trace_resource is None else trace_resource),
        D2_APPEARANCE_MANIFEST=str(snapshot),
        PS3RECOMP_METAL_FRAME_DUMP=str(frames/'f%u.ppm'),PS3RECOMP_METAL_FRAME_DUMP_EVERY=str(frame_every))
    if scene=='normal':env.pop('D2_MOVIE_SKIP',None)
    elif scene=='battle':env['D2_WARP_STAGE']='1'
    else:env['D2_WARP_TRACE']='1'
    if battle_after is not None:env.update(D2_WARP_STAGE='1',D2_WARP_DELAY_SECONDS=str(battle_after))
    if hub_character is not None:env['D2_HUB_CHARACTER']=str(hub_character)
    if persist_choice:env.update(D2_APPEARANCE_PERSIST='1',D2_APPEARANCE_PERSIST_PATH=str(stage))
    if live_events:env['D2_APPEARANCE_TEST_SEQUENCE']=json.dumps(live_events)
    try:
        scripted_times=[float(item.split(':',1)[0]) for item in env['PAD_SCRIPT'].split(',') if item]
        cutoff=max(scripted_times+[e[0] for e in events]+[0])
        if not math.isfinite(cutoff):cutoff=None
    except ValueError:cutoff=None
    (output/'planned-input.json').write_text(json.dumps(dict(pad_script=env['PAD_SCRIPT'],pad_events=events,last_scripted_input=cutoff),indent=2)+'\n')
    start=time.time();clock_start=time.monotonic();timed=False;stop=threading.Event();fired=[]
    def input_events():
        for second,mask in events:
            if stop.wait(max(0,second-(time.monotonic()-clock_start))):break
            # Four-poll presses avoid the repeated menu movement observed
            # with PAD_SCRIPT's 250 ms directional holds.
            if pad.read_text().strip():
                fired.append(dict(requested=second,mask=mask,error='Previous pad command not consumed'))
                break
            pad.write_text(f'0x{mask:04x} 4\n')
            fired.append(dict(requested=second,actual=time.monotonic()-clock_start,mask=mask))
    with (output/'runtime.log').open('w') as log:
        proc=subprocess.Popen([str(runner),str(elf)],env=env,stdout=log,stderr=subprocess.STDOUT,
                              pass_fds=() if lock_fd is None else (lock_fd,))
        (output/'process.json').write_text(json.dumps(dict(pid=proc.pid,started=start,stage=str(stage),runner_sha256=runner_sha256)))
        controller=threading.Thread(target=input_events,daemon=True);controller.start()
        try:code=proc.wait(timeout=duration)
        except subprocess.TimeoutExpired:
            timed=True;proc.terminate()
            try:code=proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();code=proc.wait()
        stop.set();controller.join(timeout=1)
    (output/'pad-events.json').write_text(json.dumps(fired,indent=2)+'\n')
    result=dict(exit_code=code,intentional_timeout=timed,elapsed=time.time()-start,
                gameplay_validated=False,stage=str(stage),runner=str(runner),runner_sha256=runner_sha256,elf_sha256=ELF_140_SHA256,
                manifest_snapshot=str(snapshot),manifest_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                fresh_cache=fresh_cache,scene=scene,hub_character=hub_character,live_sequence=live_events,persist_choice=persist_choice,battle_after=battle_after,trace_resource=int(env['D2_APPEARANCE_TRACE']))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('stage','runner','elf','output'):parser.add_argument('--'+key,required=True,type=Path)
    parser.add_argument('--duration',type=int,default=90)
    parser.add_argument('--frame-every',type=int,default=120)
    parser.add_argument('--pad-script',help='Existing native pad bridge events, seconds:mask separated by commas')
    parser.add_argument('--fresh-cache',action='store_true',help='Preserve the staged cache in the output and rebuild it; required after archive changes')
    parser.add_argument('--pad-events',help='Four-poll PAD_FILE presses at run seconds; e.g. 65:0x4000,67:0x0040,69:0x4000')
    parser.add_argument('--scene',choices=('battle','hub','normal'),default='battle',help='Battle warps to101; hub captures castle with read-only trace; normal uses ordinary startup without warp, leader override or movie skip')
    parser.add_argument('--hub-character',type=int,help='Hub-only diagnostic: native leader setter/actor refresh for one unique saved class; RAM selection only')
    parser.add_argument('--live-sequence',help='Hub-only session switch test: seconds:costume-id,seconds:original')
    parser.add_argument('--persist-choice',action='store_true',help='Explicitly remember tested live choices in the private profile')
    parser.add_argument('--battle-after',type=int,help='Hub-only diagnostic: transition to battle101 after this many launch seconds')
    parser.add_argument('--trace-resource',type=int,help='Read-only resource trace override for secondary/portrait asset investigation; binding remains unchanged')
    args=parser.parse_args()
    print(json.dumps(run(**vars(args)),indent=2))
