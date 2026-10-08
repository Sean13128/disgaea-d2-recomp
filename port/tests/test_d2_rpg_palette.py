"""Coordinated palette tests with no proprietary assets."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest

try:
    from PIL import Image
except ImportError:
    raise SystemExit(77)

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_rpg_palette import author
from d2_rpg_map import page_image, pages_of
from d2_character_export import unlzs
import test_d2_rpg_map as fixtures


class SourcePaletteTests(unittest.TestCase):
    def setUp(self):
        fixtures.MappingTests.setUp(self)

    def test_source_color_survives_palette_authoring_and_metadata_is_unchanged(self):
        Image.new('RGBA',(2,2),(0,0,255,255)).save(self.png)
        mapping=copy.deepcopy(self.mapping)
        mapping['entries'][0]['source_sha256']=hashlib.sha256(self.png.read_bytes()).hexdigest()
        expanded,packed,report=author(self.raw,[(self.raw,mapping)])
        self.assertEqual(page_image(pages_of(expanded)[0]).tobytes(),bytes((0,0,255,255))*4)
        start=pages_of(expanded)[0]['data_offset']
        self.assertEqual(expanded[:start],self.raw[:start])
        self.assertEqual(unlzs(packed),expanded)
        self.assertEqual(report['page_errors'][0]['rgb_rmse'],0)
        self.assertFalse(report['gameplay_validated'])

    def test_source_conflict_hidden_by_donor_quantization_is_rejected(self):
        mappings=[]
        for index,color in enumerate([(0,0,250,255),(0,0,255,255)]):
            path=self.root/f'blue{index}.png';Image.new('RGBA',(2,2),color).save(path)
            mapping=copy.deepcopy(self.mapping)
            mapping['entries'][0].update(source=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            mappings.append((self.raw,mapping))
        with self.assertRaisesRegex(ValueError,'Source RGBA mappings conflict'):author(self.raw,mappings)

    def test_transparency_threshold_and_partial_alpha_survive_authored_palette(self):
        image=Image.new('RGBA',(2,2))
        image.putpixel((0,0),(0,0,255,128))
        image.putpixel((1,1),(0,255,0,63))
        image.save(self.png)
        mapping=copy.deepcopy(self.mapping)
        mapping['entries'][0]['source_sha256']=hashlib.sha256(self.png.read_bytes()).hexdigest()
        expanded,_,_=author(self.raw,[(self.raw,mapping)])
        rendered=page_image(pages_of(expanded)[0])
        self.assertEqual(rendered.getpixel((1,0)),(0,0,255,128))
        self.assertEqual(rendered.getpixel((0,1)),(0,0,0,0))


if __name__=='__main__':unittest.main()
