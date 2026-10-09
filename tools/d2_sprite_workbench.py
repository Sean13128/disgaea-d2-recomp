#!/usr/bin/env python3
"""Local sprite library, comparison and private-profile import workbench."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs
import uuid
import webbrowser

from PIL import Image
from d2_character_export import anm_pages, characters, indexed_png, nispack
from d2_rpg_map import archive_member
from d2_rpg_template import donor_rectangles, idle_composites
from d2_appearance_add import REPO, local_config, masters, profile_facts

STATIC = Path(__file__).parent / 'sprite_workbench'
REFERENCE = json.loads((Path(__file__).parent/'data/d2_rpg_reference_map.json').read_text())['classes']


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_root(value, kind):
    path = Path(value).expanduser().resolve(strict=True)
    if kind == 'rpg':
        candidates = [path, path/'android', path/'assets/android']
        return next((p for p in candidates if (p/'masters/character').is_file()), None) or fail('Choose the RPG assets/android folder containing masters/character.')
    candidates = [path.parent if path.is_file() else path]
    candidates += [path/'PS3_GAME/USRDIR/Data', path/'USRDIR/Data', path/'Data']
    return next((p for p in candidates if (p/'ANM_HI.dat').is_file() and list(p.glob('START*.dat'))), None) or fail('Choose a D2 Data folder, game folder, or an archive beside START.dat and ANM_HI.dat.')


def fail(message):
    raise ValueError(message)


def integer(value, minimum=1, maximum=1000000):
    if type(value) is not int or not minimum <= value <= maximum:
        fail('Invalid numeric selection')
    return value


def separate_sprite_parts(sprites, composites, store_image):
    """Keep raw components accessible while presenting complete idle figures."""
    poses,parts,complete=[],[],{}
    for item in sprites:
        idle_keys=[(a,item['rectangle_index']) for a in item.get('animations',[]) if a in (6001,6007)] if item.get('block')=='own' else []
        composite_keys=[k for k in idle_keys if k in composites]
        is_part=item.get('match')=='clear' or bool(re.search(r'(?:_|/)(?:hand|cape|scarf|hair|part)(?:[0-9]*$|_)',item['name']))
        if composite_keys:
            parts.append(dict(item,component=True))
            for key in composite_keys:
                picture=composites[key]['image'];url=store_image(picture)
                identity=(key[0],url)
                previous=complete.get(identity)
                if previous is not None and (previous.get('pose') or not item.get('pose')):
                    continue
                name=item.get('pose') or ('wait_front' if key[0]==6001 else 'wait_back')+f'/composed-{key[1]}'
                complete[identity]=dict(item,name=name,url=url,width=picture.width,height=picture.height,
                    composed=True,pieces=composites[key]['pieces'],animations=[key[0]],match=item.get('match') if item.get('pose') else None)
        elif is_part:
            parts.append(dict(item,component=True))
        else:
            poses.append(item)
    return list(complete.values())+poses,parts


class Workbench:
    def __init__(self, workspace=None):
        self.workspace = Path(workspace or REPO/'work/sprite-workbench').resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.media = self.workspace/'media'
        self.media.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.sources = {}
        self.details = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='sprite-workbench')
        self.cancelled = set()
        self.playing = None
        # Shareable costume recipes (no artwork) are written here.
        self.recipes = REPO/'costume-recipes'
        # Costume packs carry the finished artwork; this folder is never tracked by Git.
        self.packs = REPO/'costume-packs'
        saved_jobs=self.workspace/'import-jobs.json'
        if saved_jobs.is_file():
            for job in json.loads(saved_jobs.read_text()):
                if job.get('kind') not in ('import','colors','pack'):continue
                if job.get('status') in ('queued','running'):
                    job.update(status='failed',error='The server restarted before this import completed. Inspect its output before retrying.')
                self.jobs[job['id']]=job
        config = self.workspace/'sources.json'
        if config.is_file():
            for kind, data in json.loads(config.read_text()).items():
                try:
                    root = source_root(data['path'], kind)
                    index = json.loads((self.workspace/f'{kind}-index.json').read_text())
                    self.sources[kind] = dict(path=str(root), index=index)
                except (OSError, ValueError, KeyError):
                    pass

    def image(self, image):
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        content = buffer.getvalue()
        name = hashlib.sha256(content).hexdigest()+'.png'
        path = self.media/name
        if not path.exists():
            path.write_bytes(content)
        return '/media/'+name

    def state(self):
        config = local_config()
        return dict(service='d2-sprite-workbench', sources={k:dict(path=v['path'], count=len(v['index']['characters']), indexed=v['index'].get('indexed')) for k,v in self.sources.items()},
                    jobs=list(self.jobs.values()), defaults=dict(rpg=config.get('rpg_source',''), d2=str(REPO/'Disgaea D2 A Brighter Darkness - [BLUS31313]')),
                    profile=config.get('current_profile'), import_mode='Private profiles; build Choose Color profile to select costumes in-game')

    def save_jobs(self):
        with self.lock:
            path=self.workspace/'import-jobs.json'
            temporary=path.with_suffix('.json.new')
            temporary.write_text(json.dumps([j for j in self.jobs.values() if j['kind'] in ('import','colors','pack')],indent=2,ensure_ascii=False))
            temporary.replace(path)

    def submit(self, kind, label, function):
        job_id = uuid.uuid4().hex
        with self.lock:
            job = dict(id=job_id, kind=kind, label=label, status='queued', progress='Waiting', created=time.time())
            self.jobs[job_id] = job
            if kind in ('import','colors','pack'):self.save_jobs()
        def execute():
            with self.lock:
                if job_id in self.cancelled:
                    job.update(status='cancelled', progress='Cancelled before starting')
                    if kind in ('import','colors','pack'):self.save_jobs()
                    return
                job.update(status='running', progress=label)
            try:
                result = function(job)
                job.update(status='complete', progress='Complete', result=result)
            except BaseException as error:
                job.update(status='failed', progress='Failed', error=str(error) or type(error).__name__)
            finally:
                if kind in ('import','colors','pack'):self.save_jobs()
        self.pool.submit(execute)
        return dict(job=job_id)

    def index(self, kind, value):
        if kind not in ('rpg','d2'):
            fail('Unknown library')
        root = source_root(value, kind)
        def build(job):
            if kind == 'rpg':
                rows = masters(root, 'character')
                names = masters(root, 'storycharacter')
                characters_out = []
                for row in rows:
                    rid = row['id']
                    missing = [f for f in (f'prefabs/characters/{rid}',f'atlas/chara/battle/front/front{rid}',f'atlas/chara/battle/back/back{rid}',f'atlas/chara/battle/wait_front/front{rid}',f'atlas/chara/battle/wait_back/back{rid}') if not (root/f).is_file()]
                    characters_out.append(dict(id=rid, name=row['name'], subtitle=row.get('class_name_1',''), available=not missing, missing=missing, description=row.get('description','')))
                index = dict(characters=characters_out, stories=[dict(id=r['id'], name=r['name'], img_base=r['img_base'], available=(root/f"atlas/chara/story/{r['img_base']}").is_file()) for r in names], master_sha256=fingerprint(root/'masters/character'))
            else:
                candidates = sorted(root.glob('START*.dat'))
                chosen = None
                for archive in candidates:
                    job['progress'] = 'Reading '+archive.name
                    with archive.open('rb') as stream:
                        members = nispack(stream, archive.stat().st_size)
                        char = next((r for r in members if r['name']=='char.dat'),None)
                        if char:
                            stream.seek(char['offset'])
                            raw = stream.read(char['size'])
                            chosen = (archive,raw)
                            break
                if chosen is None:
                    fail('No char.dat found in the D2 START archives')
                with (root/'ANM_HI.dat').open('rb') as stream:
                    members = nispack(stream, (root/'ANM_HI.dat').stat().st_size)
                names = {r['name'] for r in members}
                index = dict(characters=[dict(id=r['id'], name=r['name'] or f"Unnamed class {r['id']}", subtitle=r['name_230'], body=r['body_animation_ids'][0],
                    available=f"anm{r['body_animation_ids'][0]:05d}.lzs" in names, supported=str(r['id']) in REFERENCE,
                    note=REFERENCE.get(str(r['id']),{}).get('note',''), reference=REFERENCE.get(str(r['id']),{}).get('rpg_character')) for r in characters(chosen[1])],
                    table_archive=chosen[0].name, table_sha256=hashlib.sha256(chosen[1]).hexdigest(), archives=[dict(name=p.name, bytes=p.stat().st_size) for p in root.glob('*.dat')])
            index.update(path=str(root), indexed=time.time())
            with self.lock:
                (self.workspace/f'{kind}-index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2))
                self.sources[kind] = dict(path=str(root), index=index)
                self.details = {k:v for k,v in self.details.items() if k[0]!=kind}
                (self.workspace/'sources.json').write_text(json.dumps({k:dict(path=v['path']) for k,v in self.sources.items()},indent=2))
            return dict(count=len(index['characters']), path=str(root))
        return self.submit('index', 'Index '+('Disgaea RPG' if kind=='rpg' else 'Disgaea D2'), build)

    def library(self, kind):
        if kind not in self.sources:
            return dict(characters=[], stories=[])
        return self.sources[kind]['index']

    def row(self, kind, ident):
        integer(ident)
        row = next((r for r in self.library(kind)['characters'] if r['id']==ident),None)
        if row is None:
            fail('Character not found in the indexed library')
        return row

    def preview(self, kind, ident, palette=0):
        row = self.row(kind, ident)
        integer(palette,0,255)
        root = Path(self.sources[kind]['path'])
        key = (kind, str(root), ident, palette)
        def build(job):
            if key in self.details:
                return self.details[key]
            job['progress'] = 'Decoding '+row['name']
            if kind=='rpg':
                import UnityPy
                items, atlases = [], []
                signature = fingerprint(root/'masters/character')
                for facing in ('front','back','wait_front','wait_back'):
                    prefix = facing.removeprefix('wait_')
                    path = root/f'atlas/chara/battle/{facing}/{prefix}{ident}'
                    if not path.is_file():
                        continue
                    env = UnityPy.load(path.read_bytes())
                    for obj in env.objects:
                        if obj.type.name not in ('Sprite','Texture2D'):
                            continue
                        try:
                            data = obj.parse_as_object()
                            im = data.image.convert('RGBA')
                            item = dict(name=facing+'/'+data.m_Name, url=self.image(im), width=im.width, height=im.height, facing=facing)
                            (items if obj.type.name=='Sprite' else atlases).append(item)
                        except Exception as error:
                            job['progress'] = 'Some images could not decode: '+str(error)[:120]
                items.sort(key=lambda r:(not any(s in r['name'] for s in ('/stand','/wait01')),r['name']))
                parts=[r for r in items if re.search(r'_hand[0-9]*$',r['name'])]
                items=[r for r in items if r not in parts]
                result=dict(id=ident, name=row['name'], sprites=items, parts=parts, atlases=atlases, palettes=1, source_signature=signature)
            else:
                raw = archive_member(root/'ANM_HI.dat', f"anm{row['body']:05d}.lzs")
                pages = anm_pages(raw, include_rgba=False, palette_indices=[palette])
                atlases = [dict(name=f"Atlas {p['texture']} · palette {palette}",url=self.image(Image.open(io.BytesIO(indexed_png(p['width'],p['height'],p['indices'],p['colors']))).convert('RGBA')),width=p['width'],height=p['height']) for p in pages]
                # Existing rectangle reader owns the format interpretation. Replace
                # palette-zero crops with the selected palette at the same bounds.
                common = archive_member(root/'ANM_HI.dat','anm00001.lzs')
                regions, skipped = donor_rectangles(raw,common,row['body'])
                selected_pages = {p['texture']:Image.open(io.BytesIO(indexed_png(p['width'],p['height'],p['indices'],p['colors']))).convert('RGBA') for p in pages}
                sprites=[]
                template_path=REPO/'work/appearance-templates'/f"template-{row['body']:05d}.json"
                template=json.loads(template_path.read_text()) if template_path.is_file() else {}
                mappings = {(e['block'],e['rectangle_index']):e for e in template.get('entries',[]) } if template.get('donor_sha256')==hashlib.sha256(raw).hexdigest() else {}
                for region, original in regions:
                    x,y,w,h=region['destination']; mapping=mappings.get((region['block'],region['rectangle_index']),{})
                    name=mapping.get('pose') or f"{region['block']} region {region['rectangle_index']}"
                    sprites.append(dict(name=name, url=self.image(selected_pages[region['page']].crop((x,y,x+w,y+h))),width=w,height=h,
                                        **region, match=mapping.get('match'), pose=mapping.get('pose')))
                sprites.sort(key=lambda r:(not any(a in (6001,6007) for a in r['animations']),r['block'],r['rectangle_index']))
                sprites,parts=separate_sprite_parts(sprites,idle_composites(raw,row['body'],palette),self.image)
                import struct
                result=dict(id=ident,name=row['name'],sprites=sprites,parts=parts,atlases=atlases,palettes=struct.unpack_from('>I',raw,12)[0], skipped=len(skipped),
                    body=row['body'], supported=row['supported'], note=row.get('note',''), source_signature=hashlib.sha256(raw).hexdigest())
            if not result['sprites'] and not result['atlases']:
                fail('No decodable sprites or atlases for this character')
            with self.lock:
                self.details[key]=result
            return result
        return self.submit('preview','Load '+row['name'],build)

    def story(self, ident):
        integer(ident)
        root=Path(self.sources['rpg']['path'])
        row=next((r for r in self.library('rpg')['stories'] if r['id']==ident),None)
        if not row:
            fail('Unknown story illustration')
        def build(job):
            import UnityPy
            env=UnityPy.load((root/f"atlas/chara/story/{row['img_base']}").read_bytes())
            sprites=[]
            for obj in env.objects:
                if obj.type.name=='Sprite':
                    data=obj.parse_as_object(); im=data.image.convert('RGBA')
                    sprites.append(dict(name=data.m_Name,url=self.image(im),width=im.width,height=im.height))
            return dict(id=ident,name=row['name'],sprites=sprites)
        return self.submit('story','Load story art',build)

    def prepare_import(self, data):
        rpg=self.row('rpg',integer(data.get('rpg')))
        d2=self.row('d2',integer(data.get('d2')))
        if not rpg['available']:
            fail('This RPG character is missing required battle assets')
        if not d2['supported']:
            fail('This D2 character can be browsed, but its importer is not supported yet')
        profile=data.get('profile') or local_config().get('current_profile') or 'new'
        if profile!='new':
            profile=str(Path(profile).expanduser().resolve(strict=True))
        facts=profile_facts(None if profile=='new' else Path(profile),d2['id'])
        selected=archive_member(Path(self.sources['d2']['path'])/'ANM_HI.dat', f"anm{d2['body']:05d}.lzs")
        expected=archive_member(facts['content']/'ANM_HI.dat', f"anm{facts['body']:05d}.lzs")
        if d2['body']!=facts['body'] or hashlib.sha256(selected).digest()!=hashlib.sha256(expected).digest():
            fail('The selected D2 body differs from the profile donor. Browse it here, but use matching project game assets for import.')
        name=str(data.get('name') or rpg['name']).strip()
        if not name or len(name)>100 or any(ord(c)<32 for c in name):
            fail('Give the costume a name of 1–100 characters')
        story=data.get('story')
        if story is not None:
            integer(story)
            if not any(r['id']==story and r['available'] for r in self.library('rpg')['stories']):
                fail('Choose a story illustration from this RPG library')
        return dict(rpg=rpg['id'],d2=d2['id'],name=name,story=story,profile=profile,rpg_source=self.sources['rpg']['path'],d2_name=d2['name'])

    def use_import(self, job_id):
        with self.lock:
            job=self.jobs.get(job_id)
            if not job or job['kind'] not in ('import','colors','pack') or job['status']!='complete':
                fail('Select a completed import first')
            result=dict(job['result'])
        from d2_appearance_choice import select
        if job['kind']=='import':
            select(Path(result['profile']),True,result['class_id'],result['costume_id'])
        from d2_appearance_add import remember
        remember(current_profile=result['profile'])
        return dict(profile=result['profile'],selected=True)

    def play_import(self, job_id):
        if self.playing is not None and self.playing.poll() is None:
            fail('A workbench playtest is already running. Close it before launching another.')
        selection=self.use_import(job_id)
        profile=Path(selection['profile'])
        from d2_appearance_run import validate_profile
        runner=REPO/'port/build-rpg-import/DisgaeaD2Recomp'
        elf=REPO/'work/v140/EBOOT.elf'
        validate_profile(profile,runner,elf)
        sessions=profile.parent/'play-sessions';sessions.mkdir(exist_ok=True)
        output=sessions/('studio-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
        log=self.workspace/('play-'+output.name+'.log')
        with log.open('w') as stream:
            self.playing=subprocess.Popen([sys.executable,str(REPO/'tools/d2_appearance_play.py'),
                '--stage',str(profile),'--runner',str(runner),'--elf',str(elf),'--output',str(output)],
                stdout=stream,stderr=subprocess.STDOUT)
        return dict(pid=self.playing.pid,profile=str(profile),log=str(log),session=str(output))

    def export_recipe(self, job_id, reveal=False, art=False):
        """Write a costume recipe, or with art a costume pack, for a completed import.

        A recipe names the costumes and import choices only; it holds no
        artwork, game data or local paths, so it can be shared anywhere. A
        pack also carries the finished artwork so the receiver only imports
        it; packs are for private exchange and stay out of Git.
        """
        import d2_costume_recipe as recipes
        with self.lock:
            job=self.jobs.get(job_id)
            if not job or job['kind'] not in ('import','colors','pack') or job['status']!='complete':
                fail('Select a completed import first')
            profile=Path(job['result']['profile'])
            rpg=self.sources.get('rpg')
            source=rpg['path'] if rpg else local_config().get('rpg_source')
            bases={r['id']:r['img_base'] for r in rpg['index'].get('stories',[])} if rpg else None
        if not profile.is_file():
            fail('That profile no longer exists')
        if art:
            import d2_costume_pack as packs
            path=packs.unused_path(self.packs,packs.default_name(profile))
            report=packs.export_pack(profile,path,None,False,source)
            if reveal:subprocess.run(['/usr/bin/open','-R',str(path)],check=False)
            return dict(path=str(path),file=path.name,name=report['name'],count=len(report['costumes']),costumes=report['costumes'],
                        skipped=0,art=True,bytes=report['bytes'])
        data=json.loads(profile.read_text())
        classes={c['class_id'] for c in data.get('costumes',data.get('appearances',[])) if isinstance(c,dict) and type(c.get('class_id')) is int}
        recipe,skipped=recipes.export_recipe(profile,None,source,bases,recipes.d2_body_fingerprints(profile,classes))
        path=recipes.write(recipe,recipes.unused_path(self.recipes,recipe['name']))
        if reveal:
            # Show the saved file; only ever requested by the Export button.
            subprocess.run(['/usr/bin/open','-R',str(path)],check=False)
        return dict(path=str(path),file=path.name,name=recipe['name'],count=len(recipe['costumes']),
                    costumes=[f"{c['display_name']} → {c['character']}" for c in recipe['costumes']],
                    skipped=len(skipped),fingerprints=sum('sources' in c for c in recipe['costumes']))

    def import_file(self, path=None, choose=False):
        """Queue the import of a costume pack (with art) or recipe (rebuilt here).

        The costumes are added to the profile in use, in a new private
        profile; nothing existing is modified.
        """
        if choose:
            # Native chooser opened only by an explicit button press.
            script='POSIX path of (choose file with prompt "Choose a costume pack or recipe")'
            picker=subprocess.run(['/usr/bin/osascript','-e',script],text=True,capture_output=True)
            if picker.returncode:fail('File selection cancelled')
            path=picker.stdout.strip()
        if not isinstance(path,str) or not path:fail('Choose a costume pack or recipe file')
        source=Path(path).expanduser().resolve()
        if not source.is_file() or not source.name.endswith(('.d2costumepack','.d2costume.json')):
            fail('Choose a .d2costumepack or .d2costume.json file')
        job_id=uuid.uuid4().hex[:8]
        log=self.workspace/('import-file-'+job_id+'.log');answer=self.workspace/('import-file-'+job_id+'.json')
        command=[sys.executable,str(REPO/'tools/d2_appearance_add.py'),'import',str(source)]
        rpg=self.sources.get('rpg')
        if rpg and source.name.endswith('.d2costume.json'):command+=['--rpg-source',rpg['path']]
        def build(job):
            job['progress']='Adding costumes to a new private profile; checking every file'
            env=dict(os.environ,TMPDIR=str(self.workspace/'tmp'));Path(env['TMPDIR']).mkdir(exist_ok=True)
            with log.open('w') as errors,answer.open('w') as output:
                result=subprocess.run(command,stdout=output,stderr=errors,env=env)
            if result.returncode:
                fail(log.read_text(errors='replace')[-2000:].strip() or 'Import failed')
            report=json.loads(answer.read_text())
            return dict(profile=report['profile'],name=report['name'],file=source.name,
                        costumes=[f"{c['display_name']} → {c['character']}" for c in report['costumes']],
                        slots=report.get('slots'),skipped=len(report.get('skipped',[])),
                        different_sources=report.get('different_sources',[]),log=str(log))
        return self.submit('pack','Import '+source.name,build)

    def color_profile(self, job_id):
        with self.lock:
            source=self.jobs.get(job_id)
            if not source or source['kind']!='import' or source['status']!='complete':
                fail('Select a completed import first')
            profile=Path(source['result']['profile'])
        output=REPO/'work/appearance-profiles'/('colors-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        def build(job):
            from d2_appearance_colors import build as build_colors
            job['progress']='Copying private assets and saves; assigning native color choices'
            return build_colors(profile,output)
        return self.submit('colors','Build Choose Color profile',build)

    def import_costume(self, data):
        selection=self.prepare_import(data)
        job_id=uuid.uuid4().hex[:8]
        output=REPO/'work/appearance-profiles'/('studio-'+time.strftime('%Y%m%d-%H%M%S')+'-'+job_id)
        log=self.workspace/('import-'+job_id+'.log')
        command=[sys.executable,str(REPO/'tools/d2_appearance_add.py'),'add','--profile',selection['profile'],'--output',str(output),
                 '--class-id',str(selection['d2']),'--rpg-character',str(selection['rpg']),'--rpg-source',selection['rpg_source'],'--display-name',selection['name']]
        if selection['story'] is not None:
            command+=['--story-character',str(selection['story'])]
        # Building a costume does not automatically change another character's selection.
        def build(job):
            # Default queue entries extend the result of the preceding import.
            if not data.get('profile'):
                command[command.index('--profile')+1]=str(local_config().get('current_profile') or 'new')
            job['progress']='Building body, icon and illustration; validating with the game decoder'
            env=dict(os.environ,TMPDIR=str(self.workspace/'tmp'));Path(env['TMPDIR']).mkdir(exist_ok=True)
            with log.open('w') as stream:
                result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,env=env)
            if result.returncode:
                fail(log.read_text(errors='replace')[-4000:])
            evidence=next(p for p in (output/'costumes').glob(f"{selection['d2']}-*/added.json") if json.loads(p.read_text())['rpg_character']==selection['rpg'] and json.loads(p.read_text())['display_name']==selection['name'])
            report=json.loads(evidence.read_text())
            review=self.image(Image.open(evidence.parent/'review.png'))
            return dict(profile=str(output/'stage.json'),name=selection['name'],character=selection['d2_name'],class_id=selection['d2'],review=review,
                        body=report['body'],face=self.image(Image.open(evidence.parent/'face.png')) if (evidence.parent/'face.png').is_file() else None,
                        illustration=self.image(Image.open(evidence.parent/'illustration.png')) if (evidence.parent/'illustration.png').is_file() else None,
                        selected=report['selected'],costume_id=report['costume_id'],log=str(log),
                        color_slot=report.get('color_slot'),color_note=report.get('color_note'))
        return self.submit('import','Import '+selection['name']+' → '+selection['d2_name'],build)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self,status,value,content_type='application/json'):
        payload=json.dumps(value,ensure_ascii=False).encode() if content_type=='application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('X-Content-Type-Options','nosniff')
        # Content-addressed media may be cached; the page and its script must
        # always be current, or buttons added by an update stay invisible.
        self.send_header('Cache-Control','no-store' if content_type=='application/json' else 'private, max-age=3600' if content_type=='image/png' else 'no-cache')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self, mutation=False):
        address=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host')!=address:
            return False
        if mutation:
            return self.headers.get('Origin')=='http://'+address and self.headers.get('X-Workbench')=='1'
        return True

    def do_GET(self):
        if not self.allowed():
            return self.reply(403,dict(error='Invalid local host'))
        url=urlparse(self.path);query=parse_qs(url.query)
        app=self.server.app
        try:
            if url.path=='/api/state':
                with app.lock:return self.reply(200,app.state())
            if url.path=='/api/library':
                with app.lock:return self.reply(200,app.library(query.get('kind',[''])[0]))
            if re.fullmatch(r'/media/[a-f0-9]{64}\.png',url.path):
                return self.reply(200,(app.media/url.path.rsplit('/',1)[1]).read_bytes(),'image/png')
            names={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if url.path in names:
                name=names[url.path];mime={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.rsplit('.',1)[1]]
                return self.reply(200,(STATIC/name).read_bytes(),mime)
            self.reply(404,dict(error='Not found'))
        except (OSError,ValueError,KeyError) as error:
            self.reply(400,dict(error=str(error)))

    def do_POST(self):
        if not self.allowed(True):
            return self.reply(403,dict(error='Requests must come from this local workbench'))
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:
                fail('Invalid request size')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                fail('Expected a request object')
            app=self.server.app
            if self.path=='/api/index':
                result=app.index(data.get('kind'),data.get('path',''))
            elif self.path=='/api/preview':
                result=app.preview(data.get('kind'),data.get('id'),data.get('palette',0))
            elif self.path=='/api/story':
                result=app.story(data.get('id'))
            elif self.path=='/api/import':
                result=app.import_costume(data)
            elif self.path=='/api/colors':
                result=app.color_profile(data.get('job'))
            elif self.path=='/api/export':
                result=app.export_recipe(data.get('job'),data.get('reveal') is True,data.get('art') is True)
            elif self.path=='/api/import-file':
                result=app.import_file(data.get('path'),data.get('choose') is True)
            elif self.path=='/api/use':
                result=app.use_import(data.get('job'))
            elif self.path=='/api/play':
                result=app.play_import(data.get('job'))
            elif self.path=='/api/cancel':
                with app.lock:
                    job=app.jobs.get(data.get('job'))
                    if not job or job['status']!='queued':
                        fail('Only waiting jobs can be cancelled')
                    app.cancelled.add(job['id']);result=dict(cancelled=True)
            elif self.path=='/api/browse':
                # Native chooser opened only by an explicit button press.
                script='POSIX path of (choose folder with prompt "Choose the asset folder")'
                picker=subprocess.run(['/usr/bin/osascript','-e',script],text=True,capture_output=True)
                if picker.returncode:fail('Folder selection cancelled')
                result=dict(path=picker.stdout.strip())
            else:
                return self.reply(404,dict(error='Not found'))
            self.reply(200,result)
        except (ValueError,KeyError,OSError,TypeError,SystemExit,subprocess.SubprocessError) as error:
            self.reply(400,dict(error=str(error)))


def create_server(app,port=0):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.app=app
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--workspace',type=Path)
    args=parser.parse_args()
    app=Workbench(args.workspace)
    # Reopening the launcher reuses the running local GUI and its import queue.
    record=app.workspace/'server.json'
    if not args.no_open and record.is_file():
        try:
            from urllib.request import urlopen
            saved=json.loads(record.read_text())
            parsed=urlparse(saved['url'])
            if parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port:
                with urlopen(saved['url']+'/api/state',timeout=1) as response:
                    current=json.load(response)
                if current.get('service')=='d2-sprite-workbench':
                    webbrowser.open(saved['url']);app.pool.shutdown(wait=False);return
        except (OSError,ValueError,KeyError):
            pass
    server=create_server(app,args.port)
    url=f'http://127.0.0.1:{server.server_port}'
    (app.workspace/'server.json').write_text(json.dumps(dict(url=url,pid=os.getpid())))
    print('Sprite Workbench: '+url,flush=True)
    if not args.no_open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close();app.pool.shutdown(wait=True)

if __name__=='__main__':main()
