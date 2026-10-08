#!/usr/bin/env python3
"""Launch a staged appearance for ordinary play with keyboard/controller input.

Requires the importer-enabled1.40 research runner. Uses private saves/caches
and an immutable manifest snapshot. No stage warp or frame dumping by default.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from d2_appearance_run import validate_profile, profile_lock


def environment(data, roots, slot, output, profile, pad_script=None,choice_path=None,session_only=False):
    env=dict(os.environ,**roots)
    for key in list(env):
        if key.startswith('D2_CHEATS_TEST_') or key in (
            'D2_APPEARANCE_PERSIST','D2_APPEARANCE_PERSIST_PATH','D2_WARP_DELAY_SECONDS','D2_APPEARANCE_TEST_SEQUENCE','D2_CHEATS_UI_OPEN','D2_WARP_STAGE','D2_WARP_TRACE','D2_HUB_CHARACTER','D2_APPEARANCE_TRACE','PAD_FILE',
            'PAD_SCRIPT','PAD_NO_KEYBOARD','PS3RECOMP_METAL_HEADLESS',
            'PS3RECOMP_METAL_FRAME_DUMP','PS3RECOMP_METAL_FRAME_DUMP_EVERY',
            'SDL_AUDIODRIVER','D2_MOVIE_SKIP'):
            env.pop(key)
    env.update(D2_SETTINGS_PATH=str(profile/'appearance-settings.json'),
               D2_CHEATS_PRESET_DIR=str(profile/'appearance-presets'),
               D2_APPEARANCE_MANIFEST=str(output/'stage-snapshot.json'),
               D2_APPEARANCE_PERSIST='0' if session_only else '1',
               D2_APPEARANCE_PERSIST_PATH=str(choice_path or profile/'stage.json'),
               PS3_SAVEDATA_DIR=slot,PS3_SAVEDATA_UI='headless',
               PS3_TITLE='Disgaea D2 — RPG appearance private profile')
    if pad_script:env['PAD_SCRIPT']=pad_script
    return env


def play(stage,runner,elf,output,duration=None,pad_script=None,session_only=False):
    stage,*_=validate_profile(stage,runner,elf)
    with profile_lock(stage) as descriptor:
        return _play(stage,runner,elf,output,duration,pad_script,descriptor,session_only)


def _play(stage,runner,elf,output,duration=None,pad_script=None,lock_fd=None,session_only=False):
    stage,data,roots,slot,elf,runner=validate_profile(stage,runner,elf)
    entries=data.get('appearances',[data])
    if not isinstance(entries,list) or not entries or any(
        not isinstance(e,dict) or e.get('selection_mode')!='renderer-only' or not e.get('visual_class_id')
        for e in entries):
        raise ValueError('Normal play requires renderer-only visual bindings')
    if duration is not None and (type(duration) is not int or not 1<=duration<=600):
        raise ValueError('Optional smoke-test duration must be1..600 seconds')
    output=Path(output).absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError('Output must be new with an existing independent parent')
    for root in roots.values():
        if Path(root) in output.parents:raise ValueError('Output overlaps runtime content/save/cache')
    output.mkdir()
    snapshot=output/'stage-snapshot.json';snapshot.write_text(json.dumps(data,indent=2)+'\n')
    env=environment(data,roots,slot,output,stage.parent,pad_script,stage,session_only)
    started=time.time();timed=False
    with (output/'runtime.log').open('w') as log:
        proc=subprocess.Popen([str(runner),str(elf)],env=env,stdout=log,stderr=subprocess.STDOUT,
                              pass_fds=() if lock_fd is None else (lock_fd,))
        (output/'process.json').write_text(json.dumps(dict(pid=proc.pid,started=started,stage=str(stage))))
        try:
            code=proc.wait(timeout=duration)
        except (subprocess.TimeoutExpired,KeyboardInterrupt) as error:
            timed=isinstance(error,subprocess.TimeoutExpired);proc.terminate()
            try:code=proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();code=proc.wait()
    result=dict(exit_code=code,intentional_timeout=timed,elapsed=time.time()-started,
                manifest_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                stage=str(stage),runner=str(runner),private_save_slot=slot,
                controls='Normal keyboard/controller; optional explicit pad script',
                choice_persistence='Session only' if session_only else 'Private manifest; concurrent choice changes preserved',
                gameplay_validated=False)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('stage','runner','elf','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--duration',type=int,help='Optional bounded smoke test; omitted waits for player to quit')
    parser.add_argument('--pad-script',help='Optional explicit automation; ordinary play has no scripted input')
    parser.add_argument('--session-only',action='store_true',help='Keep menu choices temporary instead of remembering them')
    args=parser.parse_args();print(json.dumps(play(**vars(args)),indent=2))
