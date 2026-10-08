"""Story and battle asset IDs must not be confused during source selection."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_rpg_assets import select_story_character


class StorySelectionTests(unittest.TestCase):
    def test_separate_namespace_and_explicit_image_base(self):
        rows=[dict(id=8401,name='Other character',img_base=84),
              dict(id=13201,name="Etna (Elizabeth's Costume)",img_base=132)]
        self.assertEqual(select_story_character(rows,13201)['img_base'],132)
        with self.assertRaises(ValueError):select_story_character(rows,84)

    def test_reject_ambiguous_invalid_or_missing_mapping(self):
        row=dict(id=13201,img_base=132)
        for rows,selected in [([row,row],13201),([],13201),([row],True),([row],-1),
                              ([dict(row,img_base=True)],13201),
                              ([dict(row,img_base='../84')],13201),
                              ([dict(row,img_base=1000000)],13201)]:
            with self.subTest(rows=rows,selected=selected),self.assertRaises(ValueError):
                select_story_character(rows,selected)


if __name__=='__main__':unittest.main()
