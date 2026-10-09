"""Asset-free checks for costume recipes: export, validation, import chaining.

A recipe must never carry artwork or local paths, must reject malformed input,
and an import must leave only the finished profile behind.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
import d2_appearance_add as tool
import d2_costume_recipe as recipes


def binding(class_id, resource, costume_id, name, **extra):
    return dict(class_id=class_id, selector=1, new_resource=resource, visual_class_id=resource,
                selection_mode='renderer-only', costume_id=costume_id, display_name=name, **extra)


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='d2-recipe-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        # RPG source with the files that decide two costumes' looks.
        self.rpg = self.root/'android'
        for name in recipes.source_files(54, 79)+recipes.source_files(6):
            (self.rpg/name).parent.mkdir(parents=True, exist_ok=True)
            (self.rpg/name).write_bytes(('art of '+name).encode())
        # Private profile as the one-command importer leaves it.
        self.profile = self.root/'profile'
        first = binding(10, 902, 'dark-santa-laharl', 'Dark Santa Laharl', enabled=True)
        second = binding(30, 901, 'standard-rpg-etna', 'Standard RPG Etna')
        legacy = binding(30, 900, 'resource-900', 'Old manual costume')
        self.data = dict(mode='isolated-runtime-experiment', appearances=[first, dict(second, enabled=False)],
                         costumes=[legacy, first, second],
                         runtime_environment={k: str(self.profile/n) for k, n in
                                              [('PS3_VFS_ROOT', 'content'), ('PS3_HDD0_ROOT', 'hdd0'),
                                               ('PS3_HDD1_ROOT', 'hdd1')]})
        records = {
            '10-dark-santa-laharl': dict(class_id=10, character='Laharl', costume_id='dark-santa-laharl',
                display_name='Dark Santa Laharl', rpg_character=54, profile=str(self.profile/'stage.json'),
                steps=[dict(step='body', resource=902), dict(step='face', crop=[24, 13, 120, 109]),
                       dict(step='illustration', resource=10901, crop=[175, 272, 269, 680],
                            source=str(self.root/'work/rpg-cache/abc/char-54-story-7901/story/Sprite_1.png'))],
                review=str(self.profile/'costumes/10-dark-santa-laharl/review.png')),
            '30-standard-rpg-etna': dict(class_id=30, character='Etna', costume_id='standard-rpg-etna',
                display_name='Standard RPG Etna', rpg_character=6, steps=[dict(step='body', resource=901)],
                options=dict(story_character=None, rpg_reference=6, grow='symmetric', illustration_matte=None)),
        }
        for folder, record in records.items():
            (self.profile/'costumes'/folder).mkdir(parents=True)
            (self.profile/'costumes'/folder/'added.json').write_text(json.dumps(record))
        self.stage = self.profile/'stage.json'
        self.stage.write_text(json.dumps(self.data))

    def export(self, **changes):
        if changes:
            self.stage.write_text(json.dumps(dict(self.data, **changes)))
        return recipes.export_recipe(self.stage, rpg_source=self.rpg, story_bases={7901: 79})

    def test_export_lists_choices_without_art_or_paths(self):
        recipe, skipped = self.export()
        self.assertEqual(skipped, [dict(class_id=30, costume_id='resource-900',
                                        reason='No import record beside the profile')])
        self.assertEqual((recipe['format'], recipe['version'], recipe['name']),
                         ('d2-costume-recipe', 1, 'Costume pack (2 costumes)'))
        laharl, etna = recipe['costumes']
        self.assertEqual({k: laharl[k] for k in ('character', 'class_id', 'costume_id', 'display_name',
                                                 'rpg_character', 'story_character', 'grow', 'active')},
                         dict(character='Laharl', class_id=10, costume_id='dark-santa-laharl',
                              display_name='Dark Santa Laharl', rpg_character=54, story_character=7901, grow='yes',
                              active=True))
        self.assertEqual(laharl['face'], dict(crop=[24, 13, 120, 109]))
        self.assertEqual(laharl['illustration'], dict(crop=[175, 272, 269, 680], matte=None))
        # Every look-deciding source file is fingerprinted, by relative name only.
        self.assertEqual(sorted(laharl['sources']), sorted(recipes.source_files(54, 79)))
        self.assertEqual(laharl['sources']['atlas/chara/story/79'],
                         hashlib.sha256(b'art of atlas/chara/story/79').hexdigest())
        self.assertEqual((etna['face'], etna['grow'], etna['rpg_reference']), (False, 'symmetric', 6))
        self.assertNotIn('illustration', etna)
        self.assertNotIn('active', etna)
        text = json.dumps(recipe)
        for forbidden in (str(self.root), 'review.png', 'Sprite_1', '/Users/', '/Volumes/'):
            self.assertNotIn(forbidden, text)
        self.assertLess(len(text), 4096)

    def test_export_records_choose_color_slots_and_needs_a_record(self):
        recipe, _ = self.export(color_slots=[dict(class_id=10, color=3, costume_id='dark-santa-laharl'),
                                             dict(class_id=30, color=1, costume_id='standard-rpg-etna')])
        self.assertEqual([c.get('color') for c in recipe['costumes']], [3, 1])
        self.assertFalse(any('active' in c for c in recipe['costumes']))
        for folder in ('10-dark-santa-laharl', '30-standard-rpg-etna'):
            (self.profile/'costumes'/folder/'added.json').unlink()
        with self.assertRaisesRegex(recipes.RecipeError, 'import record'):
            self.export()
        self.stage.write_text(json.dumps(dict(self.data, mode='baseline')))
        with self.assertRaisesRegex(recipes.RecipeError, 'private costume profile'):
            recipes.export_recipe(self.stage)

    def test_missing_source_files_only_drop_fingerprints(self):
        (self.rpg/'atlas/chara/battle/front/front54').unlink()
        recipe, _ = self.export()
        self.assertNotIn('sources', recipe['costumes'][0])
        self.assertIn('sources', recipe['costumes'][1])
        self.assertIsNone(recipes.fingerprints(self.rpg, ['../outside']))
        self.assertIsNone(recipes.fingerprints(None, recipes.source_files(6)))

    def test_validation_rejects_malformed_and_hostile_recipes(self):
        good, _ = self.export()
        self.assertEqual(recipes.validate(good)['costumes'][0]['costume_id'], 'dark-santa-laharl')

        def broken(**changes):
            costume = dict(good['costumes'][0], **changes)
            return dict(good, costumes=[costume])
        cases = [dict(good, format='other'), dict(good, version=2), dict(good, version=True), dict(good, costumes=[]),
                 dict(good, costumes=[good['costumes'][0]]*2), dict(good, costumes=good['costumes']*65),
                 dict(good, name='bad\nname'), broken(class_id='10'), broken(class_id=0), broken(rpg_character=True),
                 broken(costume_id='../escape'), broken(display_name=''), broken(display_name='x'*101),
                 broken(face=dict(crop=[5, 5, 5, 9])), broken(face=dict(crop=[0, 0, 9000, 10])), broken(face='yes'),
                 broken(illustration=dict(crop=[0, 0, 1, 1], matte=[0, 0, 300])), broken(grow='huge'),
                 broken(color=5), broken(color=0), broken(sources={'../../etc/passwd': 'a'*64}),
                 broken(sources={'atlas/x': 'not-a-hash'}), broken(sources={'/abs': 'a'*64}),
                 broken(d2_body_sha256='zz'), broken(story_character=None, illustration=dict(crop=None)),
                 'text', None]
        for case in cases:
            with self.assertRaises(recipes.RecipeError, msg=repr(case)[:120]):
                recipes.validate(case)
        twice = dict(good, costumes=[dict(good['costumes'][0], color=1),
                                     dict(good['costumes'][0], costume_id='other', color=1)])
        with self.assertRaisesRegex(recipes.RecipeError, 'Extra color 1'):
            recipes.validate(twice)
        # Unknown keys never survive validation.
        self.assertNotIn('surprise', recipes.validate(dict(good, surprise=1)))
        self.assertNotIn('path', recipes.validate(broken(path='/Users/someone'))['costumes'][0])

    def test_write_never_overwrites_or_leaks_paths_and_load_is_bounded(self):
        recipe, _ = self.export()
        folder = self.root/'costume-recipes'
        path = recipes.write(recipe, recipes.unused_path(folder, recipe['name']))
        self.assertEqual(path.name, 'costume-pack-2-costumes.d2costume.json')
        self.assertEqual(recipes.load(path)['costumes'][1]['display_name'], 'Standard RPG Etna')
        with self.assertRaisesRegex(recipes.RecipeError, 'already exists'):
            recipes.write(recipe, path)
        self.assertEqual(recipes.unused_path(folder, recipe['name']).name, 'costume-pack-2-costumes-2.d2costume.json')
        recipes.write(dict(recipe, name='Renamed'), path, replace=True)
        self.assertEqual(recipes.load(path)['name'], 'Renamed')
        with self.assertRaisesRegex(recipes.RecipeError, 'local path'):
            recipes.write(dict(recipe, name='From /Users/someone/Downloads'), folder/'leak.d2costume.json')
        self.assertFalse((folder/'leak.d2costume.json').exists())
        with self.assertRaisesRegex(recipes.RecipeError, 'end in'):
            recipes.write(recipe, folder/'recipe.txt')
        (folder/'huge.d2costume.json').write_text(' '*(recipes.MAX_BYTES+1))
        (folder/'broken.d2costume.json').write_text('{not json')
        for name in ('huge.d2costume.json', 'broken.d2costume.json', 'absent.d2costume.json'):
            with self.assertRaises(recipes.RecipeError):
                recipes.load(folder/name)

    def importer(self, fail_at=None):
        """Stand-ins for the costume build and the Choose Color copy."""
        calls = []

        def run_add(arguments):
            calls.append(arguments)
            if fail_at == len(calls):
                raise SystemExit('Exact guest decoder rejected the built body')
            args = tool.build_parser().parse_args(arguments)
            previous = [] if str(args.profile) == 'new' else json.loads(Path(args.profile).read_text())['costumes']
            entry = binding(args.class_id, 900+len(previous), args.costume_id, args.display_name)
            args.output.mkdir()
            (args.output/'stage.json').write_text(json.dumps(dict(
                mode='isolated-runtime-experiment', appearances=[entry], costumes=previous+[entry])))
            tool.remember(current_profile=args.output/'stage.json')
            return dict(body=dict(exact_decoder_match=True))

        def build_colors(stage, output):
            data = json.loads(Path(stage).read_text())
            output.mkdir()
            (output/'stage.json').write_text(json.dumps(data))
            return dict(slots=[dict(s, name=s['costume_id']) for s in data['color_slots']])
        return calls, run_add, build_colors

    def test_import_chains_costumes_and_leaves_only_the_finished_profile(self):
        recipe, _ = self.export()
        path = recipes.write(recipe, self.root/'pack.d2costume.json')
        local = self.root/'appearance.json'
        local.write_text(json.dumps(dict(current_profile='/earlier/stage.json')))
        calls, run_add, build_colors = self.importer()
        output = self.root/'out'/'rebuilt'
        output.parent.mkdir()
        with patch.object(tool, 'LOCAL', local):
            report = recipes.import_recipe(path, 'new', output, self.rpg, run_add, build_colors)
            self.assertEqual(tool.local_config()['current_profile'], str(output/'stage.json'))
        self.assertEqual([p.name for p in output.parent.iterdir()], ['rebuilt'])
        self.assertEqual([c['costume_id'] for c in json.loads((output/'stage.json').read_text())['costumes']],
                         ['dark-santa-laharl', 'standard-rpg-etna'])
        first, second = calls
        # Matching files reuse the author's crops; each costume extends the previous step.
        self.assertEqual(first[:3], ['add', '--profile', 'new'])
        self.assertEqual(second[2], str(output.with_name('.rebuilt-step1')/'stage.json'))
        self.assertEqual(second[second.index('--output')+1], str(output))
        self.assertIn('--select', first)
        self.assertEqual(first[first.index('--face-crop')+1:first.index('--face-crop')+5], ['24', '13', '120', '109'])
        self.assertEqual(first[first.index('--story-character')+1], '7901')
        self.assertEqual(first[first.index('--illustration-crop')+1:first.index('--illustration-crop')+5],
                         ['175', '272', '269', '680'])
        self.assertIn('--no-face', second)
        self.assertEqual((second[second.index('--grow')+1], second[second.index('--rpg-reference')+1]),
                         ('symmetric', '6'))
        self.assertNotIn('--select', second)
        self.assertEqual([(c['source_check'], c['crops'], c['d2_check']) for c in report['costumes']],
                         [('match', 'recorded', 'unchecked')]*2)
        self.assertEqual((report['slots'], report['skipped'], report['different_sources']), (None, [], []))

    def test_different_source_files_fall_back_to_automatic_crops(self):
        recipe, _ = self.export()
        path = recipes.write(recipe, self.root/'pack.d2costume.json')
        (self.rpg/'atlas/chara/battle/front/front54').write_bytes(b'another release of the art')
        calls, run_add, build_colors = self.importer()
        with patch.object(tool, 'LOCAL', self.root/'appearance.json'):
            report = recipes.import_recipe(path, 'new', self.root/'rebuilt', self.rpg, run_add, build_colors)
        self.assertNotIn('--face-crop', calls[0])
        self.assertNotIn('--illustration-crop', calls[0])
        self.assertIn('--story-character', calls[0])
        self.assertEqual(report['costumes'][0]['crops'], 'automatic')
        self.assertEqual(report['different_sources'], ['Dark Santa Laharl'])

    def test_import_assigns_choose_color_slots_and_skips_existing_costumes(self):
        recipe, _ = self.export(color_slots=[dict(class_id=10, color=3, costume_id='dark-santa-laharl'),
                                             dict(class_id=30, color=1, costume_id='standard-rpg-etna')])
        path = recipes.write(recipe, self.root/'pack.d2costume.json')
        # Base profile already has Etna's costume, in Extra color 1.
        base = self.root/'base'
        base.mkdir()
        owned = binding(30, 900, 'standard-rpg-etna', 'Standard RPG Etna')
        (base/'stage.json').write_text(json.dumps(dict(mode='isolated-runtime-experiment', appearances=[owned],
            costumes=[owned], color_slots=[dict(class_id=30, color=1, costume_id='standard-rpg-etna')])))
        calls, run_add, build_colors = self.importer()

        def keep_slots(arguments):
            result = run_add(arguments)
            args = tool.build_parser().parse_args(arguments)
            stage = args.output/'stage.json'
            data = json.loads(stage.read_text())
            data['color_slots'] = json.loads(Path(args.profile).read_text()).get('color_slots', [])
            stage.write_text(json.dumps(data))
            return result
        output = self.root/'colors'
        with patch.object(tool, 'LOCAL', self.root/'appearance.json'):
            report = recipes.import_recipe(path, base/'stage.json', output, self.rpg, keep_slots, build_colors)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('--select', calls[0])
        self.assertEqual(report['skipped'], [dict(class_id=30, costume_id='standard-rpg-etna',
                                                  reason='Already in the profile')])
        self.assertEqual([(s['class_id'], s['color'], s['costume_id']) for s in report['slots']],
                         [(30, 1, 'standard-rpg-etna'), (10, 3, 'dark-santa-laharl')])
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith(('.', 'colors'))), ['colors'])
        with patch.object(tool, 'LOCAL', self.root/'appearance.json'), \
                self.assertRaisesRegex(recipes.RecipeError, 'already in that profile'):
            recipes.import_recipe(path, output/'stage.json', self.root/'again', self.rpg, keep_slots, build_colors)

    def test_failed_import_removes_its_folders_and_restores_the_current_profile(self):
        recipe, _ = self.export()
        path = recipes.write(recipe, self.root/'pack.d2costume.json')
        local = self.root/'appearance.json'
        local.write_text(json.dumps(dict(current_profile='/earlier/stage.json')))
        calls, run_add, build_colors = self.importer(fail_at=2)
        before = sorted(p.name for p in self.root.iterdir())
        with patch.object(tool, 'LOCAL', local):
            with self.assertRaises(SystemExit):
                recipes.import_recipe(path, 'new', self.root/'rebuilt', self.rpg, run_add, build_colors)
            self.assertEqual(tool.local_config()['current_profile'], '/earlier/stage.json')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)
        with patch.object(tool, 'LOCAL', local), self.assertRaisesRegex(recipes.RecipeError, 'new folder'):
            recipes.import_recipe(path, 'new', self.profile, self.rpg, run_add, build_colors)
        with patch.object(tool, 'LOCAL', local), self.assertRaisesRegex(recipes.RecipeError, 'existing private'):
            recipes.import_recipe(path, self.root/'absent.json', self.root/'x', self.rpg, run_add, build_colors)


if __name__ == '__main__':
    unittest.main()
