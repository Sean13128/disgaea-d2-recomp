"""Asset-free import checks: exact placement, palettes, untouched bytes, drift."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

try:
    from PIL import Image
except ImportError:
    print('SKIP: Pillow unavailable')
    raise SystemExit(77)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from d2_rpg_map import build, compose, suggest, pages_of
from d2_character_export import unlzs
from test_d2_anm import fixture


def donor_fixture():
    raw = bytearray(fixture())
    from d2_anm import parse_anm
    meta = parse_anm(raw)
    rect = meta['blocks'][0]['tables']['rectangle_candidates']['offset']
    struct.pack_into('>9H', raw, rect, 0, 0, 0, 0, 0, 0, 2, 2, 0)
    payload = meta['payload_start']
    raw[payload:payload+4] = bytes([1])*4
    raw[payload+4:payload+8] = bytes(4)  # index 0 transparent
    raw[payload+8:payload+12] = bytes([255,255,0,0])  # index 1 red
    return bytes(raw)


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='d2-map-tests-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = donor_fixture()
        self.png = self.root/'pose.png'
        image = Image.new('RGBA', (2,2), (0,0,0,0))
        image.putpixel((0,0), (255,0,0,255))
        image.save(self.png)
        self.mapping = dict(schema=1, mode='texture-diagnostic', palette=0,
            donor_sha256=hashlib.sha256(self.raw).hexdigest(),
            common_sha256=hashlib.sha256(self.raw).hexdigest(), rectangle_resource=30,
            entries=[dict(rectangle_index=0, page=0, destination=[0,0,2,2], pose='front/test',
                source=str(self.png), source_sha256=hashlib.sha256(self.png.read_bytes()).hexdigest(),
                source_crop=[0,0,2,2], placement=[0,0,2,2], flip_x=True, selected=True)])

    def test_mirror_alpha_and_exact_untouched_bytes(self):
        expanded, packed, report = build(self.raw, self.raw, self.mapping)
        page = pages_of(expanded)[0]
        self.assertEqual(bytes(page['indices']), bytes([0,1,0,0]))
        offset = page['data_offset']
        self.assertEqual(expanded[:offset], self.raw[:offset])
        self.assertEqual(expanded[offset+4:], self.raw[offset+4:])
        self.assertEqual(unlzs(packed), expanded)
        self.assertEqual(report['poses'][0]['rgb_rmse'], 0)
        self.assertFalse(report['gameplay_validated'])

    def test_source_drift_destination_drift_overlap_and_empty_rejected(self):
        cases=[]
        for key in ('donor_sha256','common_sha256'):
            m=copy.deepcopy(self.mapping);m[key]='0'*64;cases.append(m)
        for key,value in [('source_sha256','0'*64), ('destination',[0,0,1,2]),
                          ('placement',[1,0,2,2]), ('flip_x',1), ('selected',False)]:
            m=copy.deepcopy(self.mapping);m['entries'][0][key]=value;cases.append(m)
        m=copy.deepcopy(self.mapping);m['entries']*=2;cases.append(m)
        for m in cases:
            with self.subTest(mapping=m):
                with self.assertRaises(ValueError):build(self.raw,self.raw,m)
        self.png.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'source hash'):build(self.raw,self.raw,self.mapping)

    def test_suggestions_use_named_pose_but_require_explicit_selection(self):
        for name in ('reference','appearance'):
            directory=self.root/name;directory.mkdir()
            (directory/'pose.png').write_bytes(self.png.read_bytes())
            (directory/'manifest.json').write_text(json.dumps(dict(bundles=[dict(
                label='front',sprites=[dict(name='test',png='pose.png')])])) )
        result=suggest(self.raw,self.raw,self.root/'reference',self.root/'appearance',30,[0])
        self.assertEqual(len(result['entries']),1)
        self.assertEqual(result['entries'][0]['pose'],'front/test')
        self.assertFalse(result['entries'][0]['selected'])
        with self.assertRaisesRegex(ValueError,'Select explicit'):build(self.raw,self.raw,result)

    def test_transparent_part_requires_explicit_clear_and_preserves_metadata(self):
        Image.new('RGBA',(2,2)).save(self.png)
        m=copy.deepcopy(self.mapping);e=m['entries'][0]
        e['source_sha256']=hashlib.sha256(self.png.read_bytes()).hexdigest();e['operation']='clear'
        implicit=copy.deepcopy(m);implicit['entries'][0].pop('operation')
        with self.assertRaisesRegex(ValueError,'explicit clear'):build(self.raw,self.raw,implicit)
        expanded,packed,report=build(self.raw,self.raw,m)
        self.assertEqual(bytes(pages_of(expanded)[0]['indices']),bytes(4))
        offset=pages_of(expanded)[0]['data_offset']
        self.assertEqual(expanded[:offset],self.raw[:offset])
        self.assertEqual(expanded[offset+4:],self.raw[offset+4:])
        self.assertEqual(report['poses'][0]['operation'],'clear')
        Image.new('RGBA',(2,2),(255,0,0,255)).save(self.png)
        e['source_sha256']=hashlib.sha256(self.png.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'fully transparent'):build(self.raw,self.raw,m)

    def test_composition_accepts_identical_aliases_rejects_conflicting_pixels(self):
        expected, _, _ = build(self.raw, self.raw, self.mapping)
        expanded, packed, report = compose(self.raw, [(self.raw,self.mapping)]*2)
        self.assertEqual(expanded, expected)
        self.assertEqual(unlzs(packed), expanded)
        self.assertEqual(report['mapped_sprites'], 2)
        conflicting=copy.deepcopy(self.mapping)
        conflicting['entries'][0]['flip_x']=False
        with self.assertRaisesRegex(ValueError,'conflict'):
            compose(self.raw, [(self.raw,self.mapping),(self.raw,conflicting)])
        with self.assertRaisesRegex(ValueError,'requires mappings'):compose(self.raw, [])

    def test_quarter_turn_swaps_dimensions_and_preserves_metadata(self):
        image=Image.new('RGBA',(2,1));image.putpixel((0,0),(255,0,0,255));image.save(self.png)
        mapping=copy.deepcopy(self.mapping);e=mapping['entries'][0]
        e.update(source_sha256=hashlib.sha256(self.png.read_bytes()).hexdigest(),
                 source_crop=[0,0,2,1],placement=[0,0,1,2],flip_x=False,quarter_turns=1)
        expanded,_,report=build(self.raw,self.raw,mapping)
        self.assertEqual(bytes(pages_of(expanded)[0]['indices']),bytes([0,0,1,0]))
        self.assertEqual(expanded[:pages_of(expanded)[0]['data_offset']],self.raw[:pages_of(self.raw)[0]['data_offset']])
        self.assertEqual(report['poses'][0]['quarter_turns'],1)
        for invalid in (-1,4,True,1.0):
            e['quarter_turns']=invalid
            with self.assertRaises(ValueError):build(self.raw,self.raw,mapping)


if __name__=='__main__':
    unittest.main()
