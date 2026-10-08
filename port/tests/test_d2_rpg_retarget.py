"""Named-pose reuse recomputes bounds and requires a fresh review."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_rpg_map import sha,build
from d2_rpg_retarget import retarget,propose
from d2_asset_pack import compress_lzs
from test_d2_rpg_map import donor_fixture
from test_d2_asset_pack import archive


class RetargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='d2-retarget-',dir='/Volumes/Data/ai-tmp/codex');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.raw=donor_fixture()
        self.old=self.root/'old.png';Image.new('RGBA',(2,2),(255,0,0,255)).save(self.old)
        self.new=self.root/'new.png';image=Image.new('RGBA',(6,6));image.paste((0,255,0,255),(1,2,3,5));image.save(self.new)
        self.mapping=dict(schema=1,mode='texture-diagnostic',donor_sha256=sha(self.raw),common_sha256=sha(self.raw),
            member='anm00030.lzs',common_member='anm00030.lzs',rectangle_resource=30,palette=0,
            entries=[dict(rectangle_index=0,page=0,destination=[0,0,2,2],pose='front/test',
                source=str(self.old),source_sha256=sha(self.old.read_bytes()),source_crop=[0,0,2,2],
                placement=[0,0,2,2],flip_x=True,quarter_turns=1,selected=True)])
        self.sprites={'front/test':dict(path=str(self.new),sha256=sha(self.new.read_bytes()),image=image)}

    def test_new_bounds_orientations_and_unselected_proposals(self):
        result=retarget(self.raw,self.raw,self.mapping,self.sprites);e=result['entries'][0]
        self.assertEqual(e['source_crop'],[1,2,3,5]);self.assertEqual(e['placement'],[0,1,2,1])
        self.assertTrue(e['flip_x']);self.assertEqual(e['quarter_turns'],1)
        self.assertFalse(e['selected']);self.assertTrue(e['review_required'])
        self.assertEqual(self.mapping['entries'][0]['source'],str(self.old))
        with self.assertRaisesRegex(ValueError,'Select explicit'):build(self.raw,self.raw,result)

    def test_missing_pose_is_reported_without_guessing(self):
        result=retarget(self.raw,self.raw,self.mapping,{})
        self.assertEqual(result['entries'],[]);self.assertEqual(result['skipped'][0]['pose'],'front/test')
        self.assertEqual(result['retarget']['missing'],1)

    def test_transparent_parts_and_old_source_drift(self):
        image=Image.new('RGBA',(6,6));image.save(self.new)
        self.sprites['front/test'].update(image=image,sha256=sha(self.new.read_bytes()))
        result=retarget(self.raw,self.raw,self.mapping,self.sprites)
        self.assertEqual(result['entries'][0]['operation'],'clear')
        self.assertFalse(result['entries'][0]['selected'])
        self.old.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'source hash'):retarget(self.raw,self.raw,self.mapping,self.sprites)

    def test_composition_proposals_and_review_artifact_preserve_input(self):
        source=self.root/'source.dat';source.write_bytes(archive([('anm00030.lzs',compress_lzs(self.raw),0)]))
        mapping=self.root/'mapping.json';mapping.write_text(json.dumps(self.mapping))
        composition=self.root/'composition.json';composition.write_text(json.dumps(dict(schema=1,mode='texture-composition',mappings=['mapping.json'])))
        appearance=self.root/'appearance';appearance.mkdir();(appearance/'new.png').write_bytes(self.new.read_bytes())
        (appearance/'manifest.json').write_text(json.dumps(dict(bundles=[dict(label='front',sprites=[dict(name='test',png='new.png')])])) )
        before=source.read_bytes();result=propose(source,composition,appearance,self.root/'output')
        self.assertEqual(result['proposed'],1);self.assertEqual(source.read_bytes(),before)
        self.assertTrue((self.root/'output/review-00.png').is_file())
        self.assertFalse(json.loads((self.root/'output/mapping-0.json').read_text())['entries'][0]['selected'])
        with self.assertRaises(ValueError):propose(source,composition,appearance,self.root/'output')


if __name__=='__main__':unittest.main()
