"""Marker probes preserve animation/alpha/indices, saves and source archives."""
import os
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_asset_probe import mark,probe,probe_face
from d2_appearance_choice import select
from d2_appearance_inventory import extend
from d2_appearance_run import profile_lock
from d2_appearance_stage import member
from d2_character_export import anm_pages,unlzs
from d2_anm import parse_anm
from d2_asset_pack import compress_lzs
from test_d2_anm import fixture
from test_d2_asset_pack import archive

class MarkerTests(unittest.TestCase):
    def test_face_probe_preserves_other_assets_and_private_save(self):
        from d2_face_atlas import pack,decode
        raw=bytes(4)+struct.pack('>HHHHI',384,192,1,0,384*192*4)+bytes([127,11,22,33])*(384*192)
        packed=pack(raw)
        source=archive([('wf_unique1.lzs',packed,88),('keep',b'unchanged',99)])
        for filename in ('START.dat','START_1.dat'):(self.assets/filename).write_bytes(source)
        result=probe_face(self.stage,self.output,'wf_unique1.lzs',1)
        self.assertEqual(result['asset_probe']['mode'],'face-row-rgb-marker')
        self.assertEqual(len(result['asset_probe']['archives']),2)
        for filename in ('START.dat','START_1.dat'):
            self.assertEqual((self.assets/filename).read_bytes(),source)
            self.assertEqual(member(self.output/'content/PS3_GAME/USRDIR/Data'/filename,'keep')[0],b'unchanged')
            marked=decode(member(self.output/'content/PS3_GAME/USRDIR/Data'/filename,'wf_unique1.lzs')[0])[0]
            self.assertEqual(marked[:16+384*96*4],raw[:16+384*96*4])
            self.assertEqual(marked[16::4],raw[16::4])
        self.assertEqual((self.output/'hdd0/save').read_bytes(),b'save unchanged')
        with self.assertRaises(ValueError):select(self.output/'stage.json',30,'original')
        with self.assertRaises(ValueError):probe_face(self.stage,self.root/'bad','../wf_unique1.lzs',1)

    def test_only_rgb_changes_and_alpha_indices_metadata_retained(self):
        raw=bytearray(fixture());start=parse_anm(raw)['payload_start']+4
        raw[start]=0;raw[start+4]=127
        expanded,packed,report=mark(bytes(raw),30)
        self.assertEqual(unlzs(packed),expanded)
        self.assertEqual(expanded[:start],raw[:start])
        old=anm_pages(raw,include_rgba=False)[0];new=anm_pages(expanded,include_rgba=False)[0]
        self.assertEqual(old['indices'],new['indices'])
        self.assertEqual([c[3] for c in old['colors']],[c[3] for c in new['colors']])
        self.assertTrue(all(c[:3]==bytes([255,0,255]) for c in new['colors']))
        self.assertEqual(report['changed_rgb_bytes'],256)
        self.assertFalse(report['visible_consumer_validated'])
        high=bytearray(fixture());struct.pack_into('>H',high,36,40030)
        self.assertEqual(mark(bytes(high),40030)[2]['resource'],40030)
        with self.assertRaises(ValueError):mark(bytes(high),100000)
        base=fixture();meta=parse_anm(base);end=meta['texture_table_start'];block=base[32:end]
        header=bytearray(base[:32]);struct.pack_into('>I',header,0,meta['payload_start']-16+len(block));struct.pack_into('>I',header,16,2)
        compound=bytes(header)+block+block+base[end:]
        with self.assertRaisesRegex(ValueError,'one matching ANM resource block'):mark(compound,30)
        for args in [(31,(255,0,255)),(True,(255,0,255)),(30,(256,0,0)),(30,(True,0,0)),(30,(0,0))]:
            with self.assertRaises(ValueError):mark(bytes(raw),*args)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='d2-marker-',dir=os.path.realpath(tempfile.gettempdir()));self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.profile=self.root/'profile';self.profile.mkdir()
        for name in ('content','hdd0','hdd1'):(self.profile/name).mkdir()
        self.assets=self.profile/'content/PS3_GAME/USRDIR/Data';self.assets.mkdir(parents=True)
        packed=compress_lzs(fixture())
        for filename in ('ANM_HI.dat','ANM_HI_1.dat'):(self.assets/filename).write_bytes(archive([('anm00030.lzs',packed,88),('keep',b'unchanged',99)]))
        (self.assets/'START.dat').write_bytes(b'character data untouched')
        (self.profile/'hdd0/save').write_bytes(b'save unchanged');(self.profile/'hdd1/cache').write_bytes(b'old cache')
        self.stage=self.profile/'stage.json';self.stage.write_text(json.dumps(dict(mode='isolated-runtime-experiment',baseline_control=True,
            enabled=False,class_id=30,new_resource=30,selector=1,selection_mode='renderer-only',unrelated={'keep':1},
            runtime_environment={k:str(self.profile/n) for k,n in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]})))
        self.before={str(p.relative_to(self.profile)):p.read_bytes() for p in self.profile.rglob('*') if p.is_file()}
        self.output=self.root/'probe'
    def test_copied_probe_patches_every_overlay_and_rejects_costumes(self):
        result=probe(self.stage,self.output,30)
        self.assertFalse(result['baseline_control']);self.assertFalse(result['enabled']);self.assertEqual(result['unrelated'],{'keep':1})
        self.assertEqual(len(result['asset_probe']['archives']),2)
        for filename in ('ANM_HI.dat','ANM_HI_1.dat'):
            target=self.output/'content/PS3_GAME/USRDIR/Data'/filename
            self.assertEqual(member(target,'keep')[0],b'unchanged')
            self.assertEqual(member(target,'anm00030.lzs')[0],mark(fixture(),30)[1])
            self.assertNotEqual(target.stat().st_ino,(self.assets/filename).stat().st_ino)
        self.assertEqual((self.output/'content/PS3_GAME/USRDIR/Data/START.dat').read_bytes(),b'character data untouched')
        self.assertEqual((self.output/'hdd0/save').read_bytes(),b'save unchanged');self.assertEqual(list((self.output/'hdd1').iterdir()),[])
        for relative,raw in self.before.items():self.assertEqual((self.profile/relative).read_bytes(),raw)
        with self.assertRaisesRegex(ValueError,'Asset probe'):select(self.output/'stage.json',True)
        with self.assertRaisesRegex(ValueError,'Asset probe'):
            extend(self.output/'stage.json',self.root/'costume',self.assets/'START.dat',30,901,'costume')
        with self.assertRaises(ValueError):probe(self.output/'stage.json',self.root/'nested-probe',30)
    def test_bad_paths_missing_resources_locks_and_failed_rebuild(self):
        with self.assertRaises(ValueError):probe(self.stage,self.profile/'nested',30)
        with self.assertRaises(ValueError):probe(self.stage,self.output,31)
        with profile_lock(self.stage):
            with self.assertRaisesRegex(ValueError,'already in use'):probe(self.stage,self.output,30)
        with patch('d2_appearance_asset_probe.rebuild',side_effect=ValueError('fixture failure')):
            with self.assertRaisesRegex(ValueError,'fixture failure'):probe(self.stage,self.output,30)
        self.assertFalse(self.output.exists())
        for relative,raw in self.before.items():self.assertEqual((self.profile/relative).read_bytes(),raw)
if __name__=='__main__':unittest.main()
