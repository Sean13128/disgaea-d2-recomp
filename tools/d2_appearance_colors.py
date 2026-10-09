#!/usr/bin/env python3
"""Copy a private costume profile for native Choose Color selection.

Normal Color retains retail art. Extra colors 1–4 select catalogued costumes.
The existing native per-unit color field carries selection; no save is patched.
"""
import argparse
import json
from pathlib import Path
import shutil

from d2_appearance_inventory import catalog
from d2_appearance_run import profile_lock
from d2_appearance_stage import clone_tree
from d2_character_export import _no_symlinks

ROOTS = [('PS3_VFS_ROOT', 'content'), ('PS3_HDD0_ROOT', 'hdd0'), ('PS3_HDD1_ROOT', 'hdd1')]


def slots_for(data):
    _, costumes = catalog(data)
    known = {(c['class_id'], c['costume_id']): c for c in costumes}
    slots = [dict(s) for s in data.get('color_slots', [])]
    occupied = set()
    assigned = set()
    for slot in slots:
        key = (slot.get('class_id'), slot.get('color'))
        identity = (slot.get('class_id'), slot.get('costume_id'))
        if type(key[0]) is not int or type(key[1]) is not int or not 1 <= key[1] <= 4 or identity not in known or key in occupied or identity in assigned:
            raise ValueError('Invalid or duplicate native color assignment')
        occupied.add(key)
        assigned.add(identity)
    for costume in costumes:
        cls, token = costume['class_id'], costume['costume_id']
        if (cls, token) in assigned:
            continue
        free = next((color for color in range(1, 5) if (cls, color) not in occupied), None)
        if free is None:
            raise ValueError(f'Character {cls} has more than four costumes. Native menu expansion is not implemented.')
        slots.append(dict(class_id=cls, color=free, costume_id=token))
        occupied.add((cls, free))
        assigned.add((cls, token))
    if not slots:
        raise ValueError('No costumes to assign')
    return slots, [dict(s, name=known[(s['class_id'], s['costume_id'])].get('display_name') or s['costume_id']) for s in slots]


def build(stage, output):
    stage = _no_symlinks(Path(stage).absolute())
    output = _no_symlinks(Path(output).absolute())
    with profile_lock(stage):
        if stage.stat().st_size > 1024 * 1024:
            raise ValueError('Manifest exceeds 1 MiB')
        data = json.loads(stage.read_text())
        if data.get('mode') != 'isolated-runtime-experiment' or data.get('baseline_control') or data.get('asset_probe'):
            raise ValueError('Expected a private costume profile')
        slots, labels = slots_for(data)
        if output.exists() or output in stage.parents or stage.parent in output.parents:
            raise ValueError('Output must be new and outside the source profile')
        roots = []
        for key, name in ROOTS:
            root = _no_symlinks(Path(data['runtime_environment'][key]).absolute())
            if root != stage.parent / name or not root.is_dir():
                raise ValueError('Expected independent private roots')
            roots.append(root)
        for source in data.get('source_roots', []):
            source = Path(source).absolute()
            if output == source or source in output.parents:
                raise ValueError('Output overlaps original assets')
        output.parent.mkdir(parents=True, exist_ok=True)
        size = sum(p.stat().st_size for root in roots[:2] for p in root.rglob('*') if p.is_file())
        if shutil.disk_usage(output.parent).free < size + 512 * 1024**2:
            raise ValueError('Insufficient space for independent private profile')
        output.mkdir()
        try:
            for source, (_, name) in zip(roots[:2], ROOTS[:2]):
                clone_tree(source, output / name)
            (output / 'hdd1').mkdir()
            # Keep review art and importer provenance available in the new profile.
            for name in ('assets', 'costumes', 'appearance-presets'):
                if (stage.parent / name).is_dir():
                    clone_tree(stage.parent / name, output / name)
            if (stage.parent / 'appearance-settings.json').is_file():
                shutil.copy2(stage.parent / 'appearance-settings.json', output / 'appearance-settings.json')
            data['runtime_environment'] = {key: str(output / name) for key, name in ROOTS}
            data['color_slots'] = slots
            data['color_slot_source'] = str(stage)
            (output / 'stage.json').write_text(json.dumps(data, indent=2) + '\n')
            report = dict(profile=str(output / 'stage.json'), slots=labels,
                          original='Normal Color; unassigned extra colors retain retail art',
                          persistence='Native per-unit color field; save/load playtest pending',
                          menu_labels='Retail Extra color 1–4 labels')
            (output / 'color-slots.json').write_text(json.dumps(report, indent=2) + '\n')
            return report
        except Exception:
            shutil.rmtree(output)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.stage, args.output), indent=2))
