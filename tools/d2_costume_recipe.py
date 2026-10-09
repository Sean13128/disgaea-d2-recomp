#!/usr/bin/env python3
"""Costume recipes: a shareable description of imported costumes, without artwork.

A recipe is a small JSON file naming which Disgaea RPG costume becomes which
Disgaea D2 appearance, together with the few choices made while importing it
(display name, Status illustration, crops, Choose Color slot). It holds no
pixels, no game data and no local paths. Anyone with their own D2 game dump
and their own RPG assets can rebuild the same costumes from it:

    tools/costume export --output my-pack.d2costume.json
    tools/costume import my-pack.d2costume.json

Fingerprints (SHA-256) of the source files are recorded so an import can tell
when the reader's files differ from the author's.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

FORMAT = 'd2-costume-recipe'
VERSION = 1
SUFFIX = '.d2costume.json'
GAME = dict(title_id='BLUS31313', version='1.40')
NOTE = ('Contains no artwork or game data. Rebuild with your own Disgaea D2 dump and Disgaea RPG assets: '
        'tools/costume import <this file>')
IDENT = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
MAX_COSTUMES = 128
MAX_BYTES = 1024*1024


class RecipeError(ValueError):
    """A recipe that cannot be written or must not be trusted."""


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', str(text).casefold()).strip('-')[:64] or 'costumes'


def source_files(character, story_base=None):
    """RPG files, relative to assets/android, that decide how a costume looks."""
    files = ['prefabs/characters/%d' % character]
    for facing in ('front', 'back', 'wait_front', 'wait_back'):
        files.append('atlas/chara/battle/%s/%s%d' % (facing, facing.removeprefix('wait_'), character))
    if story_base is not None:
        files.append('atlas/chara/story/%s' % story_base)
    return files


def fingerprints(source, files):
    """SHA-256 per relative file; None when the source or any file is missing."""
    if not source:
        return None
    root = Path(source).expanduser()
    result = {}
    for name in files:
        if not re.fullmatch(r'[A-Za-z0-9_/.-]{1,200}', name) or '..' in name or name.startswith('/'):
            return None
        path = root/name
        if not path.is_file():
            return None
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _label(value, what, limit=100):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise RecipeError('%s must be 1–%d printable characters' % (what, limit))
    return value.strip()


def _integer(value, what, low, high):
    if type(value) is not int or not low <= value <= high:
        raise RecipeError('%s must be a whole number from %d to %d' % (what, low, high))
    return value


def _crop(value, what):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value) or \
            not (0 <= value[0] < value[2] <= 8192 and 0 <= value[1] < value[3] <= 8192):
        raise RecipeError('%s must be four pixel coordinates [x0, y0, x1, y1]' % what)
    return list(value)


def validate(recipe):
    """Checked, normalised copy of a recipe. Unknown keys are dropped."""
    if not isinstance(recipe, dict) or recipe.get('format') != FORMAT:
        raise RecipeError('This is not a costume recipe file')
    if type(recipe.get('version')) is not int or not 1 <= recipe['version'] <= VERSION:
        raise RecipeError('This recipe needs a newer version of the tools')
    costumes = recipe.get('costumes')
    if not isinstance(costumes, list) or not 1 <= len(costumes) <= MAX_COSTUMES:
        raise RecipeError('A recipe lists 1–%d costumes' % MAX_COSTUMES)
    result, seen, slots = [], set(), set()
    for raw in costumes:
        if not isinstance(raw, dict):
            raise RecipeError('Each costume must be an object')
        item = dict(class_id=_integer(raw.get('class_id'), 'class_id', 1, 32767),
                    character=_label(raw.get('character', 'Class %s' % raw.get('class_id')), 'character'),
                    display_name=_label(raw.get('display_name'), 'display_name'),
                    rpg_character=_integer(raw.get('rpg_character'), 'rpg_character', 1, 10**7))
        item['costume_id'] = raw.get('costume_id') or slug(item['display_name'])
        if not isinstance(item['costume_id'], str) or not IDENT.fullmatch(item['costume_id']):
            raise RecipeError('costume_id must be a short lowercase name such as dark-santa-laharl')
        key = (item['class_id'], item['costume_id'])
        if key in seen:
            raise RecipeError('Costume %s is listed twice for class %d' % (key[1], key[0]))
        seen.add(key)
        for name, high in (('story_character', 10**8), ('rpg_reference', 10**7)):
            if raw.get(name) is not None:
                item[name] = _integer(raw[name], name, 1, high)
        face = raw.get('face', {})
        if face is False:
            item['face'] = False
        elif isinstance(face, dict):
            item['face'] = dict(crop=_crop(face.get('crop'), 'face crop'))
        else:
            raise RecipeError('face must be false or an object')
        picture = raw.get('illustration')
        if picture is not None:
            if not isinstance(picture, dict) or 'story_character' not in item:
                raise RecipeError('An illustration needs a story_character')
            matte = picture.get('matte')
            if matte is not None and (not isinstance(matte, list) or len(matte) != 3 or
                                      any(type(v) is not int or not 0 <= v <= 255 for v in matte)):
                raise RecipeError('illustration matte must be [R, G, B]')
            item['illustration'] = dict(crop=_crop(picture.get('crop'), 'illustration crop'), matte=matte)
        grow = raw.get('grow', 'yes')
        if grow not in ('yes', 'symmetric', 'no'):
            raise RecipeError('grow must be yes, symmetric or no')
        item['grow'] = grow
        if raw.get('color') is not None:
            item['color'] = _integer(raw['color'], 'color', 1, 4)
            if (item['class_id'], item['color']) in slots:
                raise RecipeError('Two costumes of class %d use Extra color %d' % (item['class_id'], item['color']))
            slots.add((item['class_id'], item['color']))
        item['active'] = raw.get('active') is True
        sources = raw.get('sources')
        if sources is not None:
            if not isinstance(sources, dict) or len(sources) > 16 or any(
                    not isinstance(k, str) or not re.fullmatch(r'[A-Za-z0-9_/.-]{1,200}', k) or '..' in k or
                    k.startswith('/') or not isinstance(v, str) or not re.fullmatch(r'[0-9a-f]{64}', v)
                    for k, v in sources.items()):
                raise RecipeError('sources must map relative file names to SHA-256 fingerprints')
            item['sources'] = dict(sources)
        if raw.get('d2_body_sha256') is not None:
            if not isinstance(raw['d2_body_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', raw['d2_body_sha256']):
                raise RecipeError('d2_body_sha256 must be a SHA-256 fingerprint')
            item['d2_body_sha256'] = raw['d2_body_sha256']
        result.append(item)
    name = recipe.get('name')
    return dict(format=FORMAT, version=recipe['version'],
                name=_label(name, 'name') if name is not None else 'Costume pack', costumes=result)


def load(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise RecipeError('Recipe file is missing or larger than 1 MiB')
    try:
        return validate(json.loads(path.read_text(encoding='utf-8')))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecipeError('Recipe file is not valid JSON: %s' % error) from None


def _story_base(source, story, cache):
    """img_base of a story character, via the importer's master reader."""
    if 'rows' not in cache:
        from d2_appearance_add import masters
        cache['rows'] = {r.get('id'): r.get('img_base') for r in masters(source, 'storycharacter')}
    return cache['rows'].get(story)


def export_recipe(stage, name=None, rpg_source=None, story_bases=None, d2_bodies=None):
    """Recipe for every costume in a private profile.

    story_bases: optional {story id: img_base}; otherwise read from the RPG
    masters when rpg_source is given. d2_bodies: optional {class id: sha256}.
    Returns (recipe, skipped) where skipped lists costumes without an import
    record (made by the older manual tools).
    """
    from d2_appearance_inventory import catalog
    stage = Path(stage)
    data = json.loads(stage.read_text())
    if data.get('mode') != 'isolated-runtime-experiment':
        raise RecipeError('Expected a private costume profile')
    active, inventory = catalog(data)
    enabled = {(a['class_id'], a['costume_id']) for a in active if a.get('enabled', True)}
    colors = {(s.get('class_id'), s.get('costume_id')): s.get('color') for s in data.get('color_slots', [])
              if isinstance(s, dict)}
    cache, costumes, skipped = {}, [], []
    for entry in inventory:
        key = (entry['class_id'], entry['costume_id'])
        record = stage.parent/'costumes'/('%d-%s' % key)/'added.json'
        if not record.is_file():
            skipped.append(dict(class_id=key[0], costume_id=key[1], reason='No import record beside the profile'))
            continue
        added = json.loads(record.read_text())
        options = added.get('options') or {}
        steps = {s.get('step'): s for s in added.get('steps', []) if isinstance(s, dict)}
        item = dict(character=added.get('character') or 'Class %d' % key[0], class_id=key[0], costume_id=key[1],
                    display_name=entry.get('display_name') or added.get('display_name') or key[1],
                    rpg_character=added['rpg_character'])
        story = options.get('story_character')
        picture = steps.get('illustration')
        if story is None and picture:
            found = re.search(r'char-%d-story-(\d+)' % added['rpg_character'], str(picture.get('source', '')))
            story = int(found.group(1)) if found else None
        if options.get('rpg_reference') is not None:
            item['rpg_reference'] = options['rpg_reference']
        item['face'] = dict(crop=steps['face'].get('crop')) if 'face' in steps else False
        if picture and story is not None:
            item['story_character'] = story
            item['illustration'] = dict(crop=picture.get('crop'), matte=options.get('illustration_matte'))
        item['grow'] = options.get('grow', 'yes')
        if type(colors.get(key)) is int:
            item['color'] = colors[key]
        elif key in enabled and not colors:
            item['active'] = True
        base = None
        if 'story_character' in item:
            base = (story_bases or {}).get(story)
            if base is None and rpg_source and story_bases is None:
                try:
                    base = _story_base(rpg_source, story, cache)
                except (Exception, SystemExit):
                    base = None
        if 'story_character' not in item or base is not None:
            prints = fingerprints(rpg_source, source_files(item['rpg_character'], base))
            if prints:
                item['sources'] = prints
        if d2_bodies and re.fullmatch(r'[0-9a-f]{64}', str(d2_bodies.get(key[0], ''))):
            item['d2_body_sha256'] = d2_bodies[key[0]]
        costumes.append(item)
    if not costumes:
        raise RecipeError('No costume in this profile has an import record to export')
    if name is None:
        name = costumes[0]['display_name'] if len(costumes) == 1 else 'Costume pack (%d costumes)' % len(costumes)
    recipe = dict(format=FORMAT, version=VERSION, name=name, created=time.strftime('%Y-%m-%d'), game=GAME, note=NOTE,
                  costumes=costumes)
    validate(recipe)
    return recipe, skipped


def write(recipe, path, replace=False):
    """Write a validated recipe; refuses to overwrite unless asked."""
    validate(recipe)
    path = Path(path)
    if not path.name.endswith('.json'):
        raise RecipeError('Recipe files end in '+SUFFIX)
    text = json.dumps(recipe, indent=2, ensure_ascii=False)+'\n'
    if re.search(r'(/Users/|/Volumes/|/home/|[A-Za-z]:\\\\)', text):
        raise RecipeError('Refusing to write a recipe that contains a local path')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise RecipeError('%s already exists; choose another name or pass --replace' % path.name)
    temporary = path.with_name(path.name+'.new')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)
    return path


def unused_path(folder, name):
    """folder/<slug>.d2costume.json, numbered when that name is taken."""
    base = slug(name)
    candidate = Path(folder)/(base+SUFFIX)
    number = 2
    while candidate.exists():
        candidate = Path(folder)/('%s-%d%s' % (base, number, SUFFIX))
        number += 1
    return candidate


def source_check(item, rpg_source):
    """'match', 'different', or 'unchecked' for one costume's RPG files."""
    wanted = item.get('sources')
    if not wanted:
        return 'unchecked'
    found = fingerprints(rpg_source, sorted(wanted))
    if found is None:
        return 'different'
    return 'match' if found == wanted else 'different'


def d2_body_fingerprints(stage, class_ids):
    """{class id: SHA-256 of the D2 body animation member}; best effort."""
    result = {}
    try:
        from d2_appearance_add import profile_facts
        from d2_rpg_map import archive_member
        for class_id in sorted(class_ids):
            facts = profile_facts(Path(stage) if stage else None, class_id)
            member = archive_member(facts['content']/'ANM_HI.dat', 'anm%05d.lzs' % facts['body'])
            result[class_id] = hashlib.sha256(member).hexdigest()
    except (Exception, SystemExit):
        pass
    return result


def body_check(item, bodies):
    wanted = item.get('d2_body_sha256')
    if not wanted or item['class_id'] not in bodies:
        return 'unchecked'
    return 'match' if bodies[item['class_id']] == wanted else 'different'


def add_arguments(item, profile, output, rpg_source, exact):
    """Command line for the one-command importer. Recorded crops are only
    reused when the reader's RPG files are the author's (exact)."""
    command = ['add', '--profile', str(profile), '--output', str(output), '--class-id', str(item['class_id']),
               '--rpg-character', str(item['rpg_character']), '--costume-id', item['costume_id'],
               '--display-name', item['display_name'], '--grow', item['grow']]
    if rpg_source:
        command += ['--rpg-source', str(rpg_source)]
    if item.get('rpg_reference') is not None:
        command += ['--rpg-reference', str(item['rpg_reference'])]
    if item['face'] is False:
        command.append('--no-face')
    elif exact and item['face'].get('crop'):
        command += ['--face-crop']+[str(v) for v in item['face']['crop']]
    if 'illustration' in item:
        command += ['--story-character', str(item['story_character'])]
        if exact and item['illustration'].get('crop'):
            command += ['--illustration-crop']+[str(v) for v in item['illustration']['crop']]
        if item['illustration'].get('matte'):
            command += ['--illustration-matte']+[str(v) for v in item['illustration']['matte']]
    if item.get('active') and 'color' not in item:
        command.append('--select')
    return command


def chain_import(name, costumes, profile, output, add_one, build_colors=None, progress=None):
    """Add costumes one after another into a single new private profile.

    costumes: checked entries with class_id, costume_id, display_name and
    optional color/active. add_one(item, current, target) builds one costume
    into the new folder ``target`` on top of ``current`` (a profile's
    stage.json, or the word new) and returns extra report fields. When any
    Choose Color slot is involved the result is a Choose Color profile.
    Folders made on the way are removed; on failure everything made here is
    removed and the remembered current profile is restored.
    """
    import d2_appearance_add as tool
    from d2_appearance_inventory import catalog
    previous = tool.local_config().get('current_profile')
    if build_colors is None:
        from d2_appearance_colors import build as build_colors
    existing, occupied = set(), set()
    if str(profile) != 'new':
        profile = Path(profile).expanduser().absolute()
        if not profile.is_file():
            raise RecipeError('Pass an existing private profile stage.json, or "new"')
        data = json.loads(profile.read_text())
        existing = {(c['class_id'], c['costume_id']) for c in catalog(data)[1]}
        occupied = {(s.get('class_id'), s.get('color')) for s in data.get('color_slots', []) if isinstance(s, dict)}
    todo = [c for c in costumes if (c['class_id'], c['costume_id']) not in existing]
    skipped = [dict(class_id=c['class_id'], costume_id=c['costume_id'], reason='Already in the profile')
               for c in costumes if (c['class_id'], c['costume_id']) in existing]
    if not todo:
        raise RecipeError('Every costume in this file is already in that profile')
    root = tool.REPO/'work/appearance-profiles'
    output = Path(output).expanduser().absolute() if output else root/(time.strftime('%Y%m%d-%H%M%S-')+slug(name))
    if output.parent == root:
        root.mkdir(parents=True, exist_ok=True)
    if output.exists() or not output.parent.is_dir():
        raise RecipeError('Output must be a new folder inside an existing one')
    wanted = [c for c in todo if 'color' in c]
    use_colors = bool(wanted) or bool(occupied)
    made, built, current = [], [], profile
    try:
        for number, item in enumerate(todo, 1):
            last = number == len(todo) and not use_colors
            target = output if last else output.with_name('.%s-step%d' % (output.name, number))
            if progress:
                progress('Adding %d of %d: %s' % (number, len(todo), item['display_name']))
            made.append(target)
            extra = add_one(item, current, target) or {}
            built.append(dict(class_id=item['class_id'], character=item['character'], costume_id=item['costume_id'],
                              display_name=item['display_name'], **extra))
            current = target/'stage.json'
        slots = None
        if use_colors:
            # Requested slots are honoured unless the base profile already uses them.
            data = json.loads(Path(current).read_text())
            assigned = [dict(s) for s in data.get('color_slots', [])]
            taken = {(s.get('class_id'), s.get('color')) for s in assigned}
            for item in wanted:
                if (item['class_id'], item['color']) in taken:
                    continue
                assigned.append(dict(class_id=item['class_id'], color=item['color'], costume_id=item['costume_id']))
                taken.add((item['class_id'], item['color']))
            data['color_slots'] = assigned
            Path(current).write_text(json.dumps(data, indent=2)+'\n')
            if progress:
                progress('Assigning Choose Color slots')
            made.append(output)
            slots = build_colors(Path(current), output)['slots']
        for folder in made:
            if folder != output and folder.name.startswith('.'+output.name+'-step') and folder.is_dir():
                shutil.rmtree(folder)
        tool.remember(current_profile=output/'stage.json')
        return dict(profile=str(output/'stage.json'), name=name, costumes=built, skipped=skipped, slots=slots)
    except BaseException:
        for folder in made:
            if folder.is_dir() and (folder == output or folder.name.startswith('.'+output.name+'-step')):
                shutil.rmtree(folder, ignore_errors=True)
        if previous:
            tool.remember(current_profile=previous)
        raise


def import_recipe(path, profile='new', output=None, rpg_source=None, run_add=None, build_colors=None, progress=None):
    """Rebuild every costume of a recipe into one new private profile, from
    this machine's own game dump and RPG assets. Nothing outside the new
    profile is changed."""
    import d2_appearance_add as tool
    recipe = load(path)
    rpg_source = rpg_source or tool.local_config().get('rpg_source')
    if run_add is None:
        def run_add(arguments):
            return tool.add(tool.build_parser().parse_args(arguments))
    bodies = d2_body_fingerprints(None if str(profile) == 'new' else profile,
                                  {c['class_id'] for c in recipe['costumes']}) \
        if any('d2_body_sha256' in c for c in recipe['costumes']) else {}

    def add_one(item, current, target):
        check = source_check(item, rpg_source)
        # Recorded crops are pixel positions in the author's art; with
        # different files the importer's automatic crops are safer.
        summary = run_add(add_arguments(item, current, target, rpg_source, check != 'different'))
        return dict(source_check=check, crops='automatic' if check == 'different' else 'recorded',
                    d2_check=body_check(item, bodies),
                    exact_decoder_match=((summary or {}).get('body') or {}).get('exact_decoder_match'))
    report = chain_import(recipe['name'], recipe['costumes'], profile, output, add_one, build_colors, progress)
    report['different_sources'] = [b['display_name'] for b in report['costumes']
                                   if 'different' in (b['source_check'], b['d2_check'])]
    return report
