"""Illustration conversion/staging/choice use shared palette and profile tooling."""
import io
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_illustration import convert,attach
from d2_appearance_choice import select
from d2_appearance_inventory import catalog
from d2_appearance_stage import member,rebind_anm
from d2_character_export import anm_pages,unlzs
from d2_asset_pack import compress_lzs
from d2_anm import parse_anm
from test_d2_anm import fixture
from test_d2_asset_pack import archive
import test_d2_appearance_inventory as inventory_fixture


def portrait_fixture():
    raw=bytearray(rebind_anm(fixture(),30,10030)[0]);meta=parse_anm(raw)
    r=meta['blocks'][0]['tables']['rectangle_candidates']['offset'];struct.pack_into('>2H',raw,r+12,2,2)
    return bytes(raw)

class IllustrationTests(unittest.TestCase):
    def setUp(self):
        inventory_fixture.InventoryTests.setUp(self)
        self.addCleanup(self.tmp.cleanup)
        for name in ('START.dat','START_1.dat'):
            table=bytearray(member(self.data/name,'char.dat')[0]);struct.pack_into('>H',table,4+0x196,30)
            (self.data/name).write_bytes(archive([('char.dat',table,123),('keep',b'unchanged',44)]))
        for name in ('ANM_HI.dat','ANM_HI_1.dat'):
            entries=[(n,member(self.data/name,n)[0],88) for n in ('anm00030.lzs','anm00900.lzs')]
            entries.append(('anm10030.lzs',compress_lzs(portrait_fixture()),88));(self.data/name).write_bytes(archive(entries))
        self.input=self.root/'portrait.anm';self.input.write_bytes(portrait_fixture());self.output=self.root/'illustrated'
        self.before={str(p.relative_to(self.source)):p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
    def stage_illustration(self,**kwargs):
        args=dict(stage=self.stage,output=self.output,anm=self.input,class_id=30,costume_id='resource-900',resource=10901);args.update(kwargs);return attach(**args)
    def test_conversion_preserves_metadata_and_mattes_transparent_pixels(self):
        im=Image.new('RGBA',(4,4),(255,0,0,0));im.putpixel((1,1),(0,255,0,255));b=io.BytesIO();im.save(b,format='PNG')
        raw=portrait_fixture();expanded,packed,report=convert(raw,b.getvalue(),(0,0,4,4))
        self.assertEqual(unlzs(packed),expanded);end=parse_anm(raw)['payload_start'];self.assertEqual(raw[:end],expanded[:end])
        self.assertEqual(report['destination'],[0,0,2,2]);self.assertEqual(report['matte'],[255,255,255])
        page=anm_pages(expanded,include_rgba=False)[0];self.assertTrue(all(page['colors'][i][3]==255 for i in page['indices']))
        for crop in ((-1,0,4,4),(0,0,5,4),(0,0,0,4),(True,0,4,4)):
            with self.assertRaises(ValueError):convert(raw,b.getvalue(),crop)
    def test_attach_preserves_donor_tables_saves_and_original_selection(self):
        data=self.stage_illustration();active,items=catalog(data)
        self.assertEqual(active[0]['illustration_resource'],10901);self.assertEqual(items[0]['illustration_donor'],10030)
        for name in ('ANM_HI.dat','ANM_HI_1.dat'):
            dst=self.output/'content/PS3_GAME/USRDIR/Data'/name
            self.assertEqual(unlzs(member(dst,'anm10901.lzs')[0]),rebind_anm(portrait_fixture(),10030,10901)[0])
            self.assertEqual(member(dst,'anm10030.lzs')[0],member(self.data/name,'anm10030.lzs')[0])
        for name in ('START.dat','START_1.dat'):
            self.assertEqual((self.output/'content/PS3_GAME/USRDIR/Data'/name).read_bytes(),(self.data/name).read_bytes())
        self.assertEqual((self.output/'hdd0/save').read_bytes(),b'private save untouched');self.assertEqual(list((self.output/'hdd1').iterdir()),[])
        for name,before in self.before.items():self.assertEqual((self.source/name).read_bytes(),before)
        select(self.output/'stage.json',False,30);self.assertFalse(json.loads((self.output/'stage.json').read_text())['appearances'][0]['enabled'])
        select(self.output/'stage.json',True,30,'resource-900');self.assertEqual(json.loads((self.output/'stage.json').read_text())['appearances'][0]['illustration_resource'],10901)
    def test_bad_metadata_ids_collision_and_failed_rebuild_leave_source(self):
        for args in [dict(resource=True),dict(resource=20000),dict(resource=10030),dict(class_id=410),dict(costume_id='missing'),dict(output=self.source/'nested')]:
            with self.assertRaises(ValueError):self.stage_illustration(**args)
        self.input.write_bytes(fixture())
        with self.assertRaises(ValueError):self.stage_illustration()
        self.input.write_bytes(portrait_fixture())
        with patch('d2_appearance_illustration.rebuild',side_effect=ValueError('fixture failure')):
            with self.assertRaisesRegex(ValueError,'fixture failure'):self.stage_illustration()
        self.assertFalse(self.output.exists())
        for name,before in self.before.items():self.assertEqual((self.source/name).read_bytes(),before)
    def test_costume_without_illustration_clears_choice_fields(self):
        data=self.stage_illustration();other=dict(data['costumes'][0],costume_id='without',new_resource=901,visual_class_id=901)
        other.pop('illustration_resource');other.pop('illustration_donor');data['costumes'].append(other)
        stage=self.output/'stage.json';stage.write_text(json.dumps(data));select(stage,True,30,'without')
        chosen=json.loads(stage.read_text());self.assertNotIn('illustration_resource',chosen['appearances'][0]);self.assertNotIn('illustration_resource',chosen)
        select(stage,True,30,'resource-900');chosen=json.loads(stage.read_text());self.assertEqual(chosen['appearances'][0]['illustration_resource'],10901)
if __name__=='__main__':unittest.main()
