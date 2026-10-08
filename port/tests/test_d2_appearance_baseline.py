"""Original archive controls preserve inputs and cannot become costume profiles."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_baseline import baseline
from d2_appearance_choice import select
from d2_appearance_inventory import extend
from d2_appearance_run import profile_lock
from test_d2_asset_pack import archive

class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='d2-baseline-',dir='/Volumes/Data/ai-tmp/codex')
        self.root=Path(self.tmp.name);self.repo=self.root/'repo'
        self.game=self.repo/'Disgaea D2 A Brighter Darkness - [BLUS31313]'
        self.assets=self.game/'PS3_GAME/USRDIR/Data';self.assets.mkdir(parents=True)
        table=bytearray(struct.pack('>HH',1,0)+bytes(676))
        struct.pack_into('>H',table,4+0x194,30);struct.pack_into('>2H',table,4+0x1bc,30,31)
        (self.assets/'START.dat').write_bytes(archive([('char.dat',table,0),('other',b'original',4)]))
        (self.assets/'ANM_HI.dat').write_bytes(archive([('anm00030.lzs',b'original sprite',0)]))
        self.profile=self.root/'profile';self.hdd0=self.profile/'hdd0'
        self.save=self.hdd0/'home/00000001/savedata/TEST/SAVEDATA.DAT';self.save.parent.mkdir(parents=True)
        raw=bytearray(1498152);struct.pack_into('>H',raw,0x1507ec,1);struct.pack_into('>H',raw,0x598+0x1158,30)
        struct.pack_into('>2H',raw,0x598+0x11d8,30,31);self.save.write_bytes(raw)
        self.stage=self.profile/'stage.json';self.stage.write_text(json.dumps(dict(mode='isolated-runtime-experiment',
            runtime_environment={'PS3_HDD0_ROOT':str(self.hdd0)},save_patch={'slot':'TEST'})))
        self.output=self.root/'control'
    def tearDown(self):self.tmp.cleanup()
    def build(self,**kwargs):
        args=dict(repo=self.repo,stage=self.stage,output=self.output);args.update(kwargs);return baseline(**args)
    def test_original_archives_and_save_exact_and_imports_rejected(self):
        before=self.save.read_bytes();result=self.build()
        self.assertTrue(result['baseline_control']);self.assertFalse(result['enabled'])
        self.assertEqual(result['original_tables'][0]['rows'],1)
        for source in self.assets.iterdir():
            copied=self.output/'content'/source.relative_to(self.game)
            self.assertEqual(copied.read_bytes(),source.read_bytes())
            self.assertEqual(result['original_archive_sha256'][str(source.relative_to(self.game))],hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertNotEqual(copied.stat().st_ino,source.stat().st_ino)
        self.assertEqual((self.output/'hdd0'/self.save.relative_to(self.hdd0)).read_bytes(),before)
        self.assertEqual(self.save.read_bytes(),before);self.assertEqual(list((self.output/'hdd1').iterdir()),[])
        stage=self.output/'stage.json'
        with self.assertRaisesRegex(ValueError,'Original control'):select(stage,True)
        select(stage,False)
        with self.assertRaisesRegex(ValueError,'Original control'):
            extend(stage=stage,output=self.root/'extended',anm=self.assets/'START.dat',class_id=30,resource=901,costume_id='new')
        self.assertFalse((self.root/'extended').exists())
    def test_overlap_bad_slot_missing_donor_and_live_profile(self):
        with self.assertRaises(ValueError):self.build(output=self.profile/'nested')
        with self.assertRaises(ValueError):self.build(class_id=410)
        with profile_lock(self.stage):
            with self.assertRaisesRegex(ValueError,'already in use'):self.build()
        data=json.loads(self.stage.read_text());data['save_patch']['slot']='..';self.stage.write_text(json.dumps(data))
        with self.assertRaises(ValueError):self.build()
        self.assertFalse(self.output.exists())
    def test_failed_archive_readback_rolls_back_new_output(self):
        import d2_appearance_baseline as module
        original=module.clone_tree
        def corrupt(source,target):
            original(source,target)
            if source==self.game:(target/'PS3_GAME/USRDIR/Data/ANM_HI.dat').write_bytes(b'corrupt')
        with patch.object(module,'clone_tree',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'archive/source readback'):self.build()
        self.assertFalse(self.output.exists());self.assertTrue(self.save.is_file())
if __name__=='__main__':unittest.main()
