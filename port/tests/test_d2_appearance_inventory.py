"""Multi-costume authoring, overlay precedence, choice and rollback fixtures."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_inventory import extend, catalog
from d2_appearance_choice import select
from d2_appearance_run import profile_lock
from d2_appearance_stage import member, rebind_anm, append_visual_alias
from d2_asset_pack import compress_lzs
from d2_character_export import characters, unlzs
from test_d2_anm import fixture
from test_d2_asset_pack import archive


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='d2-inventory-',dir='/Volumes/Data/ai-tmp/codex')
        self.root=Path(self.tmp.name);self.source=self.root/'source';self.source.mkdir()
        for name in ('content','hdd0','hdd1'):(self.source/name).mkdir()
        self.data=self.source/'content/PS3_GAME/USRDIR/Data';self.data.mkdir(parents=True)
        table=bytearray(struct.pack('>HH',1,0)+bytes(676))
        struct.pack_into('>H',table,4+0x194,30)
        struct.pack_into('>2H',table,4+0x1bc,30,900)
        table,_=append_visual_alias(bytes(table),30,900)
        for name in ('START.dat','START_1.dat'):
            (self.data/name).write_bytes(archive([('char.dat',table,123),('keep',b'unchanged',44)]))
        donor=compress_lzs(fixture());old=compress_lzs(rebind_anm(fixture(),30,900)[0])
        for name in ('ANM_HI.dat','ANM_HI_1.dat'):
            (self.data/name).write_bytes(archive([('anm00030.lzs',donor,88),('anm00900.lzs',old,88)]))
        (self.source/'hdd0/save').write_bytes(b'private save untouched')
        (self.source/'hdd1/stale').write_bytes(b'cache must not survive')
        (self.source/'appearance-settings.json').write_text('{"private":true}')
        self.stage=self.source/'stage.json'
        self.stage.write_text(json.dumps(dict(mode='isolated-runtime-experiment',class_id=30,
            new_resource=900,visual_class_id=900,selector=1,selection_mode='renderer-only',
            unrelated={'keep':123},runtime_environment={key:str(self.source/name) for key,name in
            [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]})))
        self.anm=self.root/'input.anm';self.anm.write_bytes(fixture())
        self.before={str(p.relative_to(self.source)):p.read_bytes() for p in self.source.rglob('*') if p.is_file()}

    def tearDown(self):self.tmp.cleanup()

    def build(self,**kwargs):
        args=dict(stage=self.stage,output=self.root/'extended',anm=self.anm,class_id=30,
                  resource=901,costume_id='second-costume');args.update(kwargs)
        return extend(**args)

    def test_two_costumes_keep_original_records_and_private_save(self):
        result=self.build(display_name='Standard RPG Etna');output=self.root/'extended';data_dir=output/'content/PS3_GAME/USRDIR/Data'
        self.assertEqual([c['new_resource'] for c in result['costumes']],[900,901])
        self.assertEqual(result['appearances'][0]['new_resource'],900)
        self.assertEqual(result['costumes'][1]['display_name'],'Standard RPG Etna')
        for name in ('START.dat','START_1.dat'):
            before=member(self.data/name,'char.dat')[0];after=member(data_dir/name,'char.dat')[0]
            self.assertEqual(after[2:len(before)],before[2:])
            self.assertEqual([r['id'] for r in characters(after)],[30,900,901])
        for name in ('ANM_HI.dat','ANM_HI_1.dat'):
            payload,row=member(data_dir/name,'anm00901.lzs')
            self.assertEqual(unlzs(payload),rebind_anm(fixture(),30,901)[0])
            self.assertEqual(row['unknown_be32'],88)
            self.assertEqual(member(data_dir/name,'anm00900.lzs')[0],member(self.data/name,'anm00900.lzs')[0])
        self.assertEqual((output/'hdd0/save').read_bytes(),b'private save untouched')
        self.assertEqual((output/'appearance-settings.json').read_bytes(),(self.source/'appearance-settings.json').read_bytes())
        self.assertEqual(list((output/'hdd1').iterdir()),[])
        for name,before in self.before.items():self.assertEqual((self.source/name).read_bytes(),before)
        select(output/'stage.json',True,30,'second-costume')
        selected=json.loads((output/'stage.json').read_text())
        self.assertEqual(selected['appearances'][0]['new_resource'],901)
        self.assertEqual(selected['new_resource'],901)
        select(output/'stage.json',False,30)
        self.assertFalse(json.loads((output/'stage.json').read_text())['appearances'][0]['enabled'])
        select(output/'stage.json',True,30,'resource-900')
        self.assertEqual(json.loads((output/'stage.json').read_text())['appearances'][0]['new_resource'],900)
        self.assertEqual((output/'hdd0/save').read_bytes(),b'private save untouched')

    def test_rejects_collision_bad_name_wrong_donor_and_locked_source(self):
        for args in [dict(resource=900),dict(resource=30),dict(costume_id='../escape'),
                     dict(costume_id='resource-900'),dict(resource=True),dict(class_id=410),
                     dict(output=self.source/'nested'),dict(display_name='bad\nname'),
                     dict(display_name='x'*128),dict(display_name='')]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):self.build(**args)
                self.assertFalse((self.root/'extended').exists())
        self.anm.write_bytes(rebind_anm(fixture(),30,410)[0])
        with self.assertRaises(ValueError):self.build()
        self.anm.write_bytes(fixture())
        with profile_lock(self.stage):
            with self.assertRaisesRegex(ValueError,'already in use'):self.build()
        data=json.loads(self.stage.read_text());data['source_roots']=[str(self.root/'protected')]
        self.stage.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'original content/profile'):
            self.build(output=self.root/'protected/new-profile')
        self.assertFalse((self.root/'protected').exists())

    def test_failed_rebuild_removes_only_new_profile(self):
        with patch('d2_appearance_inventory.rebuild',side_effect=ValueError('fixture failure')):
            with self.assertRaisesRegex(ValueError,'fixture failure'):self.build()
        self.assertFalse((self.root/'extended').exists())
        for name,before in self.before.items():self.assertEqual((self.source/name).read_bytes(),before)

    def test_second_character_starts_disabled_without_touching_personality_slots(self):
        for name in ('START.dat','START_1.dat'):
            raw=member(self.data/name,'char.dat')[0]
            row=bytearray(raw[4:680]);struct.pack_into('>H',row,0x194,410)
            struct.pack_into('>2H',row,0x1bc,410,411)
            updated=bytearray(raw+row);struct.pack_into('>H',updated,0,3)
            (self.data/name).write_bytes(archive([('char.dat',bytes(updated),123)]))
        for name in ('ANM_HI.dat','ANM_HI_1.dat'):
            donor=compress_lzs(rebind_anm(fixture(),30,410)[0])
            (self.data/name).write_bytes(archive([('anm00410.lzs',donor,88)]))
        self.anm.write_bytes(rebind_anm(fixture(),30,410)[0])
        result=self.build(class_id=410,resource=902)
        self.assertEqual([e['class_id'] for e in result['appearances']],[30,410])
        self.assertFalse(result['appearances'][1]['enabled'])
        raw=member(self.root/'extended/content/PS3_GAME/USRDIR/Data/START.dat','char.dat')[0]
        self.assertEqual(next(r for r in characters(raw) if r['id']==410)['body_animation_ids'],[410,411])
        select(self.root/'extended/stage.json',True,410,'second-costume')
        after=json.loads((self.root/'extended/stage.json').read_text())
        self.assertTrue(after['appearances'][1]['enabled'])
        self.assertEqual(after['appearances'][0],result['appearances'][0])

    def test_unknown_choice_and_invalid_catalog_do_not_write(self):
        self.build();path=self.root/'extended/stage.json';before=path.read_bytes()
        for imported,identity in [(True,'missing'),(False,'second-costume')]:
            with self.assertRaises(ValueError):select(path,imported,30,identity)
            self.assertEqual(path.read_bytes(),before)
        data=json.loads(before);data['costumes'][1]['new_resource']=900
        with self.assertRaises(ValueError):catalog(data)
        data=json.loads(before);data['appearances'][0]['visual_class_id']=901
        with self.assertRaises(ValueError):catalog(data)


if __name__=='__main__':unittest.main()
