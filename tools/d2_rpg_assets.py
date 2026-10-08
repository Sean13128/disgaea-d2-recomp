#!/usr/bin/env python3
"""Extract one RPG character's source atlases and prefab metadata read-only.

Requires UnityPy (tested 1.25.4). Output must be new. Assets remain local/private.
Does not evaluate game scripts, render Unity animations, or install a D2 mod.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_default(value):
    if isinstance(value, (bytes, bytearray)):
        return {'bytes_hex': bytes(value).hex()}
    raise TypeError(type(value).__name__)


def safe_name(name):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', name)[:100] or 'unnamed'


def select_story_character(rows, story_character_id):
    """Story IDs and img_base belong to a separate namespace from battle IDs."""
    if type(story_character_id) is not int or story_character_id <= 0:
        raise ValueError('Expected a positive story-character ID')
    matches = [r for r in rows if r.get('id') == story_character_id]
    if len(matches) != 1:
        raise ValueError('Story-character ID must identify exactly one master row')
    row = matches[0]
    if type(row.get('img_base')) is not int or not 0 < row['img_base'] < 1000000:
        raise ValueError('Invalid story image-base ID')
    return row


def extract(root, character_id, output, story_character_id=None):
    import UnityPy
    for path in (root, output):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Symlink path refused')
    if output.exists() or output == root or root in output.parents or output in root.parents:
        raise ValueError('Use a new output directory outside the source tree')
    master_path = root/'masters/character'
    master_bytes = master_path.read_bytes()
    master = UnityPy.load(master_bytes)
    rows = next(o.parse_as_dict()['DataList'] for o in master.objects if o.type.name == 'MonoBehaviour')
    character = next(r for r in rows if r['id'] == character_id)
    selected = [('prefab', root/f'prefabs/characters/{character_id}')]
    for facing in ('front', 'back'):
        selected.extend((
            (facing, root/f'atlas/chara/battle/{facing}/{facing}{character_id}'),
            ('wait_'+facing, root/f'atlas/chara/battle/wait_{facing}/{facing}{character_id}')))
    story_info = None
    if story_character_id is not None:
        story_master_path = root/'masters/storycharacter'
        story_master_bytes = story_master_path.read_bytes()
        story_master = UnityPy.load(story_master_bytes)
        story_rows = next(o.parse_as_dict()['DataList'] for o in story_master.objects if o.type.name == 'MonoBehaviour')
        story_row = select_story_character(story_rows, story_character_id)
        selected.append(('story', root/f"atlas/chara/story/{story_row['img_base']}"))
        story_info = dict(master_path=str(story_master_path), master_sha256=digest(story_master_bytes),
                          row=story_row, association='Explicit story-character selection; not inferred from battle-character ID')
    if not all(p.is_file() for _, p in selected):
        raise ValueError('Missing selected character prefab or battle atlas')
    output.mkdir(parents=True)
    (output/'character.json').write_text(json.dumps(character, indent=2, ensure_ascii=False)+'\n')
    summary = dict(character_id=character_id, name=character['name'], unitypy_version=UnityPy.__version__, story_selection=story_info,
                   master=dict(path=str(master_path), sha256=digest(master_bytes)), bundles=[], clips=[],
                   limitations=['Exported clip metadata is not a reconstructed animation or D2 animation mapping.',
                                'Prefab dependencies may include shared placeholder sprites; named character atlases are exported separately.',
                                'Unity texture decoding is lossy relative to pre-compression artwork; source bundle bytes remain unchanged.',
                                'Story artwork requires an explicit story-character master ID; battle IDs do not identify story bundles.'])
    for label, path in selected:
        if path.is_symlink():
            raise ValueError('Symlink bundle refused')
        raw = path.read_bytes()
        if len(raw) > 64*1024*1024:
            raise ValueError('Bundle exceeds this focused extractor bound')
        env = UnityPy.load(raw)
        folder = output/label
        folder.mkdir()
        objects = list(env.objects)
        info = dict(label=label, path=str(path), bytes=len(raw), sha256=digest(raw),
                    types=dict(Counter(o.type.name for o in objects)), textures=[], sprites=[],
                    dependencies=[], decode_errors=[])
        for obj in objects:
            # Keep exact object bytes and full typed metadata for conversion work.
            key = f'{obj.type.name}_{obj.path_id}'
            (folder/(key+'.bin')).write_bytes(obj.get_raw_data())
            data = obj.parse_as_dict()
            (folder/(key+'.json')).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=json_default)+'\n')
            if obj.type.name == 'AssetBundle':
                info['dependencies'] = [dict(name=x, present=(root/x).is_file()) for x in data.get('m_Dependencies', [])]
            elif obj.type.name in ('Texture2D', 'Sprite'):
                entry = dict(name=data['m_Name'], path_id=obj.path_id, metadata=label+'/'+key+'.json')
                if obj.type.name == 'Sprite':
                    entry.update(rect=data['m_Rect'], pivot=data['m_Pivot'], pixels_to_units=data['m_PixelsToUnits'])
                else:
                    entry.update(width=data['m_Width'], height=data['m_Height'], format=data['m_TextureFormat'])
                try:
                    image = obj.parse_as_object().image.convert('RGBA')
                    png = key+'_'+safe_name(data['m_Name'])+'.png'
                    image.save(folder/png)
                    entry.update(png=label+'/'+png, decoded_size=image.size,
                                 alpha_extrema=image.getchannel('A').getextrema())
                except Exception as exc:
                    # Any unresolved texture reference stays explicit, never a fake PNG.
                    entry['image_error'] = type(exc).__name__+': '+str(exc)
                    info['decode_errors'].append(entry['image_error'])
                info['textures' if obj.type.name == 'Texture2D' else 'sprites'].append(entry)
            elif obj.type.name == 'AnimationClip':
                muscle = data.get('m_MuscleClip', {})
                summary['clips'].append(dict(name=data['m_Name'], sample_rate=data['m_SampleRate'],
                    start=muscle.get('m_StartTime'), stop=muscle.get('m_StopTime'), loop=muscle.get('m_LoopTime'),
                    bindings=len(data.get('m_ClipBindingConstant', {}).get('genericBindings', [])),
                    metadata=label+'/'+key+'.json', raw=label+'/'+key+'.bin'))
        if path.read_bytes() != raw:
            raise ValueError('Source bundle changed during extraction')
        info['source_unchanged'] = True
        summary['bundles'].append(info)
    if master_path.read_bytes() != master_bytes:
        raise ValueError('Source character master changed')
    if story_info is not None and story_master_path.read_bytes() != story_master_bytes:
        raise ValueError('Source story-character master changed')
    summary['files'] = {str(p.relative_to(output)):dict(bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
                        for p in output.rglob('*') if p.is_file()}
    summary['status'] = 'extracted; source hashes and output PNG readability verified; no game deployment'
    from PIL import Image
    for p in output.rglob('*.png'):
        with Image.open(p) as image:
            image.verify()
    (output/'manifest.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(dict(name=summary['name'], character_id=character_id,
        bundles=len(summary['bundles']), animation_clips=len(summary['clips']),
        textures=sum(len(b['textures']) for b in summary['bundles']),
        sprites=sum(len(b['sprites']) for b in summary['bundles']),
        image_decode_errors=sum(len(b['decode_errors']) for b in summary['bundles']),
        output=str(output)),indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Extracted assets/android directory')
    parser.add_argument('--character', type=int, default=84)
    parser.add_argument('--story-character', type=int, help='Explicit masters/storycharacter ID; img_base selects the story bundle')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    extract(args.source.absolute(), args.character, args.output.absolute(), args.story_character)
