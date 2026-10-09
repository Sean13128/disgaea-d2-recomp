"""Asset-free checks for costume packs: untrusted-file handling and import chaining.

A pack carries artwork from someone else, so everything in it is checked: the
archive layout, sizes and fingerprints, and that a body is the reader's own
character with only pixels and cell geometry changed.
"""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from PIL import Image
    from test_d2_appearance_auto import synth
except ModuleNotFoundError:
    print('Costume pack tests require Pillow')
    sys.exit(77)
import d2_appearance_add as tool
import d2_costume_pack as packs
from d2_costume_recipe import RecipeError
from d2_character_export import unlzs

TABLES = dict(
    tags=[(0, 0), (6001, 1)],
    tracks=[(0, 0, 0, 0, 0xffff, 0, 0xffff, 0xffff), (0, 0, 0, 0, 0, 2, 0xffff, 0xffff)],
    keys=[(0, 0, 1, 1, 0, 0), (8, 0, 2, 2, 0, 0)],
    rects=[(0, 0, 0, 0, 0, 0, 0, 0, 240), (0, 0, 0, 0, 4, 4, 20, 24, 150), (0, 0, 0, 0, 40, 4, 8, 8, 0)],
    transforms=[(0, 0, 0, 0, 100, 100, 0, 0), (3, -20, 0, 1, 100, 100, 0, 0), (-12, -30, 0, 2, 100, 100, 0, 0)],
    anchors=[(0, 0), (10, 12), (4, 4)])


def anm(resource=30, art=((8, 10, 12, 16),), **changes):
    raw = synth(resource, dict(TABLES, **changes), art=list(art))
    return unlzs(raw) if raw.startswith(b'dat\0') else raw


def packs_table_start(raw):
    meta_end, _, textures, palettes = struct.unpack_from('>4I', raw)
    return meta_end+16-(textures+palettes)*16


def face_png(size=(96, 96), fmt='PNG'):
    buffer = io.BytesIO()
    Image.new('RGBA', size, (200, 30, 30, 255)).save(buffer, format=fmt)
    return buffer.getvalue()


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.donor = anm()

    def accept(self, **changes):
        packs.structure_check(self.donor, anm(**changes), 30)

    def reject(self, body, pattern='.'):
        with self.assertRaisesRegex(RecipeError, pattern):
            packs.structure_check(self.donor, body, 30)

    def test_only_art_and_cell_geometry_may_differ_from_the_readers_body(self):
        self.accept()
        self.accept(art=((5, 5, 30, 30),))                                          # repainted pixels
        self.accept(rects=[TABLES['rects'][0], (0, 0, 0, 0, 2, 2, 30, 40, 150), TABLES['rects'][2]])  # grown cell
        self.accept(anchors=[(0, 0), (14, 20), (4, 4)])                             # moved pivot
        self.accept(keys=[TABLES['keys'][0], (8, 0, 0, 2, 0, 0)])                   # hidden part
        self.reject(anm(resource=31), 'not built for this character')
        self.reject(anm(tags=[(0, 0), (6007, 1)]), 'animation data')
        self.reject(anm(transforms=[TABLES['transforms'][0], (3, -20, 0, 1, 200, 100, 0, 0),
                                    TABLES['transforms'][2]]), 'animation data')
        self.reject(anm(tracks=[TABLES['tracks'][0], (0, 0x0b00, 0, 0, 0, 2, 0xffff, 0xffff)]), 'animation data')
        self.reject(anm(keys=[TABLES['keys'][0], (8, 0, 1, 2, 0, 0)]), 'animation keys')       # re-pointed key
        self.reject(anm(keys=[TABLES['keys'][0], (9, 0, 0, 2, 0, 0)]), 'animation keys')       # retimed key
        self.reject(anm(rects=[TABLES['rects'][0], (0, 0, 0, 0, 50, 4, 20, 24, 150), TABLES['rects'][2]]),
                    'outside its texture page')
        self.reject(anm(rects=[TABLES['rects'][0], (0, 0, 0, 0, 4, 4, 20, 24, 151), TABLES['rects'][2]]),
                    'outside its texture page|sprite cell')
        self.reject(anm(rects=TABLES['rects']+[(0, 0, 0, 0, 0, 0, 4, 4, 0)]), 'animation tables|texture layout')  # extra row
        # A page made taller by the importer is the reader's layout plus empty rows.
        import d2_anm_cells
        tall = d2_anm_cells.resize_pages(self.donor, {0: 128})
        packs.structure_check(self.donor, tall, 30)
        low = d2_anm_cells.resize_pages(anm(rects=[TABLES['rects'][0], (0, 0, 0, 0, 4, 70, 20, 50, 150), TABLES['rects'][2]]), {0: 128})
        packs.structure_check(self.donor, low, 30)                                  # cell placed in the new rows
        self.reject(d2_anm_cells.resize_pages(anm(tags=[(0, 0), (6007, 1)]), {0: 128}), 'animation data')
        self.reject(d2_anm_cells.resize_pages(anm(rects=[TABLES['rects'][0], (0, 0, 0, 0, 4, 100, 20, 50, 150), TABLES['rects'][2]]), {0: 128}),
                    'outside its texture page')
        shorter = bytearray(tall); struct.pack_into('>H', shorter, packs_table_start(tall)+6, 100)
        self.reject(bytes(shorter))
        # A taller page whose sheet table still claims the old height would draw garbage: refused.
        from d2_anm import parse_anm
        stale = bytearray(tall)
        struct.pack_into('>H', stale, parse_anm(tall)['blocks'][0]['tables']['sheet_refs']['offset']+6, 64)
        self.reject(bytes(stale), 'animation data')
        with self.assertRaises(RecipeError):
            packs.structure_check(tall, self.donor, 30)                              # a shorter page than the reader's
        for junk in (b'', b'not an animation', self.donor[:200], self.donor+b'\0'):
            self.reject(junk)
        # A second resource block cannot ride along.
        with self.assertRaises(RecipeError):
            packs.structure_check(self.donor, self.donor.replace(struct.pack('>I', 1), struct.pack('>I', 2), 1), 30)


class PackFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='d2-pack-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.body, self.art = anm(art=((5, 5, 30, 30),)), b'illustration bytes'
        self.face = face_png()

    def costume(self, class_id=30, costume_id='santa', **extra):
        files = dict(body=self.body, face=self.face, illustration=self.art)
        return dict(dict(class_id=class_id, character='Etna', costume_id=costume_id, display_name='Santa Etna',
                         d2_body_sha256='a'*64,
                         files={k: dict(sha256=hashlib.sha256(v).hexdigest(), bytes=len(v)) for k, v in files.items()}),
                    **extra), files

    def write(self, costumes, name='pack', members=None, manifest=None, extra=None):
        path = self.root/(name+packs.SUFFIX)
        data = manifest if manifest is not None else dict(format=packs.FORMAT, version=1, name='Test pack',
                                                          costumes=[c for c, _ in costumes])
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('pack.json', json.dumps(data))
            for item, files in costumes:
                for kind, content in files.items():
                    target = (members or {}).get(kind, packs.member_name(item, kind)) if isinstance(item.get('costume_id'), str) and isinstance(item.get('class_id'), int) else 'x'
                    archive.writestr(target, content)
            for target, content in (extra or {}).items():
                archive.writestr(target, content)
        return path

    def test_reads_only_exactly_what_the_manifest_fingerprints(self):
        good = self.costume(color=2, recipe=dict(rpg_character=54, story_character=7901, face=dict(crop=[1, 2, 30, 40]),
                                                 illustration=dict(crop=[0, 0, 5, 9]), path='/Users/someone'))
        manifest, files = packs.read_pack(self.write([good]))
        item = manifest['costumes'][0]
        self.assertEqual(sorted(files), ['costumes/30-santa/body.anm', 'costumes/30-santa/face.png',
                                         'costumes/30-santa/illustration.anm'])
        self.assertEqual((item['color'], item['recipe']['rpg_character'], item['recipe']['face']), (2, 54, dict(crop=[1, 2, 30, 40])))
        self.assertNotIn('path', item['recipe'])
        self.assertTrue(packs.is_pack(self.root/('pack'+packs.SUFFIX)))

        def refused(pattern, *args, **kwargs):
            with self.assertRaisesRegex(RecipeError, pattern):
                packs.read_pack(self.write(*args, **kwargs))
        refused('unexpected files', [good], extra={'costumes/30-santa/extra.sh': b'#!/bin/sh'})
        refused('unexpected files', [good], extra={'../outside.txt': b'x'})
        refused('missing', [good], members=dict(face='costumes/30-santa/other.png'))
        tampered = self.costume()
        tampered[1]['body'] = tampered[1]['body'][:-1]+b'\x01'
        refused('fingerprint', [tampered])
        short = self.costume()
        short[0]['files']['body']['bytes'] -= 1
        refused('size differs', [short])
        for bad in (dict(costume_id='../../etc'), dict(costume_id='UPPER'), dict(class_id=0), dict(class_id='30'),
                    dict(display_name='a\nb'), dict(d2_body_sha256='nope'), dict(color=9),
                    dict(files=dict(face=dict(sha256='a'*64, bytes=5))),
                    dict(files=dict(body=dict(sha256='a'*64, bytes=5), script=dict(sha256='a'*64, bytes=5))),
                    dict(files=dict(body=dict(sha256='a'*64, bytes=packs.MAX_ANM+1))),
                    dict(files=dict(body=dict(sha256='zz', bytes=5)))):
            refused('.', [self.costume(**bad)])
        refused('listed twice|duplicate', [self.costume(), self.costume()])
        refused('Extra color 1', [self.costume(color=1), self.costume(costume_id='other', color=1)])
        refused('not a costume pack', [good], manifest=dict(format='other', version=1, costumes=[good[0]]))
        refused('newer version', [good], manifest=dict(format=packs.FORMAT, version=2, costumes=[good[0]]))
        refused('1–', [], manifest=dict(format=packs.FORMAT, version=1, costumes=[]))
        plain = self.root/('plain'+packs.SUFFIX)
        plain.write_bytes(b'{"format": "d2-costume-pack"}')
        self.assertFalse(packs.is_pack(plain))
        with self.assertRaisesRegex(RecipeError, 'damaged'):
            packs.read_pack(plain)
        with zipfile.ZipFile(plain, 'w') as archive:
            archive.writestr('other.txt', 'x')
        with self.assertRaisesRegex(RecipeError, 'not a costume pack'):
            packs.read_pack(plain)
        with zipfile.ZipFile(plain, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('pack.json', ' '*(packs.MAX_MANIFEST+1))
        with self.assertRaisesRegex(RecipeError, 'not a costume pack'):
            packs.read_pack(plain)
        with self.assertRaisesRegex(RecipeError, 'missing or larger'):
            packs.read_pack(self.root/'absent.d2costumepack')

    def test_import_installs_in_order_assigns_slots_and_cleans_up(self):
        first, second = self.costume(10, 'santa', color=3), self.costume(30, 'yukata', active=True)
        path = self.write([first, second])
        calls = []

        def install_one(item, files, current, target, save_slot):
            calls.append((item['costume_id'], str(current), target.name, sorted(files)[:1]))
            previous = [] if str(current) == 'new' else json.loads(Path(current).read_text())['costumes']
            entry = dict(class_id=item['class_id'], selector=1, new_resource=900+len(previous),
                         visual_class_id=900+len(previous), selection_mode='renderer-only',
                         costume_id=item['costume_id'], display_name=item['display_name'])
            target.mkdir()
            (target/'stage.json').write_text(json.dumps(dict(mode='isolated-runtime-experiment', appearances=[entry],
                                                             costumes=previous+[entry])))
            return dict(body_resource=entry['new_resource'], exact_decoder_match=True)

        def build_colors(stage, output):
            data = json.loads(Path(stage).read_text())
            output.mkdir()
            (output/'stage.json').write_text(json.dumps(data))
            return dict(slots=[dict(s, name=s['costume_id']) for s in data['color_slots']])
        output = self.root/'installed'
        with patch.object(tool, 'LOCAL', self.root/'appearance.json'), patch('d2_appearance_choice.select') as select:
            report = packs.import_pack(path, 'new', output, build_colors, install_one=install_one)
            select.assert_not_called()      # Choose Color slots decide, not the interim picker
        self.assertEqual([c[:3] for c in calls], [('santa', 'new', '.installed-step1'),
                                                  ('yukata', str(output.with_name('.installed-step1')/'stage.json'),
                                                   '.installed-step2')])
        self.assertEqual(report['slots'], [dict(class_id=10, color=3, costume_id='santa', name='santa')])
        self.assertEqual((report['source'], [c['body_resource'] for c in report['costumes']]), ('costume pack', [900, 901]))
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if 'installed' in p.name), ['installed'])
        # Without slots the pack's active costumes are selected for the next launch.
        plain = self.write([self.costume(30, 'yukata', active=True)], name='plain')
        with patch.object(tool, 'LOCAL', self.root/'appearance.json'), patch('d2_appearance_choice.select') as select:
            report = packs.import_pack(plain, 'new', self.root/'second', build_colors, install_one=install_one)
            select.assert_called_once_with(self.root/'second/stage.json', True, 30, 'yukata')
        self.assertIsNone(report['slots'])
        # A failing costume leaves nothing behind.
        before = sorted(p.name for p in self.root.iterdir())

        def broken(item, files, current, target, save_slot):
            if item['costume_id'] == 'yukata':
                raise RecipeError('Pack body changes animation data')
            return install_one(item, files, current, target, save_slot)
        with patch.object(tool, 'LOCAL', self.root/'appearance.json'), self.assertRaisesRegex(RecipeError, 'animation data'):
            packs.import_pack(path, 'new', self.root/'third', build_colors, install_one=broken)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)

    def test_install_refuses_a_body_for_another_game_version_before_touching_disk(self):
        item, files = self.costume()
        manifest, members = packs.read_pack(self.write([(item, files)]))
        donor = anm()
        facts = dict(content=self.root, body=30, face=30, base=30, name='Etna', face_archives=[], inventory=[],
                     classes=set(), anm_names=set())
        before = sorted(p.name for p in self.root.iterdir())
        with patch.object(tool, 'profile_facts', return_value=facts), \
                patch('d2_rpg_map.archive_member', return_value=donor), \
                self.assertRaisesRegex(RecipeError, 'different version'):
            packs.install(manifest['costumes'][0], members, 'new', self.root/'target')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)
        # Right fingerprint but a body that alters animation data is still refused.
        evil = anm(tags=[(0, 0), (6007, 1)])
        item['d2_body_sha256'] = hashlib.sha256(donor).hexdigest()
        item['files']['body'] = dict(sha256=hashlib.sha256(evil).hexdigest(), bytes=len(evil))
        files['body'] = evil
        manifest, members = packs.read_pack(self.write([(item, files)], name='evil'))
        with patch.object(tool, 'profile_facts', return_value=facts), \
                patch('d2_rpg_map.archive_member', return_value=donor), \
                self.assertRaisesRegex(RecipeError, 'animation data'):
            packs.install(manifest['costumes'][0], members, 'new', self.root/'target')
        self.assertFalse((self.root/'target').exists())


if __name__ == '__main__':
    unittest.main()
