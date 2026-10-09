#!/usr/bin/env python3
"""Add one RPG costume to a private appearance profile with a single command.

Chains the verified steps: extract the RPG character, derive or reuse the D2
donor's pose template, build a complete body, check it with the exact guest
decoder, allocate free resource IDs, register the costume, author a face icon
and, when story art is named, a Status illustration. The result is a new
private profile; the source profile, game dump and saves are never modified.

    add     build and register a costume
    export  write a costume recipe (no artwork), or with --with-art a costume pack
    import  add the costumes of a pack, or rebuild those of a recipe
    find    search RPG battle or story character names for IDs
    list    show the costumes in a profile
    choose  pick a character's appearance for the next launch
    play    launch the private profile for ordinary play

Run with the project's .venv-rpg interpreter (Pillow and UnityPy).
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent/'data'
LOCAL = REPO/'work/appearance.json'
GAME_DIR = 'Disgaea D2 A Brighter Darkness - [BLUS31313]'
GAME_DATA = 'PS3_GAME/USRDIR/Data'
SAVE_SLOTS = ('NPUB31321_NORMAL_00', 'NPUB31321_NORMAL_01')
FACE_BANK = 'wf_unique1.lzs'


def local_config():
    """Machine-local paths (ignored by Git): RPG asset root and current profile."""
    if LOCAL.is_file() and LOCAL.stat().st_size < 65536:
        data = json.loads(LOCAL.read_text())
        if isinstance(data, dict):
            return data
    return {}


def remember(**values):
    data = local_config()
    data.update({k: str(v) for k, v in values.items() if v is not None})
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    temporary = LOCAL.with_suffix('.json.new')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    os.replace(temporary, LOCAL)


def rpg_python():
    """Interpreter that can import UnityPy for extraction."""
    try:
        import UnityPy  # noqa: F401
        return sys.executable
    except ImportError:
        candidate = REPO/'.venv-rpg/bin/python'
        if candidate.is_file():
            return str(candidate)
        raise SystemExit('UnityPy is required: python3 -m venv .venv-rpg && '
                         '.venv-rpg/bin/python -m pip install -r tools/requirements-rpg.txt')


def masters(source, name):
    code = ('import UnityPy,json,sys\n'
            'env=UnityPy.load(open(sys.argv[1],"rb").read())\n'
            'rows=next(o.parse_as_dict()["DataList"] for o in env.objects if o.type.name=="MonoBehaviour")\n'
            'json.dump(rows,sys.stdout,ensure_ascii=False,default=str)\n')
    path = Path(source)/'masters'/name
    if not path.is_file():
        raise SystemExit('Missing RPG master: '+str(path))
    out = subprocess.run([rpg_python(), '-c', code, str(path)], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def extracted(source, character, story=None):
    """Cached extraction of one RPG character; story art only when named."""
    source = source or local_config().get('rpg_source')
    if not source:
        raise SystemExit('Pass --rpg-source once (the extracted assets/android directory)')
    import hashlib
    root = Path(source).expanduser().absolute()
    # A source identity covers the masters and selected bundles, including
    # story artwork. Different asset dumps must never reuse stale ID-only art.
    paths = [root/'masters/character', root/f'prefabs/characters/{character}']
    for facing in ('front', 'back', 'wait_front', 'wait_back'):
        paths.append(root/f"atlas/chara/battle/{facing}/{facing.removeprefix('wait_')}{character}")
    if story is not None:
        paths.append(root/'masters/storycharacter')
        rows = masters(root, 'storycharacter')
        selected = [r for r in rows if r.get('id') == story]
        if len(selected) != 1:
            raise SystemExit('Story ID must identify exactly one source character')
        paths.append(root/f"atlas/chara/story/{selected[0]['img_base']}")
    identity = hashlib.sha256()
    for path in paths:
        identity.update(str(path.relative_to(root)).encode())
        identity.update(hashlib.sha256(path.read_bytes()).digest())
    cache = REPO/'work/rpg-cache'/identity.hexdigest()[:24]/('char-%d' % character if story is None else 'char-%d-story-%d' % (character, story))
    if (cache/'manifest.json').is_file():
        return cache
    if cache.exists():
        raise SystemExit('Incomplete extraction; remove it and retry: '+str(cache))
    if not source:
        raise SystemExit('Pass --rpg-source once (the extracted assets/android directory); it is remembered locally')
    cache.parent.mkdir(parents=True, exist_ok=True)
    command = [rpg_python(), str(REPO/'tools/d2_rpg_assets.py'), '--source', str(source),
               '--character', str(character), '--output', str(cache)]
    if story is not None:
        command += ['--story-character', str(story)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return cache


def profile_facts(stage, class_id):
    """Donor body, face and illustration IDs plus every used resource name."""
    from d2_appearance_inventory import catalog
    from d2_appearance_stage import member
    from d2_character_export import characters, nispack
    if stage is None:
        # A brand-new profile starts from the untouched game dump.
        data, content = None, REPO/GAME_DIR/GAME_DATA
    else:
        data = json.loads(stage.read_text())
        if data.get('mode') != 'isolated-runtime-experiment' or data.get('asset_probe') or data.get('baseline_control'):
            raise SystemExit('Expected a private costume profile')
        content = Path(data['runtime_environment']['PS3_VFS_ROOT'])/GAME_DATA
    rows, classes, names, face_archives = None, set(), set(), []
    for archive in sorted(content.glob('START*.dat')):
        with archive.open('rb') as f:
            members = {r['name'] for r in nispack(f, archive.stat().st_size)}
        if FACE_BANK in members:
            face_archives.append(archive)
        if 'char.dat' in members:
            table = characters(member(archive, 'char.dat')[0])
            classes.update(r['id'] for r in table)
            found = [r for r in table if r['id'] == class_id]
            if len(found) != 1:
                raise SystemExit('Class %d is absent or ambiguous in %s' % (class_id, archive.name))
            fact = (found[0]['body_animation_ids'][0], found[0]['raw_be16'][0x19E//2], found[0]['raw_be16'][0x196//2],
                    found[0]['name'])
            if rows is not None and rows != fact:
                raise SystemExit('Character tables disagree about class %d' % class_id)
            rows = fact
    if rows is None:
        raise SystemExit('No character table found in the profile')
    for archive in sorted(content.glob('ANM_HI*.dat')):
        with archive.open('rb') as f:
            names.update(r['name'] for r in nispack(f, archive.stat().st_size))
    inventory = catalog(data)[1] if data else []
    return dict(data=data, content=content, body=rows[0], face=rows[1], base=rows[2], name=rows[3], classes=classes,
                anm_names=names, inventory=inventory, face_archives=face_archives)


def free_resource(facts, low, high, taken=()):
    used = set(taken)
    for c in facts['inventory']:
        used.update((c['new_resource'], c['visual_class_id'], c.get('illustration_resource', 0)))
    for value in range(low, high+1):
        if value in used or value in facts['classes']:
            continue
        if 'anm%05d.lzs' % value in facts['anm_names'] or 'anm%05d.dat' % value in facts['anm_names']:
            continue
        return value
    raise SystemExit('No free resource ID in %d..%d' % (low, high))


def head_crop(sprite):
    """Square head crop from a standing sprite: top of the art, centred on the head."""
    from d2_rpg_template import mask
    image = sprite['image']
    m = mask(image)
    left, top, right, bottom = m.getbbox()
    side = max(64, min(96, round((bottom-top)*0.58), image.width))
    band = m.crop((0, top, image.width, min(image.height, top+round(side*0.8))))
    columns = [x for x in range(band.width) if band.crop((x, 0, x+1, band.height)).getbbox()]
    # Hair accessories can be lopsided; weight columns by opaque height.
    weights = [(x, sum(band.crop((x, 0, x+1, band.height)).histogram()[255:])) for x in columns]
    total = sum(w for _, w in weights) or 1
    centre = sum(x*w for x, w in weights)/total
    x0 = int(max(0, min(image.width-side, round(centre-side/2))))
    y0 = int(max(0, min(image.height-side, top-max(0, (side-round((bottom-top)*0.5))//6))))
    return [x0, y0, x0+side, y0+side]


def portrait_crop(image, aspect):
    """Tall close-up strip like the retail Status art, covering about the
    upper three fifths of the sprite and centred on the neck/shoulder band
    (hats and ribbons make the very top a poor guide). It is a starting
    point: check illustration.png and pass --illustration-crop to frame the face."""
    alpha = image.getchannel('A').point(lambda a: 255 if a >= 64 else 0)
    left, top, right, bottom = alpha.getbbox()
    height = max(1, min(bottom-top, round(image.height*0.6)))
    width = max(1, min(right-left, round(height*aspect)))
    band = alpha.crop((0, top+round((bottom-top)*0.3), image.width, top+max(1, round((bottom-top)*0.6))))
    weights = [(x, sum(band.crop((x, 0, x+1, band.height)).histogram()[255:])) for x in range(band.width)]
    total = sum(w for _, w in weights) or 1
    centre = sum(x*w for x, w in weights)/total
    x0 = int(max(0, min(image.width-width, round(centre-width/2))))
    return [x0, top, x0+width, top+height]


def convert_portrait(donor, source, crop, matte=None):
    """Status illustration from RPG story art; transparent background unless a matte is given."""
    from PIL import Image, ImageOps
    from d2_anm import parse_anm
    from d2_rpg_map import pages_of, page_image, rgba
    from d2_rpg_palette import encode_images
    if matte is not None:
        from d2_appearance_illustration import convert
        return convert(donor, source, crop, tuple(matte))
    meta = parse_anm(donor)
    pages = pages_of(donor)
    if len(meta['blocks']) != 1 or len(pages) != 1 or not 10000 <= meta['blocks'][0]['resource_id'] < 20000:
        raise ValueError('Expected a single-resource, single-page Status illustration')
    rects = {(r['x'], r['y'], r['width'], r['height']) for r in
             meta['blocks'][0]['tables']['rectangle_candidates']['records'] if r['width'] and r['height']}
    if len(rects) != 1:
        raise ValueError('Illustration has several distinct rectangles')
    x, y, w, h = next(iter(rects))
    key = next(iter(pages))
    image = rgba(source)
    x0, y0, x1, y1 = crop
    if not 0 <= x0 < x1 <= image.width or not 0 <= y0 < y1 <= image.height:
        raise ValueError('Crop exceeds source image')
    patch = ImageOps.fit(image.crop(tuple(crop)), (w, h), method=Image.Resampling.LANCZOS)
    page = page_image(pages[key])
    page.paste((0, 0, 0, 0), (0, 0, page.width, page.height))
    page.paste(patch, (x, y))
    expanded, packed, report = encode_images(donor, {key: page}, 1)
    report.update(asset_role='status-illustration', crop=list(crop), matte=None, destination=[x, y, w, h],
                  fit='Aspect-preserving cover after crop; transparent background like the retail art')
    return expanded, packed, report


def class_by_name(name):
    """D2 class ID for a supported character name such as "Etna" (case-insensitive)."""
    known = json.loads((DATA/'d2_rpg_reference_map.json').read_text())['classes']
    wanted = re.sub(r'[^a-z0-9]', '', name.casefold())
    matches = [int(k) for k, v in known.items() if re.sub(r'[^a-z0-9]', '', v['name'].casefold()) == wanted]
    if len(matches) != 1:
        raise SystemExit('Unknown character %r. Supported: %s' % (
            name, ', '.join(sorted(v['name'] for v in known.values()))))
    return matches[0]


def slug(text):
    """Short lowercase costume ID from a display name."""
    return re.sub(r'[^a-z0-9]+', '-', text.casefold()).strip('-')[:64]


def resolve_add(args):
    """Fill the optional conveniences: character by name, costume ID and output directory."""
    if (args.class_id is None) == (args.character is None):
        raise SystemExit('Name the character once: --character Etna, or --class-id 30')
    if args.class_id is None:
        args.class_id = class_by_name(args.character)
    if not args.costume_id:
        if not args.display_name:
            raise SystemExit('Give the costume a name: --display-name "Dark Santa Laharl"')
        args.costume_id = slug(args.display_name)
    if args.output is None:
        root = REPO/'work/appearance-profiles'
        root.mkdir(parents=True, exist_ok=True)
        args.output = root/(time.strftime('%Y%m%d-%H%M%S-')+args.costume_id)
    return args


def add(args):
    args = resolve_add(args)
    from d2_appearance_choice import select
    from d2_appearance_face import attach as attach_face
    from d2_appearance_illustration import attach as attach_illustration
    from d2_appearance_inventory import extend
    from d2_appearance_stage import member, stage as stage_profile
    from d2_character_export import _no_symlinks, anm_pages, indexed_png
    from d2_face_atlas import build as build_face
    from d2_lzs_probe import probe
    from d2_rpg_autobuild import build as build_body
    from d2_rpg_map import archive_member, read
    from d2_rpg_template import build_template, catalog, review_sheet

    config = local_config()
    source = args.rpg_source or config.get('rpg_source')
    fresh = str(args.profile) == 'new'
    if fresh:
        stage = None
    else:
        stage = Path(args.profile or config.get('current_profile') or '').absolute()
        if not stage.is_file():
            raise SystemExit('Pass --profile STAGE.json (an existing private profile) or --profile new')
        stage = _no_symlinks(stage)
    output = _no_symlinks(Path(args.output).absolute())
    if output.exists() or not output.parent.is_dir():
        raise SystemExit('Output must be a new directory with an existing parent')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', args.costume_id):
        raise SystemExit('Costume ID must be a short lowercase name such as dark-santa-laharl')
    started = time.time()
    facts = profile_facts(stage, args.class_id)
    if any(c['class_id'] == args.class_id and c['costume_id'] == args.costume_id for c in facts['inventory']):
        raise SystemExit('This character already has a costume with that ID')
    archive = facts['content']/'ANM_HI.dat'
    costume_dir = extracted(source, args.rpg_character, args.story_character)

    # Pose template for the D2 donor: cached per body, derived from the RPG
    # version of the same character plus the shipped shared-rectangle template.
    template_path = REPO/'work/appearance-templates'/('template-%05d.json' % facts['body'])
    if not template_path.is_file():
        reference = args.rpg_reference
        if reference is None:
            known = json.loads((DATA/'d2_rpg_reference_map.json').read_text())['classes']
            reference = known.get(str(args.class_id), {}).get('rpg_character')
        if reference is None:
            raise SystemExit('No pose template for class %d yet: pass --rpg-reference with the RPG ID of the '
                             'same character in its standard outfit (see: find --name)' % args.class_id)
        reference_dir = extracted(source, reference)
        donor = archive_member(archive, 'anm%05d.lzs' % facts['body'])
        common = DATA/'d2_humanoid_common_template.json'
        votes = json.loads(common.read_text()) if common.is_file() else None
        template = build_template(donor, archive_member(archive, 'anm00001.lzs'), reference_dir, facts['body'],
                                  votes=votes)
        template.update(member='anm%05d.lzs' % facts['body'], common_member='anm00001.lzs',
                        class_id=args.class_id, rpg_reference=reference)
        template_path.parent.mkdir(parents=True, exist_ok=True)
        review_sheet(donor, template, reference_dir, template_path.with_suffix('.review.png'))
        template_path.write_text(json.dumps(template, indent=1)+'\n')
    template = json.loads(template_path.read_text())

    work = Path(tempfile.mkdtemp(prefix='.'+output.name+'-', dir=output.parent))
    steps = []
    try:
        body = build_body(archive, template_path, costume_dir, work/'body',
                          grow=dict(yes=True, symmetric='symmetric', no=False)[args.grow])
        packed = work/'body'/template['member']
        check = probe(REPO, packed, work/'body/expanded.bin', work/'probe')
        if not check['matches']:
            raise SystemExit('Exact guest decoder rejected the built body')
        resource = args.resource or free_resource(facts, 900, 999)
        want_face = not args.no_face
        face_note = None
        if want_face and (not 0 <= facts['face'] < 500 or not facts['face_archives']):
            want_face, face_note = False, 'Class uses a face bank other than the unique group; donor icon kept'
        illustration_source = None
        if args.story_character is not None:
            sprites = json.loads(read(costume_dir/'manifest.json'))
            story = next((b for b in sprites['bundles'] if b['label'] == 'story'), None)
            pictures = [s for s in (story or {}).get('sprites', []) if s.get('png')]
            if not pictures:
                raise SystemExit('Story bundle has no decoded sprite')
            # Story bundles hold one sprite per expression; "1" is the neutral one.
            pictures.sort(key=lambda s: (s['name'] != '1', -s['decoded_size'][0]*s['decoded_size'][1], s['name']))
            illustration_source = costume_dir/pictures[0]['png']
        plan = ['body']+(['face'] if want_face else [])+(['illustration'] if illustration_source else [])

        def target(step):
            return output if step == plan[-1] else work/('profile-'+step)
        if fresh:
            # First costume: copy the game dump and the chosen save untouched,
            # then record the binding in catalogue form like later additions.
            stage_profile(REPO, target('body'), args.class_id, resource, packed, args.save_slot, True, True)
            current = target('body')/'stage.json'
            data = json.loads(current.read_text())
            entry = dict(class_id=args.class_id, selector=1, new_resource=resource, visual_class_id=resource,
                         selection_mode='renderer-only', enabled=True, costume_id=args.costume_id)
            if args.display_name:
                entry['display_name'] = args.display_name
            data.update(appearances=[entry], costumes=[dict(entry)])
            current.write_text(json.dumps(data, indent=2)+'\n')
        else:
            extend(stage, target('body'), packed, args.class_id, resource, args.costume_id, args.display_name)
            current = target('body')/'stage.json'
        steps.append(dict(step='body', resource=resource))
        if want_face:
            sprites = catalog(costume_dir)
            sprite = sprites.get('front/stand') or sprites.get('wait_front/wait01')
            if sprite is None:
                raise SystemExit('Costume has no front standing sprite for a face icon; use --no-face')
            crop = args.face_crop or head_crop(sprite)
            bank = work/FACE_BANK
            current_content = Path(json.loads(current.read_text())['runtime_environment']['PS3_VFS_ROOT'])/GAME_DATA
            bank.write_bytes(member(current_content/facts['face_archives'][0].name, FACE_BANK)[0])
            occupied = [[c['face_cell']['x'], c['face_cell']['y']] for c in facts['inventory'] if c.get('face_cell')]
            face = build_face(bank, work/'face', Path(sprite['path']), crop, True, occupied)
            attach_face(current, work/'face/atlas.lzs', args.class_id, args.costume_id,
                        face['face_x'], face['face_y'], target('face'))
            current = target('face')/'stage.json'
            steps.append(dict(step='face', crop=crop, cell=[face['face_x'], face['face_y']],
                              atlas=[face['face_width'], face['face_height']]))
        if illustration_source:
            donor_resource = facts['base']+10000
            donor_art = archive_member(archive, 'anm%05d.lzs' % donor_resource)
            from PIL import Image
            from d2_anm import parse_anm
            shape = next((r['width'], r['height']) for r in
                         parse_anm(donor_art)['blocks'][0]['tables']['rectangle_candidates']['records']
                         if r['width'] and r['height'])
            with Image.open(illustration_source) as picture:
                crop = args.illustration_crop or portrait_crop(picture.convert('RGBA'), shape[0]/shape[1])
            expanded, _, report = convert_portrait(donor_art, read(illustration_source), crop, args.illustration_matte)
            (work/'illustration').mkdir()
            (work/'illustration/expanded.bin').write_bytes(expanded)
            page = anm_pages(expanded, include_rgba=False, palette_indices=[0])[0]
            (work/'illustration/preview.png').write_bytes(
                indexed_png(page['width'], page['height'], page['indices'], page['colors']))
            picture_resource = args.illustration_resource or free_resource(facts, 10900, 10999)
            attach_illustration(current, target('illustration'), work/'illustration/expanded.bin', args.class_id,
                                args.costume_id, picture_resource, donor_resource)
            current = target('illustration')/'stage.json'
            steps.append(dict(step='illustration', resource=picture_resource, donor=donor_resource, crop=crop,
                              source=str(illustration_source)))
        # Keep the reviewable evidence beside the profile, not the bulky intermediates.
        if stage is not None and (stage.parent/'costumes').is_dir():
            shutil.copytree(stage.parent/'costumes', output/'costumes')
        evidence = output/'costumes'/('%d-%s' % (args.class_id, args.costume_id))
        evidence.mkdir(parents=True)
        for name in ('review.png', 'build.json'):
            shutil.copy2(work/'body'/name, evidence/name)
        if want_face:
            shutil.copy2(work/'face/allocated-cell.png', evidence/'face.png')
        if illustration_source:
            shutil.copy2(work/'illustration/preview.png', evidence/'illustration.png')
        if args.select:
            select(output/'stage.json', True, args.class_id, args.costume_id)
        summary = dict(profile=str(output/'stage.json'), class_id=args.class_id, character=facts['name'],
                       costume_id=args.costume_id, display_name=args.display_name, rpg_character=args.rpg_character,
                       body=dict(resource=resource, counts=body['counts'], painted=body['painted'],
                                 cleared=body['cleared'], substitutions=len(body['substitutions']),
                                 clipped_over_1_percent=len(body['clipped_over_1_percent']),
                                 fitted_frames=body.get('fitted_frames',0),
                                 enlarged_cells=len((body['cell_growth'] or {}).get('enlarged', {})),
                                 exact_decoder_match=check['matches']),
                       steps=steps, face_note=face_note, selected=bool(args.select),
                       # Choices a costume recipe needs to rebuild this costume elsewhere.
                       options=dict(story_character=args.story_character if illustration_source else None,
                                    rpg_reference=args.rpg_reference, grow=args.grow,
                                    illustration_matte=list(args.illustration_matte) if args.illustration_matte else None),
                       review=str(evidence/'review.png'), seconds=round(time.time()-started, 1),
                       native_validated=False)
        (evidence/'added.json').write_text(json.dumps(summary, indent=2)+'\n')
        remember(rpg_source=source, current_profile=output/'stage.json')
        return summary
    except BaseException:
        if output.exists():
            shutil.rmtree(output)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def find(args):
    source = args.rpg_source or local_config().get('rpg_source')
    if not source:
        raise SystemExit('Pass --rpg-source (the extracted assets/android directory)')
    needle = args.name.casefold()
    rows = masters(source, 'storycharacter' if args.story else 'character')
    keys = ('id', 'name', 'img_base') if args.story else ('id', 'name')
    return [{k: r.get(k) for k in keys} for r in rows if needle in str(r.get('name', '')).casefold()][:200]


def listing(args):
    from d2_appearance_inventory import catalog
    stage = Path(args.profile or local_config().get('current_profile') or '')
    if not stage.is_file():
        raise SystemExit('Pass --profile STAGE.json')
    active, inventory = catalog(json.loads(stage.read_text()))
    chosen = {(a['class_id'], a['costume_id']) for a in active if a.get('enabled', True)}
    return dict(profile=str(stage), costumes=[dict(class_id=c['class_id'], costume_id=c['costume_id'],
        display_name=c.get('display_name'), body=c['new_resource'], face='face_cell' in c,
        illustration=c.get('illustration_resource'), active=(c['class_id'], c['costume_id']) in chosen)
        for c in inventory])


def choose(args):
    from d2_appearance_choice import select
    stage = Path(args.profile or local_config().get('current_profile') or '')
    if not stage.is_file():
        raise SystemExit('Pass --profile STAGE.json')
    if (args.class_id is None) == (args.character is None):
        raise SystemExit('Name the character once: --character Etna, or --class-id 30')
    if args.class_id is None:
        args.class_id = class_by_name(args.character)
    original = args.costume_id == 'original'
    return select(stage, not original, args.class_id, None if original else args.costume_id)


def play(args):
    """Ordinary play on the private profile with the importer-enabled runner."""
    from d2_appearance_play import play as launch
    config = local_config()
    stage = Path(args.profile or config.get('current_profile') or '')
    if not stage.is_file():
        raise SystemExit('Pass --profile STAGE.json')
    runner = Path(args.runner or config.get('runner') or REPO/'port/build-rpg-import/DisgaeaD2Recomp')
    elf = Path(args.elf or config.get('elf') or REPO/'work/v140/EBOOT.elf')
    if not runner.is_file() or not elf.is_file():
        raise SystemExit('Importer-enabled runner or 1.40 EBOOT.elf not found; pass --runner/--elf')
    runs = stage.resolve().parent/'play-sessions'
    runs.mkdir(exist_ok=True)
    output = runs/time.strftime('%Y%m%d-%H%M%S')
    remember(runner=runner.resolve(), elf=elf.resolve(), current_profile=stage.resolve())
    return launch(stage, runner, elf, output, args.duration, None, args.session_only)


def export(args):
    """Write a costume recipe (no artwork) for the costumes in a private profile."""
    import d2_costume_recipe as recipes
    config = local_config()
    stage = Path(args.profile or config.get('current_profile') or '')
    if not stage.is_file():
        raise SystemExit('Pass --profile STAGE.json')
    source = args.rpg_source or config.get('rpg_source')
    if args.with_art:
        # A pack carries the finished artwork: importable without RPG assets,
        # for private exchange only. costume-packs/ is never tracked by Git.
        import d2_costume_pack as packs
        try:
            name = args.name
            if args.output:
                output = Path(args.output)
            elif args.replace:
                output = REPO/'costume-packs'/(recipes.slug(name or packs.default_name(stage))+packs.SUFFIX)
            else:
                output = packs.unused_path(REPO/'costume-packs', name or packs.default_name(stage))
            report = packs.export_pack(stage, output, name, args.replace, source)
        except recipes.RecipeError as error:
            raise SystemExit(str(error))
        report['note'] = ('Contains game artwork: share privately, never commit or upload publicly. '
                          'Import with: tools/costume import '+Path(report['pack']).name)
        return report
    try:
        data = json.loads(stage.read_text())
        classes = {c['class_id'] for c in data.get('costumes', data.get('appearances', []))}
        recipe, skipped = recipes.export_recipe(stage, args.name, source,
                                                d2_bodies=recipes.d2_body_fingerprints(stage, classes))
        output = Path(args.output) if args.output else recipes.unused_path(REPO/'costume-recipes', recipe['name'])
        path = recipes.write(recipe, output, args.replace)
    except recipes.RecipeError as error:
        raise SystemExit(str(error))
    return dict(recipe=str(path), name=recipe['name'],
                costumes=['%s → %s' % (c['display_name'], c['character']) for c in recipe['costumes']],
                skipped=skipped, fingerprints=sum('sources' in c for c in recipe['costumes']),
                note='No artwork inside; safe to share. Rebuild with: tools/costume import '+path.name)


def import_(args):
    """Rebuild every costume in a recipe from this machine's own game and RPG files."""
    import d2_costume_recipe as recipes
    import d2_costume_pack as packs
    # By default a pack or recipe is added to the profile in use, so existing
    # costumes stay; with none yet (or --profile new) it starts from the game dump.
    profile = args.profile
    if profile in (None, 'current'):
        current = Path(local_config().get('current_profile') or '')
        profile = str(current) if current.is_file() else 'new'
    say = lambda text: print(text, file=sys.stderr, flush=True)
    try:
        if not Path(args.recipe).is_file():
            raise recipes.RecipeError('File not found: %s' % args.recipe)
        if packs.is_pack(args.recipe):
            return packs.import_pack(args.recipe, profile, args.output, progress=say)
        return recipes.import_recipe(args.recipe, profile, args.output, args.rpg_source, progress=say)
    except recipes.RecipeError as error:
        raise SystemExit(str(error))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('add', help='Build and register one costume in a new private profile')
    a.add_argument('--profile', type=Path, help='Existing private profile stage.json (default: the last one added '
                   'to), or "new" to start a profile from the untouched game dump')
    a.add_argument('--save-slot', choices=SAVE_SLOTS, default=SAVE_SLOTS[1],
                   help='With --profile new: which port/hdd0 save to copy into the private profile')
    a.add_argument('--output', type=Path, help='New profile directory (default: a dated folder in '
                   'work/appearance-profiles)')
    a.add_argument('--character', help='D2 character by name, e.g. Etna (see tools/data/d2_rpg_reference_map.json)')
    a.add_argument('--class-id', type=int, help='D2 class ID instead of a name, e.g. 30 for Etna')
    a.add_argument('--rpg-character', type=int, required=True, help='RPG battle character ID of the costume')
    a.add_argument('--rpg-reference', type=int, help='RPG ID of the same character in its standard outfit; '
                   'needed once per D2 character unless it is in the shipped map')
    a.add_argument('--costume-id', help='Short lowercase ID (default: made from --display-name)')
    a.add_argument('--display-name')
    a.add_argument('--rpg-source', type=Path, help='Extracted RPG assets/android directory (remembered locally)')
    a.add_argument('--story-character', type=int, help='RPG story-character master ID for a Status illustration')
    a.add_argument('--illustration-crop', type=int, nargs=4, metavar=('X0', 'Y0', 'X1', 'Y1'))
    a.add_argument('--illustration-matte', type=int, nargs=3, metavar=('R', 'G', 'B'),
                   help='Opaque background colour for the Status illustration (default: transparent)')
    a.add_argument('--illustration-resource', type=int)
    a.add_argument('--face-crop', type=int, nargs=4, metavar=('X0', 'Y0', 'X1', 'Y1'),
                   help='Override the automatic head crop in the front standing sprite')
    a.add_argument('--no-face', action='store_true', help='Keep the original face icon')
    a.add_argument('--resource', type=int, help='Body resource ID; default allocates the first free 900..999')
    a.add_argument('--grow', choices=('yes', 'symmetric', 'no'), default='yes',
                   help='Enlarge the character\'s own idle/unique cells when the costume is bigger (default yes)')
    a.add_argument('--select', action='store_true', help='Make this the character\'s appearance at next launch')
    f = sub.add_parser('find', help='Search RPG character names')
    f.add_argument('--name', required=True)
    f.add_argument('--story', action='store_true', help='Search story characters (for --story-character)')
    f.add_argument('--rpg-source', type=Path)
    l = sub.add_parser('list', help='Show costumes in a profile')
    l.add_argument('--profile', type=Path)
    c = sub.add_parser('choose', help='Pick the appearance a character uses at the next launch')
    c.add_argument('--profile', type=Path)
    c.add_argument('--character', help='D2 character by name, e.g. Etna')
    c.add_argument('--class-id', type=int)
    c.add_argument('--costume-id', required=True, help='A registered costume ID, or "original"')
    g = sub.add_parser('play', help='Play the private profile; Game > Appearance switches costumes in the castle')
    g.add_argument('--profile', type=Path)
    g.add_argument('--runner', type=Path)
    g.add_argument('--elf', type=Path)
    g.add_argument('--duration', type=int, help='Optional bounded smoke test in seconds')
    g.add_argument('--session-only', action='store_true', help='Do not remember menu choices')
    x = sub.add_parser('export', help='Write a shareable costume recipe (no artwork) for a profile')
    x.add_argument('--profile', type=Path)
    x.add_argument('--output', type=Path, help='Recipe file (default: costume-recipes/<name>.d2costume.json)')
    x.add_argument('--name', help='Name shown for the pack')
    x.add_argument('--rpg-source', type=Path)
    x.add_argument('--replace', action='store_true', help='Overwrite an existing recipe file')
    x.add_argument('--with-art', action='store_true',
                   help='Write a costume pack that includes the finished artwork (private sharing only; '
                        'default folder costume-packs/, which Git ignores)')
    i = sub.add_parser('import', help='Add the costumes of a pack (with art) or a recipe (rebuilt) to a new '
                       'private profile')
    i.add_argument('recipe', type=Path, metavar='FILE', help='A .d2costumepack or .d2costume.json file')
    i.add_argument('--profile', help='Profile to extend: "current" (default; "new" when there is none), "new" '
                   'to start from the untouched game, or a stage.json path')
    i.add_argument('--output', type=Path, help='New profile folder (default: a dated folder in '
                   'work/appearance-profiles)')
    i.add_argument('--rpg-source', type=Path)
    return parser


def main():
    args = build_parser().parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    result = {'add': add, 'find': find, 'list': listing, 'choose': choose, 'play': play, 'export': export,
              'import': import_}[args.command](args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
