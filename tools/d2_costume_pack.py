#!/usr/bin/env python3
"""Costume packs: finished costumes in one file, ready to import.

A pack (``*.d2costumepack``, a zip archive) holds, for every costume, the
converted body animation, the face icon and the Status illustration, plus a
small manifest. Importing a pack needs only a Disgaea D2 game dump: no RPG
assets, no conversion.

    tools/costume export --with-art          # writes costume-packs/<name>.d2costumepack
    tools/costume import some.d2costumepack

Packs contain game artwork. They are for private exchange between people who
own the games; they are never committed to the repository (costume-packs/ is
ignored by Git). Share a costume *recipe* instead when artwork must stay out.

Everything read from a pack is treated as untrusted: member names are derived
from checked IDs, sizes are bounded, fingerprints are verified, and the body
must be the reader's own D2 body with only pixels and cell geometry changed.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import time
import zipfile

import d2_costume_recipe as recipes
from d2_costume_recipe import RecipeError

FORMAT = 'd2-costume-pack'
VERSION = 1
SUFFIX = '.d2costumepack'
NOTE = ('Contains converted game artwork for private use by owners of the games. Import with: '
        'tools/costume import <this file>. Only import packs from people you trust.')
MAX_PACK = 256*1024*1024
MAX_ANM = 48*1024*1024
MAX_FACE = 512*1024
MAX_MANIFEST = 1024*1024
FACE = 96
# Tables a costume build may change, compared with the reader's own body.
GEOMETRY = ('rectangle_candidates', 'anchor_candidates', 'keys')


def member_name(item, kind):
    """Archive member for one costume file; built from checked IDs only."""
    return 'costumes/%d-%s/%s' % (item['class_id'], item['costume_id'],
                                  dict(body='body.anm', face='face.png', illustration='illustration.anm')[kind])


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def structure_check(donor, body, donor_id):
    """Refuse a body that is not the donor with only art and cell geometry changed.

    Animation tags, tracks, transforms and every other table must be the
    reader's own; rectangles may move or resize inside their page, pivots may
    move, and sprite keys may only be blanked. Raises RecipeError otherwise.
    """
    from d2_anm import parse_anm
    try:
        a, b = parse_anm(donor), parse_anm(body)
    except (ValueError, struct.error, IndexError) as error:
        raise RecipeError('Pack body is not a valid animation file: %s' % error) from None
    if len(a['blocks']) != 1 or len(b['blocks']) != 1 or b['blocks'][0]['resource_id'] != donor_id:
        raise RecipeError('Pack body was not built for this character')
    for key in ('textures', 'palettes', 'texture_table_start', 'payload_start', 'page_sizes'):
        if a[key] != b[key]:
            raise RecipeError('Pack body has a different texture layout than this game\'s character')
    x, y = a['blocks'][0], b['blocks'][0]
    if x['bytes'] != y['bytes'] or x['header_u16'] != y['header_u16'] or donor[:x['offset']] != body[:y['offset']]:
        raise RecipeError('Pack body has different animation tables than this game\'s character')
    pages = {p['texture']: (p['width'], p['height']) for p in a['page_sizes']}
    for name, table in x['tables'].items():
        other = y['tables'][name]
        if (table['offset'], table['count'], table['stride']) != (other['offset'], other['count'], other['stride']):
            raise RecipeError('Pack body has different animation tables than this game\'s character')
        first = donor[table['offset']:table['offset']+table['count']*table['stride']]
        second = body[other['offset']:other['offset']+other['count']*other['stride']]
        if name not in GEOMETRY:
            if first != second:
                raise RecipeError('Pack body changes animation data (%s); only artwork may differ' % name)
            continue
        for row in range(table['count']):
            old = first[row*table['stride']:(row+1)*table['stride']]
            new = second[row*table['stride']:(row+1)*table['stride']]
            if old == new or name == 'anchor_candidates':
                continue
            if name == 'keys':
                before, after = struct.unpack('>6H', old), struct.unpack('>6H', new)
                if before[:2]+before[3:] != after[:2]+after[3:] or after[2] != 0:
                    raise RecipeError('Pack body changes animation keys; only artwork may differ')
            else:
                before, after = struct.unpack('>9H', old), struct.unpack('>9H', new)
                size = pages.get(after[0])
                if before[:4]+before[8:] != after[:4]+after[8:] or size is None or \
                        after[4]+after[6] > size[0] or after[5]+after[7] > size[1]:
                    raise RecipeError('Pack body has a sprite cell outside its texture page')
    # Bytes between the tables and the texture headers must be the donor's too.
    covered = bytearray(x['bytes'])
    for table in x['tables'].values():
        begin = table['relative_offset']
        covered[begin:begin+table['count']*table['stride']] = b'\1'*(table['count']*table['stride'])
    base = x['offset']
    for index, used in enumerate(covered):
        if not used and index >= 6 and donor[base+index] != body[base+index]:
            raise RecipeError('Pack body changes animation data outside the sprite tables')
    if donor[a['texture_table_start']:a['payload_start']] != body[b['texture_table_start']:b['payload_start']]:
        raise RecipeError('Pack body has different texture headers than this game\'s character')


def _validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT:
        raise RecipeError('This is not a costume pack')
    if type(manifest.get('version')) is not int or not 1 <= manifest['version'] <= VERSION:
        raise RecipeError('This pack needs a newer version of the tools')
    costumes = manifest.get('costumes')
    if not isinstance(costumes, list) or not 1 <= len(costumes) <= recipes.MAX_COSTUMES:
        raise RecipeError('A pack holds 1–%d costumes' % recipes.MAX_COSTUMES)
    result, seen, slots = [], set(), set()
    for raw in costumes:
        if not isinstance(raw, dict):
            raise RecipeError('Each costume must be an object')
        item = dict(class_id=recipes._integer(raw.get('class_id'), 'class_id', 1, 32767),
                    character=recipes._label(raw.get('character', 'Class %s' % raw.get('class_id')), 'character'),
                    display_name=recipes._label(raw.get('display_name'), 'display_name'),
                    costume_id=raw.get('costume_id'))
        if not isinstance(item['costume_id'], str) or not recipes.IDENT.fullmatch(item['costume_id']):
            raise RecipeError('costume_id must be a short lowercase name')
        key = (item['class_id'], item['costume_id'])
        if key in seen:
            raise RecipeError('Costume %s is listed twice for class %d' % (key[1], key[0]))
        seen.add(key)
        files = raw.get('files')
        if not isinstance(files, dict) or 'body' not in files or set(files)-{'body', 'face', 'illustration'}:
            raise RecipeError('Each costume needs a body and may have a face and an illustration')
        item['files'] = {}
        for kind, info in files.items():
            if not isinstance(info, dict) or not isinstance(info.get('sha256'), str) or \
                    not re.fullmatch(r'[0-9a-f]{64}', info['sha256']):
                raise RecipeError('Pack file entries need a SHA-256 fingerprint')
            limit = MAX_FACE if kind == 'face' else MAX_ANM
            item['files'][kind] = dict(sha256=info['sha256'], bytes=recipes._integer(info.get('bytes'), 'bytes', 1, limit))
        body = raw.get('d2_body_sha256')
        if not isinstance(body, str) or not re.fullmatch(r'[0-9a-f]{64}', body):
            raise RecipeError('Each costume names the D2 body it was built for')
        item['d2_body_sha256'] = body
        if raw.get('color') is not None:
            item['color'] = recipes._integer(raw['color'], 'color', 1, 4)
            if (item['class_id'], item['color']) in slots:
                raise RecipeError('Two costumes of class %d use Extra color %d' % (item['class_id'], item['color']))
            slots.add((item['class_id'], item['color']))
        item['active'] = raw.get('active') is True
        # Optional provenance: how the costume was made, so it can be re-exported as a recipe.
        if isinstance(raw.get('recipe'), dict):
            try:
                checked = recipes.validate(dict(format=recipes.FORMAT, version=1, costumes=[dict(
                    raw['recipe'], class_id=item['class_id'], costume_id=item['costume_id'],
                    display_name=item['display_name'], character=item['character'])]))['costumes'][0]
                item['recipe'] = {k: checked[k] for k in ('rpg_character', 'story_character', 'rpg_reference', 'face',
                                                          'illustration', 'grow', 'sources') if k in checked}
            except RecipeError:
                pass
        result.append(item)
    name = manifest.get('name')
    return dict(format=FORMAT, version=manifest['version'],
                name=recipes._label(name, 'name') if name is not None else 'Costume pack', costumes=result)


def read_pack(path):
    """Checked manifest and {member name: bytes}. Nothing is written to disk."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_PACK:
        raise RecipeError('Pack file is missing or larger than 256 MiB')
    try:
        with zipfile.ZipFile(path) as archive:
            infos = {i.filename: i for i in archive.infolist()}
            if len(infos) != len(archive.infolist()) or len(infos) > 3*recipes.MAX_COSTUMES+1:
                raise RecipeError('Pack has duplicate or too many members')
            info = infos.get('pack.json')
            if info is None or info.file_size > MAX_MANIFEST:
                raise RecipeError('This is not a costume pack')
            manifest = _validate_manifest(json.loads(archive.read('pack.json').decode('utf-8')))
            wanted = {'pack.json'}
            files = {}
            for item in manifest['costumes']:
                for kind, expected in item['files'].items():
                    name = member_name(item, kind)
                    wanted.add(name)
                    info = infos.get(name)
                    if info is None or info.file_size != expected['bytes'] or info.is_dir():
                        raise RecipeError('Pack is missing %s or its size differs from the manifest' % name)
                    data = archive.read(name)
                    if len(data) != expected['bytes'] or _digest(data) != expected['sha256']:
                        raise RecipeError('Pack member %s does not match its fingerprint' % name)
                    files[name] = data
            if set(infos) != wanted:
                raise RecipeError('Pack contains unexpected files')
            return manifest, files
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError, OSError) as error:
        raise RecipeError('Pack file is damaged or not a costume pack: %s' % error) from None


def is_pack(path):
    with Path(path).open('rb') as stream:
        return stream.read(4) == b'PK\x03\x04'


def default_name(stage):
    """Display name of a single costume, otherwise a count."""
    from d2_appearance_inventory import catalog
    inventory = catalog(json.loads(Path(stage).read_text()))[1]
    if len(inventory) == 1:
        return inventory[0].get('display_name') or inventory[0]['costume_id']
    return 'Costume pack (%d costumes)' % len(inventory)


def unused_path(folder, name):
    """folder/<slug>.d2costumepack, numbered when that name is taken."""
    base = recipes.slug(name)
    candidate = Path(folder)/(base+SUFFIX)
    number = 2
    while candidate.exists():
        candidate = Path(folder)/('%s-%d%s' % (base, number, SUFFIX))
        number += 1
    return candidate


def export_pack(stage, path, name=None, replace=False, rpg_source=None):
    """Write every costume of a private profile, with its artwork, to one file."""
    import d2_appearance_add as tool
    from d2_appearance_inventory import catalog
    from d2_appearance_stage import member, rebind_anm
    from d2_character_export import unlzs
    from d2_face_atlas import decode, image
    from d2_rpg_map import archive_member
    stage = Path(stage)
    path = Path(path)
    if not path.name.endswith(SUFFIX):
        raise RecipeError('Pack files end in '+SUFFIX)
    if path.exists() and not replace:
        raise RecipeError('%s already exists; choose another name or pass --replace' % path.name)
    data = json.loads(stage.read_text())
    if data.get('mode') != 'isolated-runtime-experiment':
        raise RecipeError('Expected a private costume profile')
    active, inventory = catalog(data)
    enabled = {(a['class_id'], a['costume_id']) for a in active if a.get('enabled', True)}
    colors = {(s.get('class_id'), s.get('costume_id')): s.get('color') for s in data.get('color_slots', [])
              if isinstance(s, dict)}
    # How each costume was made, when known; lets the receiver re-export a recipe.
    try:
        known = {(c['class_id'], c['costume_id']): c for c in recipes.export_recipe(stage, rpg_source=rpg_source)[0]['costumes']}
    except (RecipeError, OSError, ValueError, KeyError):
        known = {}
    costumes, members, atlas = [], {}, {}
    for entry in inventory:
        key = (entry['class_id'], entry['costume_id'])
        facts = tool.profile_facts(stage, key[0])
        archive = facts['content']/'ANM_HI.dat'
        donor = archive_member(archive, 'anm%05d.lzs' % facts['body'])
        donor = unlzs(donor) if donor.startswith(b'dat\0') else donor
        body = archive_member(archive, 'anm%05d.lzs' % entry['new_resource'])
        body = unlzs(body) if body.startswith(b'dat\0') else body
        body = rebind_anm(body, entry['new_resource'], facts['body'])[0]
        structure_check(donor, body, facts['body'])
        item = dict(character=facts['name'] or 'Class %d' % key[0], class_id=key[0], costume_id=key[1],
                    display_name=entry.get('display_name') or key[1], d2_body_sha256=_digest(donor), files={})
        produced = dict(body=body)
        cell = entry.get('face_cell')
        if cell:
            bank = facts['face_archives'][0]
            if bank not in atlas:
                raw, width, height = decode(member(bank, tool.FACE_BANK)[0])
                atlas[bank] = image(raw, width, height)
            picture = atlas[bank].crop((cell['x'], cell['y'], cell['x']+FACE, cell['y']+FACE))
            buffer = io.BytesIO()
            picture.save(buffer, format='PNG')
            produced['face'] = buffer.getvalue()
        if entry.get('illustration_resource'):
            art = archive_member(archive, 'anm%05d.lzs' % entry['illustration_resource'])
            art = unlzs(art) if art.startswith(b'dat\0') else art
            produced['illustration'] = rebind_anm(art, entry['illustration_resource'], entry['illustration_donor'])[0]
        for kind, content in produced.items():
            item['files'][kind] = dict(sha256=_digest(content), bytes=len(content))
            members[member_name(item, kind)] = content
        if type(colors.get(key)) is int:
            item['color'] = colors[key]
        elif key in enabled and not colors:
            item['active'] = True
        if key in known:
            item['recipe'] = {k: known[key][k] for k in ('rpg_character', 'story_character', 'rpg_reference', 'face',
                                                         'illustration', 'grow', 'sources') if k in known[key]}
        costumes.append(item)
    if name is None:
        name = costumes[0]['display_name'] if len(costumes) == 1 else 'Costume pack (%d costumes)' % len(costumes)
    manifest = dict(format=FORMAT, version=VERSION, name=name, created=time.strftime('%Y-%m-%d'), game=recipes.GAME,
                    note=NOTE, costumes=costumes)
    _validate_manifest(manifest)
    text = json.dumps(manifest, indent=2, ensure_ascii=False)+'\n'
    if re.search(r'(/Users/|/Volumes/|/home/|[A-Za-z]:\\\\)', text):
        raise RecipeError('Refusing to write a pack whose manifest contains a local path')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.new')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr('pack.json', text)
            for member_path, content in members.items():
                archive.writestr(member_path, content)
        read_pack(temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return dict(pack=str(path), name=name, bytes=path.stat().st_size,
                costumes=['%s → %s' % (c['display_name'], c['character']) for c in costumes],
                with_recipe=sum('recipe' in c for c in costumes))


def install(item, files, current, target, save_slot=None, decoder_check=True):
    """Register one packed costume into the new profile folder ``target``."""
    import d2_appearance_add as tool
    from d2_appearance_face import attach as attach_face
    from d2_appearance_illustration import attach as attach_illustration
    from d2_appearance_inventory import extend
    from d2_appearance_stage import member, stage as stage_profile
    from d2_asset_pack import compress_lzs
    from d2_character_export import unlzs
    from d2_face_atlas import build as build_face
    from d2_rpg_map import archive_member
    from PIL import Image
    fresh = str(current) == 'new'
    stage = None if fresh else Path(current)
    facts = tool.profile_facts(stage, item['class_id'])
    archive = facts['content']/'ANM_HI.dat'
    donor = archive_member(archive, 'anm%05d.lzs' % facts['body'])
    donor = unlzs(donor) if donor.startswith(b'dat\0') else donor
    if _digest(donor) != item['d2_body_sha256']:
        raise RecipeError('%s was built for a different version of %s than this game dump has'
                          % (item['display_name'], item['character']))
    body = files[member_name(item, 'body')]
    structure_check(donor, body, facts['body'])
    face = files.get(member_name(item, 'face'))
    note = None
    if face is not None and (not 0 <= facts['face'] < 500 or not facts['face_archives']):
        face, note = None, 'Class uses a face bank other than the unique group; original icon kept'
    art = files.get(member_name(item, 'illustration'))
    target = Path(target)
    work = Path(tempfile.mkdtemp(prefix='.'+target.name+'-', dir=target.parent))
    try:
        packed = work/('anm%05d.lzs' % facts['body'])
        packed.write_bytes(compress_lzs(body))
        check = None
        if decoder_check:
            from d2_lzs_probe import probe
            (work/'expanded.bin').write_bytes(body)
            try:
                check = bool(probe(tool.REPO, packed, work/'expanded.bin', work/'probe')['matches'])
            except FileNotFoundError:
                check = None   # no compiler on this machine; our own round trip below still applies
            if check is False:
                raise RecipeError('Exact guest decoder rejected the packed body')
        if unlzs(packed.read_bytes()) != body:
            raise RecipeError('Body compression round trip failed')
        resource = tool.free_resource(facts, 900, 999)
        plan = ['body']+(['face'] if face is not None else [])+(['illustration'] if art is not None else [])

        def step(name):
            return target if name == plan[-1] else work/('profile-'+name)
        if fresh:
            stage_profile(tool.REPO, step('body'), item['class_id'], resource, packed,
                          save_slot or tool.SAVE_SLOTS[1], True, True)
            now = step('body')/'stage.json'
            data = json.loads(now.read_text())
            entry = dict(class_id=item['class_id'], selector=1, new_resource=resource, visual_class_id=resource,
                         selection_mode='renderer-only', enabled=True, costume_id=item['costume_id'],
                         display_name=item['display_name'])
            data.update(appearances=[entry], costumes=[dict(entry)])
            now.write_text(json.dumps(data, indent=2)+'\n')
        else:
            extend(stage, step('body'), packed, item['class_id'], resource, item['costume_id'], item['display_name'])
            now = step('body')/'stage.json'
        steps = [dict(step='body', resource=resource)]
        recipe = item.get('recipe') or {}
        if face is not None:
            if len(face) > MAX_FACE:
                raise RecipeError('Face icon is too large')
            with Image.open(io.BytesIO(face)) as picture:
                if picture.format != 'PNG' or picture.size != (FACE, FACE):
                    raise RecipeError('Face icon must be a %d×%d PNG' % (FACE, FACE))
                picture.convert('RGBA').save(work/'face.png')
            bank = work/tool.FACE_BANK
            content = Path(json.loads(now.read_text())['runtime_environment']['PS3_VFS_ROOT'])/tool.GAME_DATA
            bank.write_bytes(member(content/facts['face_archives'][0].name, tool.FACE_BANK)[0])
            occupied = [[c['face_cell']['x'], c['face_cell']['y']] for c in facts['inventory'] if c.get('face_cell')]
            built = build_face(bank, work/'face', work/'face.png', [0, 0, FACE, FACE], True, occupied)
            attach_face(now, work/'face/atlas.lzs', item['class_id'], item['costume_id'],
                        built['face_x'], built['face_y'], step('face'))
            now = step('face')/'stage.json'
            crop = (recipe.get('face') or {}).get('crop') if isinstance(recipe.get('face'), dict) else None
            steps.append(dict(step='face', crop=crop, cell=[built['face_x'], built['face_y']],
                              atlas=[built['face_width'], built['face_height']]))
        if art is not None:
            donor_resource = facts['base']+10000
            (work/'illustration.bin').write_bytes(art)
            picture_resource = tool.free_resource(facts, 10900, 10999)
            attach_illustration(now, step('illustration'), work/'illustration.bin', item['class_id'],
                                item['costume_id'], picture_resource, donor_resource)
            steps.append(dict(step='illustration', resource=picture_resource, donor=donor_resource,
                              crop=(recipe.get('illustration') or {}).get('crop')))
        # Review evidence travels with the profile, as for built costumes.
        if stage is not None and (stage.parent/'costumes').is_dir():
            shutil.copytree(stage.parent/'costumes', target/'costumes')
        evidence = target/'costumes'/('%d-%s' % (item['class_id'], item['costume_id']))
        evidence.mkdir(parents=True)
        if face is not None:
            shutil.copy2(work/'face.png', evidence/'face.png')
        summary = dict(profile=str(target/'stage.json'), class_id=item['class_id'], character=facts['name'],
                       costume_id=item['costume_id'], display_name=item['display_name'], imported_from='costume pack',
                       body=dict(resource=resource, exact_decoder_match=check, structure_checked=True),
                       steps=steps, face_note=note, native_validated=False)
        if 'rpg_character' in recipe:
            summary.update(rpg_character=recipe['rpg_character'], options=dict(
                story_character=recipe.get('story_character'), rpg_reference=recipe.get('rpg_reference'),
                grow=recipe.get('grow', 'yes'), illustration_matte=(recipe.get('illustration') or {}).get('matte')))
        (evidence/'added.json').write_text(json.dumps(summary, indent=2)+'\n')
        return dict(body_resource=resource, exact_decoder_match=check, face=face is not None,
                    illustration=art is not None, note=note)
    except BaseException:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def import_pack(path, profile='new', output=None, build_colors=None, progress=None, save_slot=None,
                install_one=None):
    """Install every costume of a pack into one new private profile.

    Needs only this machine's D2 game dump. The source profile, the game dump
    and all saves are left untouched.
    """
    from d2_appearance_choice import select
    manifest, files = read_pack(path)
    if install_one is None:
        install_one = install
    chosen = []

    def add_one(item, current, target):
        result = install_one(item, files, current, target, save_slot)
        if item.get('active') and 'color' not in item:
            chosen.append(item)
        return result
    report = recipes.chain_import(manifest['name'], manifest['costumes'], profile, output, add_one, build_colors,
                                  progress)
    if report['slots'] is None:
        for item in chosen:
            select(Path(report['profile']), True, item['class_id'], item['costume_id'])
    report['source'] = 'costume pack'
    return report
