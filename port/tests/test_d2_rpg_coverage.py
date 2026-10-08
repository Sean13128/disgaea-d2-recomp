"""Source pose coverage preserves file identity and cannot imply gameplay coverage."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_rpg_coverage import coverage


class CoverageTests(unittest.TestCase):
    def fixture(self):
        return dict(sources=[dict(path='/assets/atlas/chara/battle/front/front1',serialized_files=['frontCAB']),
                             dict(path='/assets/atlas/chara/battle/back/back1',serialized_files=['backCAB'])],
                    clips=[dict(name='walk',timelines=[dict(switches=[
                        dict(serialized_file='frontCAB',sprite_name='walk01',resolved=True),
                        dict(serialized_file='backCAB',sprite_name='walk01',resolved=True)])])])

    def test_same_sprite_name_in_different_files_remains_distinct(self):
        result=coverage(self.fixture(),{'front/walk01'})
        self.assertEqual(result['missing_poses'],['back/walk01'])
        self.assertEqual(result['mapped_poses'],['front/walk01'])
        self.assertFalse(result['gameplay_validated'])

    def test_unknown_reference_is_reported_separately(self):
        data=self.fixture();data['clips'][0]['timelines'][0]['switches'][0]['resolved']=False
        result=coverage(data,{'front/walk01','back/walk01'})
        self.assertEqual(result['unclassified_switches'],1)
        self.assertEqual(len(result['clips'][0]['unclassified_switches']),1)
        data['clips'].append(dict(name='dense',unsupported='Dense sprite curve'))
        self.assertEqual(coverage(data,set())['unsupported_clips'],['dense'])

    def test_conflicting_serialized_identity_is_rejected(self):
        data=self.fixture();data['sources'][1]['serialized_files']=['frontCAB']
        with self.assertRaisesRegex(ValueError,'Ambiguous'):coverage(data,set())


if __name__=='__main__':unittest.main()
