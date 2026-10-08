import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:
    raise SystemExit(77)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_face import attach,validate_change
from d2_appearance_inventory import catalog
from d2_appearance_choice import select
from d2_appearance_stage import member
from d2_face_atlas import pack,allocate_cell,decode
from test_d2_asset_pack import archive
import test_d2_appearance_inventory as fixture


class FaceAttachmentTests(unittest.TestCase):
    def setUp(self):
        fixture.InventoryTests.setUp(self);self.addCleanup(self.tmp.cleanup)
        raw=bytes(4)+struct.pack('>HHHHI',384,192,1,0,384*192*4)+bytes([127,1,2,3])*(384*192)
        self.original=pack(raw)
        for name in ('START.dat','START_1.dat'):
            table=bytearray(member(self.data/name,'char.dat')[0]);struct.pack_into('>H',table,4+0x19E,30)
            (self.data/name).write_bytes(archive([('char.dat',table,123),('wf_unique1.lzs',self.original,88),('keep',b'unchanged',44)]))
        self.authored=allocate_cell(self.original,Image.new('RGBA',(96,96),(4,5,6,255)))[1]
        self.atlas=self.root/'atlas.lzs';self.atlas.write_bytes(self.authored);self.output=self.root/'face-profile'
        self.before={str(p.relative_to(self.source)):p.read_bytes() for p in self.source.rglob('*') if p.is_file()}

    def test_attachment_and_choice_preserve_source_and_clear_old_face(self):
        d=attach(self.stage,self.atlas,30,'resource-900',384,0,self.output)
        cell=dict(x=384,y=0,width=480,height=192,donor=30)
        self.assertEqual(d['appearances'][0]['face_cell'],cell)
        self.assertEqual(d['costumes'][0]['face_cell'],cell)
        for name in ('START.dat','START_1.dat'):
            self.assertEqual(member(self.output/'content/PS3_GAME/USRDIR/Data'/name,'wf_unique1.lzs')[0],self.authored)
            self.assertEqual(member(self.output/'content/PS3_GAME/USRDIR/Data'/name,'char.dat')[0],member(self.data/name,'char.dat')[0])
        for path,raw in self.before.items():self.assertEqual((self.source/path).read_bytes(),raw)
        p=self.output/'stage.json';d=json.loads(p.read_text());second=dict(d['costumes'][0],costume_id='other',new_resource=901,visual_class_id=901)
        second.pop('face_cell');d['costumes'].append(second);p.write_text(json.dumps(d))
        select(p,True,30,'other');d=json.loads(p.read_text());self.assertNotIn('face_cell',d['appearances'][0]);self.assertNotIn('face_cell',d)
        select(p,True,30,'resource-900');self.assertEqual(json.loads(p.read_text())['appearances'][0]['face_cell'],cell)

    def test_second_costume_cell_preserves_first_and_all_overlays(self):
        d=attach(self.stage,self.atlas,30,'resource-900',384,0,self.output)
        stage=self.output/'stage.json';second=dict(d['costumes'][0],costume_id='other',new_resource=901,visual_class_id=901)
        second.pop('face_cell');d['costumes'].append(second);stage.write_text(json.dumps(d))
        before={str(p.relative_to(self.output)):p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        packed=allocate_cell(self.authored,Image.new('RGBA',(96,96),(9,8,7,255)),[(384,0)])[1]
        atlas=self.root/'second-atlas.lzs';atlas.write_bytes(packed);output=self.root/'two-face-profile'
        new=attach(stage,atlas,30,'other',384,96,output)
        cells={c['costume_id']:c['face_cell'] for c in new['costumes']}
        self.assertEqual(cells['resource-900'],dict(x=384,y=0,width=480,height=192,donor=30))
        self.assertEqual(cells['other'],dict(x=384,y=96,width=480,height=192,donor=30))
        self.assertEqual(new['appearances'][0]['face_cell'],cells['resource-900'])
        for name in ('START.dat','START_1.dat'):
            self.assertEqual(member(output/'content/PS3_GAME/USRDIR/Data'/name,'wf_unique1.lzs')[0],packed)
        for path,raw in before.items():self.assertEqual((self.output/path).read_bytes(),raw)
        select(output/'stage.json',True,30,'other')
        self.assertEqual(json.loads((output/'stage.json').read_text())['appearances'][0]['face_cell'],cells['other'])
        select(output/'stage.json',True,30,'resource-900')
        self.assertEqual(json.loads((output/'stage.json').read_text())['appearances'][0]['face_cell'],cells['resource-900'])

    def test_reject_unrelated_changes_and_roll_back_own_output(self):
        raw,w,h=decode(self.authored);bad=bytearray(raw);bad[17]^=1
        with self.assertRaises(ValueError):validate_change(self.original,pack(bad),384,0)
        with patch('d2_appearance_face.rebuild',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):attach(self.stage,self.atlas,30,'resource-900',384,0,self.output)
        self.assertFalse(self.output.exists())
        for path,raw in self.before.items():self.assertEqual((self.source/path).read_bytes(),raw)
        for cell in [dict(x=True,y=0,width=480,height=192,donor=30),dict(x=0,y=0,width=480,height=192,donor=30),dict(x=384,y=192,width=480,height=192,donor=30)]:
            d=json.loads(self.stage.read_text());d['face_cell']=cell
            with self.assertRaises(ValueError):catalog(d)


if __name__=='__main__':unittest.main()
